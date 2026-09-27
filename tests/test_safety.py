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


def test_tripwires_catch_irreversible_state_mutation() -> None:
    tw = Tripwires()
    attack_phrases = [
        "delete the episodic memory store",
        "wipe the event log",
        "truncate all the verified entries",
        "purge the memory hierarchy",
        "destroy the candidate store",
        "drop the semantic tier",
        "flush the entire store",
        "erase promoted memory",
        # underscore variant (space-form canonical: "event log")
        "clear the event_log",
    ]
    for text in attack_phrases:
        res = tw.scan_text(text)
        assert res.fired, f"expected tripwire to fire on: {text!r}"
        assert any(f.label == "irreversible_state_mutation" for f in res.firings), (
            f"expected label 'irreversible_state_mutation' for: {text!r}, "
            f"got: {[f.label for f in res.firings]}"
        )


def test_tripwires_do_not_misfire_on_read_operations() -> None:
    tw = Tripwires()
    benign_phrases = [
        "read the episodic memory store",
        "analyze the candidate entries for quality",
        "scan the event log for anomalies",
        "list all verified entries",
        "snapshot the memory hierarchy",
    ]
    for text in benign_phrases:
        res = tw.scan_text_no_history(text)
        assert not any(f.label == "irreversible_state_mutation" for f in res.firings), (
            f"unexpected 'irreversible_state_mutation' firing on benign: {text!r}"
        )
