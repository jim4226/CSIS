"""Regression tests for the cycle-10 substrate red-team findings (S1-S5).

Each test asserts the *effect* of the remediation (cycle-6 E1 lesson: a bare
count/shape assertion that doesn't pin the remediation effect is how a silent
leak shipped). Every test in this file FAILS on the pre-cycle-10 substrate and
PASSES on the fixed substrate.

  S1 (CRITICAL) — fcntl.flock binds to the fd's inode, not the path. An
                  unlink+recreate between two holders' open() calls lets both
                  flock different inodes of the same path → mutual exclusion
                  silently broken. Fix: validate fstat(fd)==stat(path) after
                  flock and reopen/re-lock on mismatch (file_lock).
  S2 (HIGH)     — verify_chain() walks genesis→EOF, so a tail truncation/
                  rollback leaves a shorter still-consistent chain that
                  verifies True. Fix: head-anchor sidecar cross-check + reject
                  blank lines (EventLog).
  S3 (HIGH)     — a torn final line (crash mid-write, no fsync) bricks
                  construct/emit/verify via ValidationError. Fix: durable
                  fsync write + torn-last-line recovery (EventLog).
  S4 (MEDIUM)   — the re-sync adopts the last line's seq+1/hash with no
                  validation, so a forged appended line is extended forever.
                  Fix: recompute the adopted tail's hash and raise on mismatch
                  (EventLog).
  S5 (LOW)      — compute_hash claimed "sorted keys" but used insertion-order
                  model_dump_json(), making the chain hash key-order-dependent.
                  Fix: hash a canonical (sorted-key) body (SignedEvent).
"""
from __future__ import annotations

import builtins
import json
import os
import subprocess
import sys
import threading
import time
from pathlib import Path

import pytest

from csis.substrate.event_log import (
    Event,
    EventLog,
    GENESIS_PREV_HASH,
    SignedEvent,
)
from csis.substrate.file_lock import LockUnavailable, file_lock


# ---------------------------------------------------------------------------
# S1 — lock-file inode swap must not break mutual exclusion
# ---------------------------------------------------------------------------


@pytest.mark.skipif(sys.platform == "win32", reason="S1 reproduces the POSIX flock/inode-swap race")
def test_s1_inode_swap_held_fd_matches_path_inode(tmp_path: Path, monkeypatch) -> None:
    """S1 (cycle-10): after file_lock() acquires, the fd it holds MUST be the
    inode the path currently resolves to.

    We reproduce the exact race deterministically: the first open() inside
    file_lock returns inode I1, then a stale-lock cleanup unlinks+recreates the
    path (now inode I2) BEFORE flock runs. Pre-fix, file_lock flocks the
    orphaned I1, never notices the swap, and yields while "holding" an inode
    that protects nothing the path points at (fstat(fd) != stat(path)) — that
    is the broken-mutual-exclusion condition. Post-fix, the inode recheck fires
    and file_lock reopens onto I2, so the held inode matches the path.
    """
    lock_path = tmp_path / "x.lock"
    lock_path.parent.mkdir(parents=True, exist_ok=True)

    opened: list = []
    swapped = {"done": False}
    real_open = builtins.open

    def open_with_one_shot_swap(*args, **kwargs):
        f = real_open(*args, **kwargs)
        # Only instrument opens of the lock path itself.
        try:
            same = os.path.abspath(args[0]) == os.path.abspath(str(lock_path))
        except (IndexError, TypeError):
            same = False
        if same:
            opened.append(f)
            if not swapped["done"]:
                swapped["done"] = True
                # Stale-lock cleanup swaps the inode out from under this fd.
                os.unlink(lock_path)
                # Recreate a fresh inode at the same path (I2).
                real_open(lock_path, "a+b").close()
        return f

    monkeypatch.setattr("csis.substrate.file_lock.open", open_with_one_shot_swap, raising=False)

    with file_lock(lock_path):
        # The currently-held fd is the most recently opened, still-open one.
        held = opened[-1]
        held_ino = os.fstat(held.fileno()).st_ino
        path_ino = os.stat(lock_path).st_ino
        assert held_ino == path_ino, (
            "file_lock is holding an inode that the path no longer resolves to "
            "(inode swapped out from under the flock) — mutual exclusion broken"
        )


@pytest.mark.skipif(sys.platform == "win32", reason="S1 reproduces the POSIX flock/inode-swap race")
def test_s1_inode_swap_does_not_grant_concurrent_entry(tmp_path: Path, monkeypatch) -> None:
    """S1 (cycle-10): reproduce the full two-holder race and assert mutual
    exclusion survives an inode swap.

    Exact ordering from the finding (driven deterministically via the open()
    wrapper):
      1. Holder A open()s the lock path  -> inode I1 (path still resolves to I1)
      2. stale-lock cleanup unlinks I1 and recreates the path -> inode I2
      3. Holder B (a subprocess) open()s + flocks the path -> locks I2, stays in
      4. A flocks its now-orphaned I1 (succeeds — different inode than B)

    Pre-fix A then *yields* while B is still inside -> two holders in the
    critical section at once. Post-fix A's inode recheck (fstat(I1) !=
    stat(path)=I2) fires, A reopens onto I2 and blocks on B's flock, so A does
    NOT enter until B releases.
    """
    lock_path = tmp_path / "s1.lock"
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    # Step 0: establish inode I1 at the path so A's first open binds to it.
    lock_path.touch()

    b_holds = tmp_path / "b_holds"
    b_release = tmp_path / "b_release"
    real_open = builtins.open
    swapped = {"done": False}
    b_proc: dict = {"p": None}

    def open_then_swap_and_start_b(*args, **kwargs):
        # Capture A's real fd to the CURRENT inode (I1) first…
        f = real_open(*args, **kwargs)
        try:
            is_lock = os.path.abspath(args[0]) == os.path.abspath(str(lock_path))
        except (IndexError, TypeError):
            is_lock = False
        if is_lock and not swapped["done"]:
            swapped["done"] = True
            # …then perform the swap (unlink I1, recreate I2)…
            os.unlink(lock_path)
            real_open(lock_path, "a+b").close()  # I2
            # …then have subprocess B grab and hold the lock on I2.
            b_src = f"""
import os, time, sys
sys.path.insert(0, {repr(str(Path(__file__).resolve().parent.parent))})
from csis.substrate.file_lock import file_lock
with file_lock({repr(str(lock_path))}):
    open({repr(str(b_holds))}, "w").close()
    deadline = time.time() + 20
    while not os.path.exists({repr(str(b_release))}) and time.time() < deadline:
        time.sleep(0.02)
"""
            b_proc["p"] = subprocess.Popen([sys.executable, "-c", b_src])
            deadline = time.time() + 15
            while not b_holds.exists() and time.time() < deadline:
                time.sleep(0.01)
        return f

    monkeypatch.setattr("csis.substrate.file_lock.open", open_then_swap_and_start_b, raising=False)

    a_entered = threading.Event()

    def acquire_a() -> None:
        with file_lock(lock_path):
            a_entered.set()
            time.sleep(0.3)

    try:
        assert b_holds.exists() is False
        t = threading.Thread(target=acquire_a, daemon=True)
        t.start()
        # B is holding I2 (the open wrapper started B and waited for b_holds).
        # If mutual exclusion is intact, A must NOT enter while B holds.
        entered = a_entered.wait(timeout=2.0)
        assert b_holds.exists(), "subprocess B never grabbed the swapped-in inode"
        assert not entered, (
            "holder A entered the critical section while holder B was still "
            "inside (inode swap broke mutual exclusion — S1 not fixed)"
        )
    finally:
        b_release.touch()
        if b_proc["p"] is not None:
            b_proc["p"].wait(timeout=25)


# ---------------------------------------------------------------------------
# S2 — chain must be tamper-evident against tail truncation / rollback
# ---------------------------------------------------------------------------


def test_s2_tail_truncation_fails_verification(tmp_path: Path) -> None:
    """S2 (cycle-10): dropping the most recent N events (a rollback that strips,
    e.g., an auditor.signed) leaves a shorter internally-consistent chain.

    Pre-fix verify_chain() walks genesis→EOF and returns True for that prefix.
    Post-fix the head-anchor cross-check detects the missing tail and fails.
    """
    path = tmp_path / "events.jsonl"
    log = EventLog(path)
    for i in range(8):
        log.emit("coordinator", "tick", {"i": i})
    assert log.verify_chain()[0]

    # Truncate the file to drop the last 3 events (the prefix still chains).
    lines = path.read_text(encoding="utf-8").splitlines()
    kept = lines[:5]
    path.write_text("\n".join(kept) + "\n", encoding="utf-8")

    # Sanity: the kept prefix is internally consistent (so the *only* thing
    # that can flag it is the anchor cross-check).
    ok, reason = EventLog(path).verify_chain()
    assert not ok, "truncated tail verified True (S2 not fixed)"
    assert "trunc" in (reason or "").lower() or "rollback" in (reason or "").lower() or "anchor" in (reason or "").lower(), (
        f"expected a truncation/rollback reason, got: {reason!r}"
    )


def test_s2_blank_line_is_rejected_not_skipped(tmp_path: Path) -> None:
    """S2 (cycle-10): a blank/whitespace line mid-file is evidence of a torn or
    edited log and must FAIL verify_chain rather than be silently skipped."""
    path = tmp_path / "events.jsonl"
    log = EventLog(path)
    for i in range(4):
        log.emit("coordinator", "tick", {"i": i})

    lines = path.read_text(encoding="utf-8").splitlines()
    # Inject a blank line between two valid events.
    lines.insert(2, "")
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")

    ok, reason = EventLog(path).verify_chain()
    assert not ok, "blank line was silently skipped (S2 not fixed)"
    assert "blank" in (reason or "").lower() or "whitespace" in (reason or "").lower()


def test_s2_missing_anchor_is_unverifiable_not_failure(tmp_path: Path) -> None:
    """S2 (cycle-10): a pre-cycle-10 log has no anchor sidecar. That is
    'unverifiable-length', not a failure — an internally-consistent chain with
    no anchor must still verify True (documented backward-compat)."""
    path = tmp_path / "events.jsonl"
    log = EventLog(path)
    for i in range(3):
        log.emit("coordinator", "tick", {"i": i})
    # Simulate a legacy log: remove the anchor sidecar entirely.
    anchor = path.with_suffix(path.suffix + ".head")
    if anchor.exists():
        anchor.unlink()

    ok, reason = EventLog(path).verify_chain()
    assert ok, f"missing anchor should be unverifiable-length, not failure: {reason}"


# ---------------------------------------------------------------------------
# S3 — a torn last line must be recoverable (and writes must be durable)
# ---------------------------------------------------------------------------


def test_s3_torn_last_line_recovers_to_last_valid_event(tmp_path: Path) -> None:
    """S3 (cycle-10): append a torn fragment (crash mid-write) to a valid log.

    Pre-fix _restore_from_disk_unlocked feeds the fragment to
    model_validate_json, raising ValidationError — so EventLog(path) can't even
    construct, and emit/verify are bricked. Post-fix the torn LAST line is
    truncated under the lock and the log recovers to the last valid event.
    """
    path = tmp_path / "events.jsonl"
    log = EventLog(path)
    for i in range(5):
        log.emit("coordinator", "tick", {"i": i})
    good_seq = log.seq()  # 5
    good_hash = log.latest_hash()

    # Simulate a crash mid-append: a partial JSON line with NO trailing newline.
    with path.open("a", encoding="utf-8") as f:
        f.write('{"event": {"seq": 5, "timestamp": 1.0, "actor": "coord')  # torn

    # Construction must NOT raise (pre-fix it raised ValidationError).
    recovered = EventLog(path)
    assert recovered.seq() == good_seq, "did not recover to the last valid event"
    assert recovered.latest_hash() == good_hash

    # And it must remain usable: a new emit chains onto the last valid event.
    nxt = recovered.emit("coordinator", "after-recovery", {})
    assert nxt.event.seq == good_seq
    assert nxt.prev_hash == good_hash
    ok, reason = EventLog(path).verify_chain()
    assert ok, f"chain not intact after torn-line recovery: {reason}"


def test_s3_malformed_non_last_line_triggers_quarantine_recovery(tmp_path: Path) -> None:
    """S4 (cycle-10, integration): a malformed NON-final line is corruption, not
    a torn append. The first cut hard-raised here, but that bricks the log;
    instead the longest valid prefix is recovered and the full pre-recovery log
    is quarantined for forensics — the corruption is SURFACED (quarantine file +
    stderr), never silently swallowed, and the system stays usable.
    """
    path = tmp_path / "events.jsonl"
    log = EventLog(path)
    for i in range(3):
        log.emit("coordinator", "tick", {"i": i})

    lines = path.read_text(encoding="utf-8").splitlines()
    # Corrupt a NON-final line; keep a valid line after it and a trailing newline.
    lines[1] = '{"event": {"seq": 1, "timestamp": 1.0, "actor": "coord'  # malformed, mid-file
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")

    recovered = EventLog(path)  # must NOT raise
    assert recovered.seq() == 1, "should recover the valid prefix (event 0 only)"
    assert recovered.verify_chain()[0], "recovered chain must be intact"
    quarantines = list(tmp_path.glob("events.jsonl.broken-*.jsonl"))
    assert len(quarantines) == 1, "corrupt log must be quarantined, not silently dropped"


def test_s3_emit_write_is_durable_fsync(tmp_path: Path, monkeypatch) -> None:
    """S3 (cycle-10): emit() must fsync the appended line before advancing the
    in-memory head. We assert the *effect* — os.fsync is called on the log fd
    inside emit — which is what makes a torn final line a rare, recoverable
    event rather than the common case."""
    path = tmp_path / "events.jsonl"
    log = EventLog(path)

    fsync_calls = {"n": 0}
    real_fsync = os.fsync

    def counting_fsync(fd):
        fsync_calls["n"] += 1
        return real_fsync(fd)

    monkeypatch.setattr("csis.substrate.event_log.os.fsync", counting_fsync)
    log.emit("coordinator", "durable", {"x": 1})
    assert fsync_calls["n"] >= 1, "emit() did not fsync the appended line (S3 not fixed)"


# ---------------------------------------------------------------------------
# S4 — emit() must not extend a forged / non-chaining tail
# ---------------------------------------------------------------------------


def test_s4_forged_tail_is_isolated_not_extended(tmp_path: Path) -> None:
    """S4 (cycle-10): append a well-formed line whose event_hash does NOT chain.

    Pre-fix the re-sync adopts its seq+1/event_hash blindly, so the NEXT emit
    extends the forged fork (and verify keeps passing on the forged head).
    Post-fix the forged tail is QUARANTINED and the longest valid prefix
    recovered: the next emit chains onto the valid tail, never the forgery —
    S4's security property (don't extend a forged fork) holds, without bricking
    the log on a single appended garbage line.
    """
    path = tmp_path / "events.jsonl"
    log = EventLog(path)
    log.emit("coordinator", "boot", {})
    log.emit("coordinator", "tick", {"i": 1})
    valid_tail = list(EventLog(path).iter_events())[-1]

    # Forge a well-formed seq-2 line with a BOGUS event_hash (does not equal
    # compute_hash(event, prev_hash)). It parses fine — so it is NOT a torn
    # line — but it does not chain.
    forged_event = Event(seq=2, timestamp=time.time(), actor="coordinator", kind="forged", payload={"evil": True})
    forged = SignedEvent(
        event=forged_event,
        prev_hash=valid_tail.event_hash,
        event_hash="f" * 64,  # bogus — will not match the recomputed hash
    )
    with path.open("a", encoding="utf-8") as f:
        f.write(forged.model_dump_json() + "\n")

    # Constructing over the forged tail must NOT raise and must NOT adopt the
    # forged head: it recovers the 2 valid events and quarantines the rest.
    recovered = EventLog(path)
    assert recovered.seq() == 2, "forged tail must be dropped, valid prefix kept"
    nxt = recovered.emit("coordinator", "after", {})
    assert nxt.event.seq == 2, "next emit chains onto the valid prefix, not the forgery"
    assert nxt.prev_hash == valid_tail.event_hash, "must extend the valid tail, not the forged head"
    assert recovered.verify_chain()[0]
    assert len(list(tmp_path.glob("events.jsonl.broken-*.jsonl"))) == 1


def test_s4_well_formed_chaining_tail_is_accepted(tmp_path: Path) -> None:
    """S4 (cycle-10): the forgery guard must not reject a genuine chaining tail
    (no false positives) — a normally-emitted log re-opens and extends fine."""
    path = tmp_path / "events.jsonl"
    log = EventLog(path)
    for i in range(4):
        log.emit("coordinator", "tick", {"i": i})
    # Re-open (drives _restore_from_disk_unlocked through the S4 recompute) and
    # extend; must succeed.
    reopened = EventLog(path)
    e = reopened.emit("coordinator", "ok", {})
    assert e.event.seq == 4
    ok, reason = EventLog(path).verify_chain()
    assert ok, reason


# ---------------------------------------------------------------------------
# S5 — compute_hash must be canonical (key-order independent)
# ---------------------------------------------------------------------------


def test_s5_compute_hash_is_key_order_independent() -> None:
    """S5 (cycle-10): two events with the SAME payload built in different key
    order must hash equal. Pre-fix compute_hash used insertion-order
    model_dump_json(), so the chain hash depended on payload key order."""
    payload_a = {"alpha": 1, "beta": 2, "gamma": {"x": 1, "y": 2}}
    payload_b = {"gamma": {"y": 2, "x": 1}, "beta": 2, "alpha": 1}  # same data, different order
    assert payload_a == payload_b  # dict equality ignores order

    ev_a = Event(seq=0, timestamp=123.0, actor="coordinator", kind="k", payload=payload_a)
    ev_b = Event(seq=0, timestamp=123.0, actor="coordinator", kind="k", payload=payload_b)

    h_a = SignedEvent.compute_hash(ev_a, GENESIS_PREV_HASH)
    h_b = SignedEvent.compute_hash(ev_b, GENESIS_PREV_HASH)
    assert h_a == h_b, "chain hash is payload-key-order-dependent (S5 not fixed)"


def test_s5_tampering_still_detected_after_canonicalization(tmp_path: Path) -> None:
    """S5 (cycle-10): canonicalization must NOT weaken tamper detection — a
    changed payload value still flips the hash and is caught by verify_chain."""
    path = tmp_path / "events.jsonl"
    log = EventLog(path)
    log.emit("coordinator", "boot", {})
    log.emit("coordinator", "tick", {"i": 1})
    log.emit("coordinator", "tick", {"i": 2})

    lines = path.read_text(encoding="utf-8").splitlines()
    middle = SignedEvent.model_validate_json(lines[1])
    tampered = SignedEvent(
        event=middle.event.model_copy(update={"payload": {"i": 9999}}),
        prev_hash=middle.prev_hash,
        event_hash=middle.event_hash,  # stale on purpose
    )
    lines[1] = tampered.model_dump_json()
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")

    ok, reason = EventLog(path).verify_chain()
    assert not ok
    assert "event_hash mismatch" in (reason or "")
