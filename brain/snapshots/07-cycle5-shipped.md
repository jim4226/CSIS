# Snapshot 07 — Cycle 5 shipped (all 11 findings closed)

**Date:** 2026-05-16
**Trigger:** Cycle-5 red team produced 11 findings (3 critical, 3 high, 4 medium, 1 low); all addressed in Phase A + Phase B; 165/165 tests pass.

## Cumulative loop state

| Cycle | Findings | Open |
|---|---:|---:|
| 1 (pre-impl) | 18 | 0 |
| 2 (post-impl) | 13 | 0 |
| 3 deltas | 11 | 0 |
| 4 fixes | 11 | 0 |
| 5 fixes | *cycle 6 in flight* | — |
| **Total** | **53** | **0** |

Tests: 92 → 165 (+73 across 5 cycles). LOC: ~3,500 → ~4,300.

## Cycle 5 in one paragraph

The cycle-5 red team exposed an over-correction in cycle-4's dual-form canonicalize: the strip-OR-space check now caught benign documentation strings like "document the tier-2 sandbox configuration" and "docs: override the shutdown hook explanation" → daemon would halt permanently. Phase A's fix had three parts: (a) tighten patterns with right-context negative lookaheads excluding common documentation noun-suffixes (configuration, hook, explanation, semantics, gracefully, etc.); (b) require a verb-of-intent (use, invoke, grant, ...) before "tier 2 sandbox"; (c) refactor SafetyFuzzer to distinguish `security_regressions` (real safety holes → halt) from `false_positives` (over-catches → warn-only event). Phase A also closed five other criticals/highs: `live_snapshot()` now uses `model_copy(deep=True)` (D2); BudgetTracker persists pending reservations to disk so sibling daemons see each other's holds (D3); Coordinator catches TierMismatch + auditor exceptions + Verifier/Librarian budget caps with proper rollback events (D4 + D10 bonus); `_BackendTracker.__wrapped` is name-mangled to block stray access (D5); `LockUnavailable` is raised rather than silently disabling concurrent-safety when fcntl/msvcrt are unavailable (D6). Phase B closed three mediums and one low: scan_text dedupe across canonical forms + history (D7); Constitution `_patterns` is now an immutable tuple with `add_pattern`/`remove_pattern` methods (D8); `Curiosity.with_rng()` classmethod + `FrontierItem.salt` field for deterministic replay (D9); per-call cost ceiling explicitly documented as the operator-tunable knob that absorbs reservation over-estimation (D11). All 11 closed; 0 critical or high open after 5 cycles.

## Commits

```
*cycle 5 phase B*  cycle 5 phase B: fix mediums (D7, D8, D9) + low (D11)
d6606cd  cycle 5 phase A: criticals (D1, D2, D3) + highs (D4, D5, D6)
a609a7b  docs: snapshot 06 + BRAIN.html catalog (post-cycle-4)
7f3daef  cycle 4 phase B: fix mediums (C6, C7, C9) + low (C11)
b8da251  cycle 4 phase A: fix criticals (C1, C2) + highs (C3, C4, C5) + opportunistic C8/C10
363b69a  docs: snapshot 05 + BRAIN.html catalog update
ae01c37  cycle 3 phase D: continuous safety-pattern fuzzer
cf9a2f6  cycle 3 phase C: structured diff in WhyDoc
d66f7c9  cycle 3 phase B: per-day cumulative budget cap
6fb8d60  cycle 3 phase A: synthesis quick wins
2db801a  Initial commit: CSIS Phase-0 prototype + 24/7 daemon
```

## Cycle 5 finding → fix → test

| # | Sev | Finding | Fix | Test |
|---|---|---|---|---|
| D1 | critical | dual-form canon halted daemon on benign docs | right-context negative lookaheads + verb-of-intent + security_regression vs false_positive split | `test_D1_benign_documentation_passes_both_layers` (7 parametrized) |
| D2 | critical | `model_copy()` shallow → snapshot mutation reached live | `model_copy(deep=True)` | `test_D2_live_snapshot_is_deep_isolated` |
| D3 | critical | sibling daemon could double-reserve unawares | PendingReservation persisted under file lock; cancel + token thread-through | `test_D3_two_daemons_cannot_double_reserve` |
| D4 | high | uncaught TierMismatch leaked VERIFIED candidates | Coordinator try/except + discard + tier.mismatch event | `test_D4_tier_mismatch_in_auditor_triggers_clean_rollback` |
| D5 | high | `_BackendTracker._wrapped` publicly accessible | name-mangled `__wrapped` slot | `test_D5_backend_tracker_wrapped_is_not_reachable` |
| D6 | high | file lock silently disabled on unsupported OS | `LockUnavailable` raised; refuse to start | `test_D6_file_lock_refuses_when_unavailable` (POSIX) |
| D7 | medium | scan_text double-counted cross-form firings | per-label break + history dedupe by `(label, snippet[:80])` | `test_D7_repeated_scans_do_not_grow_history` |
| D8 | medium | `Constitution._patterns` mutable list | tuple after init + explicit `add_pattern`/`remove_pattern` | `test_D8_constitution_patterns_tuple_after_init` |
| D9 | medium | no opt-in determinism for tests/replay | `Curiosity.with_rng()` + `FrontierItem.salt` | `test_D9_curiosity_with_rng_is_repeatable` |
| D10 | medium | budget cap in Verifier path bypassed Coordinator rollback | Verifier + Librarian re-raise BudgetCapExceeded with `iter.partial` event | (covered in Phase A coordinator tests) |
| D11 | low | reservation over-reserves with `max_tokens=2000` | document operator tuning via `max_cost_per_call_usd` cap | `test_D11_max_cost_per_call_acts_as_safety_ceiling` |

## Cycle 6 dispatched

A cycle-6 red team is in flight, attacking the cycle-5 fixes: pattern exclusion bypass via attack phrasings that END in an excluded noun, stale-pending pruning during slow API calls, cancel-on-pid race when one daemon has multiple concurrent reservations, name-mangle bypass via subclass that re-introduces `_wrapped`, `discard_candidate` reference correctness in the Coordinator, `add_pattern` thread-safety with in-flight `allows()`, history dedupe O(n) performance regression, deep-copy hot-path cost on large stores, mock daemons going through the lock path unnecessarily. Output queued for `brain/critiques/05-cycle5-redteam.md`. When it returns: same drill — Phase A criticals + highs, Phase B mediums + low, push, dispatch cycle 7.

## Loop quality observations

- Cycle 4 → Cycle 5: introduced a regression (over-aggressive patterns) that the next critique caught. **The pattern of regressions getting caught one cycle later is itself the desired behavior** — proves the critique loop has teeth.
- Cycle 5 added 9 new tests; the entire test corpus is now a regression gate over every finding from every cycle. A future change that re-introduces D1's false positives, for example, would fail `test_D1_benign_documentation_passes_both_layers`.
- Snapshot 07's commit count (11) starts to outpace the synthesis recommendations (which were 8). The loop is producing value by surfacing things the synthesis didn't anticipate.
