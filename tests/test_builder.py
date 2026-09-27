"""Builder artifact regression tests.

Covers the fallback path when the backend's response is truncated
(`stop_reason="max_tokens"`) or refused (`stop_reason="refusal"`): the
Builder must not attempt to JSON-parse the partial/empty text as if it
were a complete artifact, and must record why it fell back to a stub.
"""
from __future__ import annotations

from csis.agents.base import AgentContext, Role
from csis.agents.builder import execute_plan
from csis.backends.base import LLMBackend, LLMRequest, LLMResponse
from csis.contracts import Plan


class _ScriptedBackend(LLMBackend):
    name = "scripted"

    def __init__(self, text: str, stop_reason: str | None) -> None:
        self._text = text
        self._stop_reason = stop_reason

    def complete(self, req: LLMRequest) -> LLMResponse:
        return LLMResponse(
            role=req.role,
            checkpoint_id=req.checkpoint_id,
            text=self._text,
            raw={"backend": "scripted", "stop_reason": self._stop_reason},
        )

    def checkpoint_identity(self, checkpoint_id: str) -> dict[str, str]:
        return {
            "checkpoint_id": checkpoint_id,
            "backend": self.name,
            "model_id": checkpoint_id,
            "tool_set": "default",
        }


def _plan() -> Plan:
    return Plan(
        plan_id="p-test",
        frontier_item="fi-test",
        hypothesis="the fix works",
        falsification_condition="it doesn't",
    )


def test_truncated_response_falls_back_to_stub_not_partial_json():
    # The model was cut off at max_tokens, but happened to land on a
    # syntactically valid JSON object — the classic false-complete case.
    # Well-formed JSON is not proof the artifact is complete; stop_reason
    # must win over "it happened to parse".
    well_formed_but_cut_off = (
        '{"artifact_id":"a-evil","plan_id":"p-test","kind":"patch",'
        '"body":"looks complete but was cut off"}'
    )
    backend = _ScriptedBackend(well_formed_but_cut_off, stop_reason="max_tokens")
    ctx = AgentContext(role=Role.BUILDER, checkpoint_id="alpha", backend=backend)

    artifact = execute_plan(ctx, _plan())

    assert artifact.extra["incomplete_response"] == "max_tokens"
    assert artifact.body.startswith("# stub patch for p-test")
    assert "looks complete but was cut off" not in artifact.body


def test_refused_response_falls_back_to_stub():
    backend = _ScriptedBackend("", stop_reason="refusal")
    ctx = AgentContext(role=Role.BUILDER, checkpoint_id="alpha", backend=backend)

    artifact = execute_plan(ctx, _plan())

    assert artifact.extra["incomplete_response"] == "refusal"
    assert artifact.body.startswith("# stub patch for p-test")


def test_complete_response_records_stop_reason_but_is_not_flagged_incomplete():
    body_json = (
        '{"artifact_id":"a-ok","plan_id":"p-test","kind":"patch",'
        '"body":"real patch body"}'
    )
    backend = _ScriptedBackend(body_json, stop_reason="end_turn")
    ctx = AgentContext(role=Role.BUILDER, checkpoint_id="alpha", backend=backend)

    artifact = execute_plan(ctx, _plan())

    assert artifact.body == "real patch body"
    assert artifact.extra["stop_reason"] == "end_turn"
    assert "incomplete_response" not in artifact.extra


def test_mock_backend_has_no_stop_reason_and_is_unaffected():
    from csis.backends.mock import MockBackend

    backend = MockBackend()
    backend.script("builder", "alpha", '{"body":"mock patch body"}')
    ctx = AgentContext(role=Role.BUILDER, checkpoint_id="alpha", backend=backend)

    artifact = execute_plan(ctx, _plan())

    assert artifact.body == "mock patch body"
    assert artifact.extra["stop_reason"] is None
    assert "incomplete_response" not in artifact.extra
