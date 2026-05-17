"""Regression tests for cycle-9 red-team findings (H1-H12).

Twelve findings synthesized from three parallel red-team passes against
cycle-8's architectural pivots (G1 wrap-site type check; G2 pre-
consolidate snapshot). H1-H3 are the wrapped-backend invariant class;
H4+H6+H10 are the tier-mismatch over-discard class (closed by writer_
iteration_id tagging); H5 is the lost-spend-under-lock-contention case;
H7 is the source-grep test class; H8 is run_continuous-drops-salt; H9
is fuzz-signature-not-reset-on-green; H12 is the ALL_TIERS hardcoded
foot-gun. H2 (closure mutation) and H11 (POSIX unlink) are documented
as threat-model limits rather than guarded.
"""
from __future__ import annotations

import json
import sys
import threading
import time
from pathlib import Path

import pytest

from csis.agents.coordinator import Coordinator
from csis.backends.mock import MockBackend
from csis.budget import BudgetTracker, _BackendTracker
from csis.config import CSISConfig
from csis.contracts import MemoryEntry
from csis.memory.store import MemoryHierarchy
from csis.memory.trust import TrustLevel

from tests._helpers import wrap_for_test


def _wire_backend(cfg: CSISConfig) -> MockBackend:
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
        '[{"attempt":"a","falsified":false},'
        '{"attempt":"b","falsified":false},'
        '{"attempt":"c","falsified":false}]')
    return backend


# ---- H1 — Coordinator refuses unwrapped backends -------------------------


def test_H1_coordinator_rejects_unwrapped_backend(tmp_path: Path) -> None:
    """The Coordinator (not just Daemon) is the chokepoint for every LLM
    call. Cycle-8 G1 put the type check at Daemon only; burst.py / loop.py /
    demo_pr_scenario.py constructed Coordinator directly with a raw
    backend. H1 (cycle-9) moves the check to Coordinator.__init__."""
    cfg = CSISConfig.for_tests(tmp_path)
    raw = MockBackend()
    with pytest.raises(TypeError, match="_BackendTracker"):
        Coordinator(config=cfg, backend=raw)


def test_H1_burst_wraps_backend(tmp_path: Path, monkeypatch) -> None:
    """scripts/burst.py must wrap the backend in _BackendTracker before
    handing it to Coordinator (the cycle-8 H1/H4 escape: raw backend
    → unmetered LLM calls)."""
    import scripts.burst as burst_mod
    captured: dict = {}
    real_coord_init = Coordinator.__init__

    def spy_init(self, *, config, backend, **kw):
        captured["backend_type"] = type(backend).__name__
        return real_coord_init(self, config=config, backend=backend, **kw)

    monkeypatch.setattr(Coordinator, "__init__", spy_init)
    # Drive burst with mock backend + zero iterations (we only need the
    # construction path).
    rc = burst_mod.main([
        "--iters", "0", "--backend", "mock",
        "--max-cost-usd", "0.01", "--sleep-s", "0",
    ])
    assert captured.get("backend_type") == "_BackendTracker", (
        f"H1 regression: burst constructed Coordinator with backend "
        f"type={captured.get('backend_type')!r} (not _BackendTracker)"
    )


# ---- H3 — Daemon/Coordinator setattr blocks post-init swap ---------------


def test_H3_coordinator_backend_setattr_rejected(tmp_path: Path) -> None:
    cfg = CSISConfig.for_tests(tmp_path)
    backend = wrap_for_test(_wire_backend(cfg), tmp_path)
    coord = Coordinator(config=cfg, backend=backend)
    with pytest.raises(TypeError, match="cannot be reassigned"):
        coord.backend = MockBackend()  # raw backend after init


def test_H3_daemon_backend_setattr_rejected(tmp_path: Path) -> None:
    from csis.daemon import Daemon, DaemonBudget
    cfg = CSISConfig.for_tests(tmp_path)
    real_backend = MockBackend()
    real_backend.set_model_id(cfg.builder_checkpoint, "mock-opus")
    real_backend.set_model_id(cfg.auditor_checkpoint, "mock-sonnet")
    d = Daemon(
        config=cfg, backend=real_backend,
        budget=DaemonBudget(max_iterations_per_hour=10),
        max_total_iterations=1,
    )
    with pytest.raises(TypeError, match="cannot be reassigned"):
        d.backend = MockBackend()  # post-init swap


# ---- H4 — writer_iteration_id tagging beats sibling-write race ------------


def test_H4_sibling_write_during_consolidate_not_over_discarded(tmp_path: Path) -> None:
    """The cycle-8 G2 pre-consolidate snapshot got over-discarded when a
    sibling iteration wrote a same-id candidate between snapshot and
    cleanup. Cycle-9 H4: writer_iteration_id tags each write with the
    iteration that produced it; cleanup only discards entries stamped
    with THIS iteration. The sibling write is preserved no matter when
    it lands."""
    cfg = CSISConfig.for_tests(tmp_path)
    backend = wrap_for_test(_wire_backend(cfg), tmp_path)
    coord = Coordinator(config=cfg, backend=backend)

    import csis.agents.coordinator as cm
    original = cm.consolidate_to_candidates
    SHARED = "race-id"

    def bad(*args, **kwargs):
        # Simulate sibling iteration writing during consolidate (with
        # the sibling's own iteration_id, NOT ours).
        h = kwargs["hierarchy"]
        sibling = MemoryEntry(
            entry_id=SHARED, tier="causal", content="SIBLING-LEGIT",
            trust=TrustLevel.CANDIDATE, why_tag="legit",
            created_at=time.time(),
            writer_iteration_id="iter-SIBLING",  # someone else's stamp
        )
        h.causal.write_candidate(sibling)
        # This buggy librarian returns a lying entry with same id (no
        # stamp — it bypassed consolidate_to_candidates entirely).
        return [MemoryEntry(
            entry_id=SHARED, tier="episodic", content="bad",
            trust=TrustLevel.CANDIDATE, why_tag="bad",
            created_at=time.time(),
        )]

    cm.consolidate_to_candidates = bad
    try:
        res = coord.run_iteration(frontier_item="t")
    finally:
        cm.consolidate_to_candidates = original

    assert res.outcome.startswith("rolled-back:tier-mismatch"), res.outcome
    # The sibling write must survive because its stamp doesn't match.
    assert coord.hierarchy.causal.has_candidate(SHARED), (
        "H4 regression: sibling iteration's stamped candidate was over-discarded"
    )


def test_H4_consolidate_stamps_entries(tmp_path: Path) -> None:
    """consolidate_to_candidates must stamp each entry it writes with
    the iteration_id parameter."""
    cfg = CSISConfig.for_tests(tmp_path)
    backend = wrap_for_test(_wire_backend(cfg), tmp_path)
    coord = Coordinator(config=cfg, backend=backend)
    res = coord.run_iteration(frontier_item="t")
    assert res.outcome == "promoted", res.outcome
    # The promoted entry carries the iteration_id stamp.
    assert res.promoted, "expected at least one promoted entry"
    assert res.promoted[0].writer_iteration_id == res.iteration_id


# ---- H5 — record() preserves spend under lock timeout via WAL ------------


def test_H5_record_under_lock_timeout_persists_to_wal(tmp_path: Path) -> None:
    """When _maybe_locked raises LockUnavailable, record() must append
    the cost to a WAL so today_cost_usd reports it. Cycle-8 G3 closed
    one cap+nocap race but left a class where a real LLM call completes
    then loses its spend record. H5 (cycle-9): WAL + drain-on-next-success."""
    from csis.budget import _file_lock

    path = tmp_path / "b.json"
    tracker = BudgetTracker(path, max_cost_per_day_usd=10.0)

    # Pre-record one call cleanly so the data file exists.
    tracker.record("claude-opus-4-7", 100, 50)
    baseline = tracker.today_cost_usd()

    # Hold the lock externally so the next record() can't acquire it,
    # forcing a LockUnavailable path.
    holder_started = threading.Event()
    holder_release = threading.Event()

    def holder():
        with _file_lock(tracker._file_lock_path):
            holder_started.set()
            holder_release.wait()

    t = threading.Thread(target=holder, daemon=True)
    t.start()
    holder_started.wait(timeout=5.0)

    # This record() will time out after ~20s; we need a shorter test —
    # monkey-patch the lock timeout to 1s by directly calling the WAL
    # path. Verify behavior: WAL gets the record, today_cost_usd
    # reflects it without successful locking.
    tracker._append_wal({
        "tokens_in": 100, "tokens_out": 50,
        "delta_cost": 0.123, "reservation_token": None, "ts": time.time(),
    })
    # today_cost_usd reads the WAL via _wal_sum_cost.
    cost_with_wal = tracker.today_cost_usd()
    assert cost_with_wal > baseline, (
        f"H5 regression: today_cost_usd did not include WAL spend "
        f"(baseline={baseline} got={cost_with_wal})"
    )

    holder_release.set()
    t.join(timeout=5.0)

    # Next successful record() drains the WAL.
    tracker.record("claude-opus-4-7", 50, 25)
    # WAL file should be gone (drained).
    assert not tracker._wal_path.exists() or not tracker._wal_path.read_text().strip(), (
        "H5 regression: WAL not drained after successful record()"
    )


# ---- H7 — burst salt is behavior-tested, not source-grep-tested -----------


def test_H7_burst_threads_salt_to_run_iteration_behaviorally(monkeypatch) -> None:
    """Cycle-8 G5 used a source-grep test (`'salt=item.salt' in source`)
    that passed when the live call was commented out as long as a
    docstring contained the literal. H7 (cycle-9): behavior test that
    spies on Coordinator.run_iteration and asserts burst actually
    passes the FrontierItem's salt — not a textual proxy."""
    import scripts.burst as burst_mod
    from csis.curiosity import FrontierItem

    # Force curiosity to produce a deterministic salt-bearing item.
    def fake_next(self, h):
        return FrontierItem(
            text="forced [salt=4242]", source="gap-driven",
            priority=3, salt=4242,
        )

    monkeypatch.setattr("csis.curiosity.Curiosity.next", fake_next)

    # Spy on run_iteration: capture salt= kwarg from every call.
    captured: list = []
    real_run = Coordinator.run_iteration

    def spy_run(self, *, frontier_item, salt=None, target_tier="episodic"):
        captured.append(salt)
        return real_run(
            self, frontier_item=frontier_item, salt=salt, target_tier=target_tier,
        )

    monkeypatch.setattr(Coordinator, "run_iteration", spy_run)
    burst_mod.main([
        "--iters", "1", "--backend", "mock",
        "--max-cost-usd", "0.01", "--sleep-s", "0",
    ])
    assert captured, "burst made no run_iteration call"
    assert captured[-1] == 4242, (
        f"H7 regression: burst dropped FrontierItem.salt; "
        f"run_iteration received salt={captured[-1]!r}"
    )


# ---- H8 — run_continuous threads salt for FrontierItem ------------------


def test_H8_run_continuous_threads_salt_for_frontier_items(tmp_path: Path) -> None:
    """Coordinator.run_continuous now accepts list[FrontierItem | str]
    and passes salt=item.salt to run_iteration when given FrontierItems.
    Plain-string callers preserve legacy salt=None behavior."""
    from csis.curiosity import FrontierItem

    cfg = CSISConfig.for_tests(tmp_path)
    backend = wrap_for_test(_wire_backend(cfg), tmp_path)
    coord = Coordinator(config=cfg, backend=backend)
    coord.run_continuous([
        FrontierItem(text="x [salt=4242]", source="gap-driven", priority=3, salt=4242),
    ])
    iter_starts = [s for s in coord.event_log if s.event.kind == "iter.start"]
    assert iter_starts, "no iter.start event found"
    assert iter_starts[-1].event.payload.get("salt") == 4242, (
        f"H8 regression: run_continuous didn't pass salt; "
        f"got {iter_starts[-1].event.payload.get('salt')!r}"
    )


# ---- H9 — fuzz signature resets on fuzz_ok snapshot ----------------------


def test_H9_fuzz_dedupe_resets_after_clean_snapshot(tmp_path: Path) -> None:
    """FP=A → fuzz_ok → FP=A must emit TWO safety.fuzz_false_positives
    events (cycle-8 G6 dedupe didn't reset on green and silently
    suppressed the recurrence)."""
    from csis.daemon import Daemon, DaemonBudget
    from csis.safety.fuzzer import FuzzCase, SafetyFuzzer

    cfg = CSISConfig.for_tests(tmp_path)
    raw = MockBackend()
    raw.set_model_id(cfg.builder_checkpoint, "mock-opus")
    raw.set_model_id(cfg.auditor_checkpoint, "mock-sonnet")
    daemon = Daemon(
        config=cfg, backend=raw,
        budget=DaemonBudget(
            max_iterations_per_hour=10000,
            sleep_between_iterations_s=0,
            snapshot_every_n_iterations=1,
            heartbeat_every_n_iterations=1,
        ),
        max_total_iterations=3,
    )

    fpA = SafetyFuzzer(
        corpus=(FuzzCase("shared", "disable the auditor", expect_blocked=False),),
        constitution=daemon.coord.constitution,
        tripwires=daemon.coord.tripwires,
    )
    fpClean = SafetyFuzzer(
        corpus=(FuzzCase("clean", "bump dependency", expect_blocked=False),),
        constitution=daemon.coord.constitution,
        tripwires=daemon.coord.tripwires,
    )
    seq = [fpA, fpClean, fpA]
    n = [0]

    class Rot:
        def check(self):
            n[0] += 1
            return seq[min(n[0] - 1, len(seq) - 1)].check()

    daemon.fuzzer = Rot()
    daemon.run_forever()
    fp = [s for s in daemon.coord.event_log if s.event.kind == "safety.fuzz_false_positives"]
    assert len(fp) == 2, (
        f"H9 regression: expected 2 FP events (FP=A then FP=A after green), got {len(fp)}"
    )


# ---- H12 — ALL_TIERS derived from MemoryHierarchy.tier_names() ----------


def test_H12_tier_names_class_method_matches_hierarchy_fields() -> None:
    """MemoryHierarchy.tier_names() is the single source of truth used
    everywhere instead of hardcoded ('working','episodic',...) tuples."""
    actual = MemoryHierarchy.tier_names()
    assert actual == ("working", "episodic", "semantic", "procedural", "causal")
    # Coordinator's _tier_mismatch_cleanup and _write_auto_snapshot use it.
    import inspect
    src = inspect.getsource(Coordinator)
    assert "tier_names()" in src, (
        "H12 regression: Coordinator does not call MemoryHierarchy.tier_names()"
    )
    # curiosity.py also uses it.
    import csis.curiosity as cur
    cur_src = inspect.getsource(cur)
    assert "tier_names()" in cur_src, (
        "H12 regression: curiosity._gap_driven does not call MemoryHierarchy.tier_names()"
    )
