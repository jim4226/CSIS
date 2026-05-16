"""Agent base + Role enum + system prompts.

Each role has:
- A name (string, used as actor in event log + LLM dispatch)
- A tier ceiling (enforced by TierGuard at execute() boundaries)
- A system prompt (loaded by the agent on each delegate())
- A checkpoint binding (alpha = builder side, beta = auditor side)

This is intentionally tiny — Phase-0 agents are thin shells over the
backend. The interesting logic lives in the verification + memory layers.
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from csis.backends.base import LLMBackend, LLMRequest, LLMResponse


class Role(str, Enum):
    COORDINATOR = "coordinator"
    RESEARCHER = "researcher"
    BUILDER = "builder"
    CRITIC = "critic"
    VERIFIER = "verifier"
    LIBRARIAN = "librarian"
    AUDITOR = "auditor"


SYSTEM_PROMPTS: dict[Role, str] = {
    Role.COORDINATOR: (
        "You are the Coordinator. Schedule sub-agents, enforce capability tiers, "
        "own the session log. Maximum delegation depth = 1. You never execute "
        "tools yourself; you delegate."
    ),
    Role.RESEARCHER: (
        "You are the Researcher (T0, read-only). Propose ONE falsifiable "
        "hypothesis for the top frontier item. Output JSON: "
        '{"plan_id":"p-..","frontier_item":"..","hypothesis":"..",'
        '"falsification_condition":"..","budget":{"time_s":60,"tokens":5000},'
        '"tier":"T0","tool_calls_planned":[]}'
    ),
    Role.BUILDER: (
        "You are the Builder (T1, sandboxed). Execute the plan in your sandbox. "
        "Output JSON: {\"artifact_id\":\"a-..\",\"plan_id\":\"..\",\"kind\":\"patch\","
        "\"body\":\"<patch text>\",\"body_hash\":\"sha256:..\","
        "\"sandbox_logs\":[]}"
    ),
    Role.CRITIC: (
        "You are the Critic (T0, adversarial). Your one job is to falsify the "
        "claim. Empty output is treated as a verification failure."
    ),
    Role.VERIFIER: (
        "You are the Verifier (T1, different checkpoint than Builder). Run the "
        "pinned graders and the critic. Produce a signed VerifierCertificate "
        "iff all V1 graders pass AND the Critic finds no falsification AND "
        "minimum critic-attempt count is met."
    ),
    Role.LIBRARIAN: (
        "You are the Librarian (T0). Consolidate verified gains into candidate "
        "memory stores. You never promote — you only propose. The Auditor "
        "decides what promotes."
    ),
    Role.AUDITOR: (
        "You are the Auditor (T0, different checkpoint than Builder). Read the "
        "structured query results from the session log (NOT free-form), produce "
        "a why-doc that diffs the candidate against the live store, and sign "
        "the why-doc with the live-store hash as precondition."
    ),
}


@dataclass
class AgentContext:
    role: Role
    checkpoint_id: str
    backend: LLMBackend

    @property
    def actor_name(self) -> str:
        return self.role.value

    def complete(self, prompt: str, max_tokens: int = 2000) -> LLMResponse:
        req = LLMRequest(
            role=self.role.value,
            checkpoint_id=self.checkpoint_id,
            system=SYSTEM_PROMPTS[self.role],
            prompt=prompt,
            max_tokens=max_tokens,
        )
        return self.backend.complete(req)
