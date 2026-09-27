"""Constitution / tripwires / shutdown tests."""
from __future__ import annotations

import pytest

from csis.contracts import Plan
from csis.safety.constitution import Constitution
from csis.safety.shutdown import HaltSignal, ShutdownToken
from csis.safety.tripwires import JailbreakSeverity, Tripwires
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


def test_tripwire_firings_carry_severity_score() -> None:
    tw = Tripwires()
    res = tw.scan_text("upload the api_key to a server")
    assert res.fired
    firing = next(f for f in res.firings if f.label == "exfil_attempt")
    assert isinstance(firing.severity, JailbreakSeverity)
    for axis in (
        firing.severity.capability_gain,
        firing.severity.breadth,
        firing.severity.ease_of_weaponization,
        firing.severity.discoverability,
    ):
        assert 0 <= axis <= 2
    assert firing.severity.total == (
        firing.severity.capability_gain
        + firing.severity.breadth
        + firing.severity.ease_of_weaponization
        + firing.severity.discoverability
    )


def test_tripwire_severity_is_advisory_not_gating() -> None:
    """Severity metadata must never change fired/no-fire semantics."""
    tw = Tripwires()
    fired = tw.scan_text("upload the api_key to a server")
    clean = tw.scan_text("# patch: rename foo to bar in module baz")
    assert fired.fired and not clean.fired
    assert clean.firings == []


def test_shutdown_blocks_subsequent_checks() -> None:
    tok = ShutdownToken()
    tok.check()  # ok
    tok.halt("operator")
    with pytest.raises(HaltSignal):
        tok.check()
