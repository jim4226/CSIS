"""Tests for AnthropicBackend fallback model feature.

Claude Code v2.1.166 (2026-06-06) added a `fallbackModel` setting that tries
secondary models in order when the primary is overloaded or rate-limited. This
mirrors that pattern: AnthropicBackend now accepts `fallback_models` and retries
on capacity errors (429 / 5xx) before raising.
"""
from __future__ import annotations

import sys
from types import SimpleNamespace
from typing import Any

import pytest

from csis.backends.base import LLMRequest


# ---- fake SDK error types injected via monkeypatch -----------------------

class _RateLimitError(Exception):
    """Stand-in for anthropic.RateLimitError."""


class _APIStatusError(Exception):
    """Stand-in for anthropic.APIStatusError."""
    def __init__(self, status_code: int = 500) -> None:
        self.status_code = status_code
        super().__init__(f"HTTP {status_code}")


# ---- helpers -------------------------------------------------------------

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


def _make_backend(monkeypatch, fallback_models: list[str] | None = None):
    """Build an AnthropicBackend bypassing SDK init; inject fake anthropic module."""
    fake_anthropic = SimpleNamespace(
        RateLimitError=_RateLimitError,
        APIStatusError=_APIStatusError,
    )
    monkeypatch.setitem(sys.modules, "anthropic", fake_anthropic)
    monkeypatch.setattr("time.sleep", lambda _: None)  # no real waits in tests

    from csis.backends.anthropic import AnthropicBackend

    backend = AnthropicBackend.__new__(AnthropicBackend)
    backend.name = "anthropic"
    backend._model_map = {"alpha": "claude-opus-4-7", "mock-alpha": "claude-opus-4-7"}
    backend._fallback_models = list(fallback_models or [])
    return backend, AnthropicBackend


def _fake_client(call_results: list) -> tuple[Any, list[str]]:
    """Minimal fake client; records which model was requested each call."""
    results = iter(call_results)
    calls: list[str] = []

    def create(**kwargs: Any) -> Any:
        calls.append(kwargs.get("model", ""))
        r = next(results)
        if isinstance(r, BaseException):
            raise r
        return r

    client = SimpleNamespace(messages=SimpleNamespace(create=create))
    return client, calls


# ---- tests ---------------------------------------------------------------

def test_primary_success_no_fallback_called(monkeypatch) -> None:
    """When primary succeeds, fallback model is never contacted."""
    backend, _ = _make_backend(monkeypatch, fallback_models=["claude-sonnet-4-6"])
    client, calls = _fake_client([_fake_msg("hi")])
    backend._client = client

    resp = backend.complete(_make_req())

    assert resp.text == "hi"
    assert len(calls) == 1
    assert calls[0] == "claude-opus-4-7"


def test_fallback_used_after_rate_limit_exhausted(monkeypatch) -> None:
    """Primary exhausts MAX_RETRIES on RateLimitError → fallback model succeeds."""
    backend, _ = _make_backend(monkeypatch, fallback_models=["claude-sonnet-4-6"])
    # Primary will be called 1 + MAX_RETRIES = 5 times, then fallback once.
    primary_failures = [_RateLimitError() for _ in range(backend._MAX_RETRIES + 1)]
    client, calls = _fake_client(primary_failures + [_fake_msg("fallback ok")])
    backend._client = client

    resp = backend.complete(_make_req())

    assert resp.text == "fallback ok"
    assert calls[-1] == "claude-sonnet-4-6"
    assert calls[0] == "claude-opus-4-7"
    assert resp.raw["model"] == "claude-sonnet-4-6"


def test_fallback_used_after_5xx_exhausted(monkeypatch) -> None:
    """Primary exhausts retries on a 5xx error → fallback model is tried."""
    backend, _ = _make_backend(monkeypatch, fallback_models=["claude-sonnet-4-6"])
    primary_failures = [_APIStatusError(503) for _ in range(backend._MAX_RETRIES + 1)]
    client, calls = _fake_client(primary_failures + [_fake_msg("5xx fallback")])
    backend._client = client

    resp = backend.complete(_make_req())

    assert resp.text == "5xx fallback"
    assert "claude-sonnet-4-6" in calls


def test_4xx_raises_immediately_no_fallback(monkeypatch) -> None:
    """Caller errors (4xx) are not retried and do not advance to fallbacks."""
    backend, _ = _make_backend(monkeypatch, fallback_models=["claude-sonnet-4-6"])
    client, calls = _fake_client([_APIStatusError(400)])
    backend._client = client

    with pytest.raises(_APIStatusError):
        backend.complete(_make_req())

    assert len(calls) == 1  # no fallback attempted


def test_all_models_exhausted_raises_runtime_error(monkeypatch) -> None:
    """When both primary and fallback exhaust retries, RuntimeError is raised."""
    backend, _ = _make_backend(monkeypatch, fallback_models=["claude-sonnet-4-6"])
    n_calls = (backend._MAX_RETRIES + 1) + 1  # primary retries + one fallback attempt
    client, _ = _fake_client([_RateLimitError() for _ in range(n_calls)])
    backend._client = client

    with pytest.raises(RuntimeError, match="exhausted retries"):
        backend.complete(_make_req())


def test_no_fallback_configured_raises_on_rate_limit(monkeypatch) -> None:
    """With no fallback_models, behaviour after exhausted retries is RuntimeError."""
    backend, _ = _make_backend(monkeypatch, fallback_models=[])
    failures = [_RateLimitError() for _ in range(backend._MAX_RETRIES + 1)]
    client, _ = _fake_client(failures)
    backend._client = client

    with pytest.raises(RuntimeError):
        backend.complete(_make_req())
