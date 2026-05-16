# Snapshot 10 — Cycle 8 shipped (6 findings closed + architectural pivot)

**Date:** 2026-05-16
**Trigger:** Cycle-8 red team produced 6 findings (2 critical, 2 high, 2 medium). All addressed; 202/202 tests pass (4 POSIX-only skipped on Windows).

## Cycle 8 in one paragraph

The cycle-8 critical (G1) called out the loop's most embarrassing pattern: G1 was the **third generation** of the same `_wrapped` exposure attack (cycle-4 C4 → cycle-6 E4 → cycle-7 F1 → cycle-8 G1). Each cycle had patched the previous guard's escape (literal name → mangled name → post-hoc setattr/metaclass), without changing the underlying design. The critique recommended an **architectural pivot**: stop trying to make `_BackendTracker` subclass-proof, and instead constrain the *wrap site* — the single point in `Daemon.__init__` where a wrapper-typed value enters the trusted runtime. Cycle 8 implemented that pivot. Subclassing `_BackendTracker` is now allowed; `type(self.backend) is _BackendTracker` (exact equality, not isinstance) at the daemon's construction defeats every subclass-shaped bypass — including the post-hoc `__init__` swap, the metaclass attack, AND every prior mangling escape — in one structurally-different check. G2 was a parallel architectural correction: the cycle-7 F2 cleanup trusted `entry.tier`, but the whole point of TierMismatch is "Librarian wrote to the wrong tier AND lied about where." G2 added pre-consolidate per-tier candidate-ID snapshots so the cleanup can brute-walk all five tiers safely (it only discards IDs introduced *this iteration*, preserving pre-existing legitimate same-id candidates from prior iterations). G3 closed a Windows-only `os.replace` race between a capped and an uncapped `BudgetTracker` sharing one file — the cycle-7 F3 conditional-lock optimization was correct in isolation but introduced this cross-tracker mode; G3's `_maybe_locked` now always tries the lock first and only falls through when the OS literally lacks fcntl/msvcrt support. G4 added a single `threading.Lock` around `Tripwires.scan_text`'s check-pop-append sequence so the `deque(maxlen)`/`OrderedDict` pair can no longer desync under thread races (reproduced live with `setswitchinterval(1e-9)` and 16 threads). G5 wired `salt=item.salt` through `scripts/burst.py` and `scripts/demo_pr_scenario.py` so the cycle-7 F4 forensic-replay parameter is actually populated by every caller. G6 added a `sha256(fp.text)[:16]` suffix to the fuzz-event dedupe signature so two FP sets that share a label name but differ in text no longer collapse into one event.

## Cycle 8 finding → fix → test

| # | Sev | Finding | Fix | Test |
|---|---|---|---|---|
| G1 | critical | 3rd-gen `_wrapped` bypass via post-hoc `__init__` swap | architectural pivot: drop subclass guard; wrap-site `type(...) is _BackendTracker` check in `Daemon.__init__` | `test_G1_daemon_rejects_subclass_backend` |
| G2 | high | F2 cleanup trusted `entry.tier` but Librarian lies about it | pre-consolidate snapshot + lie-detection + brute-walk-all-tiers cleanup that only discards iteration-local IDs | `test_G2_tier_mismatch_walks_both_claimed_and_actual` |
| G3 | critical | Win `PermissionError` from cap+nocap trackers sharing one file | `_maybe_locked` always tries lock first, falls through only when OS lacks fcntl/msvcrt | `test_G3_cap_and_nocap_trackers_coexist_on_same_file` |
| G4 | high | `_fired_history` deque / `_history_keys` set desync under race | `_history_lock` around scan_text's check-pop-append | `test_G4_concurrent_scan_text_does_not_desync` |
| G5 | medium | `scripts/burst.py` + `demo_pr_scenario.py` dropped `item.salt` | both now pass `salt=item.salt` (burst) and `salt=None` (demo, explicit) | `test_G5_burst_passes_salt` + `test_G5_demo_pr_scenario_explicitly_passes_salt` |
| G6 | medium | fuzz-event signature collapsed same-label different-text FP sets | signature includes `sha256(text)[:16]` | `test_G6_fuzz_dedupe_differentiates_same_label_different_text` |

## What the architectural pivot proves

Three cycles in a row failed to close the `_wrapped` exposure class by adding more guards to `_BackendTracker`. Cycle 8 closed it by changing **which layer** the constraint lives at. The lesson is structural: when an attack surface keeps generating new escapes faster than guards can be added, the design choice — not the guard text — is wrong. The wrap site has a **finite** entry point (one line in `Daemon.__init__`); the subclass surface has infinite escapes (anything Python's MRO + descriptor + metaclass machinery can express). Constrain the finite one.

The same lesson re-applies to G2: the F2 cleanup added more clauses to a tier-walk over `entry.tier`. The fix wasn't more clauses — it was changing what the cleanup *knows* (pre-consolidate snapshot → "what this iteration introduced") so the brute-walk is safe.

## Cumulative loop state

| Cycle | Findings | Crit | High | Med | Low | Open | Deferred | Tests |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| 1 pre-impl | 18 | 2 | 6 | 7 | 3 | 0 | 0 | 52 |
| 2 post-impl | 13 | 2 | 6 | 3 | 2 | 0 | 0 | 78 |
| 3 deltas | 11 | 2 | 4 | 4 | 1 | 0 | 0 | 114 |
| 4 fixes | 11 | 2 | 4 | 4 | 1 | 0 | 0 | 141 |
| 5 fixes | 11 | 3 | 3 | 4 | 1 | 0 | 0 | 165 |
| 6 fixes | 10 | 3 | 3 | 3 | 1 | 0 | 1 | 186 |
| 7 fixes | 7 | 1 | 2 | 3 | 1 | 0 | 0 | 195 |
| 8 fixes | 6 | 2 | 2 | 2 | 0 | 0 | 0 | **202** |
| **Total** | **87** | **17** | **30** | **30** | **10** | **0** | **1** | — |

## State of the repo

- **csis/** ~4,500 LOC. All cycle-8 changes confined to `csis/agents/coordinator.py`, `csis/agents/auditor.py`, `csis/budget.py`, `csis/daemon.py`, `csis/memory/store.py`, `csis/safety/tripwires.py`, `scripts/burst.py`, `scripts/demo_pr_scenario.py`.
- **tests/** 202 passing + 4 POSIX-only skipped on Windows + 0 failing.
- **brain/** snapshots 00-10 + 7 critiques + BRAIN.html.
- **GitHub** https://github.com/jim4226/CSIS — cycle 8 commit pending push.

## Where the loop is now

After 8 cycles:
- **87 findings**, **86 closed**, **1 deferred** (E8 Pydantic frozen-dict adapter; Phase 1).
- **Tests grew 92 → 202** (+110).
- **Cycle 8 was structurally different** from cycles 4-7 — two of the six findings were closed by changing the design rather than adding a guard. The 3rd-gen `_wrapped` attack is now closed at a layer that's not architecturally extendible by an attacker. The TierMismatch cleanup is now closed at a layer (pre-consolidate snapshot) that the attacker cannot poison.
- The cycle-8 critique itself recommended pausing: "G1 is the third generation of the same attack class; until the design shifts, cycle N+1 will keep finding cycle N's guard insufficient." Cycle 8 shifted the design.

## Recommendation: pause to reassess

Decision point: continue the critique-fix-push loop into cycle 9, or pause and pivot to a different mode of work (long-haul daemon run, real-backend burst, README polish, forensics-replay tool). The cycle-7 snapshot already flagged diminishing returns; cycle 8's architectural pivot is a natural moment to take stock. The loop has demonstrably improved the codebase (cumulative tests 92 → 202, no open findings, two architectural-level closes in one cycle), but cycles 4-7 found increasingly narrow bug classes within already-patched code paths. Cycle 9 would attack cycle-8 fixes; the marginal value of that vs. exercising the system end-to-end has shifted.
