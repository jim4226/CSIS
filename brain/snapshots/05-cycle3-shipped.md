# Snapshot 05 — Cycle 3 shipped; repo live on GitHub

**Date:** 2026-05-16
**Trigger:** Initial repo push + four cycle-3 deltas all on `main` at https://github.com/jim4226/CSIS.

## What's on GitHub now

| Commit | Subject | Tests | Phase |
|---|---|---:|---|
| 2db801a | Initial commit: CSIS Phase-0 prototype + 24/7 daemon | 92 | — |
| 6fb8d60 | cycle 3 phase A: synthesis quick wins | 96 | A |
| d66f7c9 | cycle 3 phase B: per-day cumulative budget cap | 106 | B |
| cf9a2f6 | cycle 3 phase C: structured diff in WhyDoc | 109 | C |
| ae01c37 | cycle 3 phase D: continuous safety-pattern fuzzer | 114 | D |

Tests jumped from 92 to 114 (+22 new regression tests, one per synthesis finding addressed).

## Cycle 3 changelog

| Synthesis # | Finding | Resolution | Test |
|---|---|---|---|
| #4 | `_ALLOWED_ACTORS` was a hardcoded frozenset inside EventLog; gap if a new Role is added | Lifted to `csis/agents/base.py:ALLOWED_EMIT_ACTORS`; EventLog imports lazily | `test_allowed_emit_actors_contains_every_role` |
| #6 | Mock daemon's 100% promotion / 100% skill artifact came from stable gap-driven prompts | Added a `salt` from `self._rng.randrange(0, 10_000)` to gap-driven prompts so seeds vary | `test_gap_driven_prompts_vary_under_stable_state` |
| #7 | NSSM install script hangs on interactive y/n prompt | Added `-StartNow` switch for unattended installs | (manual — no scripted PS1 test) |
| #3 | No per-day cumulative budget cap (only per-burst) | New `csis/budget.py` with `BudgetTracker` + `_BackendTracker` wrapper; `--max-cost-per-day-usd` daemon flag; persistent to `brain/daemon.budget.json` | 10 tests in `tests/test_budget.py` including `test_daemon_halts_on_budget_cap` |
| #2 | WhyDoc carried only prose + precondition hash, no structured diff | `EntryDelta` + `WhyDocDiff` types; auditor's `_build_diff` populates from candidates vs live | 3 tests in `tests/test_whydoc_diff.py` |
| #4 | Patterns rot over time; no continuous regression coverage of paraphrases | `SafetyFuzzer` + `DEFAULT_CORPUS` (20 rows); daemon runs at every snapshot boundary; halts on failure | 5 tests in `tests/test_safety_fuzzer.py` |
| (bonus) | `canonicalize` converted hyphens to spaces, leaving "dis-able the auditor" as "dis able..." which didn't match patterns | Strip separators entirely instead; "dis-able" → "disable" → matched | `test_default_corpus_passes_cleanly`, `test_P5_canonicalize_strips_separators` |

## Cycle 4 dispatched

A cycle-4 red team is currently attacking the cycle-3 deltas in background — looking at budget tracker race conditions, canonicalize regressions (especially "self-improve" → "selfimprove" false-positive risk), WhyDocDiff truthfulness under contention, fuzzer DoS surface, `_BackendTracker.__getattr__` delegation gaps, salt-determinism across restarts, and the lazy-import risk in EventLog. Output will land at `brain/critiques/03-cycle3-redteam.md`.

After it returns: address findings, push again. The pattern is now self-sustaining.

## Stats after cycle 3

| Metric | Value |
|---|---:|
| GitHub repo | https://github.com/jim4226/CSIS |
| Commits on main | 5 |
| Files tracked | 92 |
| `csis/` LOC | ~3,500 |
| Test count | 114 |
| Tests passing | 114/114 |
| Critical findings open | 0 |
| High findings open | 0 |
| Synthesis recommendations resolved | 7 of 8 (only #8 forensics-replay still pending) |

## Open / deferred to a Phase 4 (cycle 5+)

- Cycle-4 findings (still in flight)
- Forensics replay tool (synthesis #8 — lower priority)
- LLM-generated why-doc summaries
- Real Anthropic Dreams API integration
- Sandbox subprocess execution for Builder T1 work
- V3 debate / V4 replication / V5 calibration
- I4–I7 improvement layers
- Canonicalize patterns themselves (P11 test note — eliminate the
  separator-stripping word-boundary edge case)
