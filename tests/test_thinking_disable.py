"""Tests for AnthropicBackend thinking_disabled flag.

Claude Code v2.1.166 (2026-06-06) added MAX_THINKING_TOKENS=0 / --thinking
disabled to suppress extended thinking on models that think by default (e.g.
Opus 4.8). CSIS mirrors this via CSISConfig.thinking_disabled and
AnthropicBackend(thinking_disabled=True), which passes thinking={"type":
"disabled"} to the Anthropic API on every call.

Phase-0 rationale: extended thinking is a higher-capability mode that should
be gated rather than inherited silently when a new model enables it by default.
Disabling it keeps CSIS within the T0/T1 boundary intended by Phase-0.
"""
from __future__ import annotations

import sys
from types import SimpleNamespace
from typing import Any

import pytest

from csis.backends.base import LLMRequest


# ---- minimal fakes -------------------------------------------------------

class _RateLimitError(Exception):
    pass


class _APIStatusError(Exception):
    def __init__(self, status_code: int = 500) -> None:
        self.status_code = status_code


def _fake_msg(text: str = "ok") -> Any:
    return SimpleNamespace(
        content=[SimpleNamespace(text=text)],
        usage=SimpleNamespace(input_tokens=5, output_tokens=10),
        stop_reason="end_turn",
    )


def _make_req() -> LLMRequest:
    return LLMRequest(
        role="researcher",
        checkpoint_id="alpha",
        system="sys",
        prompt="p",
    )


# ---- fixture that builds a backend bypassing SDK init --------------------

def _make_backend(monkeypatch, thinking_disabled: bool = False):
    fake_anthropic = SimpleNamespace(
        RateLimitError=_RateLimitError,
        APIStatusError=_APIStatusError,
    )
    monkeypatch.setitem(sys.modules, "anthropic", fake_anthropic)
    monkeypatch.setattr("time.sleep", lambda _: None)

    from csis.backends.anthropic import AnthropicBackend

    backend = AnthropicBackend.__new__(AnthropicBackend)
    backend.name = "anthropic"
    backend._model_map = {"alpha": "claude-opus-4-7"}
    backend._thinking_disabled = thinking_disabled
    return backend


# ---- tests ---------------------------------------------------------------

def test_thinking_not_sent_by_default(monkeypatch) -> None:
    """When thinking_disabled is False, the thinking kwarg is not sent."""
    backend = _make_backend(monkeypatch, thinking_disabled=False)
    captured: list[dict] = []

    def create(**kwargs: Any) -> Any:
        captured.append(kwargs)
        return _fake_msg()

    backend._client = SimpleNamespace(messages=SimpleNamespace(create=create))
    backend.complete(_make_req())

    assert len(captured) == 1
    assert "thinking" not in captured[0]


def test_thinking_disabled_sent_when_flag_set(monkeypatch) -> None:
    """When thinking_disabled=True, thinking={"type":"disabled"} is sent."""
    backend = _make_backend(monkeypatch, thinking_disabled=True)
    captured: list[dict] = []

    def create(**kwargs: Any) -> Any:
        captured.append(kwargs)
        return _fake_msg()

    backend._client = SimpleNamespace(messages=SimpleNamespace(create=create))
    backend.complete(_make_req())

    assert len(captured) == 1
    assert captured[0].get("thinking") == {"type": "disabled"}


def test_thinking_disabled_response_text_preserved(monkeypatch) -> None:
    """Response text is correctly returned even when thinking is disabled."""
    backend = _make_backend(monkeypatch, thinking_disabled=True)
    backend._client = SimpleNamespace(
        messages=SimpleNamespace(create=lambda **_: _fake_msg("hello"))
    )
    resp = backend.complete(_make_req())
    assert resp.text == "hello"


def test_config_thinking_disabled_default_false() -> None:
    """CSISConfig.thinking_disabled defaults to False."""
    from pathlib import Path
    from csis.config import CSISConfig

    cfg = CSISConfig(
        event_log_path=Path("/tmp/t/el.jsonl"),
        memory_root=Path("/tmp/t/mem"),
        brain_root=Path("/tmp/t/brain"),
        backend="mock",
    )
    assert cfg.thinking_disabled is False


def test_config_thinking_disabled_can_be_set() -> None:
    """CSISConfig.thinking_disabled=True is accepted."""
    from pathlib import Path
    from csis.config import CSISConfig

    cfg = CSISConfig(
        event_log_path=Path("/tmp/t/el.jsonl"),
        memory_root=Path("/tmp/t/mem"),
        brain_root=Path("/tmp/t/brain"),
        backend="mock",
        thinking_disabled=True,
    )
    assert cfg.thinking_disabled is True
