"""Self-improvement domain — CSIS works on its own codebase.

Wraps PRMaintenanceDomain pointed at the CSIS repo root. The Builder's
artifacts would, in principle, modify csis/ itself. Phase-0 prudence:
the diff_scope grader is *more* strict here — touching csis/safety/ or
csis/agents/coordinator.py is forbidden without explicit human review.
"""
from __future__ import annotations

from pathlib import Path

from csis.contracts import Artifact, GraderResult
from csis.curiosity import Curiosity
from csis.domains.base import Domain, DomainReadiness
from csis.domains.pr_maintenance import PRMaintenanceDomain
from csis.verification.graders import GraderRegistry


_SELF_IMPROVE_SEEDS = (
    "test gap: csis module with no test coverage",
    "docs: csis module without module-level docstring",
    "skill candidate: factor a repeated 5-line block in csis/agents/",
    "lint pass: ruff scan of csis/",
    "type pass: mypy scan of csis/",
    "small refactor: rename for clarity in a leaf module",
    "test corpus growth: add a new edge case for an existing test",
    "auto-snapshot review: read the latest snapshot, propose one improvement",
)


class SelfImproveDomain(Domain):
    name = "self_improve"

    def __init__(self, csis_root: str | Path | None = None) -> None:
        # Default: find csis root from this file's location.
        if csis_root is None:
            csis_root = Path(__file__).resolve().parent.parent.parent
        self.csis_root = Path(csis_root).resolve()
        self._inner = PRMaintenanceDomain(self.csis_root, run_tests=True, run_lint=False, run_mypy=False)

    def can_run(self) -> DomainReadiness:
        if not (self.csis_root / "csis").exists():
            return DomainReadiness(False, f"csis/ subdir not found in {self.csis_root}")
        return self._inner.can_run()

    def describe(self) -> str:
        return f"self-improvement on the CSIS codebase at {self.csis_root}"

    def curiosity(self) -> Curiosity:
        return Curiosity(seeds=_SELF_IMPROVE_SEEDS)

    def graders(self) -> GraderRegistry:
        reg = self._inner.graders()
        # Bind into closures.
        root = self.csis_root

        # Stricter diff-scope: don't let the system modify load-bearing files.
        def self_improve_diff_scope(artifact: Artifact) -> GraderResult:
            body = artifact.body
            forbidden = (
                "csis/safety/",
                "csis/agents/coordinator.py",
                "csis/agents/auditor.py",
                "csis/agents/verifier.py",
                "csis/verification/certificates.py",
                "csis/verification/graders.py",
                "csis/memory/store.py",
                "csis/memory/trust.py",
                "csis/substrate/event_log.py",
                "csis/substrate/capability.py",
                "csis/domains/",
                "csis/daemon.py",
                "csis/config.py",
                "csis/loop.py",
            )
            touched = [p for p in forbidden if p in body]
            return GraderResult(
                grader="self_improve_diff_scope",
                passed=not touched,
                detail=(f"forbidden paths touched: {touched}" if touched else "scope ok"),
            )

        # Replace the inner diff_scope with the stricter one.
        if "pr_diff_scope" in reg.pinned:
            del reg.pinned["pr_diff_scope"]
        reg.pin("self_improve_diff_scope", self_improve_diff_scope)
        return reg
