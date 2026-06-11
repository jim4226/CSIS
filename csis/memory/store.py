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
import re
import threading
import time
import uuid
from pathlib import Path
from typing import Iterable

from pydantic import BaseModel

from csis.contracts import MemoryEntry
from csis.memory.trust import TrustLevel, role_may_read, valid_promotion
from csis.substrate.hashing import canonical_json_hash


# C1 (cycle-10): the trust-lattice ceremony legitimately mutates these
# bookkeeping fields as a candidate moves CANDIDATE -> VERIFIED -> PROMOTED
# (mark_verified bumps `trust`; promote stamps `promoted_at`). The
# candidate post-image CAS must be INVARIANT under these so the legitimate
# mark_verified() trust bump between auditor-sign and promote is not a
# false mismatch — while remaining sensitive to any change in the
# SUBSTANTIVE content the Auditor actually signed off on (content, tier,
# why_tag, extra, ...). Hashing the full model_dump() would make every
# promotion fail the post-image check, because mark_verified always runs
# in the sign->promote window.
_LATTICE_BOOKKEEPING_FIELDS: frozenset[str] = frozenset(
    {"trust", "promoted_at", "deprecated_reason", "writer_iteration_id"}
)


def content_hash(entry: MemoryEntry) -> str:
    """Hash of an entry's substantive content, excluding the trust-lattice
    bookkeeping fields (C1 cycle-10).

    This is what the Auditor signs in each ``WhyDocDiff`` delta and what
    ``promote()`` re-checks under lock as a true post-image compare-and-swap.
    A tamper to the promoted bytes (content/extra/tier) is caught; the
    legitimate trust transition is not a false positive.
    """
    body = {
        k: v
        for k, v in entry.model_dump(mode="json").items()
        if k not in _LATTICE_BOOKKEEPING_FIELDS
    }
    return canonical_json_hash(body)


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

    def live_snapshot(self) -> tuple[str, dict[str, MemoryEntry]]:
        """Cycle-4 C7 + cycle-5 D2: return (hash, deep-copied snapshot)
        atomically.

        Callers used to take the hash and then iterate read_live() — a
        TOCTOU window where a parallel promote could flip an entry's
        existence between the two reads. This method returns both
        atomically under the lock.

        Cycle-5 D2 fix: `model_copy(deep=True)` so a buggy Auditor that
        mutates nested fields (notably `extra: dict`) doesn't write
        through to the live store.

        Cycle-6 E8 (deferred): the deep copy is O(n*size) — ~22 ms at
        1000 entries with modest extras. A MappingProxyType-based fast
        path was attempted but Pydantic v2 rejects it as a dict value.
        Real fix requires a Pydantic v2 frozen-dict adapter; deferred
        to Phase 1. Operators with very-large stores can mitigate by
        increasing the snapshot cadence (i.e., consolidating less often).
        """
        with self._lock:
            snap = {eid: e.model_copy(deep=True) for eid, e in self._live.items()}
            h = canonical_json_hash({eid: e.model_dump() for eid, e in sorted(snap.items())})
            return h, snap

    def candidate_hash(self) -> str:
        with self._lock:
            snap = {eid: e.model_dump() for eid, e in sorted(self._candidate.items())}
            return canonical_json_hash(snap)

    # ---- candidate-side writes -----------------------------------------

    def write_candidate(self, entry: MemoryEntry, *, writer_iteration_id: str | None = None) -> None:
        """Add or update a candidate entry. No trust-upgrade restriction on
        the candidate side — that's what candidate is for.

        H4 (cycle-9): if `writer_iteration_id` is provided, it is stamped
        onto a model_copy of `entry` so the TierMismatch cleanup can
        identify entries written by a specific iteration (race-free vs.
        cycle-8's pre-consolidate snapshot which failed if a sibling
        iteration wrote the same entry_id mid-window).
        """
        with self._lock:
            if writer_iteration_id is not None:
                entry = entry.model_copy(update={"writer_iteration_id": writer_iteration_id})
            self._candidate[entry.entry_id] = entry
            self._flush()

    def write_candidates(
        self, entries: Iterable[MemoryEntry], *, writer_iteration_id: str | None = None
    ) -> None:
        with self._lock:
            for entry in entries:
                if writer_iteration_id is not None:
                    entry = entry.model_copy(update={"writer_iteration_id": writer_iteration_id})
                self._candidate[entry.entry_id] = entry
            self._flush()

    # ---- live-side reads ------------------------------------------------

    @staticmethod
    def _view(entry: MemoryEntry) -> MemoryEntry:
        """M4 (cycle-10): every read path hands back a deep copy, never the
        stored object.

        Pydantic v2 models (and their nested ``extra: dict``) are mutable, so
        returning the stored instance let any caller write straight through
        into ``self._live`` / ``self._candidate`` — a mutation *outside*
        ``promote()``, which is supposed to be the only mutation primitive
        (module docstring; cycle-5 D2). cycle-5 fixed this for the bulk
        ``live_snapshot`` reader but never propagated the deep copy to the
        per-entry readers, and cycle-9 H4 added a fourth leaking reader
        (``candidates_snapshot``). This single chokepoint closes all of them.
        """
        return entry.model_copy(deep=True)

    def read_live(self, entry_id: str, *, role: str) -> MemoryEntry | None:
        with self._lock:
            entry = self._live.get(entry_id)
            if entry is None:
                return None
            if not role_may_read(role, entry.trust):
                raise TrustViolation(
                    f"role={role} not permitted to read trust={entry.trust.name} in tier={self.tier}"
                )
            return self._view(entry)

    def read_candidate(self, entry_id: str, *, role: str) -> MemoryEntry | None:
        with self._lock:
            entry = self._candidate.get(entry_id)
            if entry is None:
                return None
            if not role_may_read(role, entry.trust):
                raise TrustViolation(
                    f"role={role} not permitted to read trust={entry.trust.name} in tier={self.tier}"
                )
            return self._view(entry)

    def iter_live(self, *, role: str) -> Iterable[MemoryEntry]:
        with self._lock:
            for entry in list(self._live.values()):
                if role_may_read(role, entry.trust):
                    yield self._view(entry)

    # ---- promotion ------------------------------------------------------

    def promote(
        self,
        entry_ids: list[str],
        *,
        precondition_hash: str,
        why_id: str,
        producer_role: str | None = None,
        candidate_postimage: dict[str, str] | None = None,
    ) -> list[MemoryEntry]:
        """Atomically move named candidate entries into live.

        Raises:
          PromotionPreconditionFailure — precondition_hash != current live_hash(),
                                        OR a candidate's content no longer matches
                                        the Auditor-signed post-image (C1),
                                        OR an entry has no signed post-image when
                                        one is required.
          TrustViolation              — promotion goes the wrong way through the lattice.
          TierConsumerViolation       — producer_role lacks authority to write to
                                        this tier's consumer tier (P4 invariant).
          KeyError                    — a named entry_id has no candidate.

        ``candidate_postimage`` maps entry_id -> the ``content_hash`` the
        Auditor signed in the why-doc. When provided (the Coordinator always
        provides it), each candidate's current content is re-checked against
        it under the same lock as the live-hash precondition — a true
        post-image CAS (C1 cycle-10). Direct callers (tests/primitives) may
        omit it for the legacy live-hash-only behavior.

        M2 (cycle-10): the batch is **all-or-nothing**. Every entry_id is
        fully validated (existence + lattice legality + post-image) BEFORE
        any mutation to ``self._live`` / ``self._candidate``. A mid-batch
        raise can no longer leave a half-applied PROMOTED ghost in live with
        the candidate stranded on disk (the cycle-2 P1 class).

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

            # --- validate pass: NO mutation may happen in this loop (M2) ---
            now = time.time()
            staged: list[tuple[str, MemoryEntry, MemoryEntry]] = []  # (id, promoted_cand, cand)
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
                # C1 (cycle-10): post-image CAS. The live-hash precondition
                # above only proves the LIVE store didn't move; it says nothing
                # about whether the candidate still holds the bytes the Auditor
                # signed. Re-check the candidate CONTENT here so a tamper in the
                # sign->promote window (incl. the mark_verified() step the loop
                # itself runs) cannot launder unsigned content into live.
                if candidate_postimage is not None:
                    signed = candidate_postimage.get(entry_id)
                    if signed is None:
                        raise PromotionPreconditionFailure(
                            f"no auditor-signed post-image for candidate "
                            f"{entry_id}; refusing to promote an unsigned entry"
                        )
                    actual = content_hash(cand)
                    if actual != signed:
                        raise PromotionPreconditionFailure(
                            f"candidate {entry_id} content changed since the "
                            f"auditor signed: signed={signed[:24]}... "
                            f"now={actual[:24]}... (cycle-10 C1 post-image CAS)"
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
                staged.append((entry_id, promoted_cand, cand))

            # --- commit pass: batch fully validated; no logical raise here ---
            promoted: list[MemoryEntry] = []
            for entry_id, promoted_cand, cand in staged:
                self._live[entry_id] = promoted_cand
                promoted.append(promoted_cand)
                # Move out of active candidates into the archive for audit.
                self._archive_candidate(cand, why_id)
                self._candidate.pop(entry_id, None)

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
                # M1 (cycle-10): gate the CANDIDATE->VERIFIED bump on the SAME
                # lattice-legality predicate promote() uses. Without this,
                # mark_verified was a second trust-mutating door that ignored
                # valid_promotion: a DEPRECATED candidate (trust=-1, so the
                # `>= VERIFIED` short-circuit above does NOT fire) was bumped
                # unconditionally to VERIFIED and then accepted by promote() —
                # laundering a terminal-DEPRECATED entry back up to PROMOTED.
                # DEPRECATED is terminal everywhere or it is terminal nowhere.
                if not valid_promotion(cand.trust, TrustLevel.VERIFIED):
                    raise TrustViolation(
                        f"cannot verify candidate at trust={cand.trust.name} "
                        f"in tier={self.tier} for entry={eid} "
                        f"(DEPRECATED is terminal; mark_verified honors the "
                        f"lattice exactly as promote() does — cycle-10 M1)"
                    )
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

    def has_candidate(self, entry_id: str) -> bool:
        """F2 (cycle-7) API surface: public 'does this id have a candidate'
        check, so callers don't reach into the private `_candidate` dict.
        The Coordinator's tier-mismatch cleanup uses this to determine
        which tier(s) actually need a discard call."""
        with self._lock:
            return entry_id in self._candidate

    def candidate_ids(self) -> set[str]:
        """G2 (cycle-8) API surface: snapshot of currently-present candidate
        IDs. The Coordinator takes one of these per tier BEFORE running
        the Librarian so a TierMismatch cleanup can distinguish 'IDs this
        iteration introduced' from 'IDs a prior iteration legitimately
        wrote' — preventing over-discard of pre-existing candidates that
        happen to share an entry_id (F2 regression)."""
        with self._lock:
            return set(self._candidate.keys())

    def candidates_snapshot(self) -> list[MemoryEntry]:
        """H4 (cycle-9) API surface: snapshot list of every current candidate
        entry under lock. The Coordinator's TierMismatch cleanup uses this
        to filter by writer_iteration_id (race-free vs. cycle-8's
        snapshot-diff approach). Returns a new list so callers can iterate
        safely after the lock releases.

        M4 (cycle-10): hands back deep copies, not live handles — the
        TierMismatch cleanup that consumes this only needs entry_id +
        writer_iteration_id, and a live handle let a caller mutate the store
        outside promote()."""
        with self._lock:
            return [self._view(e) for e in self._candidate.values()]

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
        # Cycle-6 fix: sanitize why_id for Windows filesystem compatibility.
        # Reason strings can contain :, =, ', and other chars that Windows
        # rejects as invalid path characters.
        safe_why = re.sub(r"[^A-Za-z0-9._-]", "_", why_id)[:80]
        stamp = int(time.time() * 1000)
        salt = uuid.uuid4().hex
        path = self._archive_dir / f"{self.tier}_{entry.entry_id}_{safe_why}_{stamp}_{salt}.json"
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

    @classmethod
    def tier_names(cls) -> tuple[str, ...]:
        """H12 (cycle-9): single source of truth for the tier names.
        Callers that need to iterate all tiers should use this instead
        of hardcoding the 5-tuple, so adding a 6th tier in the future
        doesn't silently skip cleanup/snapshot paths."""
        return tuple(cls.model_fields.keys())
