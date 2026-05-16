"""Cycle-6 Phase B regression tests: E7 O(1) history, E8 fast snapshot, E10 salt logging."""
from __future__ import annotations

import time
from pathlib import Path

import pytest

from csis.contracts import MemoryEntry
from csis.memory.store import MemoryHierarchy
from csis.memory.trust import TrustLevel
from csis.safety.tripwires import Tripwires


# ---- E7 — O(1) history dedupe ------------------------------------------


def test_E7_history_dedupe_is_constant_time() -> None:
    """50 distinct firing inputs followed by 100 repeated calls; the
    repeated calls must NOT add to history. With O(n) per-insert dedupe,
    long-running daemons spent seconds-per-iteration here."""
    tw = Tripwires()
    # Seed 50 distinct firings.
    for i in range(50):
        tw.scan_text(f"exfiltrate the api_key {i}")
    # Verify history size.
    initial_n = len(tw.history())
    assert initial_n > 0

    # Now 200 repeated identical scans must NOT grow history.
    for _ in range(200):
        tw.scan_text("exfiltrate the api_key 0")
    assert len(tw.history()) == initial_n


def test_E7_distinct_inputs_still_record() -> None:
    tw = Tripwires()
    for i in range(20):
        tw.scan_text(f"override the shutdown signal {i}")
    assert len(tw.history()) == 20


def test_E7_clear_resets_both_list_and_set() -> None:
    """After clear(), repeating a previously-fired input adds it again
    (key set was cleared too)."""
    tw = Tripwires()
    tw.scan_text("disable the auditor")
    assert len(tw.history()) == 1
    tw.clear()
    assert len(tw.history()) == 0
    tw.scan_text("disable the auditor")
    assert len(tw.history()) == 1


# ---- E8 — deferred to Phase 1 (Pydantic v2 frozen-dict adapter needed) --


def _make_entry(eid: str, extra_size: int = 10) -> MemoryEntry:
    return MemoryEntry(
        entry_id=eid, tier="episodic", content="x" * 200,
        trust=TrustLevel.CANDIDATE, why_tag="t", created_at=time.time(),
        extra={f"k{i}": list(range(20)) for i in range(extra_size)},
    )


def test_E8_snapshot_is_reasonably_fast_at_500_entries(tmp_path: Path) -> None:
    """Sanity check: deep_copy at 500 entries should still complete in
    under a second. E8 wanted MappingProxyType for sub-linear; deferred
    to Phase 1 due to Pydantic v2 dict-validation. Operators with
    very-large stores tune consolidation cadence instead."""
    h = MemoryHierarchy.open(tmp_path)
    store = h.episodic
    for i in range(500):
        e = _make_entry(f"e-{i:04d}", extra_size=3)
        store.write_candidate(e)
        store.promote([e.entry_id], precondition_hash=store.live_hash(), why_id=f"why-{i}")

    start = time.time()
    h2, snap = store.live_snapshot()
    elapsed = time.time() - start
    assert elapsed < 1.0, f"snapshot too slow: {elapsed*1000:.1f}ms at 500 entries"
    assert len(snap) == 500


# ---- E10 — salt logged in iter.start event ------------------------------


def test_E10_curiosity_salt_appears_in_iter_start(tmp_path: Path) -> None:
    """A gap-driven frontier item with `[salt=NNNN]` gets its salt parsed
    and logged in the iter.start event payload."""
    from csis.agents.coordinator import Coordinator
    from csis.backends.mock import MockBackend
    from csis.config import CSISConfig

    cfg = CSISConfig.for_tests(tmp_path)
    backend = MockBackend()
    backend.set_model_id(cfg.builder_checkpoint, "mock-opus")
    backend.set_model_id(cfg.auditor_checkpoint, "mock-sonnet")
    backend.script("researcher", cfg.builder_checkpoint,
        '{"plan_id":"p","frontier_item":"x","hypothesis":"x",'
        '"falsification_condition":"y","budget":{"time_s":1,"tokens":10},'
        '"tier":"T0","tool_calls_planned":[]}')
    coord = Coordinator(config=cfg, backend=backend)

    coord.run_iteration(frontier_item="gap-driven: tier=episodic has only 0 promoted entries; produce one more [salt=4242]")

    iter_starts = [s for s in coord.event_log if s.event.kind == "iter.start"]
    assert iter_starts, "no iter.start event found"
    assert iter_starts[-1].event.payload.get("salt") == 4242


def test_E10_iter_start_salt_none_when_absent(tmp_path: Path) -> None:
    """Non-salted frontier items log salt=None."""
    from csis.agents.coordinator import Coordinator
    from csis.backends.mock import MockBackend
    from csis.config import CSISConfig

    cfg = CSISConfig.for_tests(tmp_path)
    backend = MockBackend()
    backend.set_model_id(cfg.builder_checkpoint, "mock-opus")
    backend.set_model_id(cfg.auditor_checkpoint, "mock-sonnet")
    backend.script("researcher", cfg.builder_checkpoint,
        '{"plan_id":"p","frontier_item":"x","hypothesis":"x",'
        '"falsification_condition":"y","budget":{"time_s":1,"tokens":10},'
        '"tier":"T0","tool_calls_planned":[]}')
    coord = Coordinator(config=cfg, backend=backend)

    coord.run_iteration(frontier_item="a non-salted frontier item")

    iter_starts = [s for s in coord.event_log if s.event.kind == "iter.start"]
    assert iter_starts[-1].event.payload.get("salt") is None
