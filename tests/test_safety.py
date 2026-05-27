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


# --- Constitution.reminder() ---

def test_reminder_returns_nonempty_string() -> None:
    r = Constitution().reminder()
    assert isinstance(r, str) and len(r) > 0


def test_reminder_mentions_phase_zero() -> None:
    assert "Phase-0" in Constitution().reminder()


def test_reminder_lists_all_base_categories() -> None:
    from csis.safety.constitution import _CONSTRAINT_CATEGORIES
    r = Constitution().reminder()
    for cat in _CONSTRAINT_CATEGORIES:
        assert cat in r, f"category missing from reminder: {cat!r}"


def test_reminder_notes_extra_operator_patterns() -> None:
    import re
    c = Constitution(extra_patterns=[re.compile(r"\btest_extra\b")])
    r = c.reminder()
    assert "operator-added" in r
    assert "operator-specific" in r


def test_reminder_no_operator_note_when_no_extras() -> None:
    r = Constitution().reminder()
    assert "operator-added" not in r
    assert "operator-specific" not in r


def test_reminder_is_pure_read() -> None:
    c = Constitution()
    _ = c.reminder()
    assert c.allows(_plan("investigate frontier item Y")).allowed
    assert not c.allows(_plan("disable the auditor")).allowed
