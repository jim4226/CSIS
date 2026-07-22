"""Cycle-10 regression tests — promote-integrity cluster.

Covers the findings the coordinator/memory red-team passes reproduced and
this cycle closed:

  M1  mark_verified() must not resurrect a terminal-DEPRECATED candidate.
  M2  promote() is all-or-nothing; a mid-batch raise leaves no ghost.
  M4  every read path hands back a defensive copy, not a live handle.
  M5  TierMismatch cleanup discards an unstamped, *unadvertised* cross-tier
      write (it must not trust the Librarian's self-reported manifest).
  C1  promote() re-checks the Auditor-signed candidate post-image (a true
      CAS), while tolerating the legitimate mark_verified() trust bump.
  C2  skill promotion routes through the Auditor + locked-promote chokepoint.

Each test asserts the *effect* (cycle-6 E1: a surface-event assertion that
doesn't assert the remediation effect is how a silent leak shipped).
"""
from __future__ import annotations

from pathlib import Path

import pytest

from csis.agents.auditor import TierMismatch
from csis.agents.coordinator import Coordinator, IterationResult
from csis.backends.mock import MockBackend
from csis.config import CSISConfig
from csis.contracts import MemoryEntry
from csis.memory.store import (
    MemoryStore,
    PromotionPreconditionFailure,
    TrustViolation,
    content_hash,
)
from csis.memory.trust import TrustLevel


def _mk(eid: str, content: str = "c", trust: TrustLevel = TrustLevel.CANDIDATE,
        tier: str = "episodic", writer_iteration_id: str | None = None) -> MemoryEntry:
    return MemoryEntry(
        entry_id=eid, tier=tier, content=content, trust=trust,
        why_tag="t", created_at=1.0, writer_iteration_id=writer_iteration_id,
    )


# ---- M1 -------------------------------------------------------------------


def test_m1_mark_verified_rejects_deprecated_resurrection(tmp_path: Path) -> None:
    """A DEPRECATED candidate cannot be laundered back to VERIFIED (and thence
    PROMOTED) through the second trust-mutating door."""
    s = MemoryStore("episodic", tmp_path)
    s.write_candidate(_mk("e1", trust=TrustLevel.DEPRECATED))
    with pytest.raises(TrustViolation):
        s.mark_verified(["e1"])
    # Effect: trust stayed DEPRECATED, and promote still refuses it.
    assert s.read_candidate("e1", role="auditor").trust == TrustLevel.DEPRECATED
    with pytest.raises(TrustViolation):
        s.promote(["e1"], precondition_hash=s.live_hash(), why_id="w")


def test_m1_mark_verified_still_upgrades_a_normal_candidate(tmp_path: Path) -> None:
    s = MemoryStore("episodic", tmp_path)
    s.write_candidate(_mk("e1", trust=TrustLevel.CANDIDATE))
    out = s.mark_verified(["e1"])
    assert out[0].trust == TrustLevel.VERIFIED


# ---- M2 -------------------------------------------------------------------


def test_m2_promote_atomic_on_missing_id(tmp_path: Path) -> None:
    """A KeyError on a later id must leave NO half-applied PROMOTED ghost and
    no memory/disk divergence."""
    s = MemoryStore("episodic", tmp_path)
    s.write_candidate(_mk("e-good", trust=TrustLevel.CANDIDATE))
    with pytest.raises(KeyError):
        s.promote(["e-good", "e-missing"], precondition_hash=s.live_hash(), why_id="w")
    # Effect: e-good is NOT in live (in memory or on disk), and is still a candidate.
    assert list(s.iter_live(role="auditor")) == []
    reopened = MemoryStore("episodic", tmp_path)
    assert list(reopened.iter_live(role="auditor")) == []
    assert "e-good" in reopened.candidate_ids()


def test_m2_promote_atomic_on_trust_violation(tmp_path: Path) -> None:
    """A TrustViolation on a later id must not strand earlier ids in live."""
    s = MemoryStore("episodic", tmp_path)
    s.write_candidate(_mk("e-good", trust=TrustLevel.CANDIDATE))
    s.write_candidate(_mk("e-dep", trust=TrustLevel.DEPRECATED))
    with pytest.raises(TrustViolation):
        s.promote(["e-good", "e-dep"], precondition_hash=s.live_hash(), why_id="w")
    assert list(s.iter_live(role="auditor")) == []
    reopened = MemoryStore("episodic", tmp_path)
    assert list(reopened.iter_live(role="auditor")) == []


# ---- M4 -------------------------------------------------------------------


def test_m4_reads_return_defensive_copies(tmp_path: Path) -> None:
    """Mutating a returned entry must not write through into the store."""
    s = MemoryStore("episodic", tmp_path)
    e = _mk("e1", trust=TrustLevel.CANDIDATE)
    e.extra["k"] = "orig"
    s.write_candidate(e)
    s.mark_verified(["e1"])
    s.promote(["e1"], precondition_hash=s.live_hash(), why_id="w")

    ref = s.read_live("e1", role="auditor")
    ref.extra["poison"] = "x"
    assert "poison" not in s.read_live("e1", role="auditor").extra

    cref = next(iter(s.candidates_snapshot()), None)
    # (candidate archived after promote; re-add one to exercise candidate reads)
    s.write_candidate(_mk("e2", trust=TrustLevel.CANDIDATE))
    c = s.read_candidate("e2", role="auditor")
    c.extra["poison"] = "y"
    assert "poison" not in s.read_candidate("e2", role="auditor").extra
    snap = s.candidates_snapshot()
    snap[0].extra["poison"] = "z"
    assert all("poison" not in x.extra for x in s.candidates_snapshot())


# ---- C1 -------------------------------------------------------------------


def test_c1_post_image_rejects_tampered_candidate(tmp_path: Path) -> None:
    """A candidate whose content changed since the Auditor signed must be
    refused at promote — the live-hash precondition alone does not catch it."""
    s = MemoryStore("episodic", tmp_path)
    s.write_candidate(_mk("e1", content="APPROVED"))
    signed = content_hash(s.read_candidate("e1", role="auditor"))
    s.mark_verified(["e1"])
    # Tamper in the sign->promote window.
    s.write_candidate(_mk("e1", content="TAMPERED", trust=TrustLevel.VERIFIED))
    with pytest.raises(PromotionPreconditionFailure):
        s.promote(["e1"], precondition_hash=s.live_hash(), why_id="w",
                  candidate_postimage={"e1": signed})
    assert list(s.iter_live(role="auditor")) == []


def test_c1_legit_mark_verified_bump_still_promotes(tmp_path: Path) -> None:
    """The legitimate CANDIDATE->VERIFIED bump must NOT be a false post-image
    mismatch (content_hash excludes the lattice bookkeeping fields)."""
    s = MemoryStore("episodic", tmp_path)
    s.write_candidate(_mk("e1", content="APPROVED"))
    signed = content_hash(s.read_candidate("e1", role="auditor"))
    s.mark_verified(["e1"])  # bumps trust -> would break a naive full-dump hash
    promoted = s.promote(["e1"], precondition_hash=s.live_hash(), why_id="w",
                         candidate_postimage={"e1": signed})
    assert promoted[0].trust == TrustLevel.PROMOTED


def test_c1_promote_refuses_entry_without_signed_postimage(tmp_path: Path) -> None:
    s = MemoryStore("episodic", tmp_path)
    s.write_candidate(_mk("e1", content="X"))
    s.mark_verified(["e1"])
    with pytest.raises(PromotionPreconditionFailure):
        s.promote(["e1"], precondition_hash=s.live_hash(), why_id="w",
                  candidate_postimage={})  # empty -> no signature for e1


# ---- M5 -------------------------------------------------------------------


def _coord(tmp_path: Path) -> Coordinator:
    from tests._helpers import wrap_for_test
    cfg = CSISConfig.for_tests(tmp_path)
    backend = MockBackend()
    backend.set_model_id(cfg.builder_checkpoint, "mock-opus")
    backend.set_model_id(cfg.auditor_checkpoint, "mock-sonnet")
    return Coordinator(config=cfg, backend=wrap_for_test(backend, tmp_path))


def test_m5_cleanup_discards_unstamped_unadvertised_cross_tier_write(tmp_path: Path) -> None:
    """The TierMismatch cleanup must discard a hidden, unstamped candidate a
    buggy Librarian wrote to a non-target tier WITHOUT advertising it — the
    'wrote to a tier and lied' threat. It must not depend on the manifest."""
    coord = _coord(tmp_path)
    iteration_id = "iter-m5"

    # Advertised, stamped candidate in the target tier.
    target = coord.hierarchy.tier("episodic")
    adv = _mk("e-adv", tier="episodic", writer_iteration_id=iteration_id)
    target.write_candidate(adv, writer_iteration_id=iteration_id)

    # HIDDEN, unstamped candidate in a DIFFERENT tier, NOT advertised.
    hidden_store = coord.hierarchy.tier("semantic")
    hidden_store.write_candidate(_mk("e-hidden", tier="semantic"))  # no stamp

    # A pre-existing, unstamped, legitimate candidate that must NOT be over-discarded.
    pre = coord.hierarchy.tier("procedural")
    pre.write_candidate(_mk("e-pre", tier="procedural"))
    pre_ids = {name: {e.entry_id: content_hash(e)
                      for e in coord.hierarchy.tier(name).candidates_snapshot()}
               for name in coord.hierarchy.__class__.tier_names()}
    # e-hidden was written AFTER the snapshot above only conceptually; emulate
    # the real ordering: pre-snapshot must contain e-pre but not e-hidden.
    pre_ids["semantic"] = {}  # e-hidden is "introduced this iteration"

    result = IterationResult(iteration_id=iteration_id)
    exc = TierMismatch("lied", claimed_tier="episodic", target_tier="episodic")
    coord._tier_mismatch_cleanup(exc, [adv], iteration_id, pre_ids, result)

    # Effect: advertised + hidden both gone; the pre-existing one survives.
    assert not target.has_candidate("e-adv"), "advertised candidate must be discarded"
    assert not hidden_store.has_candidate("e-hidden"), "hidden unstamped write must be discarded (M5)"
    assert pre.has_candidate("e-pre"), "pre-existing legit candidate must NOT be over-discarded"


def test_m5_pre_existing_unstamped_candidate_not_discarded(tmp_path: Path) -> None:
    """A same-id unstamped candidate that pre-existed this iteration must
    survive (no cycle-7 F2 over-discard regression)."""
    coord = _coord(tmp_path)
    iteration_id = "iter-m5b"
    store = coord.hierarchy.tier("semantic")
    store.write_candidate(_mk("e-old", tier="semantic"))  # pre-existing, unstamped
    pre_ids = {name: {e.entry_id: content_hash(e)
                      for e in coord.hierarchy.tier(name).candidates_snapshot()}
               for name in coord.hierarchy.__class__.tier_names()}
    assert "e-old" in pre_ids["semantic"]
    result = IterationResult(iteration_id=iteration_id)
    exc = TierMismatch("x", claimed_tier="episodic", target_tier="episodic")
    coord._tier_mismatch_cleanup(exc, [], iteration_id, pre_ids, result)
    assert store.has_candidate("e-old"), "pre-existing unstamped candidate must survive"


# ---- C2 -------------------------------------------------------------------


def test_c2_promote_skill_emits_procedural_why_doc(tmp_path: Path) -> None:
    """promote_skill must produce its OWN auditor why-doc for the procedural
    tier (not borrow an unrelated iteration's) and post-image-check the skill."""
    coord = _coord(tmp_path)
    from csis.contracts import Artifact, Plan, VerifierCertificate, GraderResult, CriticFinding

    plan = Plan(plan_id="p", frontier_item="f", hypothesis="h",
                falsification_condition="x")
    artifact = Artifact(artifact_id="a", plan_id="p", kind="skill",
                        body="def helper(): pass\n", body_hash="sha256:zz",
                        extra={"is_skill": True})
    cert = VerifierCertificate(
        cert_id="c", plan_id="p", artifact_id="a", artifact_hash="sha256:zz",
        builder_checkpoint="mock-opus", verifier_checkpoint="mock-sonnet",
        grader_results=[GraderResult(grader="g", passed=True)],
        critic_findings=[CriticFinding(attempt="t", falsified=False)],
        passed=True, signed_at=1.0,
    )
    from csis.improvement.skill_library import consolidate_skill, stats as sstats
    skill_entries = consolidate_skill(
        hierarchy=coord.hierarchy, tier_guard=coord.tier_guard,
        plan=plan, artifact=artifact, cert=cert,
    )
    promoted = coord.promote_skill(
        plan=plan, artifact=artifact, cert=cert, skill_entries=skill_entries,
    )
    assert len(promoted) == 1
    assert sstats(coord.hierarchy).total_promoted == 1
    procedural_why = [
        e for e in coord.event_log
        if e.event.actor == "auditor" and e.event.kind == "auditor.signed"
        and "procedural" in (e.event.payload.get("tier_decisions") or {})
    ]
    assert procedural_why, "skill promotion must carry its own procedural why-doc"
