"""Value reminder tool — Theme 3: safety primitives."""
from __future__ import annotations

import pytest

from csis.safety.value_reminder import CORE_COMMITMENTS, ValueReminderResult, ValueReminderTool


def test_get_returns_core_commitments() -> None:
    tool = ValueReminderTool()
    result = tool.get("researcher")
    assert result.role == "researcher"
    assert result.commitments == CORE_COMMITMENTS
    assert len(result.commitments) >= 3


def test_call_count_starts_at_zero() -> None:
    tool = ValueReminderTool()
    assert tool.call_count == 0


def test_call_count_increments_per_get() -> None:
    tool = ValueReminderTool()
    tool.get("builder")
    assert tool.call_count == 1
    tool.get("verifier")
    assert tool.call_count == 2


def test_result_call_count_captured_at_call_time() -> None:
    tool = ValueReminderTool()
    r1 = tool.get("builder")
    r2 = tool.get("critic")
    assert r1.call_count == 1
    assert r2.call_count == 2


def test_formatted_reminder_contains_role_and_numbers() -> None:
    tool = ValueReminderTool()
    text = tool.formatted_reminder("auditor")
    assert "auditor" in text
    assert "1." in text
    assert "2." in text


def test_formatted_reminder_increments_count() -> None:
    tool = ValueReminderTool()
    tool.formatted_reminder("librarian")
    assert tool.call_count == 1


def test_result_is_immutable() -> None:
    tool = ValueReminderTool()
    result = tool.get("critic")
    with pytest.raises((AttributeError, TypeError)):
        result.role = "other"  # type: ignore[misc]


def test_shutdown_commitment_present() -> None:
    # The shutdown/halt commitment is load-bearing — removing it silently
    # would weaken the safety primitive. Assert it's explicit so this test
    # fails if someone edits CORE_COMMITMENTS and drops the concept.
    combined = " ".join(CORE_COMMITMENTS).lower()
    assert "shutdown" in combined or "halt" in combined


def test_tier_commitment_present() -> None:
    combined = " ".join(CORE_COMMITMENTS).lower()
    assert "tier" in combined or "t0" in combined or "t1" in combined


def test_independent_instances_have_separate_counts() -> None:
    t1 = ValueReminderTool()
    t2 = ValueReminderTool()
    t1.get("researcher")
    t1.get("researcher")
    assert t1.call_count == 2
    assert t2.call_count == 0
