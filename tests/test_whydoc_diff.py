"""Structured WhyDocDiff tests (synthesis recommendation #2)."""
from __future__ import annotations

import time
from pathlib import Path

from csis.agents.auditor import _build_diff, write_why_doc
from csis.agents.base import AgentContext, Role
from csis.backends.mock import MockBackend
from csis.contracts import (
    Artifact,
    EntryDelta,
    GraderResult,
    MemoryEntry,
    Plan,
    VerifierCertificate,
    WhyDoc,
    WhyDocDiff,
)
from csis.memory.store import MemoryHierarchy
from csis.memory.trust import TrustLevel
from csis.substrate.capability import CapabilityTier


def _entry(eid: str, content: str = "claim") -> MemoryEntry:
    return MemoryEntry(
        entry_id=eid, tier="episodic", content=content,
        trust=TrustLevel.CANDIDATE, why_tag="t", created_at=time.time(),
    )


def test_whydoc_diff_distinguishes_add_vs_mod(tmp_path: Path) -> None:
    h = MemoryHierarchy.open(tmp_path)
    store = h.episodic
    # Pre-populate live with one entry so a same-id candidate counts as mod.
    pre = _entry("existing", "old content")
    store.write_candidate(pre)
    store.promote([pre.entry_id], precondition_hash=store.live_hash(), why_id="why-seed")

    # Now propose two candidates: one with the existing id (mod) and one new (add).
    candidates = [
        _entry("existing", "new content"),
        _entry("brand-new", "fresh"),
    ]
    diff = _build_diff(store=store, target_tier="episodic", candidate_entries=candidates)
    assert diff.n_added == 1
    assert diff.n_modified == 1
    assert diff.tier_counts == {"episodic": 2}

    by_id = {d.entry_id: d for d in diff.deltas}
    assert by_id["existing"].kind == "mod"
    assert by_id["existing"].live_hash is not None
    assert by_id["brand-new"].kind == "add"
    assert by_id["brand-new"].live_hash is None


def test_whydoc_carries_structured_diff(tmp_path: Path) -> None:
    """write_why_doc emits a WhyDocDiff that summary references."""
    h = MemoryHierarchy.open(tmp_path)
    backend = MockBackend()
    ctx = AgentContext(role=Role.AUDITOR, checkpoint_id="beta", backend=backend)

    cands = [_entry("a"), _entry("b")]
    plan = Plan(plan_id="p", frontier_item="f", hypothesis="x", falsification_condition="y", tier=CapabilityTier.T0)
    cert = VerifierCertificate(
        cert_id="c", plan_id="p", artifact_id="a", artifact_hash="sha256:0123",
        builder_checkpoint="alpha", verifier_checkpoint="beta",
        grader_results=[GraderResult(grader="g", passed=True)],
        critic_findings=[], passed=True, signed_at=time.time(),
    )
    artifact = Artifact(
        artifact_id="a", plan_id="p", kind="patch", body="x",
        body_hash="sha256:dead", extra={},
    )

    wd = write_why_doc(
        ctx=ctx, hierarchy=h, target_tier="episodic",
        plan=plan, artifact=artifact, cert=cert, candidate_entries=cands,
    )
    assert isinstance(wd.diff, WhyDocDiff)
    assert wd.diff.n_added == 2 and wd.diff.n_modified == 0
    assert "2 added" in wd.summary
    assert wd.tier_decisions == {"episodic": "+2 (add=2 mod=0)"}


def test_entry_delta_validates_kind() -> None:
    """Kind is constrained to add/mod via the Literal type."""
    EntryDelta(entry_id="x", kind="add", tier="episodic", candidate_hash="sha256:0")
    EntryDelta(entry_id="x", kind="mod", tier="episodic", candidate_hash="sha256:0", live_hash="sha256:1")
    import pytest
    with pytest.raises(Exception):
        EntryDelta(entry_id="x", kind="delete", tier="episodic", candidate_hash="sha256:0")  # type: ignore
