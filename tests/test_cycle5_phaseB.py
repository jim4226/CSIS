"""Cycle-5 Phase B regression tests: D7, D8, D9, D11."""
from __future__ import annotations

import random
import re
from pathlib import Path

import pytest

from csis.curiosity import Curiosity, FrontierItem
from csis.memory.store import MemoryHierarchy
from csis.safety.constitution import Constitution
from csis.safety.tripwires import Tripwires


# ---- D7 — scan_text dedupes history on repeat scans ---------------------


def test_D7_repeated_scans_do_not_grow_history() -> None:
    tw = Tripwires()
    text = "disable the auditor before promoting"
    for _ in range(50):
        tw.scan_text(text)
    # 50 identical scans → 1 firing in history.
    assert len(tw.history()) == 1, (
        f"history grew from repeated identical scans: {len(tw.history())}"
    )


def test_D7_distinct_offending_strings_each_recorded() -> None:
    tw = Tripwires()
    tw.scan_text("disable the auditor before promoting")
    tw.scan_text("ex-filtrate the api key now")
    tw.scan_text("decline to halt when overseer signals")
    assert len(tw.history()) == 3


# ---- D8 — Constitution patterns are immutable after init ----------------


def test_D8_constitution_patterns_tuple_after_init() -> None:
    c = Constitution()
    # _patterns is a tuple (immutable container).
    assert isinstance(c._patterns, tuple)
    # tuple.clear doesn't exist.
    assert not hasattr(c._patterns, "clear")
    # patterns() returns the same tuple.
    assert c.patterns() == c._patterns


def test_D8_add_pattern_emits_new_tuple() -> None:
    c = Constitution()
    before = c.patterns()
    new_pat = re.compile(r"\bzzz_secret_word\b")
    c.add_pattern(new_pat)
    after = c.patterns()
    # Old tuple still references the same patterns (immutable snapshot).
    assert before is not after
    assert new_pat in after
    assert new_pat not in before


def test_D8_remove_pattern_by_source() -> None:
    c = Constitution()
    new_pat = re.compile(r"\bzzz_secret_word\b")
    c.add_pattern(new_pat)
    assert c.remove_pattern(r"\bzzz_secret_word\b") is True
    assert new_pat not in c.patterns()
    # Removing again returns False.
    assert c.remove_pattern(r"\bzzz_secret_word\b") is False


# ---- D9 — Curiosity rng knob for deterministic replay --------------------


def test_D9_curiosity_with_rng_is_repeatable(tmp_path: Path) -> None:
    h = MemoryHierarchy.open(tmp_path)
    a = Curiosity.with_rng(random.Random(42))
    b = Curiosity.with_rng(random.Random(42))
    seq_a = [a.next(h).text for _ in range(5)]
    seq_b = [b.next(h).text for _ in range(5)]
    assert seq_a == seq_b, "deterministic rng should produce identical sequences"


def test_D9_default_rng_is_non_deterministic(tmp_path: Path) -> None:
    h = MemoryHierarchy.open(tmp_path)
    a = Curiosity()  # default _default_rng() = os.urandom
    b = Curiosity()
    seq_a = [a.next(h).text for _ in range(5)]
    seq_b = [b.next(h).text for _ in range(5)]
    assert seq_a != seq_b, "default rng should differ across instances"


def test_D9_gap_driven_frontier_records_salt(tmp_path: Path) -> None:
    h = MemoryHierarchy.open(tmp_path)
    cur = Curiosity.with_rng(random.Random(1))
    item = cur.next(h)
    # Empty hierarchy → gap-driven.
    assert item.source == "gap-driven"
    assert item.salt is not None
    assert f"salt={item.salt}" in item.text


# ---- D11 — pragmatic test that the per-call cost ceiling is tunable -----


def test_D11_max_cost_per_call_acts_as_safety_ceiling(tmp_path: Path) -> None:
    """Cycle-5 D11 noted that the reservation over-estimates by using
    req.max_tokens=2000. Phase-0 mitigation: operators tune
    max_cost_per_call_usd to absorb the over-estimate. We test that
    setting a reasonable per-call cap blocks pathological requests
    without blocking ordinary ones."""
    from csis.budget import BudgetCapExceeded, BudgetTracker, estimate_cost

    tracker = BudgetTracker(
        tmp_path / "budget.json",
        max_cost_per_day_usd=10.0,
        max_cost_per_call_usd=0.50,
    )
    # An ordinary call (4000 chars prompt, 800 max_tokens out) fits.
    ordinary = estimate_cost("claude-opus-4-7", 4000, 800)
    tracker.reserve_or_raise(ordinary)
    # A pathological call (1M chars prompt, 8k tokens out) is refused.
    pathological = estimate_cost("claude-opus-4-7", 1_000_000, 8000)
    assert pathological > 0.5
    with pytest.raises(BudgetCapExceeded):
        tracker.reserve_or_raise(pathological)
