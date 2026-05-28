"""Regression tests for LLMRequest.effort and AnthropicBackend model-map (Opus 4.8).

These tests guard two properties introduced for the claude-opus-4-8 upgrade:
  1. LLMRequest carries an optional `effort` field (defaults to None).
  2. AnthropicBackend passes `effort` to the API when set and omits it when None.
  3. _DEFAULT_MODEL_MAP maps "alpha"/"mock-alpha" to claude-opus-4-8.
"""
from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from csis.backends.anthropic import AnthropicBackend, _DEFAULT_MODEL_MAP
from csis.backends.base import LLMRequest


# ---- LLMRequest field -------------------------------------------------------


def test_llm_request_effort_defaults_to_none():
    req = LLMRequest(role="researcher", checkpoint_id="ckpt-A", system="sys", prompt="p")
    assert req.effort is None


def test_llm_request_effort_round_trips():
    for level in ("low", "medium", "high"):
        req = LLMRequest(
            role="builder", checkpoint_id="ckpt-B", system="sys", prompt="p", effort=level
        )
        assert req.effort == level


# ---- _DEFAULT_MODEL_MAP -------------------------------------------------------


def test_alpha_maps_to_opus_4_8():
    assert _DEFAULT_MODEL_MAP["alpha"] == "claude-opus-4-8"


def test_mock_alpha_maps_to_opus_4_8():
    assert _DEFAULT_MODEL_MAP["mock-alpha"] == "claude-opus-4-8"


def test_beta_maps_to_sonnet_4_6():
    assert _DEFAULT_MODEL_MAP["beta"] == "claude-sonnet-4-6"


# ---- AnthropicBackend.complete() ------------------------------------------------


def _make_backend_with_fake_client():
    """Construct an AnthropicBackend bypassing __init__ (no real API key needed)."""
    backend = AnthropicBackend.__new__(AnthropicBackend)
    backend._model_map = dict(_DEFAULT_MODEL_MAP)

    fake_content = MagicMock()
    fake_content.text = "mock-result"
    fake_msg = MagicMock()
    fake_msg.content = [fake_content]
    fake_msg.stop_reason = "end_turn"
    fake_msg.usage = MagicMock(input_tokens=10, output_tokens=5)

    mock_client = MagicMock()
    mock_client.messages.create.return_value = fake_msg
    backend._client = mock_client
    return backend, mock_client


def test_effort_passed_to_api_when_set():
    backend, mock_client = _make_backend_with_fake_client()
    req = LLMRequest(
        role="builder", checkpoint_id="alpha", system="sys", prompt="work", effort="low"
    )
    resp = backend.complete(req)
    assert resp.text == "mock-result"
    kwargs = mock_client.messages.create.call_args.kwargs
    assert kwargs.get("effort") == "low"


def test_effort_omitted_from_api_when_none():
    backend, mock_client = _make_backend_with_fake_client()
    req = LLMRequest(
        role="verifier", checkpoint_id="alpha", system="sys", prompt="verify"
        # effort=None (default)
    )
    resp = backend.complete(req)
    assert resp.text == "mock-result"
    kwargs = mock_client.messages.create.call_args.kwargs
    assert "effort" not in kwargs
