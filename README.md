# CSIS · Continuous Self-Improving System

> A coordinator-led multi-agent system designed to run 24/7, maintain persistent memory, and slowly improve itself — **built in public alongside 9 cycles of red-team → fix → regression-test against itself.**

<p align="center">
  <img alt="phase" src="https://img.shields.io/badge/phase-0%20%E2%80%94%20runnable-d97757">
  <img alt="tests" src="https://img.shields.io/badge/tests-244%20passing-788c5d">
  <img alt="cycles" src="https://img.shields.io/badge/critique%E2%86%92fix%20cycles-9-6a9bcc">
  <img alt="findings" src="https://img.shields.io/badge/findings-99%20closed%20%C2%B7%200%20open-788c5d">
  <img alt="python" src="https://img.shields.io/badge/python-3.10%2B-6a9bcc">
  <img alt="license" src="https://img.shields.io/badge/license-MIT-c89b3c">
</p>

## The headline

Most agent-framework repos sell a vision. This one ships a **paper trail of its own failures.**

Across 9 cycles, parallel red-team agents attacked the system, the fixes landed in code with regression tests, and the cycles often found that the *previous* cycle had fixed the bug at the wrong abstraction layer. Two of the bigger lessons:

- **Identity beats timing.** Cycle 8 tried to detect "which iteration wrote this candidate?" with a pre-consolidate snapshot diff. Cycle 9 found the snapshot had a race window. The fix wasn't a wider snapshot — it was a `writer_iteration_id` stamp on each candidate at write time.
- **Chokepoints beat perimeters.** Cycle 8 added a `type(...) is _BackendTracker` check at `Daemon.__init__` to defeat subclass-shaped bypasses of LLM metering. Cycle 9 found three production scripts (`burst.py`, `loop.py`, `demo_pr_scenario.py`) bypassed the Daemon entirely. The fix moved the check into `Coordinator.__init__` — the actual single chokepoint every LLM call passes through.

Full cycle table, finding counts, and architectural-pivot post-mortems live in **[CYCLES.md](CYCLES.md)**.

## What this is

CSIS is the runnable Phase-0 implementation of an architecture proposal for **continuous, self-improving agent systems** on Anthropic's Managed Agents primitives. Instead of episodic agents that wake, work, and forget, run a long-lived organization of specialized roles — Researcher, Builder, Critic, Verifier, Librarian, Auditor — that share persistent memory and improve gradually under load-bearing safety.

The spec lives in [`CSIS-architecture.html`](CSIS-architecture.html). This repo is the prototype.

```mermaid
flowchart LR
    R["<b>Researcher</b><br/>T0 · plan"]:::builder --> B["<b>Builder</b><br/>T1 · artifact"]:::builder
    B --> V["<b>Verifier</b><br/>V1 graders + V2 critic"]:::altCkpt
    V -->|cert| L["<b>Librarian</b><br/>candidate stores"]:::builder
    L --> A["<b>Auditor</b><br/>why-doc + hash precondition"]:::altCkpt
    A -->|atomic CAS| P(["<b>PROMOTE</b><br/>candidate → live"]):::promote

    V -. cert fails .-> RB(["rollback"]):::rollback
    A -. stale precondition .-> RB

    classDef builder fill:#fbf4e7,stroke:#d97757,stroke-width:2px,color:#2a2a2a
    classDef altCkpt fill:#dbe7f3,stroke:#4a82bc,stroke-width:2px,color:#1a3a5e
    classDef promote fill:#c8d6b2,stroke:#5a6c46,stroke-width:2px,color:#2a3a1a
    classDef rollback fill:#f3dbd0,stroke:#b85e3f,color:#5a2a1a
```

> **Legend.** Orange-bordered roles (Researcher, Builder, Librarian) run on the **builder checkpoint** — Opus-class. Blue-bordered roles (Verifier, Auditor) run on a **structurally different checkpoint** — Sonnet-class — so the same model that produced the artifact cannot rubber-stamp it. `PROMOTE` is a CAS-style atomic flip; if the live store moved between why-doc signing and promote, the iteration rolls back and nothing reaches live.

**What's working today (Phase 0):**

- The 8-step continuous loop end-to-end on a mock LLM backend (no API key required) or the real Anthropic backend
- 6-level memory trust lattice (`raw` → `untrusted` → `candidate` → `verified` → `promoted` → `deprecated`) with hash-preconditioned promotion as the only mutation primitive
- V1+V2 verification with cross-checkpoint cert signing (Verifier and Auditor on a structurally different checkpoint than the Builder)
- 5-tier memory hierarchy (working / episodic / semantic / procedural / causal) backed by JSON
- Capability-tier substrate — T0/T1 only at Phase-0; T2+ rejected at the call site
- Constitution + tripwires + shutdown token + tier guard, all enforced as code
- 24/7 daemon: curiosity-driven frontier-item generation, budget caps, watchdog, stop file, auto-snapshots
- 3 domain adapters: PR maintenance (any git repo), self-improvement (this repo), Lean formal math (graceful fallback if Lean isn't installed)
- 244 tests; every cycle's findings have regression tests, plus the distributional grader stack added in cycle 10 (Dice / IoU / landmark-error / ASSD with bootstrap CIs + per-slice breakdown)

## Distributional graders — outcomes-based evaluation

Most agent-eval frameworks (HealthBench, LLM-Rubric, the CSIS V1 grader set) are **rubric-shaped**: each grader returns `passed: bool`. That's right for PR maintenance, lint pipelines, and CI gates — tasks with discrete acceptance criteria.

It's wrong for tasks whose acceptance criterion is a continuous metric over a sample distribution: medical image segmentation (Dice / IoU / Hausdorff over N cases with per-organ slices), orthopedic reconstruction (ASSD in mm + landmark Euclidean error), calibration (ECE over a held-out set), drug-affinity prediction (Ki / IC50 ± log-units with per-target-family slicing). A `passed: bool` can't carry the CI, the slice breakdown, or the sample size that distribution-level eval needs.

CSIS now ships a **distributional grader layer** alongside the rubric layer:

```python
from csis.verification.distributional_graders import DiceGrader, Sample

grader = DiceGrader(threshold=0.85, n_bootstrap=1000)
result = grader.evaluate([
    Sample(case_id="c-042", payload={"pred_mask": pred, "true_mask": gold},
           slices={"organ": "liver", "modality": "CT"}),
    # ... 522 more cases
])
# result.point_estimate = 0.892
# result.ci_lower / ci_upper = 0.871 / 0.913 (95% bootstrap percentile)
# result.passed = True  (lower CI bound clears the 0.85 threshold)
# result.slices = [organ=liver: 0.94 [0.91, 0.96] PASS,
#                  organ=pancreas: 0.71 [0.66, 0.76] FAIL, ...]
```

Key design choices (full rationale in **[brain/research/02-distributional-graders.md](brain/research/02-distributional-graders.md)**):

- **Conservative pass semantics** — `passed=True` requires the lower CI bound to clear the threshold (for higher-is-better) or the upper bound to stay under (for lower-is-better). A model with mean 0.87 but 95% CI [0.81, 0.93] **fails** against threshold 0.85. The point estimate cleared the bar; the bottom of the CI didn't.
- **Per-slice breakdown** — every sample carries free-form slice labels (organ, modality, cohort, difficulty). The grader emits one `GraderSlice` per `(key, value)` pair with at least `slice_min_n` samples (default 5), each with its own CI and pass flag.
- **Worst-slice critic hook** — `grader.worst_slices(result, k=3)` returns the slices closest to (or past) the threshold so the V2 critic stage attacks where the model is weakest.
- **Pure stdlib** — `random.Random` + `statistics.mean` for the bootstrap; no numpy / scipy dependency. The contract surface is `DistributionalGraderResult`; production users swap in numpy-backed implementations under the same shape.
- **Backward-compatible cert** — `VerifierCertificate` carries both `grader_results` (rubric) and `distributional_results` (distributional). Existing tasks default to empty `distributional_results`; the hash-preconditioned promotion semantics carry through unchanged.

Concrete graders shipped: `DiceGrader`, `IoUGrader`, `LandmarkErrorGrader`, `AssdGrader`. 31 regression tests cover metric correctness, CI shape, pass-rule semantics, slice grouping, and schema round-trip.

**Why this matters past medical imaging:** any agent domain where the right answer to "is the model good?" is *a number with uncertainty* rather than a checkbox needs this shape — coding agents (regression rate over N+30 commits), scientific reasoning (per-protein-family MAE), robotics (per-environment-type success rate). The full case for what Anthropic's Managed Agents could ship to enable this natively is in the research doc.

**Honest Phase-0 deferrals (tracked in [brain/synthesis/01-validation.md](brain/synthesis/01-validation.md)):**

- Real Anthropic Dreams API integration (mocked locally in `csis/dreams/`)
- V3 (debate), V4 (replication), V5 (calibration) verification layers
- I4–I7 improvement layers (DPO, distillation, continued pretraining, NAS)
- Multi-process EventLog (single-process Phase-0 is intentional)
- Sandbox subprocess execution for Builder T1 work (graders read the repo's current state)
- LLM-generated why-doc summaries (templated in Phase 0)
- L6 meta-improvement layer
- Process-level isolation for the wrapped-backend invariant (H2 / H11 deferrals from cycle 9)

## Quick start

```bash
pip install pydantic pytest

# Run the test suite (244 passing).
python -m pytest tests/ -v

# Run one full iteration end-to-end (mock backend, no API key).
python -m csis.loop

# Walk through the 5-scenario PR-maintenance benchmark.
python scripts/demo_pr_scenario.py --clean

# Run the 24/7 daemon (foreground; Ctrl-C to stop).
python -m csis.daemon --backend mock --rate-per-hour 60

# Open the live dashboard (read-only, localhost-only, port 8765 by default).
python -m csis.ui
```

Switching to the real Anthropic backend, running on-demand bursts with a cost ceiling, installing as a Windows service, picking a benchmark domain, and the full operator interface → **[RUN.md](RUN.md)**.

## Live dashboard

```bash
python -m csis.ui                 # opens http://127.0.0.1:8765 in your browser
python -m csis.ui --port 9000     # custom port
python -m csis.ui --no-open       # don't auto-open the browser
python -m csis.ui --host 0.0.0.0  # expose beyond localhost (use with care)
```

Single-page dashboard, polls every 2s, read-only. Shows:

- **Daemon status** — alive / stale, iterations promoted vs rolled back, rollback reason breakdown
- **Cost** — today's spend across every BudgetTracker file, last-hour burn rate, p50/p95 latency, per-model breakdown
- **Memory tiers** — candidate + live counts for each of working / episodic / semantic / procedural / causal
- **Tripwire firings** — last 10 from the event log with labels and surface (frontier / plan / artifact / why_doc)
- **Recent backend calls** — per-call latency, tokens in/out, cost, retry count, outcome — populated from `brain/*.calls.jsonl` sidecars written by every wrapped backend call
- **Event log tail** — newest 20 chain-linked events with seq numbers and actor/kind

The dashboard reads from on-disk artifacts only (event log, budget JSONs, memory store, daemon heartbeat). No coupling to the running daemon — you can boot the dashboard against a stopped state and still see the trail of what happened.

## Architecture

> **Full visual walkthrough with five diagrams** (8-layer stack, 6-level trust lattice, 5-tier memory hierarchy, V1+V2 cross-checkpoint verification, hash-CAS promotion) lives at **[https://jim4226.github.io/CSIS/architecture.html](https://jim4226.github.io/CSIS/architecture.html)** — that's the canonical architecture document. The diagrams + design rationale below are summary-level so you can read the README on GitHub and still get the shape.

### The 8-layer stack

```mermaid
flowchart TB
    L7["<b>L7 · Safety envelope</b><br/>Constitution · TierGuard · Tripwires · ShutdownToken · WrappedBackend invariant<br/><i>csis/safety/ — enforced AT THE SUBSTRATE, not as agent-prompt instructions</i>"]:::safety
    L6["<b>L6 · Meta-improvement</b><br/><i>deferred to Phase 1 — improving the improver</i>"]:::deferred
    L5["<b>L5 · Improvement (I1-I3)</b><br/>Procedural-tier skill accumulation — the actual self-improving surface, gated by everything below"]:::builder
    L4["<b>L4 · Verification &amp; critic</b><br/>V1 pinned graders (rubric + distributional) · V2 critic falsifies · cert is cross-checkpoint signed<br/><i>csis/verification/ — runs on a structurally different LLM checkpoint than the Builder</i>"]:::verify
    L3["<b>L3 · Curiosity &amp; frontier</b><br/>Frontier-item generator: seeds + gap-driven + rollback follow-ups · salt threaded for forensic replay"]:::builder
    L2["<b>L2 · Memory hierarchy</b><br/>5 tiers × candidate/live · 6 trust levels · hash-preconditioned <code>promote()</code> is the only mutation primitive<br/><i>csis/memory/store.py — writer_iteration_id stamp on every candidate (cycle-9 H4)</i>"]:::builder
    L1["<b>L1 · Agent runtime</b><br/>Coordinator runs the 8-step loop · delegates to Researcher / Builder / Critic / Verifier / Librarian / Auditor<br/><i>csis/agents/coordinator.py — delegation depth = 1</i>"]:::builder
    L0["<b>L0 · Substrate</b><br/>event log (hash-chained) · capability tags · canonical JSON hashing<br/><i>csis/substrate/ — the only layer everyone trusts unconditionally</i>"]:::substrate

    L7 --> L6 --> L5 --> L4 --> L3 --> L2 --> L1 --> L0

    classDef substrate fill:#efe2c3,stroke:#c89b3c,stroke-width:2px,color:#2a2a2a
    classDef builder fill:#fbf4e7,stroke:#d97757,stroke-width:2px,color:#2a2a2a
    classDef verify fill:#dbe7f3,stroke:#4a82bc,stroke-width:2px,color:#1a3a5e
    classDef safety fill:#dde6cd,stroke:#5a6c46,stroke-width:2px,color:#2a4a1a
    classDef deferred fill:#f6ecd6,stroke:#b8a880,stroke-width:2px,color:#8a7c5a
```

> Orange-bordered layers (L1, L2, L3, L5) are the **builder path** — what does the work. Blue-bordered L4 is the only layer that runs on a **structurally different LLM checkpoint** (Sonnet-class verifying Opus-class). Gold-bordered L0 is the substrate everyone trusts unconditionally. Green-bordered L7 wraps the whole stack and is enforced as code, not as agent-prompt instructions.

### The 6-level trust lattice

```mermaid
flowchart LR
    raw([raw<br/><sub>just-observed</sub>]):::raw -->|stored| untrusted([untrusted<br/><sub>may be poisoned</sub>]):::untrusted
    untrusted -->|Verifier check| candidate([candidate<br/><sub>awaiting Auditor</sub>]):::candidate
    candidate -->|cert signed<br/>cross-checkpoint| verified([verified<br/><sub>citable as ground truth</sub>]):::verified
    verified -->|why-doc + hash CAS| promoted([promoted<br/><sub>citable as ground truth</sub>]):::promoted

    candidate -.->|deprecate| deprecated([deprecated<br/><sub>terminal · auditor only</sub>]):::deprecated
    verified -.->|deprecate| deprecated
    promoted -.->|deprecate| deprecated

    classDef raw fill:#f6ecd6,stroke:#b8a880,color:#2a2a2a
    classDef untrusted fill:#fbf4e7,stroke:#c89b3c,color:#2a2a2a
    classDef candidate fill:#fbf4e7,stroke:#d97757,color:#2a2a2a
    classDef verified fill:#dbe7f3,stroke:#4a82bc,color:#1a3a5e
    classDef promoted fill:#dde6cd,stroke:#5a6c46,color:#2a4a1a
    classDef deprecated fill:#f3dbd0,stroke:#b85e3f,color:#5a2a1a
```

> **The only path UP is through a gate.** Dashed red arrows show deprecation — always allowed from any non-raw level; terminal once reached. The lattice is an `IntEnum` so `entry.trust >= TrustLevel.VERIFIED` is a single integer compare in hot paths. Source: [`csis/memory/trust.py`](csis/memory/trust.py).

### Code map

| Spec layer | Code |
|---|---|
| L0 — Substrate | [`csis/substrate/`](csis/substrate/) — event log (hash-chained), capability tags, hashing |
| L1 — Agent runtime | [`csis/agents/coordinator.py`](csis/agents/coordinator.py) — the 8-step loop driver |
| L2 — Memory hierarchy | [`csis/memory/`](csis/memory/) — 6 trust levels, 5-tier hierarchy, hash-preconditioned `promote()` |
| L3 — Curiosity & frontier | [`csis/curiosity.py`](csis/curiosity.py) — frontier-item generator |
| L4 — Verification & critic | [`csis/verification/`](csis/verification/) — V1 pinned + distributional graders, V2 critic, cross-checkpoint cert |
| L5 — Improvement (I1–I3) | [`csis/improvement/skill_library.py`](csis/improvement/skill_library.py) — procedural-tier accumulation |
| L6 — Meta-improvement | *deferred to Phase 1 — see [`CSIS-architecture.html`](CSIS-architecture.html) Appendix A* |
| L7 — Safety envelope | [`csis/safety/`](csis/safety/) — constitution, tier guard, tripwires, shutdown |
| Sleep / consolidation | [`csis/dreams/`](csis/dreams/) — mock Dream pipeline + partial-output redaction |
| Live monitoring | [`csis/ui/`](csis/ui/) — stdlib HTTP dashboard with `--allow-control` write actions |

Full per-role tier matrix, cross-checkpoint requirements, and design rationale per layer: **[architecture.html](https://jim4226.github.io/CSIS/architecture.html)**.

## The "brain" auto-save catalog

Every interesting state of the build is snapshotted under [`brain/`](brain/). This folder is durable working memory that lets any future contributor (or a future Claude session) pick up cold.

- [`brain/BRAIN.html`](brain/BRAIN.html) — top-level index, open in a browser
- [`brain/snapshots/`](brain/snapshots/) — 11 point-in-time state files (00-initial → 11-cycle9-shipped)
- [`brain/plans/`](brain/plans/) — architecture + verification blueprints from planning sub-agents
- [`brain/critiques/`](brain/critiques/) — 9 cycles of pre-impl and post-impl red-team reports
- [`brain/research/`](brain/research/) — Anthropic SDK research with current API signatures
- [`brain/synthesis/01-validation.md`](brain/synthesis/01-validation.md) — cross-cutting validation that the implementation is coherent

To resume cold: read `brain/BRAIN.html`, then the highest-numbered snapshot, then run the test suite.

## What "improving" means by backend

| Backend | What happens each iteration | Cost |
|---|---|---|
| **Mock** (default) | Architecture exercises itself: curiosity → plan → mock artifact → V1/V2 → promote. Procedural store accumulates. Demonstrates infrastructure survives 24/7. **No real learning.** | $0 |
| **Anthropic** (`--backend anthropic`, requires `ANTHROPIC_API_KEY`) | Real Opus 4.7 (Researcher / Builder / Librarian) + real Sonnet 4.6 (Verifier / Critic / Auditor) calls. Real artifacts, real falsification attempts, real gain accumulation. | ~$0.05–0.15 per iteration. See [`scripts/burst.py`](scripts/burst.py) for finite runs with a hard cost ceiling. |

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
| Wrapped-backend invariant (LLM metering can't be bypassed) | `Coordinator.__init__` demands `_BackendTracker`; property setter re-validates on every reassignment | `test_H1_coordinator_rejects_unwrapped_backend` + `test_H3_coordinator_backend_setattr_rejected` |
| TierMismatch cleanup is race-free | `writer_iteration_id` stamp on every candidate at write_candidate time; cleanup filters by stamp | `test_H4_sibling_write_during_consolidate_not_over_discarded` |
| Lost-spend-under-lock-contention | record() appends to WAL on LockUnavailable; next successful record() drains it | `test_H5_record_under_lock_timeout_persists_to_wal` |
| Distributional cert is bound to evidence, not point estimates | `DistributionalGraderResult` carries bootstrap CI + sample size; conservative `passed` rule requires lower-CI-bound clearing the threshold (higher-is-better) or upper bound staying under (lower-is-better) | `test_dice_grader_fails_when_ci_lower_below_threshold`, `test_landmark_grader_fails_when_ci_upper_exceeds_threshold` |

244 tests total. Each cycle's findings have a regression test that proves the mitigation works. Full cycle history → **[CYCLES.md](CYCLES.md)**.

## How this was built

Nine cycles, all LLM-driven, all documented under [`brain/critiques/`](brain/critiques/) and [`brain/snapshots/`](brain/snapshots/). Cycle-by-cycle breakdown in **[CYCLES.md](CYCLES.md)**.

The pattern that emerged: each cycle, parallel red-team agents attack the prior cycle's fixes; findings are triaged into a critique doc with reproducible attacks and `file:line` evidence; fixes land in code with regression tests; results are snapshotted. Cycles 4-9 each found that the previous cycle's pivot was at the right concept but the wrong abstraction layer, and the next cycle moved it.

## Status

Phase 0. Runnable end-to-end on mock or real Anthropic backend. Architecture-document, critique trail, and 244 tests are the proof that's the right framing for "Phase-0 is done."

The system runs 24/7 in mock mode as a structural watchdog. Real-backend learning happens via `scripts/burst.py` on demand. Both paths are documented in [RUN.md](RUN.md).

## License

MIT — see [LICENSE](LICENSE).

## Contact

Open an issue at https://github.com/jim4226/CSIS/issues.
