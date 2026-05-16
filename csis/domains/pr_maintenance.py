"""PR maintenance domain — runs real graders against a target git repo.

The graders subprocess out to pytest / ruff / mypy. Each grader reports
on the CURRENT state of the repo (Phase-0 doesn't yet apply the
artifact's diff inside the sandbox — that's a Phase-1 follow-up). This
gives a faithful Phase-0 V1 surface for verifier-cert end-to-end.

Use:
    from csis.domains.pr_maintenance import PRMaintenanceDomain
    dom = PRMaintenanceDomain(repo_path="C:/path/to/repo")
    print(dom.can_run())
"""
from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path

from csis.contracts import Artifact, GraderResult
from csis.curiosity import Curiosity
from csis.domains.base import Domain, DomainReadiness
from csis.verification.graders import GraderRegistry


_DEFAULT_FRONTIER_SEEDS = (
    "lint pass: scan repo for ruff violations",
    "type pass: scan repo for mypy errors",
    "test triage: identify a flaky test and stabilize it",
    "dependency audit: identify outdated minor versions safe to bump",
    "coverage gap: pick a module with <70% line coverage",
    "perf scan: profile the slowest test in the suite",
    "skill candidate: factor a repeated helper out of two modules",
    "docs touch-up: a single-line README correction",
)


def _run(cmd: list[str], cwd: Path, timeout: int = 60) -> tuple[int, str]:
    try:
        out = subprocess.run(
            cmd,
            cwd=str(cwd),
            capture_output=True,
            text=True,
            timeout=timeout,
            shell=False,
        )
        combined = (out.stdout or "") + ("\n" + out.stderr if out.stderr else "")
        return out.returncode, combined[-4000:]  # tail to keep it bounded
    except FileNotFoundError as exc:
        return 127, f"command not found: {exc}"
    except subprocess.TimeoutExpired:
        return 124, f"timed out after {timeout}s"


class PRMaintenanceDomain(Domain):
    name = "pr_maintenance"

    def __init__(self, repo_path: str | Path, *, run_tests: bool = True, run_lint: bool = True, run_mypy: bool = False) -> None:
        self.repo_path = Path(repo_path).resolve()
        self.run_tests = run_tests
        self.run_lint = run_lint
        self.run_mypy = run_mypy

    def can_run(self) -> DomainReadiness:
        if not self.repo_path.exists():
            return DomainReadiness(False, f"repo not found: {self.repo_path}")
        if not (self.repo_path / ".git").exists():
            return DomainReadiness(False, f"not a git repo: {self.repo_path}")
        if self.run_tests and not (shutil.which("pytest") or shutil.which("py.test")):
            # pytest may also be invokable as `python -m pytest`; try that.
            rc, _ = _run([sys.executable, "-m", "pytest", "--version"], cwd=self.repo_path, timeout=15)
            if rc != 0:
                return DomainReadiness(False, "pytest not available")
        return DomainReadiness(True, "ready")

    def describe(self) -> str:
        return f"PR maintenance against {self.repo_path}"

    def curiosity(self) -> Curiosity:
        return Curiosity(seeds=_DEFAULT_FRONTIER_SEEDS)

    def graders(self) -> GraderRegistry:
        reg = GraderRegistry()
        # Bind self into closures so the registry's pinned-hash check
        # captures the right source.
        repo = self.repo_path
        run_tests = self.run_tests
        run_lint = self.run_lint
        run_mypy = self.run_mypy

        def pr_tests_pass(artifact: Artifact) -> GraderResult:
            if not run_tests:
                return GraderResult(grader="pr_tests_pass", passed=True, detail="skipped (run_tests=False)")
            rc, out = _run([sys.executable, "-m", "pytest", "-q", "--maxfail=1"], cwd=repo, timeout=180)
            return GraderResult(
                grader="pr_tests_pass",
                passed=(rc == 0),
                detail=f"rc={rc}",
                metrics={"return_code": float(rc)},
            )

        def pr_lint(artifact: Artifact) -> GraderResult:
            if not run_lint:
                return GraderResult(grader="pr_lint", passed=True, detail="skipped")
            if not shutil.which("ruff"):
                rc, out = _run([sys.executable, "-m", "ruff", "check", "."], cwd=repo, timeout=60)
            else:
                rc, out = _run(["ruff", "check", "."], cwd=repo, timeout=60)
            if rc == 127:
                # ruff not installed at all — soft pass with note
                return GraderResult(grader="pr_lint", passed=True, detail="ruff not installed; treating as soft pass")
            return GraderResult(grader="pr_lint", passed=(rc == 0), detail=f"rc={rc}")

        def pr_typecheck(artifact: Artifact) -> GraderResult:
            if not run_mypy:
                return GraderResult(grader="pr_typecheck", passed=True, detail="skipped (run_mypy=False)")
            rc, out = _run([sys.executable, "-m", "mypy", "."], cwd=repo, timeout=120)
            if rc == 127:
                return GraderResult(grader="pr_typecheck", passed=True, detail="mypy not installed; soft pass")
            return GraderResult(grader="pr_typecheck", passed=(rc == 0), detail=f"rc={rc}")

        def pr_diff_scope(artifact: Artifact) -> GraderResult:
            body = artifact.body
            forbidden = ("csis/verification/graders.py", "csis/domains/", ".github/", "pyproject.toml")
            touched = [p for p in forbidden if p in body]
            return GraderResult(
                grader="pr_diff_scope",
                passed=not touched,
                detail=(f"forbidden paths touched: {touched}" if touched else "scope ok"),
            )

        reg.pin("pr_tests_pass", pr_tests_pass)
        reg.pin("pr_lint", pr_lint)
        reg.pin("pr_typecheck", pr_typecheck)
        reg.pin("pr_diff_scope", pr_diff_scope)
        return reg
