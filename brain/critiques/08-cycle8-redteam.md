# CSIS Phase-0 Cycle-8 Red Team — synthesis

**Target.** The cycle-8 fixes G1-G6, especially the two architectural pivots
(G1 wrap-site exact-type check; G2 pre-consolidate snapshot for tier-mismatch
cleanup). Three parallel red-team passes were dispatched, one per subset.
This synthesis dedupes their findings.

**Per-cycle letter for cycle 9 = H.** 12 findings after dedupe: **4 critical,
3 high, 2 medium, 3 low**. All reproducible live with `file:line` evidence.

Source critique reports:
- `08-cycle8-redteam-G1G3.md` — G1 + G3 attacks (5 findings)
- `08-cycle8-redteam-G2.md` — G2 attacks (3 findings)
- `08-cycle8-redteam-G4G5G6.md` — G4 + G5 + G6 + cross-cutting attacks (5 findings)

The G1 multi-entry-point finding was duplicated across two reports (agent-1 H1 = agent-3 H4). Merged below as **H1**. Numbering renormalized so cycle-9 findings are H1-H12 contiguous.

---

## Summary by finding

| # | Sev | Title | Source |
|---|---|---|---|
| H1 | critical | G1 wrap-site check is only at Daemon; Coordinator accepts raw backend (burst.py runs unmetered Anthropic) | G1G3-H1 / G4G5G6-H4 |
| H2 | critical | G1 closure-cell mutation defeats `type(...) is _BackendTracker` (verified live with 100 unmetered calls) | G1G3-H2 |
| H3 | critical | G1 post-init `setattr(d.backend, evil)` swaps wrapper after type check ran | G1G3-H3 |
| H4 | critical | G2 sibling write between pre-consolidate snapshot and librarian return is over-discarded (F2 regression returns in new guise) | G2-H1 |
| H5 | high | G3 20s lock ceiling raises **after** real LLM call completed → spend lost; daemon keeps spending against phantom $0 | G1G3-H4 |
| H6 | high | G2 concurrent `run_iteration` on a shared `MemoryHierarchy` is fundamentally unsafe and undocumented; `max_threads` config suggests it is OK | G2-H2 |
| H7 | high | G5 test is a source-grep; docstring-comment containing literal `salt=item.salt` PASSES while live call drops salt | G4G5G6-H5 |
| H8 | medium | G5 `Coordinator.run_continuous` + `csis/loop.py` still drop salt; forensic-replay loss on those paths | G4G5G6-H6 |
| H9 | medium | G6 `_last_false_positive_signature` never resets on `fuzz_ok` snapshot; FP=A → ok → FP=A emits one event (expected two) | G4G5G6-H7 |
| H10 | low | G2 `pre_consolidate_ids` is 5× separate locked captures, not hierarchy-atomic | G2-H3 |
| H11 | low | G3 POSIX unlink-during-lock race (flagged, not reproducible on Windows; needs Linux verification) | G1G3-H5 |
| H12 | low | `ALL_TIERS` hardcoded in 4 places; latent foot-gun when adding a 6th tier | G4G5G6-H8 |

---

## What this cycle says about the loop

Three cycle-9 findings (H1, H2, H3) are **independent classes of bypass against the same cycle-8 architectural pivot** (the wrap-site check). The cycle-7 critique said "constrain the wrap site" and cycle-8 added one type check at `Daemon.__init__` — but:
- H1: the trust boundary is actually `Coordinator`, not `Daemon`. Three production scripts (`burst.py`, `demo_pr_scenario.py`, `csis/loop.py`) instantiate `Coordinator` directly with a raw backend.
- H2: closure cells are mutable from Python (`fn.__closure__[i].cell_contents = ...`). The exact-type check is a *nominal* check; runtime behavior is determined by closure contents the check cannot see.
- H3: `Daemon.backend` is a plain attribute. The type check runs once in `__init__`; `setattr(d.backend, evil)` afterward succeeds.

This is the **same metabug pattern** as cycles 4-7 vs. cycle 8 G1: each cycle's fix is narrowly scoped to the prior reproducer, leaving close-relative escapes open. The right fix isn't to chase H1/H2/H3 one at a time — it's to **audit every construction site, every mutation site, and every layer of trust** for the wrapped-backend invariant in one pass.

H4 is the same story for G2: the pre-consolidate snapshot defends against pre-snapshot collisions only; a sibling write into the same id between snapshot and cleanup is treated as "this iteration introduced it" and over-discarded. Same harm as cycle-7 F2, in a wider race window. The structural fix recommended by G2-agent is **writer-id tagging on each candidate**: tag at `write_candidate` time with the iteration that wrote it, and the cleanup filters by tag rather than by snapshot diff. Race-free under any concurrency model.

Cycle-9 will close the **wrapped-backend invariant** (H1+H2+H3) and the **TierMismatch over-discard class** (H4+H10) with two architectural moves rather than three to twelve guards. H5/H8/H9 are independent tactical fixes; H7 is a test-quality fix; H12 is a maintenance trap; H2/H6/H11 require threat-model documentation.

---

## Fix strategy

### Group A — wrapped-backend invariant (H1, H2, H3) · architectural

1. **Move the wrap-site check into `Coordinator.__init__`** (`csis/agents/coordinator.py:69-78`). Coordinator is the actual chokepoint — every LLM call routes through `self.backend`. The Daemon's check becomes belt-and-suspenders.
2. **Block post-init `setattr` on backend** via a property with a setter that raises (`Coordinator.backend` and `Daemon.backend` both).
3. **Document closure-cell mutation as a known threat-model limit.** It cannot be prevented in pure Python without abandoning the closure-capture pattern; the slot+freeze pattern proposed by the agent is fragile (subclasses, `object.__setattr__`). The honest stance is: an attacker with code-execution rights inside the daemon process can defeat any in-process guard. The wrapped-backend invariant is for *honest code paths that forget to wrap*, not for adversarial in-process attackers.
4. **Update `scripts/burst.py`, `scripts/demo_pr_scenario.py`, `csis/loop.py`** to construct a `BudgetTracker` and wrap the backend explicitly before passing to `Coordinator`.

### Group B — TierMismatch over-discard (H4, H10) · architectural

Replace the pre-consolidate-snapshot model with **writer-iteration-id tagging**:

1. Add `writer_iteration_id: str | None` field to `MemoryEntry` (`csis/contracts.py`).
2. `MemoryStore.write_candidate(entry, *, writer_iteration_id: str | None = None)` stamps the field on the stored entry.
3. `consolidate_to_candidates` accepts `iteration_id` and threads it through.
4. `_tier_mismatch_cleanup` walks all five tiers and discards only entries whose `writer_iteration_id == self.iteration_id`. The pre-consolidate snapshot becomes obsolete.

Race-free, snapshot-free; survives concurrent iterations. H10's atomicity concern dissolves (no snapshot to make atomic).

### Group C — tactical fixes (H5, H7, H8, H9, H12)

- **H5**: `_file_lock` gains an `unbounded=True` parameter; daemon's record path uses it. Stop-file check inside the wait loop. Or — simpler — `record()` retries indefinitely with backoff.
- **H7**: Replace `test_G5_burst_passes_salt`'s source-grep with a behavior test that drives `burst.main()` and asserts the iter.start event payload has `salt=<int>`.
- **H8**: Change `Coordinator.run_continuous` to accept `list[FrontierItem | str]` and pass salt; update `csis/loop.py` to pass `salt=None` explicitly.
- **H9**: Reset `_last_false_positive_signature` in the `fuzz_ok` branch.
- **H12**: Replace `ALL_TIERS = ("working", ...)` constants with `tuple(MemoryHierarchy.model_fields.keys())`. Audit other hardcoded sites (`csis/curiosity.py:121`).

### Group D — document threat-model limits (H2, H6, H11)

- **H2**: Docstring on `_BackendTracker` makes the closure-cell threat explicit. Phase-0 acceptance: any in-process attacker with code-execution rights can defeat any in-process guard.
- **H6**: Docstring on `Coordinator.run_iteration` says: NOT safe to call concurrently against a shared `MemoryHierarchy` in Phase 0. Add an `_owner_lock` assertion.
- **H11**: Document POSIX unlink-during-lock as a known issue; add to "verify on Linux" TODO list. Defer fix to Phase 1 with explicit `xfail` test marker.
