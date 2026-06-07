"""Regression tests for the tiered audit pre-check.

The security-guidance plugin (Claude Code Week 22, May 25-29 2026) introduced
a tiered review pattern: fast pattern check → per-turn model review → deeper
agentic review on commit. fast_audit_check() is the CSIS equivalent of that
first tier: a cheap, no-LLM structural validation that runs before the
write_why_doc() call, catching obvious invariant violations before wasting
tokens on an LLM pass.

Theme: #7 Curiosity / frontier-item generation (automated red-teaming) +
       #2 Trust + verification

Changes covered:
  - fast_audit_check() added to csis/agents/auditor.py
  - Coordinator.run_iteration() calls fast_audit_check() before write_why_doc()
    and rolls back with auditor.precheck.failed event on violations
"""
from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest

from csis.agents.auditor import fast_audit_check
from csis.agents.coordinator import Coordinator
from csis.backends.mock import MockBackend
from csis.config import CSISConfig
from csis.contracts import MemoryEntry, VerifierCertificate
from csis.substrate.capability import CapabilityTier

from tests._helpers import wrap_for_test


# ---- helpers ---------------------------------------------------------------


def _cert(passed: bool = True) -> VerifierCertificate:
    import time
    return VerifierCertificate(
        cert_id="c-test",
        plan_id="p-test",
        artifact_id="a-test",
        artifact_hash="sha256:abc",
        builder_checkpoint="mock-alpha",
        verifier_checkpoint="mock-beta",
        grader_results=[],
        critic_findings=[],
        passed=passed,
        signed_at=time.time(),
        notes="",
    )


def _entry(entry_id: str = "e-test", tier: str = "episodic") -> MemoryEntry:
    import time
    from csis.memory.trust import TrustLevel
    return MemoryEntry(
        entry_id=entry_id,
        tier=tier,
        content="stub content",
        trust=TrustLevel.CANDIDATE,
        why_tag="test",
        created_at=time.time(),
    )


# ---- fast_audit_check unit tests ------------------------------------------


def test_fast_audit_check_passes_clean_inputs() -> None:
    violations = fast_audit_check(_cert(passed=True), [_entry(tier="episodic")], "episodic")
    assert violations == []


def test_fast_audit_check_catches_failed_cert() -> None:
    violations = fast_audit_check(_cert(passed=False), [_entry(tier="episodic")], "episodic")
    assert any("passed=False" in v for v in violations)
    assert any("c-test" in v for v in violations)


def test_fast_audit_check_catches_empty_candidates() -> None:
    violations = fast_audit_check(_cert(passed=True), [], "episodic")
    assert any("empty" in v for v in violations)


def test_fast_audit_check_ignores_tier_mismatch() -> None:
    """Tier mismatches are intentionally left to _build_diff() (cycle-6 E1 fix).
    fast_audit_check must not intercept them so the existing TierMismatch
    cleanup path continues to own the full rollback machinery."""
    entry = _entry(tier="episodic")
    violations = fast_audit_check(_cert(passed=True), [entry], "semantic")
    # No violation — the tier check is downstream in _build_diff().
    assert violations == []


def test_fast_audit_check_reports_all_violations() -> None:
    """A failed cert AND empty candidates both appear in violations."""
    violations = fast_audit_check(_cert(passed=False), [], "episodic")
    assert len(violations) >= 2
    texts = " ".join(violations)
    assert "passed=False" in texts
    assert "empty" in texts


# ---- Coordinator integration: rolls back on precheck failure --------------


def _wire_backend(cfg: CSISConfig) -> MockBackend:
    backend = MockBackend()
    backend.set_model_id(cfg.builder_checkpoint, "mock-opus")
    backend.set_model_id(cfg.auditor_checkpoint, "mock-sonnet")
    backend.script(
        "researcher", cfg.builder_checkpoint,
        '{"plan_id":"p","frontier_item":"x","hypothesis":"benign",'
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
    backend.script(
        "critic", cfg.auditor_checkpoint,
        '[{"attempt":"a","falsified":false},'
        '{"attempt":"b","falsified":false},'
        '{"attempt":"c","falsified":false}]',
    )
    return backend


def test_coordinator_rolls_back_on_empty_candidates(tmp_path: Path) -> None:
    """When consolidate_to_candidates returns [], the precheck fires, rolls back,
    and emits auditor.precheck.failed before any write_why_doc() call."""
    cfg = CSISConfig.for_tests(tmp_path)
    backend = _wire_backend(cfg)
    coord = Coordinator(config=cfg, backend=wrap_for_test(backend, tmp_path))

    import csis.agents.coordinator as coord_mod

    with patch.object(coord_mod, "consolidate_to_candidates", return_value=[]):
        res = coord.run_iteration(frontier_item="precheck-empty-test")

    assert res.outcome.startswith("rolled-back:audit-precheck")
    precheck_events = [
        s for s in coord.event_log if s.event.kind == "auditor.precheck.failed"
    ]
    assert precheck_events, "expected auditor.precheck.failed event in log"
    payload = precheck_events[0].event.payload
    assert "violations" in payload
    assert any("empty" in v for v in payload["violations"])


def test_coordinator_no_precheck_event_on_clean_iteration(tmp_path: Path) -> None:
    """A normal successful iteration emits NO auditor.precheck.failed event."""
    cfg = CSISConfig.for_tests(tmp_path)
    backend = _wire_backend(cfg)
    coord = Coordinator(config=cfg, backend=wrap_for_test(backend, tmp_path))

    res = coord.run_iteration(frontier_item="normal-iteration")

    precheck_events = [
        s for s in coord.event_log if s.event.kind == "auditor.precheck.failed"
    ]
    assert not precheck_events, (
        f"unexpected auditor.precheck.failed on clean iteration: {precheck_events}"
    )
    # A clean iteration should reach promoted or at least not be rolled back by precheck.
    assert "audit-precheck" not in res.outcome
