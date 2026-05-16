# Snapshot 08 — Cycle 6 shipped (10 findings closed, 1 deferred)

**Date:** 2026-05-16
**Trigger:** Cycle-6 red team produced 10 findings (3 critical, 3 high, 3 medium, 1 low). 9 closed in code; E8 deferred to Phase 1 with explicit docstring + sanity test. 186/186 tests pass.

## The story of cycle 6

The cycle-6 red team's most impactful finding (E1) caught an **embarrassing dead-code bug in cycle 5's D4 fix**: the `TierMismatch` handler referenced `store` while it was still unbound, and a bare `except: pass` swallowed the `NameError`. The regression test passed only because it checked outcome+event, not the store state. Lesson reinforced: regression tests must assert on the actual remediation effect, not just the surface event/outcome. Now the handler walks all five tiers and the bare except is gone.

The other critical (E2) caught an **over-correction in cycle 5's D1 fix**: the noun-suffix negative-lookaheads added to allow benign documentation strings could be bypassed by attackers appending the same nouns. The cycle-6 fix DROPS the lookaheads entirely, accepting that pattern-based safety has a fundamental ambiguity between benign documentation and adversarial use of the same words. The daemon's `safety.fuzz_false_positives` event distinguishes the two operationally: real attacks block (halt), benign docs over-caught (warn).

E3 caught a multi-call same-pid race in the budget reservation system; E4 made the backend wrapper truly closure-protected; E5 stopped requiring file locks for mock daemons; E6 made the prune timeout configurable. Phase B closed E7 (O(1) history dedupe) and E10 (salt logging). E8 (MappingProxyType-based fast snapshot) was attempted but Pydantic v2 rejects it; deferred to Phase 1 with an explicit docstring and a 500-entry sanity test that caps performance regressions.

## Cycle 6 finding → fix → test

| # | Sev | Finding | Fix | Test |
|---|---|---|---|---|
| E1 | critical | TierMismatch handler referenced unbound `store`; bare except swallowed NameError | `store` assigned earlier; bare except removed; walks ALL FIVE tiers to discard bad-id candidates | `test_E1_tier_mismatch_actually_discards_candidates` |
| E2 | critical | noun-suffix lookaheads bypassable by appending same nouns | DROPPED lookaheads in tripwires + constitution; +10 attack corpus rows | `test_E2_attack_with_doc_noun_suffix_still_blocks` (10 parametrized) |
| E3 | critical | record/cancel matched by pid not token; multi-call same-pid mis-cancelled | `PendingReservation.token` field; match by token in record/cancel | `test_E3_cancel_by_token_not_pid_for_concurrent_reservations` |
| E4 | high | `_BackendTracker.__wrapped` reachable via mangled name; subclass can re-introduce | closures (no instance attribute); `__init_subclass__` refuses `_wrapped`/`_BackendTracker__wrapped` | `test_E4_no_attribute_resolves_to_backend`, `test_E4_subclass_with_wrapped_attribute_rejected` |
| E5 | high | mock daemons required file lock even without caps | conditional `_needs_locking()` skips lock when no cap | `test_E5_mock_daemon_no_cap_works_without_locking` |
| E6 | high | 10-min prune stranded slow API calls | `prune_stale_pending_s` constructor knob, default 3600s | `test_E6_long_running_reservation_not_pruned_under_default` |
| E7 | medium | O(n) history dedupe rebuild per call | `_history_keys` set alongside list; constant-time inserts | `test_E7_history_dedupe_is_constant_time` |
| E8 | medium | live_snapshot deep-copy O(n*size) — DEFERRED | docstring documents Pydantic-frozen-dict-adapter need; 500-entry sanity test | `test_E8_snapshot_is_reasonably_fast_at_500_entries` |
| E9 | medium | corpus row cemented E2 bypass — closed in Phase A | corpus row marked `expect_blocked=True` as part of E2 attack set | (covered by E2 tests) |
| E10 | medium | curiosity salt never reached iter.start payload | regex-extract `[salt=NNNN]` from frontier_item; log as `salt` field | `test_E10_curiosity_salt_appears_in_iter_start` |

## Cumulative loop state

| Cycle | Findings | Critical | High | Med | Low | Open | Deferred | Tests |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| 1 pre-impl | 18 | 2 | 6 | 7 | 3 | 0 | 0 | 52 |
| 2 post-impl | 13 | 2 | 6 | 3 | 2 | 0 | 0 | 78 |
| 3 deltas | 11 | 2 | 4 | 4 | 1 | 0 | 0 | 114 |
| 4 fixes | 11 | 2 | 4 | 4 | 1 | 0 | 0 | 141 |
| 5 fixes | 11 | 3 | 3 | 4 | 1 | 0 | 0 | 165 |
| 6 fixes | 10 | 3 | 3 | 3 | 1 | 0 | 1 (E8) | **186** |
| **Total** | **74** | **14** | **26** | **25** | **9** | **0** | **1** | — |

## Commit timeline

```
*cycle 6 phase B*  cycle 6 phase B: fix mediums (E7, E10); document E8 deferral
e47ba9b  cycle 6 phase A: criticals (E1, E2, E3) + highs (E4, E5, E6)
84539fd  docs: snapshot 07 + BRAIN.html (post-cycle-5)
8c9734a  cycle 5 phase B: fix mediums (D7, D8, D9) + low (D11)
d6606cd  cycle 5 phase A: criticals (D1, D2, D3) + highs (D4, D5, D6)
... (and 7 earlier commits)
```

## Cycle 7 dispatched

Already in flight, attacking the cycle-6 fixes: E10 salt-regex against legitimate frontier text containing `[salt=N]`, default curiosity seeds tripping E2's still-present override_audit pattern (verifier calibration), E1 reaching into private `_candidate` attr, E7 set growing unbounded, E4 `__init_subclass__` name-mangling escape, E3 token collision at microsecond granularity from sibling PIDs, E5 conditional lock leaves writes racing, archive filename truncation collision, fuzz-false-positive event log flood, `add_pattern` non-atomic tuple replacement. Output queued for `brain/critiques/06-cycle6-redteam.md`. When it returns: Phase A criticals/highs, Phase B mediums/low, push, dispatch cycle 8.

## Reflection on the loop quality

Six cycles in. The loop is producing consistent value: each cycle catches genuine regressions introduced by the previous cycle's fixes. Cycle 6 in particular caught a CRITICAL dead-code bug (E1) that cycle 5's red team didn't find — the cycle-5 critique was right at the architectural level but the implementation had a NameError swallowed by a bare except. The lesson: regression tests must assert remediation EFFECT, not just surface event/outcome. Updated test conventions to reflect this.

The cumulative finding count (74 across 6 cycles) is starting to outpace the original synthesis (8 recommendations). The loop has surfaced an order of magnitude more than the initial planning agents anticipated.
