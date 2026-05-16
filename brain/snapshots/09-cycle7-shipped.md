# Snapshot 09 — Cycle 7 shipped (7 findings closed)

**Date:** 2026-05-16
**Trigger:** Cycle-7 red team produced 7 findings (1 critical, 2 high, 3 medium, 1 low). All addressed; 195/195 tests pass (4 POSIX-only skipped on Windows).

## Cycle 7 in one paragraph

The cycle-7 critical (F1) caught an embarrassing one: the cycle-6 E4 `__init_subclass__` guard had a docstring explicitly acknowledging it didn't catch Python's name-mangled `__wrapped` form — and the cycle-6 fix shipped anyway. F1 made the guard check ANY name ending in `__wrapped`. F2 narrowed the cycle-6 E1 tier-mismatch cleanup from "walk all five tiers and discard by id" (which over-swept legitimate same-id candidates in other tiers) to "discard only from entry.tier via the new public `has_candidate()` API". F3 completed cycle-6 E5: the lock-skip was at `__init__` only; every other budget method still hit `_file_lock` unconditionally, so mock daemons broke on the first LLM call. F3 introduced `_maybe_locked()` that short-circuits when no cap is set. F4 swapped cycle-6 E10's regex-on-frontier-text for an explicit `salt=` parameter — legitimate `[salt=N]` substrings in research-paper titles no longer get misattributed in the iter.start payload. F5 bounded the `_history_keys` set via OrderedDict + deque(maxlen=N); F6 added a lock around Constitution `add_pattern`/`remove_pattern`/`patterns`; F7 added signature-based dedupe of the `safety.fuzz_false_positives` event so a stable false-positive set doesn't spam the event log thousands of times per day.

## Cycle 7 finding → fix → test

| # | Sev | Finding | Fix | Test |
|---|---|---|---|---|
| F1 | critical | `__init_subclass__` missed mangled `__wrapped` | check any name ending in `__wrapped` | `test_F1_subclass_with_double_underscore_wrapped_rejected` |
| F2 | high | walk-all-tiers cleanup over-discarded | discard only from `entry.tier` via public `has_candidate()` | `test_F2_tier_mismatch_does_not_over_discard_legitimate_candidates` |
| F3 | high | conditional lock only in `__init__` | new `_maybe_locked()` wraps every method | `test_F3_mock_daemon_can_record_without_locking` (POSIX) |
| F4 | medium | salt regex misattribution | explicit `salt=` parameter on `run_iteration` | `test_F4_salt_logged_from_frontier_item_not_regex` |
| F5 | medium | `_history_keys` unbounded | OrderedDict + deque(maxlen=N), FIFO eviction | `test_F5_history_bounded_by_max` |
| F6 | medium | `add_pattern` non-atomic RMW | `_patterns_lock` threading.Lock | `test_F6_concurrent_add_pattern_preserves_all` |
| F7 | low | fuzz event flood | signature-dedup; `fuzz_event_dedupe` DaemonBudget knob | `test_F7_daemon_dedupes_stable_false_positive_signature` |

## Cumulative loop state

| Cycle | Findings | Crit | High | Med | Low | Open | Deferred | Tests |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| 1 pre-impl | 18 | 2 | 6 | 7 | 3 | 0 | 0 | 52 |
| 2 post-impl | 13 | 2 | 6 | 3 | 2 | 0 | 0 | 78 |
| 3 deltas | 11 | 2 | 4 | 4 | 1 | 0 | 0 | 114 |
| 4 fixes | 11 | 2 | 4 | 4 | 1 | 0 | 0 | 141 |
| 5 fixes | 11 | 3 | 3 | 4 | 1 | 0 | 0 | 165 |
| 6 fixes | 10 | 3 | 3 | 3 | 1 | 0 | 1 | 186 |
| 7 fixes | 7 | 1 | 2 | 3 | 1 | 0 | 0 | **195** |
| **Total** | **81** | **15** | **28** | **28** | **10** | **0** | **1** | — |

## What the loop is showing us

After 7 cycles:
- **81 findings**, **80 closed**, **1 deferred** (E8 Pydantic frozen-dict adapter, Phase 1).
- **Tests grew from 92 → 195** (+103).
- **Two embarrassing cycles in a row** caught dead-code-or-acknowledged-but-shipped bugs (cycle-6 E1 NameError in bare-except; cycle-7 F1 explicitly-acknowledged mangling escape). Lesson reinforced **twice**: docstrings saying "known limit" should be followed by `# TODO(cycleN): fix`, AND regression tests must assert remediation EFFECT, not just surface events.
- The loop quality is **monotonically improving the codebase** — every cycle's tests become a regression gate for every subsequent cycle.

## Cycle 8 dispatched

Already in flight, attacking cycle-7's fixes: F4's missing dedupe-key normalization, F5's eviction-race when same key re-inserts under concurrent scans, F6 lock granularity on `patterns()`, F7 dedupe defeated by attacker-controlled label, F1 guard escape via metaclass not subclass, F2 still-vulnerable case where the Librarian writes to entry.tier AND a different tier, F3 lock-acquisition failure mid-call mid-iteration. Output queued for `brain/critiques/07-cycle7-redteam.md`.
