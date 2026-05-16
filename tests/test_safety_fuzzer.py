"""Safety fuzzer tests (synthesis recommendation #4).

The default corpus must pass cleanly — every "expect blocked" string is
actually blocked, every "expect allowed" string is allowed. If you add a
new pattern that should be caught, add a corpus row; if the existing
predicates can't catch it, the test fails until they're tightened.
"""
from __future__ import annotations

from pathlib import Path

from csis.config import CSISConfig
from csis.daemon import Daemon, DaemonBudget, _select_backend
from csis.safety.fuzzer import DEFAULT_CORPUS, FuzzCase, SafetyFuzzer


def test_default_corpus_has_no_security_regressions() -> None:
    """Every adversarial corpus row must be blocked. False positives on
    the benign rows are warnings (cycle-5 D1 refinement); security
    regressions are hard-halts."""
    fz = SafetyFuzzer()
    rep = fz.check()
    assert not rep.has_security_regression, (
        f"security regressions: {rep.security_regressions}"
    )
    assert rep.cases_checked == len(DEFAULT_CORPUS)


def test_fuzzer_reports_missed_attack() -> None:
    """If we feed it a corpus that the current predicates *can't* catch,
    the fuzzer correctly reports a failure."""
    corpus = (
        FuzzCase("novel_attack", "Z0Z0Z totally not patterned", expect_blocked=True),
    )
    fz = SafetyFuzzer(corpus)
    rep = fz.check()
    assert not rep.passed
    assert rep.failures[0]["label"] == "novel_attack"


def test_fuzzer_reports_false_positive() -> None:
    """If a benign string is over-blocked, the fuzzer flags it too."""
    corpus = (
        FuzzCase("over_block", "disable the auditor", expect_blocked=False),  # benign expectation, but predicate WILL block
    )
    fz = SafetyFuzzer(corpus)
    rep = fz.check()
    assert not rep.passed
    assert rep.failures[0]["expected"] == "allowed"
    assert rep.failures[0]["got"] == "blocked"


def test_daemon_runs_fuzzer_at_snapshot_boundary(tmp_path: Path) -> None:
    """The daemon's snapshot tick runs the fuzz pass and emits
    safety.fuzz_ok when clean."""
    cfg = CSISConfig.for_tests(tmp_path)
    backend = _select_backend("mock", cfg)
    daemon = Daemon(
        config=cfg, backend=backend,
        budget=DaemonBudget(max_iterations_per_hour=10000, sleep_between_iterations_s=0,
                            snapshot_every_n_iterations=2, heartbeat_every_n_iterations=1),
        max_total_iterations=4,
    )
    daemon.run_forever()
    kinds = [s.event.kind for s in daemon.coord.event_log]
    # 4 iters, snapshot every 2 → 2 fuzz_ok events.
    fuzz_oks = sum(1 for k in kinds if k == "safety.fuzz_ok")
    assert fuzz_oks == 2, kinds


def test_daemon_halts_on_fuzz_security_regression(tmp_path: Path, monkeypatch) -> None:
    """A security regression (blocked → allowed) halts the daemon."""
    cfg = CSISConfig.for_tests(tmp_path)
    backend = _select_backend("mock", cfg)
    daemon = Daemon(
        config=cfg, backend=backend,
        budget=DaemonBudget(max_iterations_per_hour=10000, sleep_between_iterations_s=0,
                            snapshot_every_n_iterations=1, heartbeat_every_n_iterations=1),
        max_total_iterations=10,
    )
    daemon.fuzzer = SafetyFuzzer(corpus=(
        FuzzCase("planted", "totally innocuous text the predicate cannot catch", expect_blocked=True),
    ))
    rc = daemon.run_forever()
    assert rc == 0
    kinds = [s.event.kind for s in daemon.coord.event_log]
    assert "safety.fuzz_failure" in kinds
    assert daemon.stats.iterations_total <= 2


def test_daemon_warns_on_fuzz_false_positive_without_halting(tmp_path: Path) -> None:
    """A false positive (allowed → blocked) emits a warning event but the
    daemon keeps running. Cycle-5 D1 refinement: over-caught benign text
    is a tuning signal, not a halt cause."""
    cfg = CSISConfig.for_tests(tmp_path)
    backend = _select_backend("mock", cfg)
    daemon = Daemon(
        config=cfg, backend=backend,
        budget=DaemonBudget(max_iterations_per_hour=10000, sleep_between_iterations_s=0,
                            snapshot_every_n_iterations=1, heartbeat_every_n_iterations=1),
        max_total_iterations=3,
    )
    # Inject a fuzzer whose corpus expects "disable the auditor" to be
    # ALLOWED — but the current predicates correctly block it, so we get
    # a false-positive row.
    daemon.fuzzer = SafetyFuzzer(corpus=(
        FuzzCase("expected_allowed_but_blocked", "disable the auditor", expect_blocked=False),
    ))
    rc = daemon.run_forever()
    assert rc == 0
    assert daemon.stats.iterations_total == 3
    kinds = [s.event.kind for s in daemon.coord.event_log]
    assert "safety.fuzz_false_positives" in kinds
    assert "safety.fuzz_failure" not in kinds
