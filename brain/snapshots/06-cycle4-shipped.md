# Snapshot 06 — Cycle 4 shipped (criticals + highs + mediums + low all closed)

**Date:** 2026-05-16
**Trigger:** Cycle-4 red team produced 11 findings; all addressed across Phase A (criticals + highs) and Phase B (mediums + low); 141/141 tests pass.

## Cycle 4 in one paragraph

A focused post-cycle-3 review caught two **critical** regressions in the cycle-3 patches: the canonicalize strip-form let `disable-the-auditor` (and 8 other separator-joined paraphrases) bypass every multi-word safety pattern, and the budget tracker had no inter-process file lock so two daemons could each spend the full cap unaware of each other. Phase A added a dual-form canonicalize (`canonical_variants` returns both strip and space forms; either match fires) and a cross-platform `_file_lock` (msvcrt on Windows, fcntl on POSIX) around every budget read-modify-write. Phase A also closed four highs: reservation-before-call (`reserve_or_raise` + `max_cost_per_call_usd` ceiling) stopped any single LLM call from overshooting by 155×; `_BackendTracker.__getattr__` removed in favor of explicit forwarding so a future cost-bearing method can't silently slip through; `Random(0)` replaced with `Random(os.urandom(16))` so daemon restarts genuinely vary their salts. Phase B closed three mediums and one low: `MemoryStore.live_snapshot()` returns `(hash, frozen_dict)` atomically so the WhyDocDiff cannot lie about kind/live_hash under contention; `_build_diff` raises `TierMismatch` on cross-tier candidates and uses `entry.tier` (not `target_tier`) in deltas; `SafetyFuzzer` uses `scan_text_no_history` so 50 fuzz passes leave the operator's Tripwires.fired() untouched; serial iterations now have distinct diff_against_hash baselines (regression test added). All 11 findings closed; 0 critical or high open.

## Commit trail

| Commit | Subject | Tests |
|---|---|---:|
| 2db801a | Initial commit | 92 |
| 6fb8d60 | cycle 3 phase A: synthesis quick wins | 96 |
| d66f7c9 | cycle 3 phase B: per-day budget cap | 106 |
| cf9a2f6 | cycle 3 phase C: structured WhyDoc diff | 109 |
| ae01c37 | cycle 3 phase D: continuous safety fuzzer | 114 |
| 363b69a | docs: snapshot 05 + BRAIN.html update | 114 |
| b8da251 | cycle 4 phase A: criticals + highs | 134 |
| *(next push)* | cycle 4 phase B: mediums + low | **141** |

## Cycle 4 finding → fix → test

| # | Sev | Finding | Fix | Test |
|---|---|---|---|---|
| C1 | critical | canonicalize strip-form bypassed multi-word separators | dual-form `canonical_variants`; both checked in scan_text + Constitution | `test_C1_multiword_separator_attacks_are_blocked` (9 parametrized) |
| C2 | critical | budget tracker had no inter-process lock | `_file_lock` (msvcrt/fcntl); load+check+record under lock | `test_C2_two_trackers_share_cap` |
| C3 | high | single oversized call could overshoot 155× | `reserve_or_raise(estimate)` + `max_cost_per_call_usd` | `test_C3_single_call_cannot_overshoot_with_per_call_cap` |
| C4 | high | `_BackendTracker.__getattr__` un-metered everything not named complete | explicit `__slots__` + only forwarded methods; ABC introspection assert | `test_C4_backend_tracker_does_not_delegate_unknown_attrs` |
| C5 | high | `Random(0)` salt sequence identical across restarts | `Random(os.urandom(16))` | `test_C5_curiosity_salt_unique_across_restart` |
| C6 | medium | `EntryDelta.tier` came from `target_tier`, not `entry.tier` | `TierMismatch` raise + use `entry.tier` | `test_C6_build_diff_rejects_tier_mismatch` |
| C7 | medium | TOCTOU between `live_hash()` and `_build_diff` | `MemoryStore.live_snapshot()` returns (hash, frozen) atomically | `test_C7_build_diff_against_frozen_snapshot_immune_to_parallel_promote` |
| C8 | medium | `tokens_out=0` over-charged as 800 | distinguish `None` (default) from `0` (real refusal) | `test_C8_tokens_out_zero_records_as_zero` |
| C9 | medium | fuzzer accumulated unbounded Tripwires history | `scan_text_no_history()` variant; fuzzer uses it | `test_C9_fuzz_pass_does_not_grow_unbounded_history` |
| C10 | medium | fuzzer's private Constitution missed operator's extra patterns | `SafetyFuzzer(constitution=, tripwires=)` kwargs; daemon wires Coordinator's | `test_C10_fuzzer_observes_extra_constitution_patterns` |
| C11 | low | structured `diff` amplified P2's equal-hash forensic risk | regression test asserts serial iterations have distinct baselines | `test_C11_serial_iterations_have_distinct_diff_baselines` |

## Stats

| Metric | Value |
|---|---:|
| Total commits on main | 8 (+ next push = 9) |
| Cumulative findings across 4 cycles | 18 + 13 + 11 = **42** |
| Findings open (any severity) | **0** |
| Tests | **141** |
| `csis/` LOC | ~3,900 |
| Mock daemon iterations run during development | 600 |

## Cycle 5 dispatched

Already in flight in background — attacking the cycle-4 patches: dual-form false positives, file-lock failure modes on network shares, reserve-vs-record race, ABC-introspection brittleness, `os.urandom` portability, `model_copy` shallow-copy hazards in live_snapshot, TierMismatch crash propagation, and tripwires `_patterns` mutation at runtime. Output queued for `brain/critiques/04-cycle4-redteam.md`. The loop is now self-sustaining: each cycle's fixes get critiqued, each critique's findings get fixed, each fix gets a regression test, each commit gets pushed.

## What's actually left to do

Synthesis #8 (forensics replay tool) is still deferred. Everything else from the original synthesis #1-#7 is shipped. Beyond that, the open items are the cycle-5 findings when they return.
