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

from pydantic import BaseModel, Field

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
        h = hashlib.sha256()
        # Canonical JSON: sorted keys, no whitespace.
        body = event.model_dump_json()
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
            with self.path.open("a", encoding="utf-8") as f:
                f.write(signed.model_dump_json() + "\n")
            self._seq += 1
            self._prev_hash = event_hash
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
        """
        prev = GENESIS_PREV_HASH
        expected_seq = 0
        for signed in self.iter_events():
            if signed.event.seq != expected_seq:
                return False, f"seq gap at expected {expected_seq}, got {signed.event.seq}"
            if signed.prev_hash != prev:
                return False, f"prev_hash mismatch at seq {signed.event.seq}"
            recomputed = SignedEvent.compute_hash(signed.event, signed.prev_hash)
            if recomputed != signed.event_hash:
                return False, f"event_hash mismatch at seq {signed.event.seq}"
            prev = signed.event_hash
            expected_seq += 1
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
        """
        if not self.path.exists():
            return
        last_seq = -1
        last_hash = GENESIS_PREV_HASH
        with self.path.open("r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                signed = SignedEvent.model_validate_json(line)
                last_seq = signed.event.seq
                last_hash = signed.event_hash
        self._seq = last_seq + 1
        self._prev_hash = last_hash
