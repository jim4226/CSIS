# Snapshot 00 — Initial State

**Date:** 2026-05-16
**Trigger:** Session start, before any implementation work.

## What this project is

The user has authored a comprehensive architecture proposal for **CSIS** (Continuous Self-Improving System) — a coordinator-led multi-agent system intended for Anthropic's Managed Agents platform. Documents in this folder:

- `CSIS-architecture.html` — interactive HTML version (the centerpiece, 650 lines)
- `CSIS-deck.pptx` — 19-slide deck
- `CSIS-memo.docx` — 8-page memo
- `CSIS-whitepaper.docx` — long-form formal version

## What the user asked for

> "Build out the actual infrastructure to be implemented within Claude, make sure it is possible that it could run. Iterate, plan properly, attack it at every angle, agents speaking to each other in teams like a company. Several cycles. Implement, test, iterate, fix continuously, no stopping. When we hit 80% context window, save everything as HTML or markdown to a folder for reference. Auto-catalog in a brain folder."

## Operating contract (self-imposed)

1. **Build it real.** Python implementation that actually executes, gracefully degrading without an API key (mock LLM backend).
2. **Multiple angles in parallel.** Use sub-agents like a team — architect, safety, verifier, SDK researcher — so we don't tunnel-vision.
3. **Cycles.** Plan → implement → test → critique → fix → repeat.
4. **Catalog as we go.** Every cycle writes a snapshot under `brain/snapshots/` so future-Claude (or the user) can resume cold.
5. **Faithful to the doc.** Phase-0 scope: T0/T1 only, V1+V2 only, I1-I3 only, coordinator-led, cross-checkpoint Verifier/Auditor, hash-preconditioned why-docs, candidate-store promotion gate.

## CSIS doc — Phase-0 contract (one paragraph)

> Build a coordinator-led CSIS prototype on Managed Agents in a single benchmark domain (proposed: open-source PR maintenance), where one coordinator brain supervises **Researcher, Builder, Critic, Verifier, Librarian, and Auditor** roles within a single shared container; all memory writes go through **candidate Memory Stores**; **Dreams** consolidate only into reviewable output stores; and every promoted change requires a **Verifier certificate (cross-checkpoint)** plus an **Auditor why-doc with a hash precondition**.

## Components I need to build

| CSIS layer | Concrete module to write |
|---|---|
| L0 substrate | `csis/substrate/` — sandbox, capability tier tags, event log |
| L1 agent runtime | `csis/runtime/coordinator.py`, `csis/runtime/harness.py` |
| L2 memory | `csis/memory/{store,trust,tiers}.py` |
| L3 curiosity | inside `csis/agents/researcher.py` |
| L4 verification | `csis/verification/{v1_graders,v2_critic}.py` |
| L5 improvement | `csis/improvement/skills.py` (I1-I3) |
| L6 meta | deferred to Phase 1 |
| L7 safety | `csis/safety/{constitution,tripwires,shutdown}.py` |
| Sleep | `csis/dreams/{consolidator,quality}.py` |

## Hard rule from the doc

> An update cannot enter the system unless it carries a verified-gain certificate signed by the Verifier on a different model checkpoint than the agent that produced the gain, plus an Auditor why-doc with a hash-precondition matching the live store at promotion time.

This is the architectural invariant. Every test must prove this still holds.

## Folder layout decided

```
Superintellegnce/
├── csis/                # the implementation
│   ├── substrate/
│   ├── runtime/
│   ├── memory/
│   ├── agents/
│   ├── verification/
│   ├── safety/
│   ├── improvement/
│   ├── dreams/
│   └── loop.py
├── tests/               # pytest suite
├── event_log/           # append-only event log (created at runtime)
├── brain/               # auto-save catalog (this folder)
└── CSIS-*               # original docs
```
