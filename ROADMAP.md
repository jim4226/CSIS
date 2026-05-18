# CSIS roadmap

Phase 0 is shipped: the substrate runs, the loop completes end-to-end, 9 cycles of red-team-self have closed 96 of 99 findings. What follows is the prioritized list of things this prototype cannot yet do — and roughly when each becomes worth attempting.

## Phase 1 milestones (in priority order)

### P1.1 · Real Dreams API integration · **next up**

Replace the mock dreaming pipeline at `csis/dreams/` with the real Anthropic Dreams API once it's accessible to the operator. Today's mock implements the same partial-output-redaction and quality-scoring discipline so the swap should be a closed change. Risk: real Dreams has different latency + cost characteristics; will need a new round of budget tracking.

**Tracking**: see issue `roadmap-P1.1-dreams-integration`.

### P1.2 · Process-level isolation for the wrapped-backend invariant (H2 + H11) · **load-bearing**

Cycle 9 deferred two findings honestly: closure-cell mutation (H2) and POSIX unlink-during-lock (H11). Both require leaving the pure-Python in-process trust model. Two candidate paths:

- **OS subprocess sandbox**: run each agent's LLM call through a separate process bounded by OS capabilities (`prlimit` on Linux, Job Objects on Windows). The wrapped-backend invariant becomes "you can only `exec` the wrapper binary."
- **eBPF / syscall-level metering**: hook the system call boundary so any network call goes through the metered path. Heavier; more rigorous.

Either makes the H2 closure-cell attack impossible because the attacker would need code-execution rights inside a separate process they don't control.

### P1.3 · V3 (debate) verification

A second pinned Verifier on yet another checkpoint argues against the first Verifier's cert. Disagreement triggers escalation. Already designed in `CSIS-architecture.html §7.3`; just needs implementation + a new test class.

### P1.4 · V4 (replication) verification

Re-run the Builder on a different checkpoint with the same plan; require both artifacts to produce a passing cert. Catches the "lucky-Builder" failure mode where one model happens to produce a passing artifact and a different model wouldn't. Stronger than V1+V2 because it's substrate-level, not text-level.

### P1.5 · V5 (calibration) verification

Verifier reports its own confidence with a calibration history. Cert promotion is gated on calibrated confidence threshold, not on a binary pass/fail. This is the layer where the system stops being "follow the rules" and starts being "follow the rules with judgment about its own uncertainty."

### P1.6 · Multi-process EventLog

Today's `csis/substrate/event_log.py` is intentionally single-process. Phase 1 wants two cooperating daemons (e.g., one running mock, one running real) writing to a shared event log with hash-chain integrity. Approach: file-lock-mediated append + per-process hash chains that merge at a Coordinator-level meta-log.

### P1.7 · Sandbox subprocess for Builder T1 work

Today's Builder graders read the repo's current state; a real Builder would write to a sandbox subprocess running the artifact. Need: a sandboxed Python subprocess with no network and a chroot-style filesystem view, results piped back as `Artifact.body`. The cycle-9 H1+H3 chokepoint discipline carries over: the sandbox spawn is a single chokepoint.

### P1.8 · LLM-generated why-doc summaries

Today the why-doc summary is templated by the Coordinator. The architecture document treats this as a placeholder: a real Auditor would have the LLM write the summary AFTER reading the structured query results. The substitution is a one-method change but requires another tripwire pass on the LLM output before promote.

## Phase 2 milestones (later)

### P2.1 · I4 (DPO) improvement layer

Use the daemon's accumulated promoted/rolled-back set as a preference dataset for direct preference optimization. The system literally trains a sharper version of itself from its own audit log.

### P2.2 · I5 (distillation)

Distill the promoted-skill set into a smaller model that runs faster at iteration time.

### P2.3 · I6 (continued pretraining) and I7 (architecture search)

The longest-arc layers. Out of scope for any near-term planning.

### P2.4 · L6 (meta-improvement)

The system writes new graders for itself based on patterns in the cycle-history. Today's graders are hand-written; L6 would write the next cycle's graders from what cycle N-1 missed.

## Open invitations to contributors

These are areas where outside contribution would meaningfully advance the project without requiring deep familiarity with the architecture:

- A **local-backend adapter** (vLLM, llama.cpp, Ollama) so the project runs without an Anthropic key
- A **new benchmark domain** beyond PR-maintenance / self-improve / Lean (CTF, reverse-engineering, security audit, scientific literature)
- A **conference-shaped writeup** of the "identity beats timing" and "chokepoints beat perimeters" patterns observed across cycles 4-9
- **Independent replication of the cycle log** — pick cycle 6 or 7, follow the critique doc, re-execute the attacks, and confirm they're closed (or open a new finding if not)

## What the roadmap does NOT promise

- A timeline. Phase 0 took N months of part-time work; Phase 1 will take longer.
- Compatibility with frameworks like LangGraph, CrewAI, AutoGen. CSIS is a different shape (coordinator-led, no DAG, no handoff orchestration).
- A "production-ready" release. Phase 0 is research-grade infrastructure. Phase 1 will be too.

## Pointer back

← [README.md](README.md) for the project overview
← [CYCLES.md](CYCLES.md) for what's already shipped
