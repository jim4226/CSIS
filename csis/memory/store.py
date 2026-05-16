"""MemoryStore: candidate + live store pairs with hash-preconditioned promotion.

The doc's discipline:
- Memory writes go through *candidate* stores. The live store is never written
  to in place.
- Promotion is the only mutation primitive (P5 Reversibility).
- Every promotion carries a hash precondition; if the live store moved, the
  promotion fails and the loop iterates.

This module also enforces the trust-level lattice from §6.2 and the
read-only-by-default attachment rule.
"""
from __future__ import annotations

import json
import threading
import time
import uuid
from pathlib import Path
from typing import Iterable

from pydantic import BaseModel

from csis.contracts import MemoryEntry
from csis.memory.trust import TrustLevel, role_may_read, valid_promotion
from csis.substrate.hashing import canonical_json_hash


class PromotionPreconditionFailure(Exception):
    """Raised when a hash precondition no longer matches the live store."""


class TrustViolation(Exception):
    """Raised when a write/read crosses a trust boundary it shouldn't."""


class TierConsumerViolation(Exception):
    """Raised when promote() is called for a tier whose consumer ceiling
    is above the producer role's authorized ceiling (F5/P4 mitigation
    enforced at the substrate, not just at the Librarian site)."""


class MemoryStore:
    """One memory tier × (candidate | live) pair, persisted to JSON.

    The store is keyed by entry_id. Writes to the candidate side are free.
    Promoting candidate -> live requires:
      (a) a hash precondition matching the live store's current state, AND
      (b) (optional) a TierGuard authorizing the producer role to write
          to this tier's consumer tier (P4 mitigation — F5 made invariant).

    On a successful promote the candidate's trust is atomically bumped to
    PROMOTED inside the store under lock; the Coordinator never pre-writes
    PROMOTED candidates (P1 mitigation).
    """

    def __init__(
        self,
        tier: str,
        root: Path | str,
        *,
        tier_guard: "object | None" = None,
    ) -> None:
        self.tier = tier
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)
        self._lock = threading.RLock()
        self._candidate: dict[str, MemoryEntry] = {}
        self._live: dict[str, MemoryEntry] = {}
        self._candidate_path = self.root / f"{tier}.candidate.json"
        self._live_path = self.root / f"{tier}.live.json"
        self._archive_dir = self.root / "archive"
        self._archive_dir.mkdir(exist_ok=True)
        # TierGuard is optional to keep the existing call sites working;
        # the Coordinator wires one in, see coordinator.py.
        self._tier_guard = tier_guard
        self._load()

    # ---- hashing --------------------------------------------------------

    def live_hash(self) -> str:
        """Canonical hash of the live store contents.

        Used as a hash precondition — anything that wants to promote against
        the live store records this hash, and promotion fails if it moved.
        """
        with self._lock:
            snap = {eid: e.model_dump() for eid, e in sorted(self._live.items())}
            return canonical_json_hash(snap)

    def candidate_hash(self) -> str:
        with self._lock:
            snap = {eid: e.model_dump() for eid, e in sorted(self._candidate.items())}
            return canonical_json_hash(snap)

    # ---- candidate-side writes -----------------------------------------

    def write_candidate(self, entry: MemoryEntry) -> None:
        """Add or update a candidate entry. No trust-upgrade restriction on
        the candidate side — that's what candidate is for."""
        with self._lock:
            self._candidate[entry.entry_id] = entry
            self._flush()

    def write_candidates(self, entries: Iterable[MemoryEntry]) -> None:
        with self._lock:
            for entry in entries:
                self._candidate[entry.entry_id] = entry
            self._flush()

    # ---- live-side reads ------------------------------------------------

    def read_live(self, entry_id: str, *, role: str) -> MemoryEntry | None:
        with self._lock:
            entry = self._live.get(entry_id)
            if entry is None:
                return None
            if not role_may_read(role, entry.trust):
                raise TrustViolation(
                    f"role={role} not permitted to read trust={entry.trust.name} in tier={self.tier}"
                )
            return entry

    def read_candidate(self, entry_id: str, *, role: str) -> MemoryEntry | None:
        with self._lock:
            entry = self._candidate.get(entry_id)
            if entry is None:
                return None
            if not role_may_read(role, entry.trust):
                raise TrustViolation(
                    f"role={role} not permitted to read trust={entry.trust.name} in tier={self.tier}"
                )
            return entry

    def iter_live(self, *, role: str) -> Iterable[MemoryEntry]:
        with self._lock:
            for entry in list(self._live.values()):
                if role_may_read(role, entry.trust):
                    yield entry

    # ---- promotion ------------------------------------------------------

    def promote(
        self,
        entry_ids: list[str],
        *,
        precondition_hash: str,
        why_id: str,
        producer_role: str | None = None,
    ) -> list[MemoryEntry]:
        """Atomically move named candidate entries into live.

        Raises:
          PromotionPreconditionFailure — precondition_hash != current live_hash().
          TrustViolation              — promotion goes the wrong way through the lattice.
          TierConsumerViolation       — producer_role lacks authority to write to
                                        this tier's consumer tier (P4 invariant).

        On success: bumps each candidate's trust atomically to PROMOTED,
        moves it to live, archives the candidate side. The Coordinator never
        pre-writes PROMOTED candidates — that's now this store's job (P1).
        """
        with self._lock:
            # P4 invariant: tier consumer ceiling enforced at the substrate.
            if self._tier_guard is not None and producer_role is not None:
                ok, reason = self._tier_guard.write_tier(producer_role, self.tier)
                if not ok:
                    raise TierConsumerViolation(reason)

            current_live_hash = self.live_hash()
            if precondition_hash != current_live_hash:
                raise PromotionPreconditionFailure(
                    f"live store moved: precondition={precondition_hash[:24]}... "
                    f"current={current_live_hash[:24]}..."
                )

            promoted: list[MemoryEntry] = []
            now = time.time()
            for entry_id in entry_ids:
                cand = self._candidate.get(entry_id)
                if cand is None:
                    raise KeyError(f"no candidate with id={entry_id}")
                # The candidate must be eligible to promote upward through
                # the lattice. DEPRECATED is terminal; you cannot resurrect.
                if not valid_promotion(cand.trust, TrustLevel.PROMOTED):
                    raise TrustViolation(
                        f"cannot promote candidate at trust={cand.trust.name} "
                        f"in tier={self.tier} for entry={entry_id}"
                    )
                # P1/P10: bump trust to PROMOTED inside the store under lock.
                promoted_cand = cand.model_copy(
                    update={"trust": TrustLevel.PROMOTED, "promoted_at": now}
                )
                existing = self._live.get(entry_id)
                if existing is not None and not valid_promotion(existing.trust, promoted_cand.trust):
                    raise TrustViolation(
                        f"invalid promotion in tier={self.tier} for entry={entry_id}: "
                        f"{existing.trust.name} -> {promoted_cand.trust.name}"
                    )
                self._live[entry_id] = promoted_cand
                promoted.append(promoted_cand)
                # Move out of active candidates into the archive for audit.
                self._archive_candidate(cand, why_id)
                del self._candidate[entry_id]

            self._flush()
            return promoted

    def mark_verified(self, entry_ids: list[str]) -> list[MemoryEntry]:
        """P10 mitigation. After the Verifier certifies an iteration's
        candidates, the Coordinator calls this to bump CANDIDATE -> VERIFIED
        on the candidate side. If promotion later fails, the entry remains
        VERIFIED (not stale PROMOTED), so downstream readers can distinguish
        "verified but stale precondition" from "never verified."
        """
        with self._lock:
            out: list[MemoryEntry] = []
            for eid in entry_ids:
                cand = self._candidate.get(eid)
                if cand is None:
                    raise KeyError(f"no candidate with id={eid}")
                if cand.trust >= TrustLevel.VERIFIED:
                    out.append(cand)
                    continue
                upgraded = cand.model_copy(update={"trust": TrustLevel.VERIFIED})
                self._candidate[eid] = upgraded
                out.append(upgraded)
            self._flush()
            return out

    def discard_candidate(self, entry_id: str, *, reason: str) -> None:
        """Drop a candidate entry. Always allowed (it's not yet live)."""
        with self._lock:
            cand = self._candidate.pop(entry_id, None)
            if cand is None:
                return
            self._archive_candidate(cand, f"discarded:{reason}")
            self._flush()

    def deprecate_live(self, entry_id: str, *, reason: str) -> None:
        """Mark a live entry deprecated. Terminal; cannot be undone here."""
        with self._lock:
            entry = self._live.get(entry_id)
            if entry is None:
                return
            self._live[entry_id] = entry.model_copy(
                update={"trust": TrustLevel.DEPRECATED, "deprecated_reason": reason}
            )
            self._flush()

    # ---- persistence ----------------------------------------------------

    def _flush(self) -> None:
        self._candidate_path.write_text(
            json.dumps(
                {eid: e.model_dump(mode="json") for eid, e in self._candidate.items()},
                indent=2,
                sort_keys=True,
                default=str,
            ),
            encoding="utf-8",
        )
        self._live_path.write_text(
            json.dumps(
                {eid: e.model_dump(mode="json") for eid, e in self._live.items()},
                indent=2,
                sort_keys=True,
                default=str,
            ),
            encoding="utf-8",
        )

    def _load(self) -> None:
        if self._candidate_path.exists():
            raw = json.loads(self._candidate_path.read_text(encoding="utf-8") or "{}")
            self._candidate = {k: MemoryEntry.model_validate(v) for k, v in raw.items()}
        if self._live_path.exists():
            raw = json.loads(self._live_path.read_text(encoding="utf-8") or "{}")
            self._live = {k: MemoryEntry.model_validate(v) for k, v in raw.items()}

    def _archive_candidate(self, entry: MemoryEntry, why_id: str) -> None:
        # P9 mitigation: archive paths include a millisecond timestamp + a
        # random suffix so collisions between two entries with the same
        # entry_id never overwrite each other.
        stamp = int(time.time() * 1000)
        salt = uuid.uuid4().hex
        path = self._archive_dir / f"{self.tier}_{entry.entry_id}_{why_id}_{stamp}_{salt}.json"
        path.write_text(
            json.dumps(entry.model_dump(mode="json"), indent=2, default=str),
            encoding="utf-8",
        )


class MemoryHierarchy(BaseModel):
    """The five-tier hierarchy from §6.1, materialized as five stores."""

    model_config = {"arbitrary_types_allowed": True}

    working: MemoryStore
    episodic: MemoryStore
    semantic: MemoryStore
    procedural: MemoryStore
    causal: MemoryStore

    @classmethod
    def open(cls, root: Path | str, *, tier_guard: "object | None" = None) -> "MemoryHierarchy":
        root = Path(root)
        return cls(
            working=MemoryStore("working", root, tier_guard=tier_guard),
            episodic=MemoryStore("episodic", root, tier_guard=tier_guard),
            semantic=MemoryStore("semantic", root, tier_guard=tier_guard),
            procedural=MemoryStore("procedural", root, tier_guard=tier_guard),
            causal=MemoryStore("causal", root, tier_guard=tier_guard),
        )

    def tier(self, name: str) -> MemoryStore:
        return getattr(self, name)
