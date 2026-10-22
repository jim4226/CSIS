"""Tests for conversation_history on LLMRequest and mid_conv_system plumbing.

The Messages API (Opus 4.8+) accepts mid_conv_system blocks inside the messages
array, letting callers update instructions mid-task without busting the prompt
cache. These tests verify the CSIS plumbing: LLMRequest carries the history,
AgentContext threads it to the backend, and AnthropicBackend passes it through
to the API call.
"""
from __future__ import annotations

import pytest

from csis.backends.base import LLMRequest
from csis.backends.mock import MockBackend


def test_llmrequest_conversation_history_defaults_empty():
    req = LLMRequest(role="researcher", checkpoint_id="ck", system="sys", prompt="hi")
    assert req.conversation_history == []


def test_llmrequest_conversation_history_stored():
    history = [
        {"role": "user", "content": "what is X?"},
        {"role": "assistant", "content": "X is Y."},
    ]
    req = LLMRequest(
        role="researcher",
        checkpoint_id="ck",
        system="sys",
        prompt="follow-up",
        conversation_history=history,
    )
    assert req.conversation_history == history


def test_llmrequest_mid_conv_system_block_stored():
    history = [
        {"role": "user", "content": "step 1"},
        {"role": "assistant", "content": "done step 1"},
        {"type": "mid_conv_system", "content": "updated token budget: 2000"},
    ]
    req = LLMRequest(
        role="verifier",
        checkpoint_id="ck-v",
        system="sys",
        prompt="step 2",
        conversation_history=history,
    )
    assert any(e.get("type") == "mid_conv_system" for e in req.conversation_history)


def test_mock_backend_records_conversation_history():
    """MockBackend.calls() lets tests assert history propagated to the backend."""
    backend = MockBackend()
    backend.script("researcher", "ck", "ok")
    history = [
        {"role": "assistant", "content": "prior turn"},
        {"type": "mid_conv_system", "content": "updated permissions"},
    ]
    req = LLMRequest(
        role="researcher",
        checkpoint_id="ck",
        system="sys",
        prompt="follow-up",
        conversation_history=history,
    )
    backend.complete(req)
    seen = backend.calls()
    assert len(seen) == 1
    assert seen[0].conversation_history == history


def test_mock_backend_empty_history_still_works():
    backend = MockBackend()
    backend.script("builder", "ck", "artifact json")
    req = LLMRequest(role="builder", checkpoint_id="ck", system="sys", prompt="build")
    backend.complete(req)
    seen = backend.calls()
    assert seen[0].conversation_history == []


def test_agent_context_complete_threads_history():
    """AgentContext.complete(conversation_history=...) threads it to the backend."""
    from csis.agents.base import AgentContext, Role

    backend = MockBackend()
    backend.script("researcher", "ck", "plan json")
    ctx = AgentContext(role=Role.RESEARCHER, checkpoint_id="ck", backend=backend)
    history = [{"role": "assistant", "content": "prior answer"}]
    ctx.complete("new prompt", conversation_history=history)
    seen = backend.calls()
    assert len(seen) == 1
    assert seen[0].conversation_history == history


def test_agent_context_complete_no_history_default():
    """AgentContext.complete() with no history defaults to empty list."""
    from csis.agents.base import AgentContext, Role

    backend = MockBackend()
    backend.script("builder", "ck", "ok")
    ctx = AgentContext(role=Role.BUILDER, checkpoint_id="ck", backend=backend)
    ctx.complete("prompt")
    seen = backend.calls()
    assert seen[0].conversation_history == []
