# CSIS Phase-0 — operator guide

The runnable prototype of the architecture described in
[`CSIS-architecture.html`](CSIS-architecture.html). Pure Python; runs
offline by default; no API key required to demo. Built on Windows but
should run on macOS / Linux unchanged.

## TL;DR

```bash
pip install pydantic pytest

# Run the test suite (85 tests).
python -m pytest tests/ -v

# Run a single 8-step loop iteration end-to-end (no API key needed).
python -m csis.loop

# Walk through the 5-scenario PR-maintenance benchmark.
python scripts/demo_pr_scenario.py --clean

# Run the 24/7 daemon (foreground, Ctrl-C to stop).
python -m csis.daemon --backend mock --rate-per-hour 60

# Run the 24/7 daemon with auto-restart on crash (PowerShell).
.\scripts\run_daemon.ps1 -Backend mock -RatePerHour 60

# Stop the daemon at any time:
New-Item -ItemType File .\STOP
# or just delete it later:
Remove-Item .\STOP
```

Expected end-state after the demo: 1 iteration promotes, 4 iterations roll
back (one per failure class — diff-scope, broken tests, perf regression,
constitution violation), the chained event log stays intact.

## Architecture in one paragraph

A Coordinator runs 6 sub-agents (Researcher, Builder, Critic, Verifier,
Librarian, Auditor) on the 8-step loop from CSIS §4. Every memory write
goes through a candidate store. Promotion requires (a) a Verifier
certificate built on a different model checkpoint than the Builder, (b)
an Auditor why-doc whose `hash_precondition` matches the live store at
promote time. The promotion call is atomic — if the live store moved
between when the why-doc was signed and when promote was attempted, the
substrate refuses and emits a rolled-back event.

## File map

```
csis/                       implementation (2,800 LOC, 28 files)
  substrate/                event log, capability tags, hashing
  memory/                   trust levels, MemoryStore, hierarchy
  safety/                   constitution, tier_guard, tripwires, shutdown
  backends/                 LLMBackend ABC + MockBackend + AnthropicBackend
  verification/             V1 graders, V2 critic, cert build (F1, F6, F7)
  dreams/                   mock Dream pipeline + quality + F4 redaction
  agents/                   coordinator + 6 sub-agents
  loop.py                   runnable demo entry point
  __main__.py               python -m csis runs the demo

tests/                      66+ pytest tests, one per major invariant
scripts/
  demo_pr_scenario.py       5-scenario PR-maintenance walkthrough

brain/                      auto-save catalog (read this to resume cold)
  BRAIN.html                top-level index — open in a browser
  README.md                 catalog layout explanation
  snapshots/                point-in-time state files (00, 01, 02, ...)
  plans/                    blueprint outputs from planning sub-agents
  critiques/                red-team reports (pre- and post-impl)
  research/                 SDK / pattern research
```

## Tier-by-tier mapping (CSIS doc § to code)

| CSIS layer (spec §) | Code |
|---|---|
| L0 substrate | `csis/substrate/event_log.py`, `csis/substrate/capability.py`, `csis/substrate/hashing.py` |
| L1 agent runtime | `csis/agents/coordinator.py`, `csis/agents/base.py` |
| L2 memory | `csis/memory/trust.py`, `csis/memory/store.py` |
| L3 curiosity | inside `csis/agents/researcher.py` (Phase-0 stub) |
| L4 verification | `csis/verification/` |
| L5 improvement (I1–I3) | candidate-store path through `csis/memory/store.py` + `csis/agents/librarian.py` |
| L6 meta | **out of scope for Phase-0** |
| L7 safety | `csis/safety/` |
| Sleep / consolidation | `csis/dreams/pipeline.py`, `csis/dreams/quality.py` |

## Red-team findings and their mitigations

| ID | Finding | Mitigation | Test |
|---|---|---|---|
| F1 | Mock-vs-mock cross-checkpoint is decorative | `verification/certificates.py: assert_cross_checkpoint` requires ≥2 distinct components in `{checkpoint_id, model_id, tool_set, backend}` | `test_cross_checkpoint_requires_two_distinct_components`, `test_iteration_rolls_back_on_same_checkpoint` |
| F2 | TOCTOU between Auditor sign and promote | `memory/store.py: MemoryStore.promote()` re-checks live hash under a lock; Coordinator wraps in `_promotion_lock` | `test_promote_rejects_stale_precondition`, `test_promote_serialization_under_contention` |
| F3 | Promotion atomicity not provided by substrate | Same as F2 + chained event log replay-on-wake | Covered by F2 tests |
| F4 | Dreams partial output is an injection vector | `dreams/pipeline.py` `force_partial` path → `dreams/quality.py: redact_for_partial` returns metadata only | `test_partial_output_is_redacted_F4` |
| F5 | T0 → T1 escalation via Librarian | `safety/tier_guard.py: write_tier()` rejects writes whose destination consumer tier > role ceiling | `test_tier_guard_blocks_t0_writer_to_procedural` |
| F6 | V1 cannot catch corrupted grader | `verification/graders.py: GraderRegistry.verify_pinned_hashes` checks pinned source hash at every cert build | `test_pinned_grader_drift_detection`, `test_cert_build_rejects_drifted_grader` |
| F7 | Critic incentive is structurally absent | `verification/critic_stack.py: CriticEvaluator` tracks catch rate on seeded flaws independent of throughput; cert requires `min_critic_attempts` | `test_cert_rejects_too_few_critic_attempts`, `test_seeded_flaw_evaluator_tracks_catch_rate` |
| F8 | Auditor reads spoofable session log | `agents/auditor.py: structured_query()` allow-lists trusted producers only | `test_structured_query_excludes_untrusted_producer` |
| F10 | Cadence bypass via template variants | `dreams/pipeline.py: CadenceBudget` keyed per tier, not per template | `test_cadence_per_tier_not_per_template_F10` |
| F11 | Tripwire firings as side-channel oracle | `agents/coordinator.py` emits only label, never snippet, in `tripwire.fired` event | `test_coordinator_event_for_tripwire_has_labels_not_snippets` |

## Switching to the real Anthropic backend

```bash
pip install anthropic
export ANTHROPIC_API_KEY=sk-ant-...
export CSIS_BACKEND=anthropic
python -m csis.loop
```

The default checkpoint mapping is:

| CSIS label | Anthropic model |
|---|---|
| `mock-alpha` or `alpha` | `claude-opus-4-7` |
| `mock-beta` or `beta` | `claude-sonnet-4-6` |

These map to the two Dreams-supported models. F1's cross-checkpoint
invariant is satisfied by construction: Opus and Sonnet have different
model IDs.

To use a different mapping, override the model_map argument to
`AnthropicBackend(model_map={...})` or extend `csis/backends/anthropic.py`.

**Important**: every iteration costs tokens on both checkpoints (Builder
side + Verifier side + critic). At Phase-0 prices (rough order of
magnitude in May 2026) a single iteration is on the order of a few cents
of LLM cost. Plan budget accordingly.

## Resuming from a previous run

The event log under `event_log/` and memory stores under `memory_store/`
are persistent. Re-running `python -m csis.loop` will append to them
rather than start fresh. To reset:

```bash
rm -rf event_log/ memory_store/
```

The `--clean` flag on `scripts/demo_pr_scenario.py` does the equivalent
for just the demo scenario's stores.

## Shutdown

The Overseer (operator) halts the system by calling
`ShutdownToken.halt()`. In a deployed setup this is wired to a control
plane endpoint; in the demo it's a Python call. After halt, any
subsequent `run_iteration` raises `HaltSignal` — no agent prompt can
override this, by L0 design.

## Where to look next

- `brain/snapshots/02-cycle1-complete.md` — what's in the current build.
- `brain/critiques/01-pre-impl-redteam.md` — pre-impl threat model (18 findings).
- `brain/critiques/02-post-impl-redteam.md` — post-impl threat model.
- `CSIS-architecture.html` — the spec this implements (open in browser).

## 24/7 daemon

`csis/daemon.py` runs the loop continuously. Each tick: ask the curiosity
module for the next frontier item, run one Coordinator iteration, record
the outcome, touch the heartbeat, write an auto-snapshot every N
iterations.

### Files the daemon writes

| Path | What |
|---|---|
| `brain/daemon.heartbeat` | JSON, refreshed every iteration. External monitor reads `ts` to detect staleness. |
| `brain/daemon.stats.json` | Rolling stats: total iters, promoted, rolled-back, rollback reason histogram, skill library size. |
| `brain/snapshots/auto-NNNNNN.md` | Auto-snapshot every `--snapshot-every` iterations (default 25). |
| `brain/daemon_logs/daemon-<stamp>.log` | Per-run stdout/stderr capture (PowerShell launcher only). |
| `event_log/session.jsonl` | Continued from prior runs. Chain stays intact across restarts. |
| `memory_store/<tier>.{candidate,live}.json` | Persistent memory. Procedural tier grows as the system accumulates skills. |

### Stop / kill

- Drop a `STOP` file in the repo root. The daemon checks every tick and exits cleanly within ~1 sleep interval.
- Send SIGINT/SIGTERM. The signal handler calls `ShutdownToken.halt()`.
- Just close the console. The next launcher start will pick up where it left off (event log + memory stores persist).

### Budget / rate

`--rate-per-hour N` caps work to N iterations per rolling hour. The
daemon sleeps until the budget window slides. `--sleep-s S` adds a fixed
sleep between iterations (default 1s). For mock backend this is a CPU
politeness knob; for the real Anthropic backend it directly limits
spend.

### Surviving reboots

Two options on Windows:

1. **Task Scheduler.** Create a Task triggered "At log on" or "At startup," Action: `pwsh.exe -File <repo>\scripts\run_daemon.ps1`, Working Dir: `<repo>`. The PowerShell launcher already restarts on crash.
2. **NSSM (Non-Sucking Service Manager).** Run it as a true Windows service:
   ```
   nssm install CSIS python -u -m csis.daemon
   nssm set CSIS AppDirectory <path-to-csis-repo>
   nssm start CSIS
   ```

### What "improving" means by backend

- **Mock (default)** — the architecture exercises itself end-to-end. The procedural store accumulates skill entries, the event log grows monotonically, dreams consolidate, stats trend, snapshots accumulate. The *content* is scripted, so this demonstrates the system is structurally sound but doesn't *learn* anything new about the world.
- **Real Anthropic backend** — every iteration is a real Opus call (Researcher/Builder/Librarian) + a real Sonnet call (Verifier/Critic/Auditor). The Builder produces real artifacts; the Verifier really runs the graders; the Critic really attempts to falsify. At Phase-0 prices a single iteration is roughly a few cents (Opus is the heavier side). At `--rate-per-hour 60` that's on the order of $1-3/hour. Set `--rate-per-hour 6` and `--sleep-s 600` to crawl at $0.10-0.30/hour for casual long-running.

### Switching to the real backend

```bash
pip install anthropic
$env:ANTHROPIC_API_KEY = "sk-ant-..."
python -m csis.daemon --backend anthropic --rate-per-hour 12
```

There is no per-day budget cap baked into the daemon. The companion
`scripts/burst.py` enforces a per-run cost ceiling instead — see "Bursts" below.

## Bursts — finite real-backend runs

`scripts/burst.py` is for when you want to spend a fixed amount of LLM
budget on a short burst of real work, then exit. Pair it with the mock
daemon running 24/7 as a watchdog.

```bash
# 10 real iterations against the CSIS codebase itself.
python scripts/burst.py --iters 10 --domain self_improve

# 5 real iterations against your own git repo.
python scripts/burst.py --iters 5 --domain pr_maintenance --repo-path C:/path/to/repo

# 3 real Lean iterations (gracefully soft-passes if Lean isn't installed).
python scripts/burst.py --iters 3 --domain lean_math

# Hard cost ceiling. Burst exits cleanly when the rough estimate exceeds it.
python scripts/burst.py --iters 50 --domain self_improve --max-cost-usd 2.0
```

Cost estimate uses approximate Phase-0 prices and is intentionally
conservative. The ceiling is checked *before* each iteration so you
never overspend by more than one iteration's worth.

## Domain adapters

Three domain adapters ship in `csis/domains/`. The daemon and burst
both accept `--domain <name>`; the daemon swaps the V1 grader registry
+ curiosity-seed list to match.

| Name | What it does | Prereqs |
|---|---|---|
| `pr_maintenance` | Real graders against a target git repo: pytest, ruff, mypy. | A git repo path; pytest in env. ruff/mypy optional (soft-pass if missing). |
| `self_improve` | Same as PR maintenance but pointed at the CSIS repo itself. Strict diff_scope grader blocks edits to load-bearing files (safety, coordinator, auditor, verifier, memory store, etc.). | None — just `python scripts/burst.py --domain self_improve`. |
| `lean_math` | V1 = `lean --check` on the artifact body + sorry/admit grep + line-budget cap. | Lean 4 on PATH. With `graceful_fallback=True` (default) it soft-passes when Lean is missing. |

Each adapter's `can_run()` reports prerequisites. The daemon refuses
to start when a domain's prereqs aren't met (returns exit code 2 with
a printed reason).

## Surviving reboots (continued)

### Option A — manual PowerShell launcher

```powershell
# In a regular PowerShell window:
.\scripts\run_daemon.ps1 -Backend mock -RatePerHour 60
```

The launcher restarts on crash, logs to `brain/daemon_logs/`, and
exits cleanly when a `STOP` file appears in the repo root. Close the
window to stop; it won't survive log-off.

### Option B — Windows service via NSSM (survives log-off and reboot)

```powershell
# In an *elevated* PowerShell (Administrator):
choco install nssm                  # if you don't have it
.\scripts\install_service.ps1       # configure + (optionally) start the CSIS service

# Verify:
sc.exe query CSIS
Get-Content .\brain\daemon.heartbeat

# Stop and uninstall:
.\scripts\uninstall_service.ps1
```

The install script accepts the same daemon flags:

```powershell
.\scripts\install_service.ps1 -Backend mock -RatePerHour 30 -SnapshotEvery 50
.\scripts\install_service.ps1 -Backend anthropic -RatePerHour 6 -Domain self_improve
```

Service logs land in `brain/service_logs/CSIS.out.log` and `CSIS.err.log`
with 5MB rotation.

## Limits of this prototype

- Mock Dreams only (real Dreams API is described in `brain/research/01-anthropic-sdk.md`; integration is a follow-up).
- No real sandbox; Builder is a mock. Real Phase-0 needs `csis/substrate/sandbox.py` calling out to subprocess + microVM.
- I4–I7 improvement layers are out of scope per the Phase-0 contract.
- V3 (debate), V4 (replication), V5 (calibration) are Phase 1+.
- Constitution patterns are deliberately small; production needs a classifier-backed predicate.
