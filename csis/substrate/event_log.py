"""Append-only event log.

The session log is the durable substrate the Auditor reads to write the
why-doc that gates every promotion. Per §15: 'nothing safety-critical lives
only in harness memory.' Everything goes through this.

Format: one JSON object per line (JSONL). Each line is a SignedEvent with
a content hash that chains to the previous line's hash, giving us a poor
person's hash chain for tamper-evidence.

**Snapshot-12 fix (chain-integrity, cross-process):** ``emit()`` and
``_restore_from_disk()`` now acquire an inter-process file lock for the
read-current-state + write-line + advance-counter critical section. The
previous threading.Lock only serialized callers in the SAME process, so
two daemon instances (or daemon + burst.py running concurrently) racing
on the same session.jsonl could each cache a stale ``_seq``, write
overlapping seq values, and break the hash chain. The pre-snapshot-12
session.jsonl in this repo accumulated 5 such breaks; they are quarantined
to ``event_log/session.broken-pre-snap12.jsonl`` and a new chain starts
fresh from genesis.
"""
from __future__ import annotations

import hashlib
import json
import os
import sys
import threading
import time
from pathlib import Path
from typing import Any, Iterator

from pydantic import BaseModel, Field, ValidationError

from csis.substrate.file_lock import LockUnavailable, file_lock


GENESIS_PREV_HASH: str = "0" * 64


class Event(BaseModel):
    """A single event in the session log.

    The schema is intentionally permissive on `payload` — different event
    types have different shapes, and we don't want to fork the model.
    Strict shape checking lives in the producers (e.g., the Verifier
    produces VerifierCertificate-shaped payloads, the Auditor produces
    WhyDoc-shaped payloads).
    """

    seq: int = Field(..., description="Monotonic counter starting at 0")
    timestamp: float = Field(..., description="Unix time, seconds")
    actor: str = Field(..., description="Role that emitted this event")
    kind: str = Field(..., description="Event kind, e.g. 'plan.proposed', 'verifier.cert', 'auditor.signed'")
    payload: dict[str, Any] = Field(default_factory=dict)


class SignedEvent(BaseModel):
    """An Event wrapped with hash chaining for tamper-evidence."""

    event: Event
    prev_hash: str
    event_hash: str

    @staticmethod
    def compute_hash(event: Event, prev_hash: str) -> str:
        """Chain hash of an event over the previous hash.

        S5 (cycle-10): the previous implementation claimed "Canonical JSON:
        sorted keys" but actually used ``event.model_dump_json()`` which
        preserves *insertion order*. That made the chain hash depend on the
        payload key order, so two semantically-identical events could hash
        differently (and a re-serialized payload could fail to verify). We
        now hash a genuinely canonical body (sorted keys, no whitespace,
        deterministic across runtimes). This changes the hash of
        newly-written events vs. pre-cycle-10 logs, but the chain is
        self-consistent because emit() and verify_chain() both route through
        this method.
        """
        h = hashlib.sha256()
        # Canonical JSON: sorted keys, no whitespace, stable across runtimes.
        body = json.dumps(
            event.model_dump(mode="json"),
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
        )
        h.update(prev_hash.encode("utf-8"))
        h.update(body.encode("utf-8"))
        return h.hexdigest()


def _load_allowed_actors() -> frozenset[str]:
    """Lazy import to avoid a substrate <- agents cycle at module load.

    Synthesis gap #4 fix: the allow-list now lives next to the Role enum
    (csis.agents.base.ALLOWED_EMIT_ACTORS). EventLog imports it lazily so
    the substrate layer doesn't depend on the agents layer at import time
    — only at the first emit() call, by which time everything is loaded.
    """
    from csis.agents.base import ALLOWED_EMIT_ACTORS
    return ALLOWED_EMIT_ACTORS


class UnknownActorError(Exception):
    """Raised when emit() is called with an actor not in the Phase-0 allow-list.

    P7 mitigation. The Phase-0 discipline is: every actor that emits to the
    log must be one of the known role names. If a future role is added, the
    allow-list must be updated explicitly so the F8 structured_query
    audit-evidence trust contract continues to hold.
    """


class ChainForgeryError(Exception):
    """S4 (cycle-10): raised when the on-disk tail does not chain.

    The re-sync that ``emit()`` performs adopts the last line's ``seq+1`` and
    ``event_hash`` as the new chain head. If that last line is well-formed but
    its ``event_hash`` does not match ``compute_hash(event, prev_hash)`` it is
    a forged/corrupt fork; trusting it would make every future emit extend the
    forgery. We raise instead of silently chaining onto it. (A *torn* — i.e.
    unparseable — final line is a different case handled by S3 truncation.)
    """


class EventLog:
    """Append-only JSONL event log with in-memory cache.

    Thread-safe AND process-safe. The threading.Lock serializes intra-process
    callers; the inter-process file lock (snapshot-12) serializes across
    OS processes so two daemons (or daemon + burst.py) targeting the same
    session.jsonl can't race on the seq counter and tear the hash chain.

    P7 mitigation: emit() rejects actor strings not in _ALLOWED_ACTORS so
    a sub-agent's payload cannot spoof a "verifier"-tier event.
    """

    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()
        # Distinct lock file so a corrupt session.jsonl doesn't strand the
        # lock (and vice versa). Matches the budget.py convention.
        self._lock_path = self.path.with_suffix(self.path.suffix + ".lock")
        # S2 (cycle-10): head-anchor sidecar. Holds {count, latest_hash} for
        # the chain as last written. verify_chain() cross-checks the walked
        # length and final hash against it, so a tail truncation/rollback
        # (dropping the most recent N events, e.g. an auditor.signed) — which
        # leaves a shorter but internally-consistent chain that would
        # otherwise verify True — now fails verification.
        self._anchor_path = self.path.with_suffix(self.path.suffix + ".head")
        self._seq = 0
        self._prev_hash = GENESIS_PREV_HASH
        if self.path.exists():
            self._restore_from_disk()
        else:
            # touch the file so callers can rely on its existence
            self.path.touch()

    # ---- writes ---------------------------------------------------------

    def emit(self, actor: str, kind: str, payload: dict[str, Any] | None = None) -> SignedEvent:
        """Append a new event. Returns the signed wrapper.

        Raises UnknownActorError if `actor` is not in the Phase-0 allow-list
        (P7 mitigation).

        Snapshot-12: acquires an inter-process file lock for the
        read-tail / write-line / advance-counter critical section so
        concurrent processes share a single linear hash chain.
        """
        if actor not in _load_allowed_actors():
            raise UnknownActorError(
                f"actor={actor!r} not in Phase-0 allow-list; "
                f"add to csis.agents.base.ALLOWED_EMIT_ACTORS to introduce a new role."
            )
        with self._lock, file_lock(self._lock_path):
            # Re-sync from disk under the lock so we see any sibling
            # writes that landed since our last emit. This is the fix
            # for the cross-process seq race that broke the chain.
            # eventlog-K3 (cycle-13): use the TAIL-only fast path, not the
            # full-file re-parse — the old _restore_from_disk_unlocked()
            # read_bytes() the whole file and ran model_validate_json on EVERY
            # line just to read the last record's seq/hash, giving O(n) work
            # per emit / O(n^2) per session while holding the cross-process
            # lock for O(n). The tail path parses one record; it falls back to
            # the full walk only when the tail is torn/non-chaining (recovery).
            self._resync_tail_unlocked()
            event = Event(
                seq=self._seq,
                timestamp=time.time(),
                actor=actor,
                kind=kind,
                payload=payload or {},
            )
            event_hash = SignedEvent.compute_hash(event, self._prev_hash)
            signed = SignedEvent(event=event, prev_hash=self._prev_hash, event_hash=event_hash)
            # S3 (cycle-10): make the append durable. Plain open("a") with no
            # flush/fsync left the bytes in libc/OS buffers; a crash mid-write
            # produced a torn final line that bricked every subsequent
            # construct/emit/verify (model_validate_json raised on the
            # fragment). flush()+fsync() under the lock guarantees the line is
            # on stable storage before we advance the in-memory chain head.
            with self.path.open("a", encoding="utf-8") as f:
                f.write(signed.model_dump_json() + "\n")
                f.flush()
                os.fsync(f.fileno())
            self._seq += 1
            self._prev_hash = event_hash
            # S2 (cycle-10): advance the head anchor in the SAME locked
            # section so it stays in lock-step with the log tail.
            self._write_anchor_unlocked(self._seq, self._prev_hash)
            return signed

    # ---- reads ----------------------------------------------------------

    def __iter__(self) -> Iterator[SignedEvent]:
        return self.iter_events()

    def iter_events(self, start: int = 0) -> Iterator[SignedEvent]:
        """Yield SignedEvents in order, optionally starting at a seq number.

        eventlog-K2 (cycle-13): read the file's bytes under the inter-process
        ``file_lock`` (snapshot-12 serialized WRITERS but left READERS
        lock-free, so a reader concurrent with an emit's non-atomic
        write+flush+fsync could observe a torn partial final line — a spurious
        ValidationError on the promotion-gating audit path the Auditor drives
        via ``structured_query``). We snapshot the lines under the lock, then
        release it before yielding so a slow consumer can't hold the lock. A
        torn FINAL line (a sibling that crashed mid-append while we did not hold
        the lock) is dropped rather than raised; a malformed NON-final line is
        still a hard error (real corruption, surfaced by construction/recovery).
        """
        if not self.path.exists():
            return
        with self._lock, file_lock(self._lock_path):
            with self.path.open("r", encoding="utf-8") as f:
                lines = f.readlines()
        n = len(lines)
        for idx, raw in enumerate(lines):
            line = raw.strip()
            if not line:
                continue
            try:
                signed = SignedEvent.model_validate_json(line)
            except ValidationError:
                if idx == n - 1 and not raw.endswith("\n"):
                    return  # torn final line — stop cleanly (K2)
                raise
            if signed.event.seq >= start:
                yield signed

    def latest_hash(self) -> str:
        """Useful for hash-preconditioned writes elsewhere."""
        return self._prev_hash

    def seq(self) -> int:
        return self._seq

    # ---- integrity ------------------------------------------------------

    def verify_chain(self) -> tuple[bool, str | None]:
        """Walk the file and confirm every line's hash chains correctly.

        Returns (True, None) if intact, (False, reason) otherwise. Cheap
        enough to run at startup and at every Auditor sign step.

        S2 (cycle-10): two additional integrity properties beyond the
        genesis->EOF walk, which on its own treats any internally-consistent
        prefix as valid (so a tail truncation/rollback that drops the most
        recent events — including ``auditor.signed`` — verified True):
          * Blank/whitespace-only lines are now a hard failure rather than
            silently skipped (they have no business in an append-only log and
            mask a torn or edited file).
          * The walked length and final hash are cross-checked against the
            head-anchor sidecar. If the anchor says N events ending in hash H
            and the file walks to fewer events or a different final hash, the
            tail was truncated/rolled back and verification fails. A missing
            anchor is treated as 'unverifiable-length' (the chain still has to
            be internally consistent, but we cannot prove the tail is whole).
        """
        prev = GENESIS_PREV_HASH
        expected_seq = 0
        if self.path.exists():
            # eventlog-K2 (cycle-13): snapshot the log under the inter-process
            # lock so a concurrent emit can't present a torn final line as a
            # spurious verification failure.
            with self._lock, file_lock(self._lock_path):
                with self.path.open("r", encoding="utf-8") as f:
                    _lines = f.readlines()
            for physical_lineno, raw in enumerate(_lines):
                    line = raw.strip()
                    if not line:
                        # S2: reject, do not skip.
                        return False, (
                            f"blank/whitespace line at physical line "
                            f"{physical_lineno} (torn or edited log)"
                        )
                    try:
                        signed = SignedEvent.model_validate_json(line)
                    except ValidationError:
                        return False, (
                            f"unparseable line at physical line {physical_lineno} "
                            f"(torn write or corruption)"
                        )
                    if signed.event.seq != expected_seq:
                        return False, f"seq gap at expected {expected_seq}, got {signed.event.seq}"
                    if signed.prev_hash != prev:
                        return False, f"prev_hash mismatch at seq {signed.event.seq}"
                    recomputed = SignedEvent.compute_hash(signed.event, signed.prev_hash)
                    if recomputed != signed.event_hash:
                        return False, f"event_hash mismatch at seq {signed.event.seq}"
                    prev = signed.event_hash
                    expected_seq += 1

        # S2: cross-check the walked length/final-hash against the head anchor.
        anchor = self._read_anchor()
        if anchor is not None:
            anchor_count, anchor_hash = anchor
            if expected_seq < anchor_count or (
                expected_seq == anchor_count and prev != anchor_hash
            ):
                return False, (
                    f"tail truncation/rollback: head-anchor expects "
                    f"{anchor_count} events ending in {anchor_hash[:12]}…, "
                    f"file walks {expected_seq} events ending in "
                    f"{prev[:12]}…"
                )
            if expected_seq > anchor_count:
                # eventlog-K1 (cycle-13): the file is LONGER than the anchor —
                # emit() fsyncs the event LINE and only THEN advances the
                # anchor, so an honest crash/SIGKILL in that window leaves a
                # durable, fully-chained event whose anchor write was lost. The
                # walk above already proved every hash links from genesis, so
                # the chain IS intact — returning False here (as the old code
                # did, contradicting its own comment) reported a healthy chain
                # as tampered and would, e.g., wrongly halt a
                # verify-on-startup. Only a SHORTER file (rollback, above) or a
                # same-length divergent hash is a real failure; a longer intact
                # chain is not. The next emit() realigns the anchor.
                return True, None
        return True, None

    # ---- internal -------------------------------------------------------

    def _restore_from_disk(self) -> None:
        """Public-ish wrapper: acquires the inter-process file lock and
        reloads. Used at __init__ time; ``emit`` calls the _unlocked
        variant since it already holds the lock."""
        with file_lock(self._lock_path):
            self._restore_from_disk_unlocked()

    def _resync_tail_unlocked(self) -> None:
        """Emit-time re-sync: recover ``_seq``/``_prev_hash`` by parsing ONLY
        the tail of the file (eventlog-K3 cycle-13).

        Caller MUST hold ``self._lock`` and the inter-process file lock. Reads a
        bounded chunk from the end of the file, extracts the last complete line,
        and adopts it if it parses and chains — O(1) amortized instead of the
        full-file O(n) re-parse. Any ambiguity (a torn trailing fragment, a line
        longer than the chunk, a non-parseable or non-chaining tail) falls back
        to the full-walk ``_restore_from_disk_unlocked()``, which owns the
        delicate S3/S4/recovery logic. This method never adopts an unvalidated
        tail, so S4's "never extend a forged fork" property is preserved.
        """
        if not self.path.exists():
            return
        try:
            size = self.path.stat().st_size
        except OSError:
            self._restore_from_disk_unlocked()
            return
        if size == 0:
            self._seq = 0
            self._prev_hash = GENESIS_PREV_HASH
            return
        chunk_size = 65536
        start = max(0, size - chunk_size)
        with self.path.open("rb") as f:
            f.seek(start)
            chunk = f.read()
        ends_with_newline = chunk.endswith(b"\n")
        if not ends_with_newline:
            # Possible torn final line (a sibling crashed mid-append while we
            # held no lock). Let the full walk detect/recover it.
            self._restore_from_disk_unlocked()
            return
        body = chunk[:-1]  # drop the final newline
        nl = body.rfind(b"\n")
        if nl == -1:
            if start > 0:
                # The last line is longer than our chunk (or we started
                # mid-line): we cannot prove it is complete — full walk.
                self._restore_from_disk_unlocked()
                return
            last_line = body  # whole file is a single line
        else:
            last_line = body[nl + 1:]
        tail = last_line.decode("utf-8", errors="replace").strip()
        if not tail:
            self._restore_from_disk_unlocked()
            return
        try:
            last = SignedEvent.model_validate_json(tail)
        except ValidationError:
            self._restore_from_disk_unlocked()
            return
        if SignedEvent.compute_hash(last.event, last.prev_hash) != last.event_hash:
            # Non-chaining tail (forged append or pre-cycle-10 hash format):
            # quarantine + recover via the full walk (S4).
            self._restore_from_disk_unlocked()
            return
        self._seq = last.event.seq + 1
        self._prev_hash = last.event_hash

    def _restore_from_disk_unlocked(self) -> None:
        """Read the file's tail and update ``_seq``/``_prev_hash``.

        Caller MUST hold ``self._lock`` and the inter-process file lock.
        Used inside emit() so each append is based on the live file state
        (not a stale process-local cache). Pre-snapshot-12 the cache could
        drift behind a sibling daemon's writes, which caused the 5
        chain breaks at iter.start events in the historical log.

        S3 (cycle-10): torn-last-line tolerance. A crash mid-append leaves a
        partial final line; the old code fed every line to
        ``model_validate_json`` and the fragment raised ValidationError,
        bricking construct/emit/verify. We now treat a ValidationError on the
        FINAL physical line as a torn write: truncate it back to the last
        newline (under the lock we already hold) and recover from the last
        valid event. A malformed NON-final line is still a hard error — it
        cannot be a torn append.

        S4 (cycle-10): non-chaining-tail handling. The adopted tail
        (``seq+1``/``event_hash`` that future emits extend) used to be trusted
        with zero validation, so a single appended forged line made every
        future emit extend the forged fork. Before adopting the last line we
        recompute its hash. A well-formed line whose ``event_hash`` does not
        match ``compute_hash(event, prev_hash)`` is a forged append OR a
        legacy log written before the S5 hash-format change. The first cut of
        S4 hard-raised here — but that BRICKS every existing deployment's log
        on upgrade (every pre-S5 line fails to recompute) and lets any appended
        garbage DoS the system. Instead we QUARANTINE the full log and recover
        the longest valid prefix (see ``_recover_to_valid_prefix_unlocked``):
        the forged/legacy suffix is isolated and never extended — S4's security
        property holds — while the system stays usable.
        """
        if not self.path.exists():
            return

        raw = self.path.read_bytes()
        text = raw.decode("utf-8", errors="replace")
        physical = text.split("\n")
        # If the file ends with "\n", split() leaves a trailing "" — a clean
        # end. Otherwise the last element is the bytes after the last newline
        # (possibly a torn fragment).
        ends_with_newline = text.endswith("\n")

        last_signed: SignedEvent | None = None
        n_lines = len(physical)
        for idx, rawline in enumerate(physical):
            is_last_element = idx == n_lines - 1
            line = rawline.strip()
            if not line:
                continue
            try:
                signed = SignedEvent.model_validate_json(line)
            except ValidationError:
                if is_last_element and not ends_with_newline:
                    # S3: torn final line (crash mid-append). Benign — drop it
                    # and recover the prior valid tail; no quarantine needed.
                    self._recover_to_valid_prefix_unlocked(
                        raw, reason="torn final line", quarantine=False
                    )
                    return
                # Malformed non-final (or newline-terminated) line: corruption.
                self._recover_to_valid_prefix_unlocked(
                    raw,
                    reason=f"unparseable line at physical index {idx}",
                    quarantine=True,
                )
                return
            last_signed = signed

        if last_signed is None:
            self._seq = 0
            self._prev_hash = GENESIS_PREV_HASH
            return

        # S4: prove the adopted tail chains before trusting it.
        recomputed = SignedEvent.compute_hash(
            last_signed.event, last_signed.prev_hash
        )
        if recomputed != last_signed.event_hash:
            self._recover_to_valid_prefix_unlocked(
                raw,
                reason=(
                    f"non-chaining tail at seq {last_signed.event.seq} "
                    f"(forged append or pre-cycle-10 hash format)"
                ),
                quarantine=True,
            )
            return
        self._seq = last_signed.event.seq + 1
        self._prev_hash = last_signed.event_hash

    def _recover_to_valid_prefix_unlocked(
        self, raw: bytes, *, reason: str, quarantine: bool
    ) -> None:
        """Walk from genesis, keep the LONGEST VALID PREFIX, drop the rest.

        Caller MUST hold ``self._lock`` and the inter-process file lock. The
        full chain (parse + contiguous seq + prev_hash linkage + event_hash
        recompute) is validated from genesis; the first line that breaks the
        chain ends the valid prefix. When ``quarantine`` is set (a forged /
        legacy / corrupt suffix, as opposed to a benign torn crash tail) the
        full pre-recovery log is copied to a ``.broken-<ts>.jsonl`` sidecar for
        forensics. The live log is then rewritten to the valid prefix, the
        in-memory head is set to that prefix's tail, and the anchor is realigned
        so a later verify_chain() doesn't read a stale (longer) anchor as a
        truncation. The dropped suffix is never adopted as the chain head, so a
        forged append can never be extended (S4's security intent).
        """
        parts = raw.split(b"\n")
        ends_with_newline = raw.endswith(b"\n")
        prev = GENESIS_PREV_HASH
        expected_seq = 0
        valid_bytes = 0
        for idx, part in enumerate(parts):
            is_last = idx == len(parts) - 1
            if is_last and ends_with_newline and part == b"":
                break
            if not part.strip():
                break
            try:
                signed = SignedEvent.model_validate_json(part.decode("utf-8"))
            except (ValidationError, UnicodeDecodeError):
                break
            if (
                signed.event.seq != expected_seq
                or signed.prev_hash != prev
                or SignedEvent.compute_hash(signed.event, signed.prev_hash)
                != signed.event_hash
            ):
                break
            prev = signed.event_hash
            expected_seq += 1
            valid_bytes += len(part) + 1  # +1: a complete line always has "\n"

        self._seq = expected_seq
        self._prev_hash = prev
        if quarantine:
            self._quarantine_unlocked(raw, reason)
        with self.path.open("wb") as f:
            f.write(raw[:valid_bytes])
            f.flush()
            os.fsync(f.fileno())
        # cycle-11 Finding-2: recovery may SHRINK the live file to drop a
        # forged/corrupt suffix, but it must never SHRINK the head anchor below
        # a previously-attested length. If the existing anchor attests MORE
        # events than we recovered, the dropped suffix was valid signed history
        # — a tail rollback the attacker paired with one corrupt byte to
        # trigger recovery — so leaving the anchor intact keeps verify_chain()
        # reporting the truncation instead of laundering it (the S4 fix must not
        # defeat the S2 fix). Only (re)write the anchor when recovery did NOT
        # drop attested history: a pre-cycle-10 legacy log has no anchor, and a
        # genuine forged-append-past-the-attested-end recovers a prefix at
        # least as long as the anchor claims.
        existing = self._read_anchor()
        if existing is None or self._seq >= existing[0]:
            self._write_anchor_unlocked(self._seq, self._prev_hash)

    # cycle-12 Finding-2 (inherent-limit note, # TODO(phase-1)): this recovery
    # path no longer launders a rollback by realigning the anchor down. But a
    # lightweight (count, latest_hash) sidecar is tamper-EVIDENT for the common
    # cases (truncation, corruption) — it is not tamper-PROOF against an on-disk
    # attacker who can (a) delete the .head sidecar (a missing anchor reads as
    # "unverifiable length" and verify_chain passes), or (b) truncate the tail
    # and let the daemon re-emit PAST the attested length, at which point the
    # high-water advances onto the new chain. Closing these fully needs Phase-1
    # signed-checkpoint attestation (an anchor signed on a different checkpoint,
    # rebuilt-from-checkpoint on a missing sidecar, with per-emit verification
    # against it) — beyond the in-process / honest-crash threat model this
    # sidecar serves. verify_chain() is advisory (recorded into snapshots, not a
    # halt gate); the authoritative durability story is the chain itself plus
    # the cross-checkpoint why-doc that gates each promotion.

    def _quarantine_unlocked(self, raw: bytes, reason: str) -> None:
        """Copy a corrupt/legacy log aside for forensics before truncation.

        Caller MUST hold ``self._lock`` and the inter-process file lock. This
        is the documented pre-snapshot-12 'quarantine the broken chain and
        start fresh' discipline, applied automatically on recovery.
        """
        stamp = time.strftime("%Y%m%d-%H%M%S", time.gmtime())
        stamp = f"{stamp}-{int(time.time() * 1000) % 1000:03d}"
        qpath = self.path.with_suffix(self.path.suffix + f".broken-{stamp}.jsonl")
        try:
            qpath.write_bytes(raw)
        except OSError:
            pass
        print(
            f"[event_log] WARNING: {reason}; quarantined {len(raw)} bytes to "
            f"{qpath.name} and recovered the longest valid prefix "
            f"({self._seq} events). The forged/legacy suffix was isolated, not "
            f"extended (cycle-10 S4).",
            file=sys.stderr,
        )

    # ---- head anchor (S2) ----------------------------------------------

    def _write_anchor_unlocked(self, count: int, latest_hash: str) -> None:
        """S2 (cycle-10): durably persist the head anchor {count, latest_hash}.

        Caller MUST hold ``self._lock`` and the inter-process file lock so the
        anchor stays in lock-step with the log tail. Written atomically via a
        temp file + ``os.replace`` so a crash can never leave a torn anchor
        (which would itself become a false truncation signal).
        """
        tmp = self._anchor_path.with_suffix(self._anchor_path.suffix + ".tmp")
        body = json.dumps(
            {"count": count, "latest_hash": latest_hash},
            sort_keys=True,
            separators=(",", ":"),
        )
        with tmp.open("w", encoding="utf-8") as f:
            f.write(body)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp, self._anchor_path)

    def _read_anchor(self) -> tuple[int, str] | None:
        """S2 (cycle-10): read the head anchor, or None if absent/unreadable.

        A missing anchor means 'unverifiable-length' (pre-cycle-10 logs, or a
        log that has never been emitted to through this code path): callers
        treat that as 'cannot prove the tail is whole' rather than a failure.
        A *malformed* anchor is treated the same as missing — we will not let a
        corrupt sidecar wedge verification of an otherwise-intact chain.
        """
        if not self._anchor_path.exists():
            return None
        try:
            data = json.loads(self._anchor_path.read_text(encoding="utf-8"))
            count = int(data["count"])
            latest_hash = str(data["latest_hash"])
        except (OSError, ValueError, KeyError, TypeError):
            return None
        return count, latest_hash
