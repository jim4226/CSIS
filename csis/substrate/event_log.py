"""Append-only event log.

The session log is the durable substrate the Auditor reads to write the
why-doc that gates every promotion. Per §15: 'nothing safety-critical lives
only in harness memory.' Everything goes through this.

Format: one JSON object per line (JSONL). Each line is a SignedEvent with
a content hash that chains to the previous line's hash, giving us a poor
person's hash chain for tamper-evidence.
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


_ALLOWED_ACTORS: frozenset[str] = frozenset(
    {"coordinator", "researcher", "builder", "critic", "verifier", "librarian", "auditor", "overseer", "substrate"}
)


class UnknownActorError(Exception):
    """Raised when emit() is called with an actor not in the Phase-0 allow-list.

    P7 mitigation. The Phase-0 discipline is: every actor that emits to the
    log must be one of the known role names. If a future role is added, the
    allow-list must be updated explicitly so the F8 structured_query
    audit-evidence trust contract continues to hold.
    """


class EventLog:
    """Append-only JSONL event log with in-memory cache.

    Thread-safe. The lock guards both the file write and the seq/prev_hash
    update so concurrent emits stay consistent.

    P7 mitigation: emit() rejects actor strings not in _ALLOWED_ACTORS so
    a sub-agent's payload cannot spoof a "verifier"-tier event.
    """

    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()
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
        (P7 mitigation)."""
        if actor not in _ALLOWED_ACTORS:
            raise UnknownActorError(
                f"actor={actor!r} not in Phase-0 allow-list; "
                f"update csis.substrate.event_log._ALLOWED_ACTORS to add new roles."
            )
        with self._lock:
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
