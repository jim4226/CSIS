"""Regression tests for the advisor-tool-builder integration.

Anthropic shipped the advisor tool (advisor-tool-2026-03-01) in April 2026
and added the max_tokens cap parameter on June 2, 2026. This lets a faster
executor model call a higher-intelligence advisor mid-generation for strategic
guidance within a single API request — a natural fit for CSIS's Builder role,
which benefits from Opus-level planning without paying Opus rates for every
output token.

Changes covered:
  - LLMRequest.advisor_model / advisor_max_tokens fields (backends/base.py)
  - AgentContext.advisor_model field threaded through complete() (agents/base.py)
  - AnthropicBackend uses beta.messages.create when advisor_model is set (backends/anthropic.py)
  - CSISConfig.builder_advisor_model / builder_advisor_max_tokens (config.py)
  - Coordinator._ctx(BUILDER) propagates builder_advisor_model (agents/coordinator.py)
"""
from __future__ import annotations

import types
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from csis.agents.base import AgentContext, Role
from csis.agents.coordinator import Coordinator
from csis.backends.base import LLMRequest, LLMResponse
from csis.backends.mock import MockBackend
from csis.config import CSISConfig

from tests._helpers import wrap_for_test


# ---- LLMRequest fields ---------------------------------------------------


def test_llm_request_accepts_advisor_fields() -> None:
    req = LLMRequest(
        role="builder",
        checkpoint_id="mock-alpha",
        system="sys",
        prompt="test",
        advisor_model="claude-opus-4-8",
        advisor_max_tokens=2048,
    )
    assert req.advisor_model == "claude-opus-4-8"
    assert req.advisor_max_tokens == 2048


def test_llm_request_advisor_defaults_to_none() -> None:
    req = LLMRequest(role="builder", checkpoint_id="a", system="s", prompt="p")
    assert req.advisor_model is None
    assert req.advisor_max_tokens is None


# ---- AgentContext threading -----------------------------------------------


def test_agent_context_passes_advisor_to_request() -> None:
    """AgentContext with advisor_model writes it into every LLMRequest it creates."""
    captured: list[LLMRequest] = []

    class _Tracking(MockBackend):
        def complete(self, req: LLMRequest) -> LLMResponse:
            captured.append(req)
            return super().complete(req)

    ctx = AgentContext(
        role=Role.BUILDER,
        checkpoint_id="mock-alpha",
        backend=_Tracking(),
        advisor_model="mock-beta",
    )
    ctx.complete("hello")
    assert captured, "expected at least one LLMRequest to be captured"
    assert captured[0].advisor_model == "mock-beta"


def test_agent_context_none_advisor_propagated() -> None:
    """Default AgentContext passes advisor_model=None so no advisor is invoked."""
    captured: list[LLMRequest] = []

    class _Tracking(MockBackend):
        def complete(self, req: LLMRequest) -> LLMResponse:
            captured.append(req)
            return super().complete(req)

    ctx = AgentContext(
        role=Role.BUILDER,
        checkpoint_id="mock-alpha",
        backend=_Tracking(),
    )
    ctx.complete("hello")
    assert captured[0].advisor_model is None


# ---- MockBackend ignores advisor_model ------------------------------------


def test_mock_backend_ignores_advisor_model() -> None:
    """MockBackend.complete() works transparently when advisor_model is set."""
    backend = MockBackend()
    req = LLMRequest(
        role="builder",
        checkpoint_id="mock-alpha",
        system="sys",
        prompt="test",
        advisor_model="claude-opus-4-8",
        advisor_max_tokens=2048,
    )
    resp = backend.complete(req)
    assert isinstance(resp.text, str)


# ---- AnthropicBackend routes to beta.messages.create ---------------------


def _make_fake_anthropic_backend(beta_calls: list, regular_calls: list):
    """Build an AnthropicBackend whose internal _client is replaced with a fake."""
    from csis.backends.anthropic import AnthropicBackend

    class FakeMsg:
        content = []
        usage = types.SimpleNamespace(input_tokens=10, output_tokens=5)
        stop_reason = "end_turn"

    class FakeBetaMessages:
        def create(self, **kwargs):
            beta_calls.append(kwargs)
            return FakeMsg()

    class FakeRegularMessages:
        def create(self, **kwargs):
            regular_calls.append(kwargs)
            return FakeMsg()

    class FakeClient:
        beta = types.SimpleNamespace(messages=FakeBetaMessages())
        messages = FakeRegularMessages()

    backend = object.__new__(AnthropicBackend)
    backend._client = FakeClient()
    backend._model_map = {
        "mock-alpha": "claude-sonnet-4-6",
        "mock-beta": "claude-opus-4-8",
    }
    return backend


def test_anthropic_backend_uses_beta_when_advisor_set() -> None:
    """AnthropicBackend calls beta.messages.create with the advisor tool definition."""
    beta_calls: list = []
    regular_calls: list = []
    backend = _make_fake_anthropic_backend(beta_calls, regular_calls)

    req = LLMRequest(
        role="builder",
        checkpoint_id="mock-alpha",
        system="sys",
        prompt="test",
        advisor_model="mock-beta",
        advisor_max_tokens=2048,
    )
    backend.complete(req)

    assert len(beta_calls) == 1
    assert len(regular_calls) == 0
    tool = beta_calls[0]["tools"][0]
    assert tool["type"] == "advisor_20260301"
    assert tool["name"] == "advisor"
    assert tool["model"] == "claude-opus-4-8"  # resolved via _model_map
    assert tool["max_tokens"] == 2048
    assert "advisor-tool-2026-03-01" in beta_calls[0]["betas"]


def test_anthropic_backend_uses_regular_when_no_advisor() -> None:
    """AnthropicBackend uses the standard messages.create path when advisor_model is None."""
    beta_calls: list = []
    regular_calls: list = []
    backend = _make_fake_anthropic_backend(beta_calls, regular_calls)

    req = LLMRequest(
        role="builder",
        checkpoint_id="mock-alpha",
        system="sys",
        prompt="test",
    )
    backend.complete(req)

    assert len(regular_calls) == 1
    assert len(beta_calls) == 0


def test_anthropic_backend_advisor_without_max_tokens() -> None:
    """advisor_max_tokens=None omits the max_tokens key from the tool definition."""
    beta_calls: list = []
    regular_calls: list = []
    backend = _make_fake_anthropic_backend(beta_calls, regular_calls)

    req = LLMRequest(
        role="builder",
        checkpoint_id="mock-alpha",
        system="sys",
        prompt="test",
        advisor_model="mock-beta",
    )
    backend.complete(req)

    tool = beta_calls[0]["tools"][0]
    assert "max_tokens" not in tool


# ---- CSISConfig ----------------------------------------------------------


def test_config_advisor_fields_default_none(tmp_path: Path) -> None:
    cfg = CSISConfig.for_tests(tmp_path)
    assert cfg.builder_advisor_model is None
    assert cfg.builder_advisor_max_tokens is None


def test_config_advisor_fields_assignable(tmp_path: Path) -> None:
    cfg = CSISConfig.for_tests(tmp_path)
    cfg.builder_advisor_model = "claude-opus-4-8"
    cfg.builder_advisor_max_tokens = 2048
    assert cfg.builder_advisor_model == "claude-opus-4-8"
    assert cfg.builder_advisor_max_tokens == 2048


# ---- Coordinator._ctx propagation ----------------------------------------


def test_coordinator_builder_ctx_gets_advisor_model(tmp_path: Path) -> None:
    """Coordinator._ctx(BUILDER) includes builder_advisor_model from config."""
    cfg = CSISConfig.for_tests(tmp_path)
    cfg.builder_advisor_model = "claude-opus-4-8"
    backend = MockBackend()
    backend.set_model_id(cfg.builder_checkpoint, "mock-opus")
    backend.set_model_id(cfg.auditor_checkpoint, "mock-sonnet")
    coord = Coordinator(config=cfg, backend=wrap_for_test(backend, tmp_path))

    builder_ctx = coord._ctx(Role.BUILDER, side="builder")
    assert builder_ctx.advisor_model == "claude-opus-4-8"


def test_coordinator_non_builder_ctx_has_no_advisor(tmp_path: Path) -> None:
    """Roles other than BUILDER never receive an advisor model."""
    cfg = CSISConfig.for_tests(tmp_path)
    cfg.builder_advisor_model = "claude-opus-4-8"
    backend = MockBackend()
    backend.set_model_id(cfg.builder_checkpoint, "mock-opus")
    backend.set_model_id(cfg.auditor_checkpoint, "mock-sonnet")
    coord = Coordinator(config=cfg, backend=wrap_for_test(backend, tmp_path))

    for role in (Role.RESEARCHER, Role.VERIFIER, Role.LIBRARIAN, Role.AUDITOR):
        side = "auditor" if role in (Role.VERIFIER, Role.AUDITOR) else "builder"
        ctx = coord._ctx(role, side=side)
        assert ctx.advisor_model is None, f"{role} should not get an advisor model"


def test_coordinator_no_advisor_model_in_config(tmp_path: Path) -> None:
    """With no builder_advisor_model in config, BUILDER ctx has advisor_model=None."""
    cfg = CSISConfig.for_tests(tmp_path)
    assert cfg.builder_advisor_model is None
    backend = MockBackend()
    backend.set_model_id(cfg.builder_checkpoint, "mock-opus")
    backend.set_model_id(cfg.auditor_checkpoint, "mock-sonnet")
    coord = Coordinator(config=cfg, backend=wrap_for_test(backend, tmp_path))

    builder_ctx = coord._ctx(Role.BUILDER, side="builder")
    assert builder_ctx.advisor_model is None
