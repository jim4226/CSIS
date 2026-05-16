"""Regression tests for cycle-7 red-team findings (F1-F7)."""
from __future__ import annotations

import re
import threading
import time
from pathlib import Path

import pytest

from csis.budget import BudgetTracker, _BackendTracker
from csis.config import CSISConfig
from csis.curiosity import Curiosity, FrontierItem
from csis.memory.store import MemoryHierarchy
from csis.safety.constitution import Constitution
from csis.safety.tripwires import Tripwires


# ---- F1 — __init_subclass__ catches mangled __wrapped --------------------


def test_F1_subclass_with_double_underscore_wrapped_rejected() -> None:
    """The cycle-6 docstring acknowledged this as a 'known limit';
    cycle-7 actually fixes it. Python name-mangles `__wrapped` inside
    a subclass body to `_<subclass>__wrapped`; the guard now checks for
    any name ending in `__wrapped`."""
    def define_with_double_underscore():
        class EvilB(_BackendTracker):
            __wrapped = "smuggled"  # Python mangles → _EvilB__wrapped
        return EvilB

    with pytest.raises(TypeError):
        define_with_double_underscore()


def test_F1_subclass_with_arbitrary_mangled_name_rejected() -> None:
    """Even if someone tries to spell out the mangled form directly."""
    def define_with_arbitrary_mangle():
        class EvilC(_BackendTracker):
            _Foo__wrapped = "smuggled"  # arbitrary mangle-like name
        return EvilC

    with pytest.raises(TypeError):
        define_with_arbitrary_mangle()


# ---- F2 — tier-mismatch cleanup uses public API, doesn't over-discard ---


def test_F2_has_candidate_public_api(tmp_path: Path) -> None:
    """has_candidate is the public surface; tests don't have to reach
    into the private _candidate dict."""
    h = MemoryHierarchy.open(tmp_path)
    assert not h.episodic.has_candidate("nope")
    from csis.contracts import MemoryEntry
    from csis.memory.trust import TrustLevel
    e = MemoryEntry(entry_id="x", tier="episodic", content="c",
                    trust=TrustLevel.CANDIDATE, why_tag="t", created_at=time.time())
    h.episodic.write_candidate(e)
    assert h.episodic.has_candidate("x")
    h.episodic.discard_candidate("x", reason="test")
    assert not h.episodic.has_candidate("x")


def test_F2_tier_mismatch_does_not_over_discard_legitimate_candidates(tmp_path: Path) -> None:
    """A legitimate candidate in tier X with entry_id E must NOT be
    discarded just because a bad candidate in tier Y also has entry_id E.
    Cycle-7 F2: discard only from tiers that ACTUALLY have the id."""
    from csis.agents.coordinator import Coordinator
    from csis.backends.mock import MockBackend
    from csis.contracts import MemoryEntry
    from csis.memory.trust import TrustLevel
    import csis.agents.coordinator as coord_mod

    cfg = CSISConfig.for_tests(tmp_path)
    backend = MockBackend()
    backend.set_model_id(cfg.builder_checkpoint, "mock-opus")
    backend.set_model_id(cfg.auditor_checkpoint, "mock-sonnet")
    backend.script("researcher", cfg.builder_checkpoint,
        '{"plan_id":"p","frontier_item":"x","hypothesis":"benign",'
        '"falsification_condition":"y","budget":{"time_s":1,"tokens":10},'
        '"tier":"T0","tool_calls_planned":[]}')
    backend.script("builder", cfg.builder_checkpoint,
        '{"artifact_id":"a","plan_id":"p","kind":"patch","body":"# x\\n",'
        '"body_hash":"sha256:zz","sandbox_logs":[],'
        '"extra":{"tests_pass":true,"lint_clean":true,"type_clean":true,'
        '"coverage_delta":0.0,"perf_ratio":1.0}}')
    backend.script("critic", cfg.auditor_checkpoint,
        '[{"attempt":"a","falsified":false},{"attempt":"b","falsified":false},{"attempt":"c","falsified":false}]')

    coord = Coordinator(config=cfg, backend=backend)

    # Pre-seed semantic with a LEGITIMATE candidate that happens to share
    # an entry_id with what the buggy Librarian will produce.
    shared_id = "shared-id-42"
    legit = MemoryEntry(entry_id=shared_id, tier="semantic", content="legit",
                       trust=TrustLevel.CANDIDATE, why_tag="legit", created_at=time.time())
    coord.hierarchy.semantic.write_candidate(legit)

    # Buggy Librarian: produces a bad candidate with the same id in causal.
    original = coord_mod.consolidate_to_candidates

    def bad(*args, **kwargs):
        from csis.memory.trust import TrustLevel as TL
        bad_entry = MemoryEntry(
            entry_id=shared_id, tier="causal", content="bad",
            trust=TL.CANDIDATE, why_tag="bad", created_at=time.time(),
        )
        kwargs["hierarchy"].tier("causal").write_candidate(bad_entry)
        return [bad_entry]

    coord_mod.consolidate_to_candidates = bad
    try:
        res = coord.run_iteration(frontier_item="test")
    finally:
        coord_mod.consolidate_to_candidates = original

    assert res.outcome.startswith("rolled-back:tier-mismatch"), res.outcome
    # F2 (cycle-7): the bad candidate (causal, shared_id) MUST be
    # discarded — its tier matches the entry.tier the handler uses.
    assert not coord.hierarchy.causal.has_candidate(shared_id)
    # The legitimate candidate (semantic, shared_id) MUST remain because
    # the handler now only touches entry.tier, not all five tiers.
    assert coord.hierarchy.semantic.has_candidate(shared_id), (
        "F2 regression: legitimate semantic candidate was over-discarded"
    )


# ---- F3 — mock-daemon methods work without locking -----------------------


def test_F3_mock_daemon_can_record_without_locking(tmp_path: Path, monkeypatch) -> None:
    """A BudgetTracker without a cap must not enter the file lock on
    any method. Mock daemons on POSIX-no-fcntl now work end-to-end,
    not just at __init__."""
    import sys
    if sys.platform == "win32":
        pytest.skip("POSIX-only fcntl-removal test")
    monkeypatch.setitem(sys.modules, "fcntl", None)

    t = BudgetTracker(tmp_path / "budget.json")
    assert t.max_cost_per_day_usd is None
    # These would have raised LockUnavailable in cycle 6 even though
    # __init__ now skips. Now all of them go through _maybe_locked.
    t.record("mock-opus", 100, 50)
    t.check_or_raise()
    snap = t.snapshot()
    assert snap["today"]["calls"] == 1


# ---- F4 — salt taken from FrontierItem, not regex ------------------------


def test_F4_salt_logged_from_frontier_item_not_regex(tmp_path: Path) -> None:
    """Cycle-6 E10 used a regex on the frontier_item string. F4 fix:
    daemon passes FrontierItem.salt explicitly. Tests confirm that
    legitimate `[salt=X]` substrings in frontier text DON'T attach a
    salt unless one was actually generated by curiosity."""
    from csis.agents.coordinator import Coordinator
    from csis.backends.mock import MockBackend

    cfg = CSISConfig.for_tests(tmp_path)
    backend = MockBackend()
    backend.set_model_id(cfg.builder_checkpoint, "mock-opus")
    backend.set_model_id(cfg.auditor_checkpoint, "mock-sonnet")
    backend.script("researcher", cfg.builder_checkpoint,
        '{"plan_id":"p","frontier_item":"x","hypothesis":"x",'
        '"falsification_condition":"y","budget":{"time_s":1,"tokens":10},'
        '"tier":"T0","tool_calls_planned":[]}')
    coord = Coordinator(config=cfg, backend=backend)

    # Frontier text contains a misleading [salt=999] but NO salt is passed.
    coord.run_iteration(
        frontier_item="research paper: 'analysis [salt=999] of cryptography'",
        salt=None,
    )
    iter_starts = [s for s in coord.event_log if s.event.kind == "iter.start"]
    assert iter_starts[-1].event.payload.get("salt") is None

    # When salt IS passed explicitly, it's recorded.
    coord.run_iteration(frontier_item="gap-driven [salt=4242]", salt=4242)
    iter_starts = [s for s in coord.event_log if s.event.kind == "iter.start"]
    assert iter_starts[-1].event.payload.get("salt") == 4242


# ---- F5 — bounded history --------------------------------------------------


def test_F5_history_bounded_by_max() -> None:
    """history_max caps the deque size; oldest firings are evicted FIFO."""
    tw = Tripwires(history_max=50)
    for i in range(150):
        tw.scan_text(f"exfiltrate the api_key {i}")
    assert tw.history_size() == 50
    # The history is bounded; no matter how many distinct inputs we
    # feed, size stays at 50.
    for i in range(50_000):
        tw.scan_text(f"override the shutdown signal {i}")
    assert tw.history_size() == 50


def test_F5_default_history_max_is_10k() -> None:
    tw = Tripwires()
    assert tw._history_max == 10_000


# ---- F6 — Constitution add_pattern is thread-safe -----------------------


def test_F6_concurrent_add_pattern_preserves_all() -> None:
    """20 threads each add a unique pattern; assert ALL of them end up
    in the final patterns tuple (no lost updates)."""
    c = Constitution()
    initial_count = len(c.patterns())

    def add_n(n: int) -> None:
        for i in range(50):
            c.add_pattern(re.compile(rf"\bunique_thread_{n}_{i}\b"))

    threads = [threading.Thread(target=add_n, args=(n,)) for n in range(20)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    final = c.patterns()
    # 20 threads × 50 patterns each = 1000 new patterns.
    assert len(final) == initial_count + 1000, (
        f"lost-update detected: expected {initial_count + 1000}, got {len(final)}"
    )


# ---- F7 — fuzz event dedup -----------------------------------------------


def test_F7_daemon_dedupes_stable_false_positive_signature(tmp_path: Path) -> None:
    """A daemon that hits the same false-positive set on every snapshot
    must emit safety.fuzz_false_positives ONLY when the signature
    changes — not on every snapshot."""
    from csis.daemon import Daemon, DaemonBudget, _select_backend
    from csis.safety.fuzzer import DEFAULT_CORPUS, FuzzCase, SafetyFuzzer

    cfg = CSISConfig.for_tests(tmp_path)
    backend = _select_backend("mock", cfg)
    daemon = Daemon(
        config=cfg, backend=backend,
        budget=DaemonBudget(max_iterations_per_hour=10000, sleep_between_iterations_s=0,
                            snapshot_every_n_iterations=1, heartbeat_every_n_iterations=1),
        max_total_iterations=5,
    )
    # Inject a corpus that always produces the same false-positive.
    daemon.fuzzer = SafetyFuzzer(
        corpus=(FuzzCase("planted_fp", "disable the auditor", expect_blocked=False),),
        constitution=daemon.coord.constitution,
        tripwires=daemon.coord.tripwires,
    )
    daemon.run_forever()

    fp_events = [s for s in daemon.coord.event_log if s.event.kind == "safety.fuzz_false_positives"]
    # 5 snapshots → without dedupe = 5 events; with dedupe = 1 event.
    assert len(fp_events) == 1, (
        f"F7 regression: expected 1 deduped event, got {len(fp_events)}"
    )
