"""Domain ABC — what every benchmark adapter must provide.

A Domain plugs into the Coordinator at two points:
  - it owns the V1 grader registry (real subprocess graders, not mock)
  - it owns the curiosity frontier-seed list

The Builder's LLM prompt is unchanged in Phase-0; future cycles can let
the domain supply a domain-specific system prompt.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Callable

from csis.curiosity import Curiosity
from csis.verification.graders import GraderRegistry


@dataclass
class DomainReadiness:
    ready: bool
    reason: str = ""


@dataclass
class ContextEngine:
    """Deterministic retrieval layer for a domain's data corpus.

    Separates agent creative work from data access so retrieval variance
    does not contaminate grader results. When a domain supplies one, the
    Coordinator injects fetch() output as structured context instead of
    letting agents discover data via free-form tool calls.
    """

    label: str
    fetch: Callable[[], str]


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

    def context_engine(self) -> ContextEngine | None:
        """Deterministic retrieval layer for this domain's data, or None.

        Not abstract — existing domains that use agent-driven retrieval
        return None and need no change. Override when the domain can
        supply a pinned, auditable corpus (theorem databases, test-case
        fixtures, reference implementations) that should bypass the
        agent's free-form tool calls.
        """
        return None
