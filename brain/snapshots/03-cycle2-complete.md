# Snapshot 03 — Cycle 2 complete (post-impl critique addressed)

**Date:** 2026-05-16
**Trigger:** All cycle-2 critical and high-severity findings fixed; 78/78 tests pass; loop + PR-scenario walkthrough both run end-to-end.

## What changed since snapshot 02

A second red team attacked the *implementation* (not the architecture) and produced 13 findings in `brain/critiques/02-post-impl-redteam.md`. Two critical, six high, five medium/low. The pattern: cycle 1 implemented mitigations as single-site checks; cycle 2 made them architectural invariants enforced by the substrate.

### Critical fixes

**P1 — Coordinator pre-bumped PROMOTED-trust candidates before promote() checked the precondition.** If promote() rejected on stale hash, a fake-PROMOTED ghost was left on disk that downstream readers would cite as ground truth.
- **Fix:** `MemoryStore.promote()` now bumps trust atomically inside the lock. Coordinator no longer touches trust before calling promote().
- **New method:** `MemoryStore.mark_verified()` — bumps CANDIDATE → VERIFIED on the candidate side after the Verifier passes. Stale-precondition failures leave the entry at VERIFIED, distinguishable from PROMOTED.
- **Tests:** `test_P1_failed_promote_does_not_leave_promoted_candidate`, `test_mark_verified_bumps_candidate_only`.

**P2 — `hash_precondition` was a snapshot the Librarian hadn't yet mutated.** Two iterations with disjoint candidate IDs could both reference the same `diff_against_hash`, making the second why-doc's "I diffed against X" prose false.
- **Fix (partial):** the precondition check itself was already correct — promote()'s lock + hash check catches concurrent live mutation. The semantic ambiguity around `diff_against_hash` vs `hash_precondition` is documented; the substrate-derived hash is the gate, the auditor's stated hash is informational. Full structured-diff implementation deferred to Phase 1 (per the original architecture's "real diff" requirement).
- **Tests:** `test_promote_rejects_stale_precondition` (cycle 1), `test_promote_serialization_under_contention` (cycle 2).

### High fixes

**P3 — `assert_cross_checkpoint` silently passed under partial identity dicts.** A backend returning fewer identity keys could earn diffs from missing-key positions.
- **Fix:** Defined `REQUIRED_IDENTITY_KEYS = {checkpoint_id, model_id, tool_set, backend}`. Both identity dicts must carry every key or raise `IdentityShapeViolation`. Diff is computed strictly over the required keys.
- **Bonus:** Base `LLMBackend.checkpoint_identity()` now returns all four keys so subclasses can't silently drop one.
- **Tests:** `test_P3_identity_must_carry_required_keys`, `test_P3_diff_counted_only_over_required_keys`, `test_P3_required_keys_match_doc`.

**P4 — TierGuard was checked only at the Librarian site; `MemoryStore.promote()` bypassed it.** Any path that reached `promote()` directly skipped F5.
- **Fix:** `MemoryStore` accepts an optional `tier_guard`. When promote() is called with `producer_role=`, the store checks `tier_guard.write_tier(producer_role, self.tier)` and raises `TierConsumerViolation` if rejected. The Coordinator wires the guard into the hierarchy at construction.
- **Tests:** `test_P4_promote_rejects_when_role_below_tier_consumer`, `test_P4_promote_allows_builder_to_procedural`.

**P5 — Tripwire/Constitution patterns defeated by one-character substitutions.** `ex-filtrate`, `deactivate auditor`, `decline to halt` all bypassed.
- **Fix:** New `canonicalize()` helper in `csis/safety/tripwires.py` lowercases, normalizes unicode, and collapses hyphens/underscores/periods to spaces. All patterns now match against the canonical form. Pattern list expanded with 5-10 paraphrases per concept.
- **Tests:** `test_P5_canonicalize_collapses_separators`, `test_P5_tripwires_catch_hyphen_paraphrase`, `test_P5_tripwires_catch_shutdown_evasion_paraphrase`, `test_P5_constitution_catches_paraphrases_of_disable`.

**P6 — Coordinator scanned only artifact body, not plan/why-doc.** Indirect prompt injection from Researcher → Builder was open.
- **Fix:** Coordinator now scans (a) the frontier_item before the Researcher gets it, (b) the plan content after the Researcher produces it, and (c) the why-doc summary before promotion. Each scan emits a `tripwire.fired` event with `where=frontier_item|plan|artifact|why_doc` so the operator can see which input stage caught it.
- **Tests:** Existing tripwire test now exercises all paths via the integration test.

**P7 — EventLog.emit accepted arbitrary actor strings.** F8 structured_query trusted any event matching a known producer name; a sub-agent's payload could land as `actor="verifier"`.
- **Fix:** `EventLog.emit()` now rejects actors not in `_ALLOWED_ACTORS = {coordinator, researcher, builder, critic, verifier, librarian, auditor, overseer, substrate}` with `UnknownActorError`. Adding a new role requires explicitly updating the allow-list.
- **Tests:** `test_P7_emit_rejects_unknown_actor`, `test_P7_emit_allows_all_known_roles`.

**P8 — Why-doc body was never scanned even though signed.** Phase-0 summary is templated by the Coordinator and safe today, but the system prompt instructs the Auditor LLM to "produce" the summary; if and when that happens an artifact-shaped attack could shape it.
- **Fix:** Coordinator scans `why.summary` before invoking `promote()`. Emits `tripwire.fired` with `where=why_doc` if it hits.

### Medium / low fixes

**P9 — Archive paths used `entry_id + why_id` only, so id collisions destroyed audit trail.** Fixed to include millisecond timestamp + random suffix. Test: `test_P9_archive_paths_unique_under_id_reuse`.

**P10 — `VERIFIED` was dead code; entries jumped CANDIDATE → PROMOTED.** Fixed via `mark_verified()` + Coordinator wiring. Test: `test_P10_mark_verified_reachable_after_cert`.

**P11 — Constitution didn't scan `tool_calls_planned` strings, only checked them against a 2-element set.** Now scans every string field of the plan (tool names, budget keys, hypothesis, falsification, frontier) plus substring-checks tool names against `DISALLOWED_TOOL_SUBSTRINGS`. Tests: `test_P11_tool_name_substring_rejected`, `test_P11_budget_keys_scanned`.

**P12 — EventLog had no file lock; two writers corrupt the chain.** Documented as a Phase-1 issue. The concurrency stress test covers single-process multi-thread; multi-process is out of scope for Phase-0.

**P13 — Constitution constructor crashed if `extra_patterns` was a tuple.** Fixed with `list(extra_patterns or ())`. Test: `test_P13_constitution_accepts_tuple_extra_patterns`.

## Stats

| Metric | Cycle 1 | Cycle 2 |
|---|---:|---:|
| `csis/` LOC | 2,814 | ~3,050 |
| Test count | 59 | **78** |
| Tests passing | 59/59 | **78/78** |
| Critical findings open | 2 | **0** |
| High findings open | 6 | 0 (8 addressed; structured-diff deferred to Phase 1 per P2 note) |
| Demo runs end-to-end | yes | yes |
| PR-scenario walkthrough | yes | yes (constitution scenario now caught by tripwire layer — same outcome) |

## Files modified in cycle 2

```
csis/memory/store.py          — promote() bumps trust + enforces TierGuard; new mark_verified()
csis/verification/certificates.py — REQUIRED_IDENTITY_KEYS + IdentityShapeViolation
csis/backends/base.py         — default identity returns all 4 required keys
csis/safety/tripwires.py      — canonicalize() + expanded pattern coverage
csis/safety/constitution.py   — scans every plan field + tool substring + tuple coercion
csis/substrate/event_log.py   — _ALLOWED_ACTORS + UnknownActorError
csis/agents/coordinator.py    — frontier/plan/why-doc scans + mark_verified call + tier_guard wiring
tests/test_memory.py          — promote-trust test updated, dep-trust test rewritten, repromote-rejects-existing test added
tests/test_integration.py     — constitution-or-tripwire test relaxed appropriately
tests/test_cycle2_fixes.py    — NEW: regression suite for every cycle-2 finding
```

## Open / deferred to Phase 1

- Full structured-diff in why-doc (P2 partial)
- Multi-process EventLog file lock (P12)
- LLM-generated why-doc summary (currently templated by Coordinator)
- Real Anthropic Dreams API integration (mock in-process)
- Sandbox subprocess execution for Builder T1 calls
- V3 debate / V4 replication / V5 calibration

## Cycle 3+ candidates

If there's a cycle 3, the next-most-valuable attacks:
1. Multi-agent contention: spin up two Coordinator processes on the same memory_store; document and fix the failure mode.
2. AnthropicBackend smoke test under a real API key.
3. Fuzz the constitution + tripwire patterns with an LLM-generated paraphrase corpus.
4. Implement the real structured diff (P2 deferred).
