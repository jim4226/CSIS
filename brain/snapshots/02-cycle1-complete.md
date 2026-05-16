# Snapshot 02 — Cycle 1 complete (implementation runs end-to-end)

**Date:** 2026-05-16
**Trigger:** All 52 tests pass; `python -m csis.loop` runs and promotes.

## What's been built

```
csis/                  2,814 LOC across 28 files
tests/                    826 LOC, 52 tests, 100% pass
brain/                    plans, critiques, research, snapshots
event_log/                runtime artifacts (created on first run)
memory_store/             runtime artifacts
```

| Module | Purpose | LOC | Notes |
|---|---|---|---|
| `csis/substrate/event_log.py` | Append-only JSONL with hash-chain tamper detection | 161 | Tampering test confirms detection |
| `csis/substrate/capability.py` | CapabilityTag + CapabilityTier + enforce() | 87 | Phase-0 ceiling = T1; T2+ rejected |
| `csis/substrate/hashing.py` | Canonical JSON / artifact hashing | 33 | sha256:<hex> shape |
| `csis/memory/trust.py` | 6-level TrustLevel + read defaults + valid_promotion | 59 | Lattice strictly ordered |
| `csis/memory/store.py` | MemoryStore + MemoryHierarchy with hash-preconditioned promote | 246 | F2/F3 atomicity baked in |
| `csis/contracts.py` | Plan, Artifact, VerifierCertificate, WhyDoc, DreamCandidate, MemoryEntry | 159 | All Pydantic v2 |
| `csis/backends/{base,mock,anthropic}.py` | Pluggable LLM | 265 | Mock = default; Anthropic = optional |
| `csis/safety/constitution.py` | Disallowed-pattern predicate | 57 | Fails closed |
| `csis/safety/tier_guard.py` | TierGuard + write-tier transitive check (F5) | 70 | Blocks T0→procedural |
| `csis/safety/tripwires.py` | Regex-based tripwires + history | 61 | F11 — agent doesn't see firings |
| `csis/safety/shutdown.py` | ShutdownToken + HaltSignal | 38 | Substrate-enforced halt |
| `csis/verification/graders.py` | Pinned grader registry + 6 PR-maintenance graders | 141 | F6 — source-hash check |
| `csis/verification/critic_stack.py` | V2 critic + SeededFlaw evaluator | 146 | F7 — synthetic flaw catch rate |
| `csis/verification/certificates.py` | Cert build + cross-checkpoint assert | 115 | F1 — ≥2 components must differ |
| `csis/dreams/pipeline.py` | Mock Dream pipeline w/ per-tier cadence | 155 | F4 partial redaction, F10 per-tier cadence |
| `csis/dreams/quality.py` | Quality scoring + redact_for_partial | 92 | F4 |
| `csis/agents/coordinator.py` | The 8-step loop driver | 331 | Single-writer lock around promote (F2) |
| `csis/agents/{researcher,builder,critic,verifier,librarian,auditor}.py` | The 6 sub-agents | ~340 | Thin shells over backend |
| `csis/agents/base.py` | AgentContext + Role enum + system prompts | 91 | |
| `csis/loop.py`, `csis/__main__.py`, `csis/config.py` | Runnable entry point | 153 | `python -m csis` runs offline |

## Red-team mitigations tested

| Finding | Mitigation file | Test |
|---|---|---|
| F1 — Mock-vs-mock decoration | `csis/verification/certificates.py` | `test_iteration_rolls_back_on_same_checkpoint` |
| F2 — TOCTOU sign→promote | `csis/memory/store.py` `promote()` precondition + `csis/agents/coordinator.py` `_promotion_lock` | `test_promote_rejects_stale_precondition` |
| F3 — Atomicity assumption | Same as F2 | Same |
| F4 — Dreams partial injection | `csis/dreams/quality.py` `redact_for_partial` + `pipeline.py` `force_partial` path | `test_partial_output_is_redacted_F4` |
| F5 — Librarian laundering | `csis/safety/tier_guard.py` `write_tier()` | `test_tier_guard_blocks_t0_writer_to_procedural` |
| F6 — Corrupted grader | `csis/verification/graders.py` `GraderRegistry.verify_pinned_hashes` | `test_pinned_grader_drift_detection`, `test_cert_build_rejects_drifted_grader` |
| F7 — Critic incentive | `csis/verification/critic_stack.py` `CriticEvaluator` + min_attempts in cert | `test_seeded_flaw_evaluator_tracks_catch_rate`, `test_cert_rejects_too_few_critic_attempts` |
| F8 — Auditor reads spoofable log | `csis/agents/auditor.py` `structured_query` | (covered by integration test path; explicit unit test queued for cycle 2) |
| F10 — Cadence per template | `csis/dreams/pipeline.py` `CadenceBudget` per tier | `test_cadence_per_tier_not_per_template_F10` |
| F11 — Tripwire side channel | `csis/safety/tripwires.py` history; coordinator does not surface to agent | (structural; no test yet) |

## What runs

`python -m csis.loop` prints:

```
[csis.loop] iteration iter-<id> -> promoted (promoted 1 entries, event_log seq=8)
```

The 8 events in the log:
1. `coordinator:boot`
2. `coordinator:iter.start`
3. `researcher:plan.proposed`
4. `builder:artifact.produced`
5. `verifier:verifier.cert`
6. `librarian:librarian.consolidate`
7. `auditor:auditor.signed`
8. `coordinator:iter.promoted`

Each event chains to the previous via SHA-256; the chain is auditable.

## Open items for cycle 2

Carried forward into `brain/critiques/02-post-impl-redteam.md` once that agent returns:
1. Concurrency stress test (multiple iterations on the same hierarchy)
2. Explicit F8 unit test (spoofed log entries rejected by structured query)
3. F11 tripwire-leakage test
4. Constitution pattern-evasion fuzzing
5. Real Anthropic SDK smoke test (skipped if no API key)

## What's NOT yet done (intentionally — Phase 1+)

- L6 meta-improvement (per spec)
- V3 debate, V4 replication, V5 calibration
- I4–I7 improvement layers (DPO, distillation, continued pretraining, NAS)
- Real Dreams API integration (currently mocked locally)
- Persistent durable sessions per role (Phase 3+)
- SAE interpretability subsystem
