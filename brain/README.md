# BRAIN — Auto-Save Catalog for CSIS Build

This folder is the durable working memory across context windows. Every meaningful state of the build is snapshotted here so that the next conversation (or the next iteration of THIS conversation past compaction) can pick up cold.

## Folder layout

| Folder | Purpose |
|---|---|
| `snapshots/` | Whole-context snapshots at major milestones. Each is a self-contained markdown file titled `NN-name.md`. |
| `cycles/` | One folder per iteration cycle (cycle-01, cycle-02, ...) containing plan, implementation diff, test results, critique. |
| `research/` | Outputs of research sub-agents (Anthropic SDK capabilities, multi-agent patterns, safety literature). |
| `plans/` | Implementation plans from planning sub-agents, one per angle. |
| `critiques/` | Adversarial critique reports from red-team sub-agents. |
| `BRAIN.html` | Top-level index (built at the end of each cycle) — opens in a browser to navigate everything. |

## Read order if you're picking this up cold

1. `snapshots/00-initial.md` — what the project is and where we started
2. The highest-numbered file in `snapshots/` — current state of the build
3. The highest-numbered folder in `cycles/` — what was happening most recently
4. `../csis/` — the actual code being built
5. `../tests/` — proof that it runs

## Auto-save policy

A snapshot is written at every cycle boundary, AND opportunistically when context budget approaches a cliff. Files use markdown so they remain readable from any model in any future session.
