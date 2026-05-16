# Snapshot 01 — After parallel planning team returned

**Trigger:** Four planning agents (architect, SDK researcher, red-team, verification engineer) all completed in parallel. 11/11 substrate tests passing.

## What each agent delivered

| Agent | File | Verdict |
|---|---|---|
| Architecture | `brain/plans/01-architecture.md` | ~2,650 LOC budget. Suggests `types/` and `backends/` subpackages. Aligns with my existing skeleton. |
| SDK research | `brain/research/01-anthropic-sdk.md` | Managed Agents shipped April 8 2026 (`managed-agents-2026-04-01`). Dreams = `dreaming-2026-04-21`. Hash precondition via `content_sha256` on `memories.update` is real. SDK signatures captured. |
| Red team | `brain/critiques/01-pre-impl-redteam.md` | 18 findings, 2 critical (F1 mock-vs-mock, F2 TOCTOU sign→promote), 6 high. |
| Verification | `brain/plans/02-verification.md` | 8 PR graders, 7 math graders. Mock-alpha/mock-beta checkpoint discipline. Anti-gaming list. |

## Critical findings to bake into implementation

1. **F1 — Mock checkpoint discipline.** `CheckpointID` must include `(model_id, system_prompt_hash, tool_set_hash)`. Cert MUST reject same-model self-confirmation. → bake into `verification/certificates.py`.
2. **F2 — TOCTOU between Auditor sign and promote.** Use atomic CAS on promote (already done in `MemoryStore.promote()` via lock + precondition). Also serialize through Librarian queue. → bake into `runtime/coordinator.py`.
3. **F4 — Dreams partial injection.** Quarantined candidate stores must redact to metadata only. → bake into `dreams/quality.py`.
4. **F5 — Librarian-as-laundering.** Tier of an actor includes transitive tier of stores it writes to. → bake into `safety/tier_guard.py`.
5. **F6 — Corrupted grader.** Graders pinned by content hash at task start; cert fails on divergence. → bake into `verification/graders.py`.
6. **F7 — Critic incentive.** Seeded synthetic flaws periodically; precision/recall floor pairs with verified-gain rate. → bake into `verification/critic_stack.py`.
7. **F8 — Auditor reads spoofable log.** Apply trust to log entries; Auditor uses structured query, not free-form. → bake into `agents/auditor.py`.

## Divergences from architect's plan (intentional, documented)

- Architect proposed `csis/types/` subpackage; I'm keeping `csis/contracts.py` flat (one file, fewer imports, same effect). Refactor later only if files outgrow this.
- Architect proposed Pydantic `frozen=True`; I'm using normal mutable models because `model_copy(update=...)` works on both and I want test ergonomics. Frozen can be added in cycle 2 if it catches bugs.
- I'm not separating `runtime/scheduler.py` from `agents/`. Phase-0 has <30 LOC of scheduling.

## What's built so far (~700 LOC, 11 tests passing)

- `csis/memory/trust.py` — 6-level TrustLevel enum with read defaults
- `csis/memory/store.py` — MemoryStore with hash-preconditioned promote
- `csis/memory/__init__.py` — empty
- `csis/substrate/capability.py` — CapabilityTag, CapabilityTier, enforce(), PHASE_0_CEILING
- `csis/substrate/event_log.py` — append-only JSONL with hash-chained tamper detection
- `csis/substrate/hashing.py` — canonical JSON / artifact hashing
- `csis/substrate/__init__.py` — empty
- `csis/contracts.py` — Plan, Artifact, VerifierCertificate, WhyDoc, DreamCandidate, MemoryEntry
- `csis/__init__.py` — version + public re-exports

## Next: cycle 1 implementation push

Order:
1. `csis/backends/{base,mock,anthropic}.py` — pluggable LLM
2. `csis/agents/{base,coordinator,researcher,builder,critic,verifier,librarian,auditor}.py`
3. `csis/verification/{graders,critic_stack,certificates}.py` — with F1+F6+F7 mitigations
4. `csis/safety/{constitution,tier_guard,tripwires,shutdown}.py` — with F5 mitigation
5. `csis/dreams/{pipeline,quality}.py` — with F4 mitigation
6. `csis/loop.py` + `csis/__main__.py`
7. `tests/test_*.py` — full end-to-end test
8. Snapshot 02 + invite the red team to attack the *implementation*

Discipline: every red-team finding gets a test that proves the mitigation works.
