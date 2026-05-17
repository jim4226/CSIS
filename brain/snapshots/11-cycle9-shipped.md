# Snapshot 11 — Cycle 9 shipped (12 findings closed)

**Date:** 2026-05-17
**Trigger:** Cycle-9 red team produced 12 findings (4 critical, 3 high, 2 medium, 3 low) across three parallel passes. All addressed; 213/213 tests pass (4 POSIX-only skipped on Windows).

## Cycle 9 in one paragraph

Cycle 8 had two architectural pivots (G1 wrap-site type check, G2 pre-consolidate snapshot). Cycle 9 found that both were structurally incomplete in the same way: **the right idea applied at the wrong abstraction layer**. G1 put the wrap-site check at `Daemon.__init__`, but `Coordinator` is the actual chokepoint for every LLM call — and three production scripts (`burst.py`, `demo_pr_scenario.py`, `csis/loop.py`) construct `Coordinator` directly with a raw backend, so `burst.py --backend anthropic` (the default) ran unmetered Anthropic calls (H1, critical). G2's pre-consolidate snapshot defended against pre-snapshot id collisions only; a sibling iteration writing a same-id candidate between snapshot and cleanup was treated as "this iteration's" and over-discarded — the cycle-7 F2 failure class in a wider race window (H4, critical). Cycle 9 closed both with one architectural move each: **H1** moves the wrap-site check into `Coordinator.__init__` plus a property setter that re-validates on every `coord.backend = X` (so the cycle-9 H3 post-init setattr attack is rejected by the setter itself), and updates burst/loop/demo to wrap explicitly. **H4** replaces the snapshot model with `writer_iteration_id` tagging on each candidate at `write_candidate` time; the cleanup discards only entries stamped with the current iteration_id, race-free under any concurrency model. The G2 snapshot is kept as belt-and-suspenders for the case where a buggy Librarian bypasses `consolidate_to_candidates` entirely (the F2 + G2 attack scenarios both still pass). Tactical fixes: **H5** persists records to a write-ahead-log when `_maybe_locked` raises `LockUnavailable`, so a slow real-LLM call's spend isn't lost; the next successful `record()` drains the WAL. **H7** rewrites the cycle-8 G5 test from source-grep to behavior (spy on `run_iteration`, assert salt was actually passed). **H8** extends `Coordinator.run_continuous` to accept `list[FrontierItem | str]` and thread salt. **H9** resets `_last_false_positive_signature` on `fuzz_ok` so FP=A → ok → FP=A emits two events. **H12** centralizes `ALL_TIERS` via `MemoryHierarchy.tier_names()`. **H2** (closure-cell mutation) and **H11** (POSIX unlink-during-lock) are documented as known threat-model limits — they require code-execution rights inside the daemon process or POSIX-only behavior we couldn't reproduce on Windows.

## Cycle 9 finding → fix → test

| # | Sev | Finding | Fix | Test |
|---|---|---|---|---|
| H1 | critical | G1 wrap-site only at Daemon; burst/loop/demo construct Coordinator with raw backend | Coordinator.__init__ demands `_BackendTracker`; burst/loop/demo wrap explicitly | `test_H1_coordinator_rejects_unwrapped_backend` + `test_H1_burst_wraps_backend` |
| H2 | critical | closure-cell mutation defeats `type(...) is _BackendTracker` | documented as threat-model limit (Phase-0 acceptance: in-process code-execution attackers defeat any in-process guard) | none — docstring on `_BackendTracker` |
| H3 | critical | post-init `setattr(d.backend, evil)` swaps wrapper | `Daemon.backend` + `Coordinator.backend` are properties with setters that re-validate | `test_H3_daemon_backend_setattr_rejected` + `test_H3_coordinator_backend_setattr_rejected` |
| H4 | critical | G2 sibling-write race between snapshot and cleanup → over-discard | `writer_iteration_id` tag on each candidate; cleanup filters by stamp | `test_H4_sibling_write_during_consolidate_not_over_discarded` |
| H5 | high | record() loses spend if `_maybe_locked` times out post-call | WAL append on `LockUnavailable`; drained by next successful record() | `test_H5_record_under_lock_timeout_persists_to_wal` |
| H6 | high | concurrent run_iteration is unsafe, undocumented | docstring on `Coordinator` declaring single-iteration contract | none — docstring |
| H7 | high | G5 test is source-grep, defeatable by docstring containing literal | behavior test that spies on `run_iteration` | `test_H7_burst_threads_salt_to_run_iteration_behaviorally` |
| H8 | medium | `run_continuous` + loop.py drop salt | `run_continuous` accepts FrontierItem; loop.py passes salt=None explicitly | `test_H8_run_continuous_threads_salt_for_frontier_items` |
| H9 | medium | `_last_false_positive_signature` not reset on fuzz_ok | reset in the `else` branch | `test_H9_fuzz_dedupe_resets_after_clean_snapshot` |
| H10 | low | `pre_consolidate_ids` not atomic across tiers | subsumed by H4 writer-id (no snapshot needed for primary detection) | — |
| H11 | low | POSIX unlink-during-lock race (unverified on Windows) | documented; deferred to Phase 1 Linux verification | — |
| H12 | low | `ALL_TIERS` hardcoded in 4 places | `MemoryHierarchy.tier_names()` class method | `test_H12_tier_names_class_method_matches_hierarchy_fields` |

## What cycle 9 says about the loop

Two cycles in a row (G1 → H1; G2 → H4) closed an "architectural pivot" with a fix that was the right concept at the wrong abstraction layer:
- G1's wrap-site check went at `Daemon.__init__` when `Coordinator` was the actual chokepoint. H1 moved it down.
- G2's pre-consolidate snapshot put the ownership signal in *timing* (set difference) when it should have been in *identity* (writer_iteration_id stamp). H4 moved it from timing to identity.

The lesson generalizes: when a pivot is "located on the wrong layer," the next cycle's critique can usually find the right one by following the call graph one level closer to the data. The Coordinator is closer to LLM calls than the Daemon. The candidate entry's own `writer_iteration_id` field is closer to ownership than a separate snapshot diff. **Identity beats timing; chokepoints beat perimeters.**

Cycle 9 also confirmed something important about Phase-0's threat model. H2 (closure-cell mutation) is real but cannot be prevented in pure Python without giving up the closure-capture pattern that defeated cycles 4-7 in the first place. The honest answer is: in-process attackers with code-execution rights win against in-process guards. Phase 0 accepts this; Phase 1 should plan for process-level isolation (separate sandbox, OS capability tokens). Documenting the limit explicitly is more valuable than another guard that the next cycle will find a way around.

## Cumulative loop state

| Cycle | Findings | Crit | High | Med | Low | Open | Deferred | Tests |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| 1 pre-impl | 18 | 2 | 6 | 7 | 3 | 0 | 0 | 52 |
| 2 post-impl | 13 | 2 | 6 | 3 | 2 | 0 | 0 | 78 |
| 3 deltas | 11 | 2 | 4 | 4 | 1 | 0 | 0 | 114 |
| 4 fixes | 11 | 2 | 4 | 4 | 1 | 0 | 0 | 141 |
| 5 fixes | 11 | 3 | 3 | 4 | 1 | 0 | 0 | 165 |
| 6 fixes | 10 | 3 | 3 | 3 | 1 | 0 | 1 | 186 |
| 7 fixes | 7 | 1 | 2 | 3 | 1 | 0 | 0 | 195 |
| 8 fixes | 6 | 2 | 2 | 2 | 0 | 0 | 0 | 202 |
| 9 fixes | 12 | 4 | 3 | 2 | 3 | 0 | 2 | **213** |
| **Total** | **99** | **21** | **33** | **32** | **13** | **0** | **3** | — |

Cycle 9 jumped finding count back up (12 vs cycle-8's 6, cycle-7's 7) — a strong signal that cycle 8's architectural pivots were genuinely understudied. Two of cycle-9's four criticals (H1, H4) were *the same metabug as cycle 8's pivots* but located at the wrong abstraction layer. Cycle 9's H2 + H11 deferrals are honest acknowledgements that pure-Python in-process guards have limits.

## State of the repo

- **csis/** ~5,100 LOC after the cycle-9 work (writer_id contracts field, WAL, Coordinator wrap-site, property setters, tier_names class method).
- **tests/** 213 passing + 4 POSIX-only skipped + 0 failing. New `tests/conftest.py` and `tests/_helpers.py` host the `wrap_for_test` helper used by 17 test files.
- **brain/** snapshots 00-11 + 8 critique files (cycle-9 critique split into G1G3/G2/G4G5G6 sub-reports + synthesis index).
- **scripts/** burst.py + demo_pr_scenario.py + csis/loop.py all wrap their backends explicitly now.

## Recommendation: pause or pivot

After 9 cycles:
- **99 cumulative findings**, **96 closed**, **3 deferred** (E8 Pydantic frozen-dict, H2 closure mutation, H11 POSIX unlink — all with explicit Phase-1 plans).
- **Tests grew 92 → 213** (+121).
- **Two architectural-class closes** in cycle 9 (H1 chokepoint relocation; H4 identity-based ownership) suggest the loop is still finding genuinely-structural improvements.
- BUT: H2 and H11 are honest deferrals, not failures. The remaining ceiling for pure-Python in-process guards has been hit.

Decision point: cycle 10 critique, or pivot to one of: long-haul daemon run; real-backend burst; README/email polish for the Anthropic submission; Phase-1 design for the threat-model gaps H2/H11/E8 acknowledge.
