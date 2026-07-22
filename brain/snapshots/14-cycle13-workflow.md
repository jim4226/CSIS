# Snapshot 14 — Cycle 13 (Workflow-driven red-team), shipped

Self-contained state after cycle 13. Picks up from snapshot 13 (cycles 10–12).

## Headline

Cycle 12 declared the loop **converged** (0 critical/high). Cycle 13 ran the
methodology through the **Workflow orchestration primitive** — parallel finders
per subsystem, each finding adversarially verified by three diverse-lens
skeptics (reproduce / scope / coverage) — and reached surface the convergence
claim had never tested: the six **agent-role modules** and the **deep
verification statistics**, none directly attacked in any prior cycle. It found
**15 defects, three high**. Convergence was scoped to the adversary that had
actually run; a new orchestration on new surface found new defects.

## Counts

- Tests: **414 passing** (was 389); 25 new cycle-13 regression tests, 22 of
  which fail on the pre-fix source.
- Findings to date: **147** total, **144 closed in code**, **3 deferred**
  (E8, H2, J2 — Phase-1).
- `python -m csis.loop` promotes end-to-end.

## The three HIGH findings

- **agents-K1** — the self-improve **diff-scope grader**, the load-bearing
  control that stops the loop certifying an artifact which rewrites its own
  `coordinator.py`/safety files, was a raw substring test over the diff body.
  It was bypassable by a path-normalization spelling (`csis/agents//coordinator.py`,
  `csis/./agents/...`, `csis/x/../agents/...`) that `git apply` still writes to
  the real file. Now extracts + normalizes the diff's target paths
  (`posixpath.normpath`), unioned with the legacy substring check.
- **crosscut-K1** — Unicode whitespace separators (U+2028/U+2029/U+1680, which
  NFKC does not fold to a space) survived `_strip_invisible` and were then
  *deleted* by the ASCII fold, gluing `disable<U+2028>the<U+2028>auditor` →
  `disabletheauditor` and defeating every multi-word pattern in both the
  Constitution and the Tripwires. `_strip_invisible` now maps all category-Z /
  `isspace` chars to a real space.
- **verification-K1** — the bootstrap CI (and the signed PASS/FAIL) depended on
  sample **row order**, not just the value multiset. Now sorts the sample (the
  mean is exchangeable, so the true distribution is order-invariant).

## The rest, by subsystem

- **Memory**: promote/mark_verified returned live `_live`/`_candidate` handles
  (M4 boundary never applied to the RETURNS) — now `_view()`d; a `_flush`
  OSError left an applied-but-reported-failed ghost — now rolls back.
- **Event log**: `verify_chain` reported an honest-crash longer-than-anchor
  chain as BROKEN — now intact; readers took no lock and raised on a torn line
  — now locked + tolerant; emit re-parsed the whole file O(n) — now a bounded
  tail read with full-walk fallback.
- **Verification**: a min-n floor on the main estimate (a single sample no
  longer passes with a zero-width CI); the distributional verdict now **gates
  and is recorded on the cert** (it was silently ignored); a `model_declared`
  flag ends the false-reject of a legit checkpoint==model pair.
- **Coordinator/config**: an *overwritten* pre-existing cross-tier candidate is
  now discarded on rollback (pre-consolidate CONTENT hashes, not id-sets); the
  post-promote check gates on the real halt signal, not sticky tripwire
  history; `config.phase_ceiling` is now enforced as the effective ceiling
  (can only tighten).
- **Dreams**: the contradiction detector now catches internal negations
  (whitespace-collapse after the negation substitution).

## Lesson

**"Converged" is scoped to the adversary you actually ran.** A determin­istic
Workflow reaching the agent-role modules and the distributional statistics —
surface cycles 10–12 never directly attacked — found 15 defects behind a
"converged" label. The audit is only as wide as its widest pass; the budget
subsystem (heavily attacked in cycles 3/5/8/9/11/12) came back clean, and the
new surface did not.
