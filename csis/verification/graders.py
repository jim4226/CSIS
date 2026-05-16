"""V1 graders — programmatic verifiers.

Phase-0 ships PR-maintenance graders (per brain/plans/02-verification.md).
Each grader is a pure function `(artifact, context) -> GraderResult`. They
key off `artifact.body` plus `artifact.extra.get('scenarios')` so the
prototype can script outcomes deterministically.

F6 mitigation (corrupted grader): the GraderRegistry pins each grader's
source-hash at task start. If the file/function content changes mid-task,
the cert build fails. We compute the hash from the function's source code
via `inspect.getsource`.
"""
from __future__ import annotations

import hashlib
import inspect
from dataclasses import dataclass, field
from typing import Callable

from csis.contracts import Artifact, GraderResult


Grader = Callable[[Artifact], GraderResult]


@dataclass
class PinnedGrader:
    name: str
    fn: Grader
    source_hash: str  # sha256:<hex> of the function's source at pin time


@dataclass
class GraderRegistry:
    """Pinned grader set captured at task start.

    The Verifier runs `evaluate(artifact)` against the pinned set. If any
    grader's current source no longer matches its pinned hash, the
    Verifier refuses to produce a cert.
    """

    pinned: dict[str, PinnedGrader] = field(default_factory=dict)

    def pin(self, name: str, fn: Grader) -> None:
        src = inspect.getsource(fn)
        h = "sha256:" + hashlib.sha256(src.encode("utf-8")).hexdigest()
        self.pinned[name] = PinnedGrader(name=name, fn=fn, source_hash=h)

    def verify_pinned_hashes(self) -> tuple[bool, list[str]]:
        """Return (ok, list of grader names whose source has drifted)."""
        drifted: list[str] = []
        for pg in self.pinned.values():
            current_src = inspect.getsource(pg.fn)
            current_hash = "sha256:" + hashlib.sha256(current_src.encode("utf-8")).hexdigest()
            if current_hash != pg.source_hash:
                drifted.append(pg.name)
        return (not drifted, drifted)

    def evaluate(self, artifact: Artifact) -> list[GraderResult]:
        results: list[GraderResult] = []
        for pg in self.pinned.values():
            try:
                results.append(pg.fn(artifact))
            except Exception as exc:  # noqa: BLE001 — a grader that throws is a fail
                results.append(GraderResult(grader=pg.name, passed=False, detail=f"raised: {exc!r}"))
        return results


# ---- Phase-0 PR-maintenance grader set ------------------------------------
# These mock graders read artifact.extra["scenarios"] for deterministic
# outcomes. In a real run they'd shell out to pytest/mypy/ruff/etc.


def tests_pass_grader(artifact: Artifact) -> GraderResult:
    """Did the unit test suite pass after applying the patch?"""
    scenarios = (artifact.extra if hasattr(artifact, "extra") else {})
    if isinstance(getattr(artifact, "extra", None), dict):
        scenarios = artifact.extra
    else:
        scenarios = {}
    passed = bool(scenarios.get("tests_pass", True))
    return GraderResult(grader="tests_pass", passed=passed, detail="mock")


def lint_grader(artifact: Artifact) -> GraderResult:
    scenarios = getattr(artifact, "extra", {}) or {}
    passed = bool(scenarios.get("lint_clean", True))
    return GraderResult(grader="lint", passed=passed, detail="mock")


def typecheck_grader(artifact: Artifact) -> GraderResult:
    scenarios = getattr(artifact, "extra", {}) or {}
    passed = bool(scenarios.get("type_clean", True))
    return GraderResult(grader="typecheck", passed=passed, detail="mock")


def coverage_delta_grader(artifact: Artifact) -> GraderResult:
    scenarios = getattr(artifact, "extra", {}) or {}
    delta = float(scenarios.get("coverage_delta", 0.0))
    passed = delta >= -0.005  # ≤ 0.5% regression tolerated
    return GraderResult(
        grader="coverage_delta",
        passed=passed,
        detail=f"delta={delta:+.4f}",
        metrics={"coverage_delta": delta},
    )


def diff_scope_grader(artifact: Artifact) -> GraderResult:
    """F5/F6-adjacent: reject diffs that touch grader files or eval scaffolding."""
    body = artifact.body
    forbidden_paths = ("tests/", "csis/verification/graders.py", ".github/", "pyproject.toml")
    touched = [p for p in forbidden_paths if p in body]
    return GraderResult(
        grader="diff_scope",
        passed=not touched,
        detail=(f"forbidden paths touched: {touched}" if touched else "scope ok"),
    )


def perf_regression_grader(artifact: Artifact) -> GraderResult:
    scenarios = getattr(artifact, "extra", {}) or {}
    ratio = float(scenarios.get("perf_ratio", 1.0))  # 1.0 = same as base
    passed = ratio <= 1.20  # ≤20% slowdown
    return GraderResult(
        grader="perf_regression",
        passed=passed,
        detail=f"p95_ratio={ratio:.3f}",
        metrics={"perf_ratio": ratio},
    )


def make_default_pr_registry() -> GraderRegistry:
    reg = GraderRegistry()
    reg.pin("tests_pass", tests_pass_grader)
    reg.pin("lint", lint_grader)
    reg.pin("typecheck", typecheck_grader)
    reg.pin("coverage_delta", coverage_delta_grader)
    reg.pin("diff_scope", diff_scope_grader)
    reg.pin("perf_regression", perf_regression_grader)
    return reg
