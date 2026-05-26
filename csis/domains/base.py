"""Domain ABC — what every benchmark adapter must provide.

A Domain plugs into the Coordinator at two points:
  - it owns the V1 grader registry (real subprocess graders, not mock)
  - it owns the curiosity frontier-seed list

Two optional hooks, `system_prompt()` and `allowed_tools()`, are Phase-1
wiring points. They mirror the `AgentDefinition.prompt` and
`AgentDefinition.tools` fields from Anthropic's Agent SDK
(code.claude.com/docs/en/agent-sdk/overview), which establish that an
agent's instructions and tool access are part of its definition, not just
runtime configuration. Returning ``None`` from either preserves Phase-0
behaviour (global SYSTEM_PROMPTS[Role.BUILDER] and no tool filtering).
The Coordinator will pass non-None values through to execute_plan once
P1.7 (sandbox subprocess) lands.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass

from csis.curiosity import Curiosity
from csis.verification.graders import GraderRegistry


@dataclass
class DomainReadiness:
    ready: bool
    reason: str = ""


class Domain(ABC):
    name: str = "abstract"

    @abstractmethod
    def can_run(self) -> DomainReadiness:
        """Verify prerequisites: repo exists, binary in PATH, etc.

        The daemon calls this at startup and refuses to run if False.
        Domains that gracefully degrade (e.g., lean_math without Lean)
        should return ready=True but advertise a fallback grader set.
        """
        ...

    @abstractmethod
    def graders(self) -> GraderRegistry:
        """Return a fresh GraderRegistry with this domain's V1 graders pinned."""
        ...

    @abstractmethod
    def curiosity(self) -> Curiosity:
        """Return a domain-specific curiosity with appropriate seed items."""
        ...

    @abstractmethod
    def describe(self) -> str:
        """One-line description shown by the daemon on startup."""
        ...

    def system_prompt(self) -> str | None:
        """Domain-specific system prompt override for the Builder.

        Return ``None`` to use the global ``SYSTEM_PROMPTS[Role.BUILDER]``
        default. Override in a concrete domain to supply instructions
        tailored to the domain's artifact format, constraints, or
        evaluation criteria.

        Phase-1 wiring point: the Coordinator will pass a non-None value
        to ``execute_plan`` once P1.7 (sandbox subprocess for Builder T1
        work) lands. Until then, a non-None return has no runtime effect
        but documents the domain's intent and makes the interface
        discoverable for contributors adding new benchmark adapters.
        """
        return None

    def allowed_tools(self) -> list[str] | None:
        """Domain-specific tool allowlist for the Builder.

        Return ``None`` to apply no tool filtering (Phase-0 default).
        Override to restrict the Builder to a named set of tools, e.g.
        ``["Read", "Bash"]`` for a domain whose artifacts are shell
        scripts. An empty list means *no tools* are permitted.

        Phase-1 wiring point: maps to ``AgentDefinition.tools`` in
        Anthropic's Agent SDK — the principle that capability restriction
        is part of the agent's definition, not ad-hoc runtime policy.
        """
        return None
