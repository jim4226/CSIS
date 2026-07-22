# CSIS Phase-0 Cycle-10 Red Team — synthesis

**Target.** The post-cycle-9 system as shipped: the cycle-9 fixes (H1 chokepoint
relocation, H3 property setters, H4 writer-id tagging) plus the two additions
that were shipped as *feature/bug work and never went through a red-team cycle* —
the distributional grader stack and the cross-process event-log chain-integrity
fix. Five parallel red-team passes were dispatched, one per subsystem of the
loop. This synthesis dedupes their findings.

**23 findings after dedupe: 9 critical, 5 high, 5 medium, 4 low.** Every finding
was reproduced live with `file:line` evidence; all are now closed in code with a
regression test that asserts the *effect* (cycle-6 E1 discipline). Test count
**250 → 352**.

Source critique reports (one parallel pass per subsystem):
- Substrate & concurrency — `event_log.py`, `file_lock.py`, `hashing.py`, `capability.py` (S1–S5)
- Memory & trust lattice — `store.py`, `trust.py`, `contracts.py` (M1–M5)
- Safety & capability boundary — `safety/*`, `budget.py` (SF1–SF5)
- Verification — `verification/*`, distributional graders (Vf1–Vf7)
- Coordinator & loop — `coordinator.py`, role agents, `daemon.py` (C1–C3)

Two findings were duplicates across passes and are merged below: **C3 = SF1**
(the unicode/zero-width canonicalizer evasion, found independently by the safety
and coordinator passes) and **C1 = M3** (the candidate post-image CAS, flagged as
a live exploit by the coordinator pass and as a "documented-but-live" deferral by
the memory pass).

---

## Summary by finding

| # | Sev | Title | Where |
|---|---|---|---|
| M1 | **critical** | `mark_verified()` resurrects a terminal-DEPRECATED candidate to VERIFIED→PROMOTED (a second trust-mutating door that skipped `valid_promotion`) | `memory/store.py` |
| M2 | **critical** | `promote()` non-atomic: a mid-batch raise leaves a ghost PROMOTED entry in live + memory/disk divergence (cycle-2 P1 class) | `memory/store.py` |
| C1 | **critical** | `promote()` re-checks only the *live* hash, never the Auditor-signed *candidate* post-image — content tampered in the sign→promote window promotes with a valid why-doc (unclosed half of cycle-2 F2) | `memory/store.py`, `agents/coordinator.py`, `agents/auditor.py` |
| S1 | **critical** | Lock-file unlink/recreate swaps the flock inode → two processes enter the critical section (the deferred H11, reproduced on Linux) | `substrate/file_lock.py` |
| Vf1 | **critical** | Cross-checkpoint cert spoofable: `model_id` defaults to `checkpoint_id`, so a label rename clears the distinctness bar while one backend grades its own work (cycle-1 F1 re-opened) | `verification/certificates.py` |
| Vf2 | **critical** | Distributional verdict non-deterministic: a shared, never-reset RNG flips PASS/FAIL across identical runs and changes the cert hash | `verification/distributional_graders.py` |
| Vf3 | **critical** | A NaN per-sample metric is laundered into `passed=True` via an undefined NaN-sort in the bootstrap | `verification/distributional_graders.py` |
| SF1 | **critical** | Unicode/zero-width/soft-hyphen/homoglyph evasion of the shared canonicalizer defeats BOTH the constitution and tripwires (`disable<ZWSP>the auditor` promotes) | `safety/tripwires.py` |
| SF2 | **critical** | Budget cap gates ignore un-drained WAL spend → daemon spends past the cap (cycle-9 H5 on the enforcement side) | `budget.py` |
| M5 | high | TierMismatch cleanup trusts the Librarian's self-reported manifest → an unstamped, unadvertised cross-tier write survives rollback | `agents/coordinator.py` |
| S2 | high | Chain not tamper-evident against tail truncation/rollback (a dropped tail still `verify_chain()==True`) | `substrate/event_log.py` |
| S3 | high | A torn last line (crash mid-emit) wedges the entire log; no fsync | `substrate/event_log.py` |
| Vf4 | high | `inf`/`nan` metric breaks the cert JSON round-trip the Auditor relies on (dump→null, load→reject) | `verification/distributional_graders.py`, `contracts.py` |
| C2 | high | Daemon skill-promotion injects into the capability-changing `procedural` tier with NO Auditor why-doc, outside the promotion lock, with a mis-attributed why_id | `daemon.py`, `agents/coordinator.py` |
| M4 | medium | Every per-entry read returns a live mutable reference → mutation outside `promote()` (cycle-5 D2 re-introduced; cycle-9 H4 added a 4th leaking reader) | `memory/store.py` |
| S4 | medium | `emit()` re-sync extends an unverified/forged tail; a broken chain never halts the daemon | `substrate/event_log.py` |
| Vf5 | medium | Slice CIs computed at `min(n_bootstrap,200)` while the cert reports the main `n_bootstrap` | `verification/distributional_graders.py` |
| Vf6 | medium | Both-empty masks auto-score 1.0 → an all-empty-truth eval set passes any prediction | `verification/distributional_graders.py` |
| SF3 | medium | `TierGuard.write_tier` fails OPEN on any non-exact tier name (`.get(name, T0)`) | `safety/tier_guard.py` |
| S5 | low | `compute_hash` claims canonical sorted-key JSON but uses insertion order → chain hash is payload-key-order dependent | `substrate/event_log.py` |
| Vf7 | low | Critic `min_attempts` satisfiable with duplicate/trivial attempts (cardinality, not distinct work) | `verification/certificates.py` |
| SF4 | low | Safety fuzzer rot-gate is structurally blind to SF1: `expected_layer` is dead metadata and the corpus has zero Unicode rows | `safety/fuzzer.py` |
| SF5 | low | `escalate_to_t2` verb-allowlist misses common request verbs (provide/want/acquire/obtain/escalate) | `safety/tripwires.py` |

---

## What this cycle says about the loop

Cycle 10 confirmed the loop's own thesis from the outside: **a subsystem that
doesn't go through a red-team cycle doesn't get the cycle's adversary.** The two
most alarming clusters — Vf1–Vf7 (the distributional graders) and S1–S5 (the
cross-process event log) — were both shipped as feature/bug work after the nine
cycles, and both harbored a critical regression of a property the system claims
load-bearing. The distributional verdict was not a deterministic function of its
inputs (Vf2/Vf3/Vf4); the cross-checkpoint cert that is the *core* F1 defense was
spoofable by a label rename in the default config (Vf1); and the just-fixed chain
integrity (snapshot-12) trusted three things the filesystem never promised —
inode identity (S1), append-only-ness/durability (S2/S3), and tail honesty (S4).

The same meta-bug the loop keeps re-learning recurred one ring out at every
chokepoint the prior cycles had so carefully centralized:

- **Memory:** cycle 9 made `promote()` race-safe, so the escapes moved to the
  *other* trust-mutating door (`mark_verified`, M1), to `promote`'s own
  non-transactional loop (M2), to the per-entry *read* boundary (M4), and to the
  candidate *post-image* that `promote` never re-checked (C1). The chokepoint for
  memory was never `promote()`; it is *every method that writes a trust level* and
  *every method that hands out an entry*.
- **Safety:** the cycle-2→3→5 hyphen arms race was fought entirely in ASCII;
  SF1 is the identical evasion class escaping into the *alphabet* the
  canonicalizer normalizes over (zero-width, Unicode dashes, homoglyphs). And SF2
  is cycle-9 H5 exactly: the WAL was plumbed so the cost *read* paths see in-flight
  spend, a docstring promised the cap check sees it too, and the two methods that
  actually *enforce* the cap were never wired to it.
- **Promotion:** cycle-9 H1 said "audit every site of the invariant." C2 found a
  *second* `promote()` call site (the daemon's skill path) that no cycle had
  audited — and it is the one promotion that actually changes Builder capability.

The fix discipline that closes all 23 is the one the loop already wrote in stone:
**enforce the invariant at the single chokepoint, and assert the remediation
*effect* — on the degenerate and adversarial inputs — not a surface event.**

---

## Fix strategy (by invariant, not by reproducer)

**Memory trust + read boundary (M1, M2, M4, C1).** Route the question "is this
trust transition legal?" through `valid_promotion` at *every* mutating method
(`mark_verified` now gates exactly as `promote` does — M1). Make `promote`
validate the whole batch before any mutation (M2). Hand back deep copies from
*every* read path via one `_view()` chokepoint (M4). Add a true post-image CAS:
the Auditor signs a `content_hash()` that excludes the lattice-bookkeeping fields
(so the legitimate `mark_verified` bump is not a false mismatch) and `promote`
re-checks it under the promotion lock (C1).

**Tier-mismatch identity (M5).** The cleanup identifies this-iteration writes
*structurally* (unstamped AND absent from the pre-consolidate snapshot), never by
the Librarian's self-reported manifest — "ownership belongs on the data," applied
to the cleanup itself.

**Promotion chokepoint (C2).** The daemon's skill promotion routes through a new
`Coordinator.promote_skill()` that uses the same Auditor + locked-promote path as
every other tier, so the capability-changing tier gets its own signed why-doc.

**Event-log chain integrity (S1–S5).** Fix each at the two chokepoints
(`file_lock`, `EventLog`): an inode-identity recheck after flock (S1); a
head-anchor sidecar so truncation/rollback is detected (S2); fsync + torn-tail
recovery (S3); a chain-validated re-sync that *quarantines and recovers the
longest valid prefix* on a forged/legacy tail instead of extending it — robust
across the S5 hash-format migration rather than bricking every existing log (S4);
and a canonical sorted-key chain hash (S5).

**Cross-checkpoint + distributional verdict (Vf1–Vf7).** Bind the cert to a
*different declared model* (Vf1); make every `evaluate()` a deterministic function
of (data, seed) with fresh per-call/per-slice RNGs (Vf2); reject non-finite
samples and require finite CI bounds (Vf3); reject non-finite metrics at cert
construction (Vf4); record the actual slice resample count (Vf5); surface
degenerate cases (Vf6); count distinct critic attempts (Vf7).

**Safety canon + cap (SF1–SF5).** Fold the canonicalizer over the full Unicode
alphabet — format/combining/dash strip + homoglyph fold (SF1); include WAL spend
in both cap gates (SF2); fail the tier guard *closed* on unknown names (SF3);
make the fuzzer enforce `expected_layer` and carry the SF1 rows (SF4); gate
`escalate_to_t2` on a broadened acquisition-verb set that still lets benign
documentation pass (SF5).

---

## Re-attack (cycle 11)

Per the loop's discipline, two focused re-attack passes were dispatched against
the cycle-10 fixes themselves. They found **6 close-relative escapes** — and,
true to form, several were a cycle-10 fix opening a hole against its *sibling*
cycle-10 fix. All passed the 352-test suite, because the cycle-10 regression
tests exercised only the empty-state / clean-recovery cases. All six are now
closed with regression tests on the non-trivial cases (`tests/test_cycle11_reattack.py`;
19 of 31 fail on the cycle-10 source, all pass after). Suite **352 → 383**.

| # | Sev | Title | Fix |
|---|---|---|---|
| Finding-1 | **critical** | SF2 WAL drain silently discarded — `_drain` then `_load` overwrote it, losing the spend and reopening the H5 cap bypass on any non-empty budget file (the cycle-10 test used a fresh $0 tracker, so the drain "survived" by luck) | load before drain |
| Finding-2 | high | S4 quarantine-recovery realigned the S2 head-anchor *down*, laundering a tail-rollback that S2 was built to catch — the S4 fix defeating the S2 fix | recovery never shrinks the anchor below a previously-attested length |
| F1 | high | M5 cleanup only caught `writer_iteration_id is None`; a *forged non-null* stamp on a hidden cross-tier write evaded rollback (the stamp is a field the untrusted Librarian controls) | identify this-iteration writes by the forge-proof pre-consolidate snapshot, not the self-reported stamp |
| F2 | medium | M2's commit pass still did the per-entry archive *disk write* inside the mutation loop, so an `OSError` mid-commit left a P1 ghost | archive after the in-memory transition + flush; atomic temp+replace flush |
| Finding-3 | medium | SF5's acquisition-verb gate still missed authorize/permit/requesting/seeking/require/"t2 execution please"/>2-word gaps (the cycle-6 E2 enumerate-the-verb trap) | invert the gate — fire on the t2-capability noun phrase, exempt a small stable documentation-verb set |
| F3 | low | Vf1's model_id "different model" check was a raw `==`; case/whitespace/zero-width deltas made the same model read as two | normalize (NFKC + strip-format + casefold) before comparing |

The cycle-10 fixes that **held up** under attack: C1's post-image CAS (content-hash
field selection is correct), the SF1 canonicalizer (fullwidth, mathematical
alphanumerics, BOM/word-joiner/bidi, ligatures all folded), and the S5 canonical
hash (no nondeterminism found). The throughline of the six that didn't: **a fix
must assert its effect on the adversarial and degenerate inputs, and on a
non-empty starting state — not just the clean path.** Cycle 11's tests do.
