# Snapshot 13 — Cycle 10 + the cycle-11 re-attack, shipped

Self-contained state of the build after the cycle-10 red-team and the cycle-11
re-attack of its fixes. Picks up from snapshot 12 (the cross-process
chain-integrity fix).

## Headline

- **Cycle 10** ran the repo's methodology against the whole post-cycle-9 system,
  with five parallel red-team passes (one per subsystem). **23 findings — 9
  critical, 5 high, 5 medium, 4 low** — all closed in code with effect-asserting
  regression tests. The two subsystems shipped after cycle 9 *without* a cycle —
  the distributional graders and the cross-process event log — held the most
  criticals (a non-deterministic verifier verdict, a spoofable cross-checkpoint
  cert, a brick-on-legacy chain fix). Cycle-9's deferred **H11 was closed** as S1.
- **Cycle 11** re-attacked the cycle-10 fixes and found **6 close-relative
  escapes** — several a cycle-10 fix opening a hole against its sibling. All
  closed. Suite **250 → 383**.

## Test + finding counts

- Tests: **383 passing** (was 250 at the start of cycle 10).
- Findings to date: **128** total, **126 closed in code**, **2 deferred** (E8
  Pydantic frozen-dict; H2 in-process closure-cell mutation — the documented
  pure-Python ceiling).
- The loop runs end-to-end on the mock backend (`python -m csis.loop` → promoted).

## What shipped, by subsystem

**Memory / promotion (M1, M2, M4, C1, C2 + cycle-11 F1, F2).** `mark_verified`
now honors the lattice (no DEPRECATED resurrection); `promote` is validate-then-
commit atomic with a candidate post-image CAS (`content_hash` excludes the
lattice-bookkeeping fields) and archives after the flush; reads hand back deep
copies; the TierMismatch cleanup identifies this-iteration writes by the
forge-proof pre-consolidate snapshot, not a Librarian-controlled stamp; daemon
skill promotion routes through the Auditor + locked-promote chokepoint
(`Coordinator.promote_skill`).

**Substrate / event log (S1–S5 + cycle-11 Finding-2).** Post-`flock` inode-
identity recheck (closes H11); head-anchor sidecar detects tail truncation/
rollback; fsync + torn-tail recovery; a non-chaining tail (forged or pre-S5
legacy) is **quarantined and the longest valid prefix recovered** rather than
bricking — and recovery never shrinks the anchor below a previously-attested
length, so it can't launder a rollback; canonical sorted-key chain hash.

**Verification (Vf1–Vf7 + cycle-11 F3).** The cross-checkpoint cert binds to a
*different declared model* (normalized comparison; the real `AnthropicBackend`
differs only by `model_id`, so requiring a second axis would reject production);
every distributional `evaluate()` is a deterministic function of (data, seed)
with fresh per-call/per-slice RNGs; non-finite samples/metrics are rejected;
slice resample counts are recorded; degenerate masks are surfaced; critic
attempts are counted distinct.

**Safety (SF1–SF5 + cycle-11 Finding-1, Finding-3).** The shared canonicalizer
folds the full Unicode alphabet (format/combining/dash strip + homoglyph fold),
closing the zero-width/homoglyph evasion of both the constitution and tripwires;
both budget cap gates include WAL spend AND the WAL drain is applied on top of
the freshly-loaded state (no lost spend); the tier guard fails closed on unknown
names; the fuzzer enforces `expected_layer` and carries the Unicode rows; the
`escalate_to_t2` tripwire fires on the capability noun phrase with a
documentation-intent exemption.

## Where the trail lives

- Cycle-10 synthesis + the cycle-11 re-attack table: `brain/critiques/09-cycle10-redteam.md`.
- Regression tests: `tests/test_cycle10_{promote_integrity,substrate,verification,safety}.py`
  and `tests/test_cycle11_reattack.py`.
- Audit log + totals: `CYCLES.md`.

## Read order if picking this up cold

1. `brain/snapshots/00-initial.md` — what the project is.
2. This file — current state.
3. `brain/critiques/09-cycle10-redteam.md` — the most recent red-team + re-attack.
4. `../csis/` (the code) and `../tests/` (the proof it runs).

## Honest limits (unchanged)

The two mottos held up and so did the failure mode: every cycle-10 fix that
broke under the cycle-11 re-attack did so the same way — it asserted its effect
on the clean/empty path, and a close relative walked through the adversarial or
non-empty one. The remaining H2 deferral is explicit: an in-process attacker
with code-execution rights defeats any in-process guard; the answer is
process-level isolation (Phase 1), not another in-process check.
