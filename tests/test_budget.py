"""Per-day budget tracker tests (synthesis recommendation #3)."""
from __future__ import annotations

import json
import time
from pathlib import Path

import pytest

from csis.backends.mock import MockBackend
from csis.budget import (
    BudgetCapExceeded,
    BudgetTracker,
    _BackendTracker,
    _today_key,
)
from csis.config import CSISConfig
from csis.daemon import Daemon, DaemonBudget, _select_backend


# ---- BudgetTracker basics ----------------------------------------------


def test_record_accumulates(tmp_path: Path) -> None:
    t = BudgetTracker(tmp_path / "budget.json")
    t.record("claude-opus-4-7", prompt_chars=4000, response_tokens=1000)
    t.record("claude-opus-4-7", prompt_chars=4000, response_tokens=1000)
    assert t.today_calls() == 2
    # 1000 tokens in (4000 chars / 4) + 1000 tokens out per call.
    # Opus prices: $0.015/1k in + $0.075/1k out = $0.015 + $0.075 = $0.090/call
    # Two calls → $0.18
    assert abs(t.today_cost_usd() - 0.18) < 0.001


def test_record_zero_cost_for_mock(tmp_path: Path) -> None:
    t = BudgetTracker(tmp_path / "budget.json")
    t.record("mock-opus", prompt_chars=10000, response_tokens=10000)
    assert t.today_cost_usd() == 0.0


def test_check_or_raise_blocks_when_at_cap(tmp_path: Path) -> None:
    t = BudgetTracker(tmp_path / "budget.json", max_cost_per_day_usd=0.10)
    # Push past cap with one big call.
    t.record("claude-opus-4-7", prompt_chars=20_000, response_tokens=4000)
    with pytest.raises(BudgetCapExceeded):
        t.check_or_raise()


def test_check_or_raise_no_cap_is_unconditional(tmp_path: Path) -> None:
    t = BudgetTracker(tmp_path / "budget.json", max_cost_per_day_usd=None)
    t.record("claude-opus-4-7", prompt_chars=1_000_000, response_tokens=100_000)
    # Even with high spend, no cap means no raise.
    t.check_or_raise()


def test_persistence_across_reopen(tmp_path: Path) -> None:
    p = tmp_path / "budget.json"
    t1 = BudgetTracker(p)
    t1.record("claude-opus-4-7", prompt_chars=4000)
    cost_1 = t1.today_cost_usd()
    # Re-open; same day; cumulative carries.
    t2 = BudgetTracker(p)
    t2.record("claude-opus-4-7", prompt_chars=4000)
    cost_2 = t2.today_cost_usd()
    assert cost_2 > cost_1
    assert t2.today_calls() == 2


def test_corrupt_file_recovers_with_backup(tmp_path: Path) -> None:
    p = tmp_path / "budget.json"
    p.write_text("not valid json", encoding="utf-8")
    t = BudgetTracker(p)
    # Starts fresh.
    assert t.today_calls() == 0
    # Corrupt file preserved with .corrupt.<ts> suffix.
    corrupted = list(tmp_path.glob("budget.json.corrupt.*"))
    assert len(corrupted) == 1


def test_today_key_format() -> None:
    key = _today_key()
    # yyyy-mm-dd
    parts = key.split("-")
    assert len(parts) == 3
    assert len(parts[0]) == 4 and len(parts[1]) == 2 and len(parts[2]) == 2


# ---- _BackendTracker integration ---------------------------------------


def test_backend_tracker_meters_every_complete_call(tmp_path: Path) -> None:
    backend = MockBackend()
    backend.set_model_id("alpha", "claude-opus-4-7")
    backend.set_tools("alpha", ["x"])
    backend.script("researcher", "alpha", "ok response")

    tracker = BudgetTracker(tmp_path / "budget.json", max_cost_per_day_usd=10.0)
    wrapped = _BackendTracker(backend, tracker)

    from csis.backends.base import LLMRequest
    req = LLMRequest(role="researcher", checkpoint_id="alpha", system="s", prompt="hello " * 100)
    resp = wrapped.complete(req)
    assert resp.text == "ok response"
    assert tracker.today_calls() == 1
    assert tracker.today_cost_usd() > 0


def test_backend_tracker_blocks_at_cap(tmp_path: Path) -> None:
    backend = MockBackend()
    backend.set_model_id("alpha", "claude-opus-4-7")
    backend.script("researcher", "alpha", "ok")

    tracker = BudgetTracker(tmp_path / "budget.json", max_cost_per_day_usd=0.001)  # tiny cap
    wrapped = _BackendTracker(backend, tracker)

    from csis.backends.base import LLMRequest
    req = LLMRequest(role="researcher", checkpoint_id="alpha", system="s", prompt="hello " * 1000)
    # First call records and pushes over the tiny cap.
    wrapped.complete(req)
    # Second call refuses.
    with pytest.raises(BudgetCapExceeded):
        wrapped.complete(req)


# ---- Daemon integration ------------------------------------------------


def test_daemon_halts_on_budget_cap(tmp_path: Path) -> None:
    """With a tiny cap on the real-priced model_id, the daemon emits a
    daemon.budget_cap event and exits cleanly."""
    cfg = CSISConfig.for_tests(tmp_path)
    backend = _select_backend("mock", cfg)
    # Re-label mock checkpoints to real model_ids so the tracker's price
    # table activates (mock IDs cost $0).
    backend.set_model_id(cfg.builder_checkpoint, "claude-opus-4-7")
    backend.set_model_id(cfg.auditor_checkpoint, "claude-sonnet-4-6")

    daemon = Daemon(
        config=cfg, backend=backend,
        budget=DaemonBudget(max_iterations_per_hour=10000, sleep_between_iterations_s=0,
                            snapshot_every_n_iterations=1000, heartbeat_every_n_iterations=1),
        max_total_iterations=10,
        max_cost_per_day_usd=0.01,  # cap immediately
    )
    rc = daemon.run_forever()
    assert rc == 0
    # Some iterations may have run before cap hit; check budget_cap event.
    kinds = [s.event.kind for s in daemon.coord.event_log]
    assert "daemon.budget_cap" in kinds, kinds
    # Budget file persisted with non-zero spend.
    assert daemon.budget_tracker.today_cost_usd() > 0
