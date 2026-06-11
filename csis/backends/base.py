"""LLMBackend abstract base — what every agent calls through.

Two implementations: MockBackend (default, offline, deterministic) and
AnthropicBackend (optional, real API). The interface is intentionally
narrow: one method to complete a prompt for a given role+checkpoint.

The `checkpoint_id` matters for cross-checkpoint pinning (red-team F1).
A mock backend with `builder_checkpoint != auditor_checkpoint` is a
*structural* discipline regardless of whether the underlying model
actually differs — the test suite asserts on the cert that the
identifiers differ, which catches the architecture-level bug.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any


@dataclass
class LLMRequest:
    role: str
    checkpoint_id: str
    system: str
    prompt: str
    tools: list[str] = field(default_factory=list)
    max_tokens: int = 2000
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class LLMResponse:
    role: str
    checkpoint_id: str
    text: str
    tool_calls: list[dict[str, Any]] = field(default_factory=list)
    tokens_in: int = 0
    tokens_out: int = 0
    raw: dict[str, Any] = field(default_factory=dict)


class LLMBackend(ABC):
    """All agents talk to one of these. Returns a response, never throws on
    a normal completion. Network/quota errors are raised so the Coordinator
    can decide whether to escalate or retry."""

    name: str = "base"

    @abstractmethod
    def complete(self, req: LLMRequest) -> LLMResponse: ...

    def checkpoint_identity(self, checkpoint_id: str) -> dict[str, str]:
        """The structural identity the cert records. F1 mitigation: includes
        the model id family so same-model certs are detectable downstream.

        P3 (cycle 2): must return all REQUIRED_IDENTITY_KEYS — checkpoint_id,
        model_id, tool_set, backend.

        Vf1 (cycle 10): the base implementation deliberately leaves
        ``model_id == checkpoint_id`` (the un-declared default). Cross-checkpoint
        enforcement (`assert_cross_checkpoint`) now REJECTS that as "model
        identity not declared", and excludes ``checkpoint_id`` from the
        distinctness count. So a subclass/backend that forgets to assert a real
        model id cannot pass the gate by merely renaming the checkpoint label —
        it MUST declare a structurally-meaningful ``model_id`` (e.g. the
        AnthropicBackend reports the real model; MockBackend.set_model_id sets
        one; csis/loop.py and csis/daemon.py set distinct ids for both
        checkpoints). Subclasses MUST override with real values to be usable on
        either side of a cross-checkpoint cert."""
        return {
            "checkpoint_id": checkpoint_id,
            "backend": self.name,
            "model_id": checkpoint_id,
            "tool_set": "default",
        }
