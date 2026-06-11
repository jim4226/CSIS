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
            self._restore_from_disk_unlocked()
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
        """Yield SignedEvents in order, optionally starting at a seq number."""
        if not self.path.exists():
            return
        with self.path.open("r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                signed = SignedEvent.model_validate_json(line)
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
            with self.path.open("r", encoding="utf-8") as f:
                for physical_lineno, raw in enumerate(f):
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
                # The file is LONGER than the anchor (e.g. an append landed
                # but the anchor write was lost). The chain is internally
                # consistent; flag it so a stale anchor doesn't masquerade as
                # truncation, but don't fail an otherwise-intact longer chain.
                return False, (
                    f"head-anchor stale/behind: file has {expected_seq} events "
                    f"but anchor records {anchor_count} (anchor write lost?)"
                )
        return True, None

    # ---- internal -------------------------------------------------------

    def _restore_from_disk(self) -> None:
        """Public-ish wrapper: acquires the inter-process file lock and
        reloads. Used at __init__ time; ``emit`` calls the _unlocked
        variant since it already holds the lock."""
        with file_lock(self._lock_path):
            self._restore_from_disk_unlocked()

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

        S4 (cycle-10): forged-tail rejection. The adopted tail
        (``seq+1``/``event_hash`` that future emits extend) used to be trusted
        with zero validation, so a single appended forged line made every
        future emit extend the forged fork. Before adopting the last line as
        the new chain head we recompute its hash; a well-formed line whose
        ``event_hash`` does not match ``compute_hash(event, prev_hash)`` is a
        forgery and raises (it is NOT torn — it parses fine — so truncation is
        not the right remedy).
        """
        if not self.path.exists():
            return

        raw = self.path.read_bytes()
        # Physical lines, preserving byte offsets so we can truncate a torn
        # tail precisely. A trailing newline yields no empty final element.
        text = raw.decode("utf-8", errors="replace")
        physical = text.split("\n")
        # If the file ends with "\n", split() leaves a trailing "" — that's a
        # clean end, not a torn line. Otherwise the last element is the bytes
        # written after the last newline (possibly a torn fragment).
        ends_with_newline = text.endswith("\n")

        last_signed: SignedEvent | None = None
        truncated = False
        n_lines = len(physical)
        for idx, rawline in enumerate(physical):
            is_last_element = idx == n_lines - 1
            line = rawline.strip()
            if not line:
                # Empty trailing element after a final newline, or an
                # interior blank line. Interior blanks are tolerated here
                # (verify_chain is the strict auditor); a trailing empty
                # element is just the clean end-of-file.
                continue
            try:
                signed = SignedEvent.model_validate_json(line)
            except ValidationError:
                if is_last_element and not ends_with_newline:
                    # S3: torn final line. Truncate back to the byte after the
                    # last newline and recover from the last valid event.
                    self._truncate_torn_tail_unlocked(raw)
                    truncated = True
                    break
                # Malformed non-final (or newline-terminated) line: real
                # corruption, not a torn append.
                raise
            last_signed = signed

        if last_signed is None:
            self._seq = 0
            self._prev_hash = GENESIS_PREV_HASH
        else:
            # S4: do not trust the adopted tail blindly — prove it chains.
            recomputed = SignedEvent.compute_hash(
                last_signed.event, last_signed.prev_hash
            )
            if recomputed != last_signed.event_hash:
                raise ChainForgeryError(
                    f"refusing to extend a non-chaining tail at seq "
                    f"{last_signed.event.seq}: stored event_hash does not "
                    f"match recomputed hash (forged/corrupt last line). "
                    f"emit() would otherwise extend this forged fork."
                )
            self._seq = last_signed.event.seq + 1
            self._prev_hash = last_signed.event_hash

        if truncated:
            # S3 + S2: after dropping a torn tail, realign the head anchor to
            # the recovered state so a subsequent verify_chain doesn't read a
            # stale (longer) anchor as a mismatch.
            self._write_anchor_unlocked(self._seq, self._prev_hash)

    def _truncate_torn_tail_unlocked(self, raw: bytes) -> None:
        """S3 (cycle-10): drop a torn final line back to the last newline.

        Caller MUST hold ``self._lock`` and the inter-process file lock.
        """
        nl = raw.rfind(b"\n")
        keep = raw[: nl + 1] if nl != -1 else b""
        with self.path.open("wb") as f:
            f.write(keep)
            f.flush()
            os.fsync(f.fileno())

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
