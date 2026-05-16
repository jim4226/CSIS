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
