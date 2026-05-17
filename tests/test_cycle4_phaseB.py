"""Cycle-4 Phase B regression tests: C6, C7, C9, C11."""
from __future__ import annotations

import threading
import time
from pathlib import Path

import pytest

from csis.agents.auditor import TierMismatch, _build_diff, write_why_doc
from csis.agents.base import AgentContext, Role
from csis.backends.mock import MockBackend
from csis.contracts import (
    Artifact,
    GraderResult,
    MemoryEntry,
    Plan,
    VerifierCertificate,
)
from csis.memory.store import MemoryHierarchy
from csis.memory.trust import TrustLevel
from csis.safety.fuzzer import SafetyFuzzer
from csis.substrate.capability import CapabilityTier


def _entry(eid: str, tier: str = "episodic", content: str = "claim") -> MemoryEntry:
    return MemoryEntry(
        entry_id=eid, tier=tier, content=content,  # type: ignore[arg-type]
        trust=TrustLevel.CANDIDATE, why_tag="t", created_at=time.time(),
    )


# ---- C6 — entry.tier vs target_tier mismatch raises ---------------------


def test_C6_build_diff_rejects_tier_mismatch(tmp_path: Path) -> None:
    h = MemoryHierarchy.open(tmp_path)
    store = h.episodic
    # Candidate's tier says "causal" but target is "episodic" → bug.
    cand = _entry("e", tier="causal")
    with pytest.raises(TierMismatch):
        _build_diff(store=store, target_tier="episodic", candidate_entries=[cand])


def test_C6_build_diff_uses_entry_tier_in_delta(tmp_path: Path) -> None:
    """When tiers match, the EntryDelta and tier_counts use entry.tier
    (so a future multi-tier consolidation path remains truthful)."""
    h = MemoryHierarchy.open(tmp_path)
    store = h.semantic
    cand = _entry("s", tier="semantic")
    diff = _build_diff(store=store, target_tier="semantic", candidate_entries=[cand])
    assert diff.deltas[0].tier == "semantic"
    assert diff.tier_counts == {"semantic": 1}


# ---- C7 — TOCTOU-safe live snapshot -------------------------------------


def test_C7_live_snapshot_returns_consistent_pair(tmp_path: Path) -> None:
    """live_snapshot() returns (hash, frozen_dict) atomically. The hash
    must equal canonical_json_hash of the dict."""
    h = MemoryHierarchy.open(tmp_path)
    store = h.episodic
    # Seed live with one entry so the snapshot has content.
    seed = _entry("seed")
    store.write_candidate(seed)
    store.promote([seed.entry_id], precondition_hash=store.live_hash(), why_id="why-seed")

    h2, snap = store.live_snapshot()
    assert h2 == store.live_hash()
    assert "seed" in snap


def test_C7_build_diff_against_frozen_snapshot_immune_to_parallel_promote(tmp_path: Path) -> None:
    """The diff must reflect the snapshot it was given, not the live
    store's current state. A parallel write between snapshot and
    _build_diff must NOT affect the diff's kind/live_hash fields."""
    h = MemoryHierarchy.open(tmp_path)
    store = h.episodic

    cand = _entry("racy")
    diff_inputs = [cand]
    # Take the snapshot WITH cand absent.
    _, frozen = store.live_snapshot()

    # Simulate a parallel iteration that promotes a different entry with
    # the SAME id between snapshot and _build_diff.
    intruder = _entry("racy", content="intruder content")
    store.write_candidate(intruder)
    store.promote([intruder.entry_id], precondition_hash=store.live_hash(), why_id="why-intruder")

    # Now _build_diff is called with the frozen snapshot (cand absent at
    # snapshot time), even though the live store now has the intruder.
    diff = _build_diff(
        store=store, target_tier="episodic",
        candidate_entries=diff_inputs, live_snapshot=frozen,
    )
    # The diff sees the snapshot, so "racy" is recorded as add (not mod).
    assert diff.deltas[0].kind == "add"
    assert diff.deltas[0].live_hash is None


# ---- C9 — fuzzer doesn't pollute Tripwires.fired() ----------------------


def test_C9_fuzz_pass_does_not_grow_unbounded_history() -> None:
    """Running the fuzzer N times on the default corpus must NOT
    accumulate history. Phase A added scan_text_no_history; Phase B
    test confirms the fuzzer uses it."""
    fz = SafetyFuzzer()
    initial = len(fz.tripwires.history())
    for _ in range(50):
        fz.check()
    final = len(fz.tripwires.history())
    assert final == initial, (
        f"fuzzer is polluting Tripwires.history(): "
        f"initial={initial} after_50_passes={final}"
    )


def test_C9_fuzz_does_not_flag_fired_on_operator_tripwires() -> None:
    """An operator's Tripwires instance injected into the fuzzer must
    not have `fired()` return True purely because the fuzzer scanned it."""
    from csis.safety.tripwires import Tripwires

    op_tw = Tripwires()
    assert not op_tw.fired()
    fz = SafetyFuzzer(tripwires=op_tw)
    for _ in range(10):
        fz.check()
    assert not op_tw.fired(), (
        f"operator's Tripwires.fired() == True after fuzz, polluting state. "
        f"history len={len(op_tw.history())}"
    )


# ---- C11 — different live state → different diff_against_hash -----------


def _full_iter(coord, frontier: str) -> None:
    coord.run_iteration(frontier_item=frontier)


def _make_coord(tmp_path):
    from csis.agents.coordinator import Coordinator
    from csis.config import CSISConfig

    cfg = CSISConfig.for_tests(tmp_path)
    backend = MockBackend()
    backend.set_model_id(cfg.builder_checkpoint, "mock-opus")
    backend.set_model_id(cfg.auditor_checkpoint, "mock-sonnet")
    backend.set_tools(cfg.builder_checkpoint, ["x"])
    backend.set_tools(cfg.auditor_checkpoint, ["y"])
    backend.script(
        "researcher", cfg.builder_checkpoint,
        '{"plan_id":"p","frontier_item":"f","hypothesis":"x",'
        '"falsification_condition":"y","budget":{"time_s":1,"tokens":10},'
        '"tier":"T0","tool_calls_planned":[]}',
    )
    backend.script(
        "builder", cfg.builder_checkpoint,
        '{"artifact_id":"a","plan_id":"p","kind":"patch","body":"# x\\n",'
        '"body_hash":"sha256:zz","sandbox_logs":[],'
        '"extra":{"tests_pass":true,"lint_clean":true,"type_clean":true,'
        '"coverage_delta":0.0,"perf_ratio":1.0}}',
    )
    backend.script("critic", cfg.auditor_checkpoint,
        '[{"attempt":"a","falsified":false},'
        '{"attempt":"b","falsified":false},'
        '{"attempt":"c","falsified":false}]')
    from tests._helpers import wrap_for_test
    return Coordinator(config=cfg, backend=wrap_for_test(backend, tmp_path))


def test_C11_serial_iterations_have_distinct_diff_baselines(tmp_path: Path) -> None:
    """Two serial promotions move the live store; their why-docs'
    diff_against_hash MUST differ (no shared baseline lying about
    forensic replay)."""
    coord = _make_coord(tmp_path)
    res1 = coord.run_iteration(frontier_item="first")
    assert res1.outcome == "promoted", res1.outcome
    res2 = coord.run_iteration(frontier_item="second")
    assert res2.outcome == "promoted", res2.outcome

    why1, why2 = res1.why, res2.why
    assert why1 is not None and why2 is not None
    assert why1.diff_against_hash != why2.diff_against_hash, (
        f"diff_against_hash collision across promoting iterations: "
        f"{why1.diff_against_hash[:24]}... = {why2.diff_against_hash[:24]}..."
    )
