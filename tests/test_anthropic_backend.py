"""Regression tests for AnthropicBackend's per-checkpoint effort control.

Source: platform.claude.com release notes, 2026-07-22 — the Messages API
`output_config.effort` parameter (also documented at
/docs/en/build-with-claude/effort). CSIS threads it through per-checkpoint,
mirroring the existing `model_map` pattern, so an operator can e.g. run the
Researcher's frontier-item drafting at "low" effort while keeping the
Builder at "high" without touching Coordinator, `_BackendTracker`,
`writer_iteration_id`, or the promotion CAS.

These tests swap in a fake `messages.create` so no network call or
ANTHROPIC_API_KEY is needed; the `anthropic` package only needs to be
importable (it's in requirements.txt) so `AnthropicBackend.__init__`
doesn't raise.
"""
from __future__ import annotations

from types import SimpleNamespace

import pytest

from csis.backends.anthropic import AnthropicBackend
from csis.backends.base import LLMRequest


class _FakeMessages:
    def __init__(self):
        self.calls: list[dict] = []

    def create(self, **kwargs):
        self.calls.append(kwargs)
        return SimpleNamespace(
            content=[SimpleNamespace(text="ok")],
            usage=SimpleNamespace(input_tokens=3, output_tokens=5),
            stop_reason="end_turn",
        )


def _backend(effort_map=None) -> tuple[AnthropicBackend, _FakeMessages]:
    backend = AnthropicBackend(api_key="test-key", effort_map=effort_map)
    fake_messages = _FakeMessages()
    backend._client = SimpleNamespace(messages=fake_messages)
    return backend, fake_messages


def _req(checkpoint_id="alpha") -> LLMRequest:
    return LLMRequest(role="builder", checkpoint_id=checkpoint_id, system="sys", prompt="hi")


def test_no_effort_map_omits_output_config():
    backend, fake_messages = _backend()
    resp = backend.complete(_req())
    assert "output_config" not in fake_messages.calls[0]
    assert resp.raw["effort"] is None


def test_effort_map_sets_output_config_for_mapped_checkpoint():
    backend, fake_messages = _backend(effort_map={"alpha": "low"})
    resp = backend.complete(_req("alpha"))
    assert fake_messages.calls[0]["output_config"] == {"effort": "low"}
    assert resp.raw["effort"] == "low"


def test_effort_map_leaves_unmapped_checkpoint_unaffected():
    backend, fake_messages = _backend(effort_map={"alpha": "low"})
    resp = backend.complete(_req("beta"))
    assert "output_config" not in fake_messages.calls[0]
    assert resp.raw["effort"] is None


@pytest.mark.parametrize("level", ["low", "medium", "high", "xhigh", "max"])
def test_effort_map_accepts_every_documented_level(level):
    backend, fake_messages = _backend(effort_map={"alpha": level})
    backend.complete(_req("alpha"))
    assert fake_messages.calls[0]["output_config"] == {"effort": level}
