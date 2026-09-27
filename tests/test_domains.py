"""Domain adapter smoke tests.

These don't exercise full subprocess paths (would require pytest installed
inside a target repo); they exercise the adapter contracts:
  - can_run() returns DomainReadiness with sensible reason
  - graders() returns a GraderRegistry that passes verify_pinned_hashes
  - curiosity() returns a Curiosity with non-empty seeds
  - context_engine() returns None or a valid ContextEngine
"""
from __future__ import annotations

import shutil
from pathlib import Path

import pytest

from csis.domains.base import ContextEngine, Domain, DomainReadiness
from csis.domains.lean_math import LeanMathDomain
from csis.domains.pr_maintenance import PRMaintenanceDomain
from csis.domains.self_improve import SelfImproveDomain
from csis.verification.graders import GraderRegistry


def _check_domain_contract(d: Domain) -> None:
    readiness = d.can_run()
    assert isinstance(readiness, DomainReadiness)
    reg = d.graders()
    assert isinstance(reg, GraderRegistry)
    assert reg.pinned, "graders() returned an empty registry"
    ok, drifted = reg.verify_pinned_hashes()
    assert ok and not drifted
    cur = d.curiosity()
    assert cur.seeds and len(cur.seeds) >= 3
    assert d.describe()
    engine = d.context_engine()
    assert engine is None or isinstance(engine, ContextEngine)


def test_pr_maintenance_contract_with_fake_repo(tmp_path: Path) -> None:
    # Create a minimal fake git repo so can_run can find .git/.
    (tmp_path / ".git").mkdir()
    dom = PRMaintenanceDomain(repo_path=tmp_path, run_tests=False, run_lint=False, run_mypy=False)
    _check_domain_contract(dom)
    readiness = dom.can_run()
    assert readiness.ready, readiness.reason


def test_pr_maintenance_can_run_false_when_repo_missing(tmp_path: Path) -> None:
    dom = PRMaintenanceDomain(repo_path=tmp_path / "does-not-exist")
    readiness = dom.can_run()
    assert not readiness.ready
    assert "not found" in readiness.reason


def test_self_improve_contract() -> None:
    dom = SelfImproveDomain()
    _check_domain_contract(dom)
    # The graders include the stricter diff-scope grader.
    reg = dom.graders()
    assert "self_improve_diff_scope" in reg.pinned
    assert "pr_diff_scope" not in reg.pinned


def test_lean_math_contract_graceful() -> None:
    dom = LeanMathDomain(graceful_fallback=True)
    _check_domain_contract(dom)
    # Without Lean installed, graceful_fallback still reports ready=True.
    readiness = dom.can_run()
    assert readiness.ready  # graceful mode


def test_lean_math_no_graceful_fails_without_lean() -> None:
    if shutil.which("lean") is not None:
        pytest.skip("lean is installed; test only meaningful when missing")
    dom = LeanMathDomain(graceful_fallback=False)
    readiness = dom.can_run()
    assert not readiness.ready


def test_self_improve_diff_scope_blocks_load_bearing_files() -> None:
    from csis.contracts import Artifact
    from csis.substrate.hashing import hash_artifact

    dom = SelfImproveDomain()
    reg = dom.graders()
    grader = reg.pinned["self_improve_diff_scope"].fn

    body = (
        "diff --git a/csis/agents/coordinator.py b/csis/agents/coordinator.py\n"
        "+ subtle change\n"
    )
    art = Artifact(
        artifact_id="a", plan_id="p", kind="patch",
        body=body, body_hash=hash_artifact(body), extra={},
    )
    result = grader(art)
    assert not result.passed
    assert "forbidden" in result.detail


def test_daemon_select_domain_known_names(tmp_path: Path) -> None:
    """Daemon's _select_domain helper recognizes all three + 'none'."""
    from csis.daemon import _select_domain

    assert _select_domain(None, repo_path=None) is None
    assert _select_domain("none", repo_path=None) is None

    # pr_maintenance requires repo path
    with pytest.raises(SystemExit):
        _select_domain("pr_maintenance", repo_path=None)

    # Set up a fake repo
    (tmp_path / ".git").mkdir()
    dom = _select_domain("pr_maintenance", repo_path=str(tmp_path))
    assert dom is not None and dom.name == "pr_maintenance"

    dom = _select_domain("self_improve", repo_path=None)
    assert dom is not None and dom.name == "self_improve"

    dom = _select_domain("lean_math", repo_path=None)
    assert dom is not None and dom.name == "lean_math"

    with pytest.raises(SystemExit):
        _select_domain("bogus_domain", repo_path=None)


def test_context_engine_default_is_none(tmp_path: Path) -> None:
    (tmp_path / ".git").mkdir()
    domains: list[Domain] = [
        PRMaintenanceDomain(repo_path=tmp_path, run_tests=False, run_lint=False, run_mypy=False),
        SelfImproveDomain(),
        LeanMathDomain(graceful_fallback=True),
    ]
    for d in domains:
        assert d.context_engine() is None, f"{d.name}.context_engine() should default to None"


def test_context_engine_custom_domain_returns_engine() -> None:
    from csis.curiosity import Curiosity

    class _CorpusDomain(Domain):
        name = "corpus_test"

        def can_run(self) -> DomainReadiness:
            return DomainReadiness(True, "test")

        def graders(self) -> GraderRegistry:
            reg = GraderRegistry()
            reg.pin("always_pass", lambda a: __import__("csis.contracts", fromlist=["GraderResult"]).GraderResult(grader="always_pass", passed=True))
            return reg

        def curiosity(self) -> Curiosity:
            return Curiosity(seeds=("a", "b", "c"))

        def describe(self) -> str:
            return "corpus test domain"

        def context_engine(self) -> ContextEngine:
            return ContextEngine(label="test-corpus", fetch=lambda: "deterministic corpus data")

    d = _CorpusDomain()
    engine = d.context_engine()
    assert engine is not None
    assert isinstance(engine, ContextEngine)
    assert engine.label == "test-corpus"
    assert engine.fetch() == "deterministic corpus data"
