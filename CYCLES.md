# Nine cycles of red-team → fix → regression-test

A self-improving system that doesn't audit itself is a vibes-driven research demo. This document is the audit log.

Each cycle: parallel red-team agents attack the previous cycle's fixes; findings get triaged into `brain/critiques/NN-cycleN-redteam.md` with reproducible attacks + `file:line` evidence; fixes land in code with regression tests; results snapshotted in `brain/snapshots/`. Cycles 4-9 each found that the previous cycle's pivot was at the right concept but the wrong abstraction layer, and the next cycle moved it.

## The numbers

| Cycle | Findings | Critical | High | Medium | Low | Open | Deferred | Tests after |
|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| 1 pre-impl | 18 | 2 | 6 | 7 | 3 | 0 | 0 | 52 |
| 2 post-impl | 13 | 2 | 6 | 3 | 2 | 0 | 0 | 78 |
| 3 deltas | 11 | 2 | 4 | 4 | 1 | 0 | 0 | 114 |
| 4 fixes | 11 | 2 | 4 | 4 | 1 | 0 | 0 | 141 |
| 5 fixes | 11 | 3 | 3 | 4 | 1 | 0 | 0 | 165 |
| 6 fixes | 10 | 3 | 3 | 3 | 1 | 0 | 1 | 186 |
| 7 fixes | 7 | 1 | 2 | 3 | 1 | 0 | 0 | 195 |
| 8 fixes | 6 | 2 | 2 | 2 | 0 | 0 | 0 | 202 |
| 9 fixes | 12 | 4 | 3 | 2 | 3 | 0 | 2 | **213** |
| **Total** | **99** | **21** | **33** | **32** | **13** | **0** | **3** | — |

**99 findings, 96 closed in code, 3 deferred** (E8 Pydantic frozen-dict; H2 closure-cell mutation; H11 POSIX unlink-during-lock — all with explicit Phase-1 plans). Test count grew **92 → 213 (+121)** across the nine cycles.

## What changed cycle by cycle

| Cycle | The thing the loop learned |
|---:|---|
| **1** | The pre-implementation red team. Found 18 architecture-level issues *before* code existed — F2 (TOCTOU between auditor sign and promote), F1 (mock-vs-mock self-confirmation). Set the test bar at 52. |
| **2** | The post-implementation red team. 13 new findings against the *implementation* — P1 (fake-PROMOTED ghosts after failed promote), P2 (stale-hash semantics), P5 (patterns defeated by hyphen substitution). All critical/high closed; tests 52→78. |
| **3** | The deltas cycle. The cycle-2 fixes themselves became attack surface — C1 (canon regression: one canonical form not enough; needed strip+space dual form), C2 (budget tracker single-process lock insufficient when run in parallel). Tests 78→114. |
| **4** | C-class fixes landed. The TOCTOU window in `_build_diff` got closed with a frozen `live_snapshot`. Tests 114→141. |
| **5** | D1 (dual-form-canonicalization false positives), D2 (shallow snapshot allowed mutation through), D3 (sibling reservation race in budget). Tests 141→165. |
| **6** | E1 was an embarrassing one — bare `except:` swallowed a `NameError` in the cycle-5 D4 fix, silently leaking VERIFIED candidates after every TierMismatch for the entire cycle. Lesson written in stone: **regression tests must assert remediation *effect*, not just surface events.** Tests 165→186; E8 Pydantic frozen-dict deferred. |
| **7** | Another embarrassing one — F1 caught a `_wrapped` mangling escape the cycle-6 E4 docstring had *explicitly acknowledged* and shipped anyway. Lesson written in stone (again): **docstrings saying "known limit" must be followed by `# TODO(cycleN): fix`.** Tests 186→195. |
| **8** | **Architectural pivot #1.** G1 was the third generation of the same `_wrapped` exposure attack (cycle-4 C4 → cycle-6 E4 → cycle-7 F1 → cycle-8 G1). Each prior cycle added another guard to `_BackendTracker.__init_subclass__`; each got bypassed by the next escape (literal name → mangled name → post-hoc setattr → metaclass). Cycle 8 stopped fighting subclass attacks and added a wrap-site `type(self.backend) is _BackendTracker` check at `Daemon.__init__`. Tests 195→202. |
| **9** | **Architectural pivot #2** — and a humbling rerun of pivot #1. Twelve findings, four critical. H1 found cycle 8's wrap-site check was at the *wrong layer* — `Coordinator` (not `Daemon`) is the actual chokepoint, and three production scripts bypassed Daemon entirely. H3 found the check ran *once* in `__init__`; `setattr(d.backend, evil)` afterward swapped the wrapper silently. H4 found cycle-8 G2's pre-consolidate snapshot was racy — a sibling iteration writing a same-id candidate between snapshot and cleanup got over-discarded. Fixes: chokepoint relocation (H1), property setters that re-validate (H3), `writer_iteration_id` stamp on every candidate at write time (H4). H2 + H11 honestly deferred — in-process pure-Python guards have a ceiling. Tests 202→**213**. |

## Two patterns that kept reappearing

**Pattern 1: identity beats timing.**
Cycle 7 narrowed TierMismatch cleanup from "walk all five tiers" to "walk `entry.tier`" — but the buggy-Librarian threat model is exactly "wrote to one tier AND lied about it in entry.tier." Cycle 8 added a pre-consolidate snapshot to identify "what this iteration introduced" by id-set difference. Cycle 9 found that approach has its own race window: a sibling iteration writing a same-id candidate between snapshot and cleanup is indistinguishable from "introduced by this iteration." The fix that ended the arms race wasn't a wider snapshot — it was a `writer_iteration_id` field on the candidate itself, stamped atomically at `write_candidate` time. **Ownership belongs on the data, not in the timing.**

**Pattern 2: chokepoints beat perimeters.**
Cycle 4 captured the wrapped backend in a closure. Cycle 6 found subclasses could re-introduce `_wrapped` and bypass it; added `__init_subclass__` guard. Cycle 7 found Python's `__wrapped` name-mangling escape; widened the guard. Cycle 8 dropped the subclass guard entirely and added `type(self.backend) is _BackendTracker` at the *Daemon* wrap site. Cycle 9 found three production scripts bypass the Daemon entirely — they construct `Coordinator` directly with a raw backend. The fix moved the check into `Coordinator.__init__` (the *real* chokepoint every LLM call passes through) and added property setters that re-validate on assignment. **Constrain the finite chokepoint; don't try to perimeter-fence an infinite surface.**

## Two honest deferrals from cycle 9

**H2: closure-cell mutation.** `fn.__closure__[i].cell_contents = EvilBackend()` swaps the wrapped backend while `type(self.backend) is _BackendTracker` still passes. Reproduced live with 100 unmetered real-backend calls in the cycle-9 critique. The Phase-0 stance: in pure Python, any in-process attacker with code-execution rights defeats any in-process guard. Slot+freeze patterns can be bypassed via `object.__setattr__`; the closure pattern via `cell_contents=`. The wrapped-backend invariant is for *honest code paths that forget to wrap* (cycle 9 found three, all now wrap explicitly). For adversarial in-process attackers, the answer is process-level isolation (separate sandbox, OS capability tokens, separate identity), not in-process guards. Tracked for Phase 1.

**H11: POSIX unlink-during-lock race.** The cycle-9 red team flagged a POSIX-only race where deleting the lock file mid-lock could let a second opener acquire a parallel lock. Not reproducible on Windows (the OS blocks the unlink). Deferred to Phase 1 Linux verification with an `xfail`-shaped test marker.

## How to read the trail

Each cycle's critique lives at `brain/critiques/NN-cycleN-redteam.md` with reproducible attacks. Each cycle's commit and shipped state lives at `brain/snapshots/NN-cycleN-shipped.md`. The cycle-9 critique is split into three sub-reports (G1G3, G2, G4G5G6) plus a synthesis `08-cycle8-redteam.md`.

Top-of-funnel for a cold reader: open `brain/BRAIN.html` in a browser. It is the catalog and has clickable links to every cycle, plan, critique, snapshot, and live source file.

## What "9 cycles of self-critique" doesn't claim

- This is not a proof of safety. The 213 tests + 99 findings closed are *evidence* of careful engineering, not *certification* of safe behavior under adversarial conditions. The cycle 9 H2/H11 deferrals are explicit about this.
- The LLM backend is mock by default. Real Anthropic calls are gated behind `--backend anthropic` + an `ANTHROPIC_API_KEY` + cost ceilings + WAL-backed budget metering. No agent is currently improving itself at production scale on this codebase.
- "Self-improving" in Phase 0 means *the infrastructure for self-improvement is working and tested*. Real learning happens via `scripts/burst.py` on demand against the real Anthropic backend. The longer-arc framing is in [CSIS-architecture.html Appendix A](CSIS-architecture.html#appA).

## Pointer back

← [README.md](README.md) for the project overview.
