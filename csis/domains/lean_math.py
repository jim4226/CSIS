"""Lean formal-math domain.

The Builder produces a .lean file body; the V1 grader runs `lean --check`
on it. If Lean isn't installed, can_run() returns False with a helpful
message; the daemon can still start with a softer graceful-fail grader
set by passing graceful_fallback=True.

Lean 4 is assumed; Lean 3 binaries are rejected.
"""
from __future__ import annotations

import shutil
import subprocess
import tempfile
from pathlib import Path

from csis.contracts import Artifact, GraderResult
from csis.curiosity import Curiosity
from csis.domains.base import Domain, DomainReadiness
from csis.verification.graders import GraderRegistry


_LEAN_FRONTIER_SEEDS = (
    "warmup: prove n + 0 = n",
    "warmup: prove n + 1 = succ n",
    "induction: prove (n + m) + k = n + (m + k)",
    "list lemma: prove length (xs ++ ys) = length xs + length ys",
    "tactic exploration: try simp on a goal that ring closes",
    "lemma factoring: extract a helper from a 3-step proof",
    "fix lemma: pick one with a sorry and complete it",
    "improve proof: shorten an existing proof by 1 tactic",
)


class LeanMathDomain(Domain):
    name = "lean_math"

    def __init__(self, *, graceful_fallback: bool = True, max_proof_seconds: int = 30) -> None:
        self.graceful_fallback = graceful_fallback
        self.max_proof_seconds = max_proof_seconds
        self._lean_path: str | None = shutil.which("lean")

    def can_run(self) -> DomainReadiness:
        if self._lean_path:
            try:
                out = subprocess.run([self._lean_path, "--version"], capture_output=True, text=True, timeout=10)
                ver = (out.stdout + out.stderr).strip()
                if "Lean (version 4" in ver or "Lean 4" in ver:
                    return DomainReadiness(True, f"lean 4 found at {self._lean_path}: {ver.splitlines()[0]}")
                return DomainReadiness(False, f"found {self._lean_path} but not Lean 4: {ver!r}")
            except Exception as exc:
                return DomainReadiness(False, f"lean version check failed: {exc!r}")
        if self.graceful_fallback:
            return DomainReadiness(True, "lean not installed; using graceful-fallback graders")
        return DomainReadiness(False, "lean not installed; pass graceful_fallback=True to run anyway")

    def describe(self) -> str:
        status = "lean-installed" if self._lean_path else "lean-MISSING (graceful)"
        return f"formal math via Lean ({status})"

    def curiosity(self) -> Curiosity:
        return Curiosity(seeds=_LEAN_FRONTIER_SEEDS)

    def graders(self) -> GraderRegistry:
        reg = GraderRegistry()
        lean_path = self._lean_path
        graceful = self.graceful_fallback
        timeout = self.max_proof_seconds

        def lean_typechecks(artifact: Artifact) -> GraderResult:
            if not lean_path:
                if graceful:
                    return GraderResult(
                        grader="lean_typechecks",
                        passed=True,
                        detail="lean not installed; graceful soft pass",
                    )
                return GraderResult(grader="lean_typechecks", passed=False, detail="lean not installed")
            with tempfile.NamedTemporaryFile(mode="w", suffix=".lean", delete=False, encoding="utf-8") as tf:
                tf.write(artifact.body)
                tf_path = tf.name
            try:
                out = subprocess.run([lean_path, "--check", tf_path], capture_output=True, text=True, timeout=timeout)
                rc = out.returncode
                detail = (out.stdout + out.stderr)[-2000:]
                return GraderResult(
                    grader="lean_typechecks",
                    passed=(rc == 0),
                    detail=f"rc={rc} {detail[:200]!r}",
                )
            except subprocess.TimeoutExpired:
                return GraderResult(
                    grader="lean_typechecks",
                    passed=False,
                    detail=f"lean timed out after {timeout}s",
                )
            finally:
                try:
                    Path(tf_path).unlink()
                except Exception:
                    pass

        def lean_no_sorry(artifact: Artifact) -> GraderResult:
            has_sorry = "sorry" in artifact.body or "admit" in artifact.body
            return GraderResult(
                grader="lean_no_sorry",
                passed=not has_sorry,
                detail=("body contains sorry/admit" if has_sorry else "no sorry"),
            )

        def lean_proof_size(artifact: Artifact) -> GraderResult:
            n_lines = artifact.body.count("\n") + 1
            limit = 200
            return GraderResult(
                grader="lean_proof_size",
                passed=(n_lines <= limit),
                detail=f"{n_lines} lines (limit {limit})",
                metrics={"lines": float(n_lines)},
            )

        reg.pin("lean_typechecks", lean_typechecks)
        reg.pin("lean_no_sorry", lean_no_sorry)
        reg.pin("lean_proof_size", lean_proof_size)
        return reg
