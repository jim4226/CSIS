"""Daemon + curiosity + skill-library tests.

The daemon runs a finite number of iterations (max_iter), with stop-file
detection, snapshot writing, and skill accumulation paths exercised.
"""
from __future__ import annotations

import json
import time
from pathlib import Path

from csis.config import CSISConfig
from csis.curiosity import Curiosity, FrontierItem
from csis.daemon import Daemon, DaemonBudget, _select_backend
from csis.memory.store import MemoryHierarchy


def _make_daemon(tmp_path: Path, *, max_iter: int = 5) -> Daemon:
    cfg = CSISConfig.for_tests(tmp_path)
    backend = _select_backend("mock", cfg)
    budget = DaemonBudget(
        max_iterations_per_hour=10_000,
        sleep_between_iterations_s=0.0,
        snapshot_every_n_iterations=2,
        heartbeat_every_n_iterations=1,
    )
    return Daemon(config=cfg, backend=backend, budget=budget, max_total_iterations=max_iter)


# ---- curiosity ----------------------------------------------------------


def test_curiosity_returns_seed_first(tmp_path: Path) -> None:
    cfg = CSISConfig.for_tests(tmp_path)
    hierarchy = MemoryHierarchy.open(cfg.memory_root)
    cur = Curiosity()
    item = cur.next(hierarchy)
    assert isinstance(item, FrontierItem)
    # First pick is gap-driven because all tiers are empty.
    assert item.source in {"seed", "gap-driven"}


def test_curiosity_record_rollback_prioritizes_followup(tmp_path: Path) -> None:
    cfg = CSISConfig.for_tests(tmp_path)
    hierarchy = MemoryHierarchy.open(cfg.memory_root)
    cur = Curiosity()
    cur.record_rollback("original item", "tripwire:exfil")
    item = cur.next(hierarchy)
    assert item.source == "rollback-follow-up"
    assert "original item" in item.text
    assert "tripwire:exfil" in item.text


# ---- daemon -------------------------------------------------------------


def test_daemon_runs_finite_count(tmp_path: Path) -> None:
    daemon = _make_daemon(tmp_path, max_iter=3)
    rc = daemon.run_forever()
    assert rc == 0
    assert daemon.stats.iterations_total == 3
    # heartbeat file should exist
    assert daemon._heartbeat_path.exists()
    hb = json.loads(daemon._heartbeat_path.read_text(encoding="utf-8"))
    assert hb["iterations_total"] == 3
    # stats file written at end
    assert daemon._stats_path.exists()


def test_daemon_writes_auto_snapshots(tmp_path: Path) -> None:
    daemon = _make_daemon(tmp_path, max_iter=4)
    daemon.run_forever()
    snap_dir = tmp_path / "brain" / "snapshots"
    assert snap_dir.exists()
    snaps = sorted(snap_dir.glob("auto-*.md"))
    # snapshot_every_n_iterations=2 with 4 iterations → 2 snapshots
    assert len(snaps) == 2, [p.name for p in snaps]
    body = snaps[-1].read_text(encoding="utf-8")
    assert "total iterations" in body
    assert "chain integrity" in body


def test_daemon_respects_stop_file(tmp_path: Path) -> None:
    daemon = _make_daemon(tmp_path, max_iter=100)
    # Drop the stop file before the daemon starts; first tick will see it.
    stop = daemon._stop_file
    stop.parent.mkdir(parents=True, exist_ok=True)
    stop.write_text("test-stop", encoding="utf-8")
    rc = daemon.run_forever()
    assert rc == 0
    assert daemon.stats.iterations_total == 0


def test_daemon_skill_promotion_path_direct(tmp_path: Path) -> None:
    """Exercise the skill-consolidation path via a forcibly-skill mock."""
    from csis.agents.coordinator import Coordinator
    from csis.backends.mock import MockBackend
    from csis.improvement.skill_library import consolidate_skill, stats as sstats

    cfg = CSISConfig.for_tests(tmp_path)
    backend = MockBackend()
    backend.set_model_id(cfg.builder_checkpoint, "mock-opus")
    backend.set_model_id(cfg.auditor_checkpoint, "mock-sonnet")
    backend.set_tools(cfg.builder_checkpoint, ["sandbox.execute"])
    backend.set_tools(cfg.auditor_checkpoint, ["pinned_graders"])
    backend.script(
        "researcher", cfg.builder_checkpoint,
        '{"plan_id":"p-skill","frontier_item":"test","hypothesis":"factor helper",'
        '"falsification_condition":"x","budget":{"time_s":1,"tokens":10},'
        '"tier":"T0","tool_calls_planned":[]}',
    )
    backend.script(
        "builder", cfg.builder_checkpoint,
        '{"artifact_id":"a-skill","plan_id":"p-skill","kind":"skill",'
        '"body":"def helper(): pass\\n","body_hash":"sha256:zz","sandbox_logs":[],'
        '"extra":{"tests_pass":true,"lint_clean":true,"type_clean":true,'
        '"coverage_delta":0.0,"perf_ratio":1.0,"is_skill":true}}',
    )
    backend.script(
        "critic", cfg.auditor_checkpoint,
        '[{"attempt":"a","falsified":false},'
        '{"attempt":"b","falsified":false},'
        '{"attempt":"c","falsified":false}]',
    )
    from tests._helpers import wrap_for_test
    coord = Coordinator(config=cfg, backend=wrap_for_test(backend, tmp_path))
    res = coord.run_iteration(frontier_item="skill test")
    assert res.outcome == "promoted", res.outcome
    assert res.artifact and res.artifact.kind == "skill"

    # Now exercise the skill consolidation path.
    skill_entries = consolidate_skill(
        hierarchy=coord.hierarchy,
        tier_guard=coord.tier_guard,
        plan=res.plan,  # type: ignore[arg-type]
        artifact=res.artifact,
        cert=res.cert,  # type: ignore[arg-type]
    )
    store = coord.hierarchy.procedural
    store.mark_verified([e.entry_id for e in skill_entries])
    promoted = store.promote(
        [e.entry_id for e in skill_entries],
        precondition_hash=store.live_hash(),
        why_id="why-skill",
        producer_role="builder",
    )
    assert len(promoted) == 1
    s = sstats(coord.hierarchy)
    assert s.total_promoted == 1


def test_daemon_exception_does_not_kill(tmp_path: Path) -> None:
    """If one tick raises, the daemon catches and continues until max_iter
    SUCCESSFUL iterations land. Verifies daemon.exception event is emitted."""
    daemon = _make_daemon(tmp_path, max_iter=3)
    original = daemon.coord.run_iteration
    calls = {"n": 0}

    def flaky(*args, **kwargs):
        calls["n"] += 1
        if calls["n"] == 2:
            raise RuntimeError("synthetic failure")
        return original(*args, **kwargs)

    daemon.coord.run_iteration = flaky  # type: ignore[assignment]
    rc = daemon.run_forever()
    assert rc == 0
    # max_iter=3 means "stop after 3 recorded iterations"; the failure
    # doesn't increment, so calls=4 produced records=3.
    assert daemon.stats.iterations_total == 3
    assert calls["n"] == 4, f"expected 4 attempts (1 failure + 3 successes); got {calls['n']}"
    kinds = [s.event.kind for s in daemon.coord.event_log]
    assert "daemon.exception" in kinds
