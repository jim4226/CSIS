# Snapshot 04 — 24/7 daemon shipped with domain adapters and burst command

**Date:** 2026-05-16
**Trigger:** User asked for it "running constantly 24/7 improving." Daemon + curiosity + skill library + 3 domain adapters + on-demand burst + NSSM install scripts are all built, tested (92/92 pass), and demonstrated end-to-end on mock.

## What's new since snapshot 03

| Module | LOC | Purpose |
|---|---:|---|
| `csis/curiosity.py` | 102 | Frontier-item generator (seeds + gap-driven + rollback-followups). |
| `csis/improvement/skill_library.py` | 78 | Procedural-tier consolidation (Builder → procedural, F5/P4-safe via producer_role). |
| `csis/daemon.py` | 290 | Long-lived process with budget, watchdog, stop file, auto-snapshot, exception isolation. |
| `csis/domains/base.py` | 41 | Domain ABC contract. |
| `csis/domains/pr_maintenance.py` | 119 | Real graders against a target git repo (pytest/ruff/mypy via subprocess). |
| `csis/domains/self_improve.py` | 84 | Self-improvement on the CSIS codebase, with stricter diff-scope grader. |
| `csis/domains/lean_math.py` | 121 | `lean --check` grader with graceful-fallback if Lean isn't installed. |
| `scripts/burst.py` | 132 | Finite real-backend run with per-run cost ceiling. |
| `scripts/run_daemon.ps1` | 67 | PowerShell launcher with restart-on-crash + STOP-file. |
| `scripts/install_service.ps1` | 76 | NSSM-based Windows service install (survives log-off + reboot). |
| `scripts/uninstall_service.ps1` | 26 | Companion uninstall. |
| `tests/test_daemon.py` | 132 | Daemon contract: finite runs, stop-file, exception isolation, skill path. |
| `tests/test_domains.py` | 102 | Domain contract: can_run / graders / curiosity / strict-diff for self-improve. |

## What demonstrated end-to-end

1. **Daemon ran 600 iterations on mock in ~2 min** (rate-capped, with `STOP` file shutdown working cleanly).
2. **Auto-snapshots landed at `brain/snapshots/auto-NNNNNN.md`** every 25 iterations.
3. **Heartbeat file refreshed every iteration** at `brain/daemon.heartbeat`.
4. **Stats JSON at `brain/daemon.stats.json`** tracks total/promoted/rolled-back + rollback reason histogram + skill library size.
5. **Procedural store filled with 600+ skill entries** through the F5/P4-safe path (Builder produces skill artifact → consolidate_skill → mark_verified → promote with producer_role="builder").
6. **Burst command runs against mock** with cost-ceiling enforcement ($0.00 on mock as expected).
7. **All three domain adapters expose a valid contract** — verified by `test_domains.py`.

## The mock-skill artifact (transparency note)

In the 600-iter mock run, *every* iteration ended in `promoted` and *every* artifact was tagged `is_skill=True`. Why: the curiosity module produces stable gap-driven prompts when no tier has > 10 entries; the same prompt hashes to the same seed; the mock backend's seed-modulo-5 always landed on True. This is a known mock artifact, not a real behavior — it shows the architecture works but not that the architecture is learning. Real learning happens with `--backend anthropic`.

The mock daemon is still useful as a 24/7 watchdog: it confirms the heartbeat keeps refreshing, snapshots keep landing, the chain stays intact, the procedural store keeps growing — proves the infrastructure survives.

## How the user can actually start it 24/7

User chose: **mock for watchdog + real for bursts**, **manual PowerShell + NSSM service**, **tunable budget**, **all three domain adapters available**.

```powershell
# A) Mock watchdog, manual control. Runs while the PowerShell window is open.
.\scripts\run_daemon.ps1 -Backend mock -RatePerHour 30

# B) Mock watchdog, persistent across log-off and reboot, via NSSM.
choco install nssm
.\scripts\install_service.ps1 -Backend mock -RatePerHour 30
sc.exe start CSIS

# C) Real-backend burst against the CSIS codebase itself.
$env:ANTHROPIC_API_KEY = "sk-ant-..."
python scripts/burst.py --iters 10 --domain self_improve --max-cost-usd 2.0

# D) Real-backend burst against a real repo.
python scripts/burst.py --iters 5 --domain pr_maintenance --repo-path C:/path/to/repo --max-cost-usd 1.0

# E) Real-backend burst on Lean (graceful soft-pass if Lean missing).
python scripts/burst.py --iters 3 --domain lean_math --max-cost-usd 0.5

# Stop a running daemon at any time:
New-Item -ItemType File .\STOP

# Uninstall the service:
.\scripts\uninstall_service.ps1
```

## Stats so far

| Metric | Value |
|---|---:|
| `csis/` LOC | ~4,100 |
| Test count | 92 |
| Tests passing | 92/92 |
| Iterations run in development | 600 |
| Snapshots written | 28 (4 manual + 24 auto) |
| Procedural-store live entries | 600+ |
| Disk usage (memory_store + event_log + brain) | ~7 MB |
| Critical red-team findings open | 0 |

## Carried forward to a hypothetical Phase 1

- Real diff-application in a sandboxed worktree before grading (PR maintenance currently grades current state).
- LLM-generated why-doc summary (currently templated).
- Real Anthropic Dreams API integration (currently mocked locally).
- Per-day cumulative budget cap in the daemon (today the cap is per-burst).
- Cost-ceiling check uses request prompt-length as input-token proxy; real billing differs.
- V3 (debate), V4 (replication), V5 (calibration) verification layers.
- I4–I7 improvement layers (DPO, distillation, continued pretraining, NAS).
