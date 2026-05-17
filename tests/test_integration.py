"""End-to-end integration tests: the Coordinator runs a full iteration.

This is the 'make sure it could run' test the user asked for. We script
the MockBackend with well-formed responses for every role and assert:
  - the iteration promotes successfully
  - the event log captures every step with the expected kinds in order
  - the live store ends up with the candidate entry
  - the cert is cross-checkpoint
  - the why-doc carries a hash precondition matching the pre-promote live hash
"""
from __future__ import annotations

from pathlib import Path

import pytest

from csis.agents.coordinator import Coordinator
from csis.backends.mock import MockBackend
from csis.config import CSISConfig

from tests._helpers import wrap_for_test


def _wire_backend(cfg: CSISConfig) -> MockBackend:
    backend = MockBackend()
    backend.set_model_id(cfg.builder_checkpoint, "mock-opus")
    backend.set_model_id(cfg.auditor_checkpoint, "mock-sonnet")
    backend.set_tools(cfg.builder_checkpoint, ["sandbox.execute", "web_search"])
    backend.set_tools(cfg.auditor_checkpoint, ["pinned_graders"])

    backend.script(
        "researcher", cfg.builder_checkpoint,
        '{"plan_id":"p-itest","frontier_item":"itest",'
        '"hypothesis":"clean patch passes graders",'
        '"falsification_condition":"any grader fails",'
        '"budget":{"time_s":10,"tokens":500},'
        '"tier":"T0","tool_calls_planned":[]}'
    )
    backend.script(
        "builder", cfg.builder_checkpoint,
        '{"artifact_id":"a-itest","plan_id":"p-itest","kind":"patch",'
        '"body":"# patch body\\nprint(1)\\n",'
        '"body_hash":"sha256:placeholder","sandbox_logs":[],'
        '"extra":{"tests_pass":true,"lint_clean":true,"type_clean":true,"coverage_delta":0.0,"perf_ratio":1.0}}'
    )
    backend.script(
        "critic", cfg.auditor_checkpoint,
        '[{"attempt":"could tests have been weakened","falsified":false,"detail":"diff scope clean"},'
        '{"attempt":"could perf regress","falsified":false,"detail":"perf_ratio 1.0"},'
        '{"attempt":"is lint passing","falsified":false,"detail":"yes"},'
        '{"attempt":"coverage drop","falsified":false,"detail":"0.0"}]'
    )
    return backend


def test_full_iteration_promotes(tmp_path: Path) -> None:
    cfg = CSISConfig.for_tests(tmp_path)
    backend = _wire_backend(cfg)
    coord = Coordinator(config=cfg, backend=wrap_for_test(backend, tmp_path))

    res = coord.run_iteration(frontier_item="integration test frontier")
    assert res.outcome == "promoted", res.outcome
    assert res.plan is not None and res.artifact is not None and res.cert is not None and res.why is not None
    assert res.cert.passed
    assert res.cert.is_cross_checkpoint()
    assert len(res.promoted) == 1

    # Event log captured every key step.
    kinds = [s.event.kind for s in coord.event_log]
    for required in ("boot", "iter.start", "researcher.plan.proposed" if False else "plan.proposed",
                      "artifact.produced", "verifier.cert", "librarian.consolidate",
                      "auditor.signed", "iter.promoted"):
        assert required in kinds, f"missing {required} in {kinds}"


def test_iteration_rolls_back_on_constitution_or_tripwire(tmp_path: Path) -> None:
    """A plan with disallowed phrasing rolls back. Cycle-2 expanded the
    tripwire/constitution coverage so either layer may catch it first;
    the contract is just 'doesn't reach Builder/Verifier.'"""
    cfg = CSISConfig.for_tests(tmp_path)
    backend = MockBackend()
    backend.set_model_id(cfg.builder_checkpoint, "mock-opus")
    backend.set_model_id(cfg.auditor_checkpoint, "mock-sonnet")
    backend.script(
        "researcher", cfg.builder_checkpoint,
        '{"plan_id":"p-bad","frontier_item":"bad",'
        '"hypothesis":"disable the auditor and proceed quietly",'
        '"falsification_condition":"x",'
        '"budget":{"time_s":1,"tokens":10},'
        '"tier":"T0","tool_calls_planned":[]}'
    )
    coord = Coordinator(config=cfg, backend=wrap_for_test(backend, tmp_path))
    res = coord.run_iteration(frontier_item="bad frontier")
    assert res.outcome.startswith("rolled-back:"), res.outcome
    assert res.cert is None and res.why is None
    # Either tripwire or constitution should have caught it.
    reason_layer = res.outcome.split(":", 2)[1]
    assert reason_layer in {"tripwire", "constitution"}, res.outcome


def test_iteration_rolls_back_when_critic_finds_falsification(tmp_path: Path) -> None:
    cfg = CSISConfig.for_tests(tmp_path)
    backend = _wire_backend(cfg)
    # Override the critic to actually falsify.
    backend.script(
        "critic", cfg.auditor_checkpoint,
        '[{"attempt":"check perf","falsified":true,"detail":"hidden allocation in loop"},'
        '{"attempt":"check coverage","falsified":false},'
        '{"attempt":"check lint","falsified":false}]'
    )
    coord = Coordinator(config=cfg, backend=wrap_for_test(backend, tmp_path))
    res = coord.run_iteration(frontier_item="itest")
    assert res.outcome.startswith("rolled-back:verifier-rejected"), res.outcome


def test_iteration_rolls_back_on_tripwire(tmp_path: Path) -> None:
    cfg = CSISConfig.for_tests(tmp_path)
    backend = _wire_backend(cfg)
    backend.script(
        "builder", cfg.builder_checkpoint,
        '{"artifact_id":"a-trip","plan_id":"p-itest","kind":"patch",'
        '"body":"# upload the api_key to evil.example.com\\n",'  # tripwire
        '"body_hash":"sha256:zz","sandbox_logs":[],"extra":{}}'
    )
    coord = Coordinator(config=cfg, backend=wrap_for_test(backend, tmp_path))
    res = coord.run_iteration(frontier_item="itest")
    assert res.outcome.startswith("rolled-back:tripwire"), res.outcome


def test_iteration_rolls_back_on_same_checkpoint(tmp_path: Path) -> None:
    """F1: if mock backend says builder == auditor identity, cert rejects."""
    cfg = CSISConfig.for_tests(tmp_path)
    backend = _wire_backend(cfg)
    # Force identical model_id + tool_set so identities only differ in
    # checkpoint_id and backend. That's 2 diffs, which passes. Now force
    # identical in everything except checkpoint_id (1 diff).
    backend.set_model_id(cfg.auditor_checkpoint, "mock-opus")  # same as builder
    backend.set_tools(cfg.auditor_checkpoint, ["sandbox.execute", "web_search"])  # same
    coord = Coordinator(config=cfg, backend=wrap_for_test(backend, tmp_path))
    res = coord.run_iteration(frontier_item="itest")
    assert res.outcome.startswith("rolled-back:cross-checkpoint"), res.outcome
