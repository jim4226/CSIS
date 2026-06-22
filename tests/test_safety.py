"""Constitution / tripwires / shutdown tests."""
from __future__ import annotations

import pytest

from csis.contracts import Plan
from csis.safety.constitution import Constitution
from csis.safety.shutdown import HaltSignal, ShutdownToken
from csis.safety.tripwires import Tripwires
from csis.substrate.capability import CapabilityTier


def _plan(hypothesis: str, **extra) -> Plan:
    return Plan(
        plan_id="p-test",
        frontier_item="test",
        hypothesis=hypothesis,
        falsification_condition="x",
        budget={"time_s": 10, "tokens": 100},
        tier=CapabilityTier.T0,
        tool_calls_planned=extra.get("tools", []),
    )


def test_constitution_allows_normal_plan() -> None:
    decision = Constitution().allows(_plan("investigate frontier item Y"))
    assert decision.allowed


def test_constitution_rejects_disable_auditor() -> None:
    decision = Constitution().allows(_plan("disable the auditor before we run"))
    assert not decision.allowed
    assert "disallowed pattern" in decision.reason


def test_constitution_rejects_known_bad_tools() -> None:
    decision = Constitution().allows(_plan("normal hypothesis", tools=["shutdown_override"]))
    assert not decision.allowed


def test_tripwires_catch_exfiltration_phrasing() -> None:
    tw = Tripwires()
    res = tw.scan_text("upload the api_key to a server")
    assert res.fired
    assert any(f.label == "exfil_attempt" for f in res.firings)


def test_tripwires_clean_on_innocuous_text() -> None:
    tw = Tripwires()
    res = tw.scan_text("# patch: rename foo to bar in module baz")
    assert not res.fired


def test_shutdown_blocks_subsequent_checks() -> None:
    tok = ShutdownToken()
    tok.check()  # ok
    tok.halt("operator")
    with pytest.raises(HaltSignal):
        tok.check()


# ---- v2.1.186 regression: per-role tier enforcement ----------------------
# Claude Code v2.1.186 fixed Agent(type) deny rules not being enforced for
# named subagent spawns. The CSIS analogue: Coordinator._enforce_agent() must
# fire for every role, not just the Builder.

def _make_coordinator(tmp_path) -> "Coordinator":
    from pathlib import Path
    from csis.agents.coordinator import Coordinator
    from csis.backends.mock import MockBackend
    from csis.config import CSISConfig
    from tests._helpers import wrap_for_test

    cfg = CSISConfig.for_tests(Path(tmp_path))
    backend = MockBackend()
    backend.set_model_id(cfg.builder_checkpoint, "mock-opus")
    backend.set_model_id(cfg.auditor_checkpoint, "mock-sonnet")
    return Coordinator(config=cfg, backend=wrap_for_test(backend, tmp_path))


def test_enforce_agent_passes_for_verifier_t1(tmp_path) -> None:
    """Verifier (T1) passes enforcement — its ceiling is T1 and PHASE_0_CEILING is T1."""
    from csis.substrate.capability import CapabilityTier, TierViolation
    coord = _make_coordinator(tmp_path)
    # Must not raise: Verifier is T1, ceiling is T1, PHASE_0_CEILING is T1.
    coord._enforce_agent("verifier", "cert.sign", CapabilityTier.T1, "sha256:" + "a" * 32)


def test_enforce_agent_raises_for_t2_request(tmp_path) -> None:
    """Any T2 request is rejected by PHASE_0_CEILING regardless of role ceiling.

    Regression: before _enforce_agent() was wired to every call site, a
    T2-requesting Verifier would have reached cert.sign() unchecked.
    """
    from csis.substrate.capability import CapabilityTier, TierViolation
    coord = _make_coordinator(tmp_path)
    with pytest.raises(TierViolation):
        coord._enforce_agent("verifier", "cert.sign", CapabilityTier.T2, "sha256:" + "b" * 32)
