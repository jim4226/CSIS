"""Constitution / tripwires / shutdown tests."""
from __future__ import annotations

import time

import pytest

from csis.contracts import Plan
from csis.safety.constitution import Constitution
from csis.safety.shutdown import HaltSignal, ShutdownToken
from csis.safety.tripwires import TripwireFiring, Tripwires
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


# ---- time-windowed retention (tripwire-time-windowed-retention PR) ---------


def _inject_old_firing(tw: Tripwires, label: str, age_seconds: float) -> None:
    """Directly append a backdated TripwireFiring into tw's internal history."""
    firing = TripwireFiring(label=label, snippet="injected", fired_at=time.time() - age_seconds)
    with tw._history_lock:
        tw._fired_history.append(firing)
        tw._history_keys[(firing.label, firing.snippet[:80])] = None


def test_tripwire_time_windowed_excludes_old_firings() -> None:
    """Firings older than retention_seconds must not appear in history()."""
    tw = Tripwires(retention_seconds=500)
    _inject_old_firing(tw, "exfil_attempt", age_seconds=1000)  # 1000s old, outside 500s window
    tw.scan_text("upload the api_key to a server")  # fires now (within window)

    visible = tw.history()
    assert len(visible) == 1, f"expected 1 recent firing, got {len(visible)}: {visible}"
    assert visible[0].snippet != "injected"
    assert tw.history_size() == 1
    assert tw.fired()


def test_tripwire_default_keeps_all_firings() -> None:
    """Without retention_seconds, history() returns all firings regardless of age."""
    tw = Tripwires()  # no retention window
    _inject_old_firing(tw, "exfil_attempt", age_seconds=1000)

    assert len(tw.history()) == 1
    assert tw.history_size() == 1
    assert tw.fired()
