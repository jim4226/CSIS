# CSIS · Continuous Self-Improving System

> A coordinator-led multi-agent system that runs 24/7, maintains persistent memory, and slowly improves itself — built on the architecture described in [`CSIS-architecture.html`](CSIS-architecture.html) (v0.2 Phase-0 contract).

<p align="center">
  <img alt="status" src="https://img.shields.io/badge/status-Phase--0-d97757">
  <img alt="tests" src="https://img.shields.io/badge/tests-92%20passing-788c5d">
  <img alt="python" src="https://img.shields.io/badge/python-3.10%2B-6a9bcc">
  <img alt="license" src="https://img.shields.io/badge/license-MIT-c89b3c">
</p>

```
┌───────────────────────────────────────────────────────────────────────────┐
│                            CSIS · the loop                                │
│                                                                           │
│   Researcher  →  Builder  →  Verifier  →  Librarian  →  Auditor  →  PROMOTE │
│      (T0)        (T1)       (T1, alt        (T0)        (T0, alt           │
│                              ckpt)                       ckpt)              │
│                                ↓                            ↓               │
│                          V1 graders                  hash-preconditioned    │
│                          + V2 critic                     why-doc CAS         │
│                                ↓                            ↓               │
│                       VerifierCert                   atomic candidate→live  │
└───────────────────────────────────────────────────────────────────────────┘
```

## What this is

CSIS is the runnable implementation of an architecture proposal for **continuous, self-improving agent systems** built on Anthropic's Managed Agents primitives. The idea: instead of episodic agents that wake, work, and forget, run a long-lived organization of specialized roles — Researcher, Builder, Critic, Verifier, Librarian, Auditor — that share persistent memory and improve gradually under load-bearing safety.

The architecture document ([CSIS-architecture.html](CSIS-architecture.html)) is the spec. This repo is the prototype.

**What's working today (Phase 0):**

- The 8-step continuous loop from §4 of the spec, end-to-end runnable on a mock LLM backend (no API key required) or the real Anthropic backend.
- 6-level memory trust lattice (`raw` → `untrusted` → `candidate` → `verified` → `promoted` → `deprecated`) with hash-preconditioned promotion as the only mutation primitive.
- V1+V2 verification stack with cross-checkpoint cert signing (the Verifier and Auditor run on a structurally different checkpoint than the Builder).
- 5-tier memory hierarchy (working / episodic / semantic / procedural / causal) backed by JSON files.
- Capability-tier substrate (T0/T1 only at Phase-0; T2+ rejected at the call site).
- Constitution + tripwires + shutdown-token + tier guard — all enforced as code, not as prompt.
- 24/7 daemon with curiosity-driven frontier-item generation, budget caps, watchdog, stop-file, and auto-snapshots.
- 3 domain adapters: PR maintenance (any git repo), self-improvement (this repo), Lean formal math (with graceful fallback if Lean isn't installed).
- 92 tests; every red-team mitigation has a regression test.

**What's not Phase 0:**

- Real Anthropic Dreams API integration (mocked locally in `csis/dreams/`).
- V3 (debate), V4 (replication), V5 (calibration) verification layers.
- I4–I7 improvement layers (DPO, distillation, continued pretraining, neural architecture search).
- Multi-process EventLog (single-process Phase-0 is intentional).
- Sandbox subprocess execution for Builder T1 work (graders read the repo's current state).
- LLM-generated why-doc summaries (templated in Phase 0).
- L6 meta-improvement layer.

These are honest deferrals to Phase 1+, all listed in [brain/synthesis/01-validation.md](brain/synthesis/01-validation.md) with priorities.

## Quick start

```bash
pip install pydantic pytest

# Run the test suite.
python -m pytest tests/ -v

# Run a single full iteration end-to-end (mock backend).
python -m csis.loop

# Walk through the 5-scenario PR-maintenance benchmark.
python scripts/demo_pr_scenario.py --clean

# Run the 24/7 daemon (foreground; Ctrl-C to stop).
python -m csis.daemon --backend mock --rate-per-hour 60
```

For switching to the real Anthropic backend, running on-demand bursts with a cost ceiling, installing as a Windows service, picking a benchmark domain, and the full operator interface, read **[RUN.md](RUN.md)**.

## Architecture map

| Spec layer (`CSIS-architecture.html`) | Code |
|---|---|
| L0 — Substrate | [`csis/substrate/`](csis/substrate/) — event log (hash-chained), capability tags, hashing |
| L1 — Agent runtime | [`csis/agents/coordinator.py`](csis/agents/coordinator.py) — the 8-step loop driver |
| L2 — Memory hierarchy | [`csis/memory/`](csis/memory/) — 6 trust levels, 5-tier hierarchy, hash-preconditioned `promote()` |
| L3 — Curiosity & frontier | [`csis/curiosity.py`](csis/curiosity.py) — frontier-item generator (seeds + gap-driven + rollback follow-ups) |
| L4 — Verification & critic | [`csis/verification/`](csis/verification/) — V1 pinned graders, V2 critic, cross-checkpoint cert |
| L5 — Improvement (I1–I3) | [`csis/improvement/skill_library.py`](csis/improvement/skill_library.py) — procedural-tier accumulation |
| L6 — Meta-improvement | *deferred to Phase 1* |
| L7 — Safety envelope | [`csis/safety/`](csis/safety/) — constitution, tier_guard, tripwires, shutdown |
| Sleep / consolidation | [`csis/dreams/`](csis/dreams/) — mock Dream pipeline + quality scoring + partial-output redaction |

The full eight-layer stack and the per-role tier matrix are in `CSIS-architecture.html` §3 and §5.

## The "brain" auto-save catalog

Every interesting state of the build is snapshotted under [`brain/`](brain/). This folder is the durable working memory that lets any future contributor (or a future Claude session) pick up cold.

- [`brain/BRAIN.html`](brain/BRAIN.html) — top-level index, open in a browser
- [`brain/snapshots/00-initial.md`](brain/snapshots/00-initial.md) → snapshot 04 — point-in-time state files
- [`brain/plans/`](brain/plans/) — architecture + verification blueprints from planning sub-agents
- [`brain/critiques/`](brain/critiques/) — pre-impl and post-impl red-team reports (31 total findings, 0 critical/high open)
- [`brain/research/`](brain/research/) — Anthropic SDK research with current API signatures
- [`brain/synthesis/01-validation.md`](brain/synthesis/01-validation.md) — cross-cutting validation that the implementation is coherent

To resume cold: read `brain/BRAIN.html`, then the highest-numbered file in `brain/snapshots/`, then run the test suite. The full read order is documented in `brain/README.md`.

## What "improving" means by backend

| Backend | What happens each iteration | Cost |
|---|---|---|
| **Mock** (default) | Architecture exercises itself: curiosity → plan → mock artifact → V1/V2 → promote. Procedural store accumulates. Demonstrates infrastructure survives 24/7. **No real learning.** | $0 |
| **Anthropic** (`--backend anthropic`, requires `ANTHROPIC_API_KEY`) | Real Opus 4.7 (Researcher/Builder/Librarian) + real Sonnet 4.6 (Verifier/Critic/Auditor) calls. Real artifacts; real falsification attempts; real gain accumulation. | ~$0.05–0.15 per iteration. See [`scripts/burst.py`](scripts/burst.py) for finite runs with a hard cost ceiling. |

## Safety properties (load-bearing)

| Property | Implementation | Regression test |
|---|---|---|
| Capability cannot grow faster than oversight | Phase-0 hard ceiling = T1; T2+ rejected at the call site | `test_enforce_rejects_above_phase_0_ceiling_even_if_actor_authorized` |
| Memory mutation is reversible | Candidate stores + `MemoryStore.promote()` is the only path to live | `test_promote_rejects_stale_precondition` |
| Cross-checkpoint verification | `assert_cross_checkpoint` requires ≥2 distinct identity components | `test_cross_checkpoint_requires_two_distinct_components` |
| Grader integrity | Pinned source-hash check at every cert build | `test_pinned_grader_drift_detection` |
| Audit-only structured query | `structured_query()` allow-lists trusted producers only | `test_structured_query_excludes_untrusted_producer` |
| Shutdown enforced at substrate | `ShutdownToken.halt()` raises `HaltSignal` on next iteration | `test_shutdown_blocks_subsequent_checks` |
| Atomic promotion under contention | Single-writer lock + hash-preconditioned CAS | `test_promote_serialization_under_contention` |

There are 92 tests total. Each red-team finding (18 pre-impl + 13 post-impl) has a corresponding test that proves the mitigation works.

## How this was built

Two cycles, both LLM-driven, both documented:

1. **Cycle 1** — 4 planning sub-agents (architect, SDK researcher, pre-impl red team, verification engineer) returned in parallel; their outputs synthesized into the implementation skeleton; 11 substrate tests → 52 full tests; demo loop running end-to-end.
2. **Cycle 2** — post-implementation red team attacked the *implementation* (not the architecture); 13 new findings including 2 critical; all critical + high addressed by promoting single-site checks into substrate-level invariants; 78 → 92 tests with new daemon + curiosity + skill + domain coverage.

[`brain/synthesis/01-validation.md`](brain/synthesis/01-validation.md) is the synthesis pass over both cycles' outputs. **Verdict: valid for Phase-0 release.**

## Status

Phase 0. The repository is the prototype that has to work before the longer-arc framing in [Appendix A](CSIS-architecture.html#appA) can be argued for.

The system runs 24/7 in mock mode as a structural watchdog. Real-backend learning happens via `scripts/burst.py` on demand. Both paths are documented in [RUN.md](RUN.md).

## License

MIT — see [LICENSE](LICENSE).

## Contact

Jaron — jim4226@miami.edu — University of Miami
