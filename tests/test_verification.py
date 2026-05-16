"""Verification stack tests.

Red-team coverage:
  F1 — mock-vs-mock cross-checkpoint must be structural, not decorative
  F6 — corrupted grader: pinned source hash check
  F7 — critic incentive: seeded synthetic flaws + minimum attempts
"""
from __future__ import annotations

import time

import pytest

from csis.backends.mock import MockBackend
from csis.contracts import Artifact, CriticFinding, GraderResult, Plan
from csis.substrate.capability import CapabilityTier
from csis.substrate.hashing import hash_artifact
from csis.verification.certificates import (
    CrossCheckpointViolation,
    GraderDriftViolation,
    assert_cross_checkpoint,
    build_certificate,
)
from csis.verification.critic_stack import (
    CriticEvaluator,
    SeededFlaw,
    parse_critic_output,
    run_critic,
)
from csis.verification.graders import (
    GraderRegistry,
    make_default_pr_registry,
    tests_pass_grader as _tests_pass_grader,
)


# ---- helpers ------------------------------------------------------------


def _plan() -> Plan:
    return Plan(
        plan_id="p-1",
        frontier_item="test",
        hypothesis="x",
        falsification_condition="y",
        tier=CapabilityTier.T0,
    )


def _artifact(scenarios: dict | None = None, body: str = "# clean patch\n") -> Artifact:
    return Artifact(
        artifact_id="a-1",
        plan_id="p-1",
        kind="patch",
        body=body,
        body_hash=hash_artifact(body),
        extra=scenarios or {},
    )


# ---- F1 — cross-checkpoint -------------------------------------------


def test_cross_checkpoint_requires_two_distinct_components() -> None:
    same = {"checkpoint_id": "alpha", "model_id": "M", "tool_set": "T", "backend": "mock"}
    diff_only_id = {"checkpoint_id": "beta", "model_id": "M", "tool_set": "T", "backend": "mock"}
    # Only checkpoint_id differs — fails (1 < 2).
    with pytest.raises(CrossCheckpointViolation):
        assert_cross_checkpoint(same, diff_only_id, min_distinct_components=2)
    # Two distinct components — passes.
    diff_two = {"checkpoint_id": "beta", "model_id": "N", "tool_set": "T", "backend": "mock"}
    assert_cross_checkpoint(same, diff_two)  # no raise


def test_cert_rejects_same_identity() -> None:
    builder = {"checkpoint_id": "alpha", "model_id": "M", "tool_set": "T", "backend": "mock"}
    verifier = dict(builder)  # identical — must reject
    with pytest.raises(CrossCheckpointViolation):
        build_certificate(
            plan=_plan(),
            artifact=_artifact(),
            builder_identity=builder,
            verifier_identity=verifier,
            grader_results=[GraderResult(grader="g", passed=True)],
            critic_findings=[CriticFinding(attempt="x", falsified=False)] * 3,
        )


# ---- V1 graders ----------------------------------------------------------


def test_default_registry_pass_clean_artifact() -> None:
    reg = make_default_pr_registry()
    artifact = _artifact({"tests_pass": True, "lint_clean": True, "type_clean": True, "coverage_delta": 0.0, "perf_ratio": 1.0})
    results = reg.evaluate(artifact)
    assert all(r.passed for r in results), [r for r in results if not r.passed]


def test_default_registry_fails_on_test_break() -> None:
    reg = make_default_pr_registry()
    artifact = _artifact({"tests_pass": False, "lint_clean": True, "type_clean": True, "coverage_delta": 0.0, "perf_ratio": 1.0})
    results = reg.evaluate(artifact)
    assert any(r.grader == "tests_pass" and not r.passed for r in results)


def test_diff_scope_grader_blocks_grader_file_change() -> None:
    body = "diff --git a/csis/verification/graders.py b/csis/verification/graders.py\n+ removed assert\n"
    reg = make_default_pr_registry()
    results = reg.evaluate(_artifact(body=body))
    assert any(r.grader == "diff_scope" and not r.passed for r in results)


# ---- F6 — pinned grader hash check ------------------------------------


def test_pinned_grader_drift_detection() -> None:
    reg = GraderRegistry()
    reg.pin("tests_pass", _tests_pass_grader)
    ok, drifted = reg.verify_pinned_hashes()
    assert ok and not drifted
    # Simulate drift by replacing the pinned source hash with garbage.
    reg.pinned["tests_pass"].source_hash = "sha256:" + "0" * 64
    ok, drifted = reg.verify_pinned_hashes()
    assert not ok and "tests_pass" in drifted


def test_cert_build_rejects_drifted_grader() -> None:
    builder = {"checkpoint_id": "alpha", "model_id": "M", "tool_set": "T", "backend": "mock"}
    verifier = {"checkpoint_id": "beta", "model_id": "N", "tool_set": "T", "backend": "mock"}
    with pytest.raises(GraderDriftViolation):
        build_certificate(
            plan=_plan(),
            artifact=_artifact(),
            builder_identity=builder,
            verifier_identity=verifier,
            grader_results=[GraderResult(grader="g", passed=True)],
            critic_findings=[CriticFinding(attempt="x", falsified=False)] * 3,
            grader_drift=["g"],
        )


# ---- V2 critic ----------------------------------------------------------


def test_critic_parses_well_formed_array() -> None:
    text = '[{"attempt":"a","falsified":false,"detail":"d"},{"attempt":"b","falsified":true,"detail":"e"}]'
    findings = parse_critic_output(text)
    assert len(findings) == 2
    assert findings[1].falsified


def test_critic_parses_with_prose_around_array() -> None:
    text = "Sure. Here are my attempts:\n[{\"attempt\":\"a\",\"falsified\":false}]\nThanks."
    assert len(parse_critic_output(text)) == 1


def test_critic_runs_through_mock_backend() -> None:
    backend = MockBackend()
    backend.script("critic", "beta",
                   '[{"attempt":"x","falsified":false},{"attempt":"y","falsified":false},{"attempt":"z","falsified":false}]')
    findings = run_critic(
        backend=backend,
        checkpoint_id="beta",
        plan=_plan(),
        artifact=_artifact(),
        grader_results=[],
        min_attempts=3,
    )
    assert len(findings) == 3
    assert not any(f.falsified for f in findings)


# ---- F7 — critic minimum attempts -------------------------------------


def test_cert_rejects_too_few_critic_attempts() -> None:
    builder = {"checkpoint_id": "alpha", "model_id": "M", "tool_set": "T", "backend": "mock"}
    verifier = {"checkpoint_id": "beta", "model_id": "N", "tool_set": "T", "backend": "mock"}
    cert = build_certificate(
        plan=_plan(),
        artifact=_artifact(),
        builder_identity=builder,
        verifier_identity=verifier,
        grader_results=[GraderResult(grader="g", passed=True)],
        critic_findings=[],  # too few
        min_critic_attempts=3,
    )
    assert not cert.passed
    assert "minimum" in cert.notes


def test_seeded_flaw_evaluator_tracks_catch_rate() -> None:
    backend = MockBackend()
    # Critic correctly identifies flaw 1 (falsified=true) and misses flaw 2.
    backend.script("critic", "beta", [
        '[{"attempt":"a","falsified":true,"detail":"caught"},{"attempt":"b","falsified":false},{"attempt":"c","falsified":false}]',
        '[{"attempt":"a","falsified":false},{"attempt":"b","falsified":false},{"attempt":"c","falsified":false}]',
    ])
    evaluator = CriticEvaluator()
    flaw = SeededFlaw(label="f1", plan=_plan(), artifact=_artifact(), grader_results=[])
    caught_1 = evaluator.submit_seeded(backend=backend, checkpoint_id="beta", flaw=flaw)
    caught_2 = evaluator.submit_seeded(backend=backend, checkpoint_id="beta", flaw=flaw)
    assert caught_1 and not caught_2
    assert evaluator.catch_rate() == 0.5
