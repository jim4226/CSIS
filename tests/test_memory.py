"""Memory + trust + hash-preconditioned promotion tests.

Red-team findings covered:
  F2 — TOCTOU between sign and promote (precondition rejection under change)
  F3 — atomicity assumption (hash precondition is the source of truth)
  F5 — Librarian-as-laundering (write-tier transitive check)
"""
from __future__ import annotations

import time
import uuid
from pathlib import Path

import pytest

from csis.contracts import MemoryEntry
from csis.memory.store import (
    MemoryHierarchy,
    MemoryStore,
    PromotionPreconditionFailure,
    TrustViolation,
)
from csis.memory.trust import (
    READ_DEFAULTS,
    TrustLevel,
    role_may_read,
    valid_promotion,
)
from csis.safety.tier_guard import TierGuard


# ---- trust lattice ------------------------------------------------------


def test_trust_level_ordering() -> None:
    assert TrustLevel.RAW < TrustLevel.UNTRUSTED < TrustLevel.CANDIDATE < TrustLevel.VERIFIED < TrustLevel.PROMOTED


def test_valid_promotion_upward_only() -> None:
    assert valid_promotion(TrustLevel.UNTRUSTED, TrustLevel.CANDIDATE)
    assert valid_promotion(TrustLevel.CANDIDATE, TrustLevel.PROMOTED)
    assert not valid_promotion(TrustLevel.PROMOTED, TrustLevel.CANDIDATE)  # downgrade rejected
    assert not valid_promotion(TrustLevel.DEPRECATED, TrustLevel.VERIFIED)  # terminal


def test_role_read_defaults() -> None:
    assert role_may_read("researcher", TrustLevel.UNTRUSTED)
    # F8-adjacent: builder shouldn't read untrusted directly
    assert not role_may_read("builder", TrustLevel.UNTRUSTED)
    assert role_may_read("auditor", TrustLevel.DEPRECATED)
    assert not role_may_read("researcher", TrustLevel.DEPRECATED)


def test_can_cite_as_ground_truth() -> None:
    assert TrustLevel.can_cite_as_ground_truth(TrustLevel.VERIFIED)
    assert TrustLevel.can_cite_as_ground_truth(TrustLevel.PROMOTED)
    assert not TrustLevel.can_cite_as_ground_truth(TrustLevel.CANDIDATE)


# ---- memory store: write/read/promote ----------------------------------


def _entry(tier: str = "episodic", trust: TrustLevel = TrustLevel.CANDIDATE) -> MemoryEntry:
    return MemoryEntry(
        entry_id=f"e-{uuid.uuid4().hex[:8]}",
        tier=tier,  # type: ignore[arg-type]
        content="some claim",
        trust=trust,
        why_tag="researcher-v1: derived from frontier item X",
        created_at=time.time(),
    )


def test_store_roundtrip(tmp_path: Path) -> None:
    """Per cycle-2 P1+P10 fix: promote() bumps trust to PROMOTED atomically."""
    store = MemoryStore("episodic", tmp_path)
    e = _entry()
    store.write_candidate(e)
    pre_hash = store.live_hash()
    why_id = "why-test"

    promoted = store.promote([e.entry_id], precondition_hash=pre_hash, why_id=why_id)
    assert len(promoted) == 1
    assert promoted[0].trust == TrustLevel.PROMOTED
    assert promoted[0].promoted_at is not None
    # Re-open from disk — live should still have it at PROMOTED trust.
    reopened = MemoryStore("episodic", tmp_path)
    read_back = reopened.read_live(e.entry_id, role="auditor")
    assert read_back is not None
    assert read_back.entry_id == e.entry_id
    assert read_back.trust == TrustLevel.PROMOTED


def test_promote_rejects_stale_precondition(tmp_path: Path) -> None:
    """F2/F3: if the live store moves between why-doc sign and promote(),
    the promote must fail rather than silently overwrite."""
    store = MemoryStore("episodic", tmp_path)
    e1 = _entry()
    e2 = _entry()
    store.write_candidate(e1)
    store.write_candidate(e2)

    # Auditor records the pre-hash (empty live store).
    pre_hash = store.live_hash()
    # Another thread sneaks in a promote first.
    store.promote([e1.entry_id], precondition_hash=pre_hash, why_id="why-other")

    # Now the original auditor's promote tries with the stale pre_hash —
    # must fail.
    with pytest.raises(PromotionPreconditionFailure):
        store.promote([e2.entry_id], precondition_hash=pre_hash, why_id="why-late")


def test_repromote_over_existing_live_entry_rejected(tmp_path: Path) -> None:
    """Once an entry is PROMOTED in live, a second promotion of a new
    candidate with the same entry_id must fail — PROMOTED -> PROMOTED is
    not a strict-greater transition. Demote-then-rewrite goes through
    deprecate_live + new entry_id (the audit-trail path)."""
    store = MemoryStore("episodic", tmp_path)
    first = _entry()
    store.write_candidate(first)
    store.promote(
        [first.entry_id], precondition_hash=store.live_hash(), why_id="why-first",
    )
    # Try to overwrite via a new candidate with the same id.
    overwrite = _entry()
    overwrite = overwrite.model_copy(update={"entry_id": first.entry_id})
    store.write_candidate(overwrite)
    with pytest.raises(TrustViolation):
        store.promote(
            [overwrite.entry_id], precondition_hash=store.live_hash(), why_id="why-bad",
        )


def test_read_blocks_unauthorized_role(tmp_path: Path) -> None:
    """After deprecate_live(), only Auditor may read the entry (per §6.2)."""
    store = MemoryStore("episodic", tmp_path)
    e = _entry()
    store.write_candidate(e)
    store.promote([e.entry_id], precondition_hash=store.live_hash(), why_id="why-keep")
    # Now deprecate the live entry. Researcher cannot read DEPRECATED.
    store.deprecate_live(e.entry_id, reason="superseded by new evidence")
    with pytest.raises(TrustViolation):
        store.read_live(e.entry_id, role="researcher")
    # Auditor still can.
    assert store.read_live(e.entry_id, role="auditor") is not None


def test_promote_rejects_deprecated_candidate(tmp_path: Path) -> None:
    """Cycle-2 invariant: promote() refuses to resurrect a DEPRECATED
    candidate. DEPRECATED is terminal."""
    store = MemoryStore("episodic", tmp_path)
    dep = _entry(trust=TrustLevel.DEPRECATED)
    store.write_candidate(dep)
    with pytest.raises(TrustViolation):
        store.promote([dep.entry_id], precondition_hash=store.live_hash(), why_id="why-bad")


def test_mark_verified_bumps_candidate_only(tmp_path: Path) -> None:
    """P10 fix: mark_verified bumps CANDIDATE -> VERIFIED on candidate side
    so downstream can distinguish 'verified but stale precondition' from
    'never verified.'"""
    store = MemoryStore("episodic", tmp_path)
    e = _entry()
    store.write_candidate(e)
    [v] = store.mark_verified([e.entry_id])
    assert v.trust == TrustLevel.VERIFIED
    # idempotent
    [v2] = store.mark_verified([e.entry_id])
    assert v2.trust == TrustLevel.VERIFIED


def test_hierarchy_open_creates_all_tiers(tmp_path: Path) -> None:
    h = MemoryHierarchy.open(tmp_path)
    for name in ("working", "episodic", "semantic", "procedural", "causal"):
        assert h.tier(name).tier == name


# ---- F5 — Librarian-as-laundering -------------------------------------


def test_tier_guard_blocks_t0_writer_to_procedural() -> None:
    """A T0 actor cannot write directly to procedural — that store's consumer
    is T1 Builder, and a write there influences code execution."""
    guard = TierGuard()
    ok, reason = guard.write_tier("researcher", "procedural")
    assert not ok
    assert "consumer tier" in reason


def test_tier_guard_allows_librarian_to_working() -> None:
    guard = TierGuard()
    ok, _ = guard.write_tier("librarian", "working")
    assert ok


def test_tier_guard_allows_builder_to_procedural() -> None:
    guard = TierGuard()
    ok, _ = guard.write_tier("builder", "procedural")
    assert ok
