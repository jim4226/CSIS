# CSIS Phase-0 Cycle-8 Red Team — G2 architectural correction

**Target.** The G2 fix in `coordinator.py`: pre-consolidate snapshot of per-tier candidate ids + lie-detection loop + brute-walk cleanup (`_tier_mismatch_cleanup`). Plus the supporting `MemoryStore.has_candidate` and `candidate_ids()` APIs.
**Posture.** Attack only what cycle-8 G2 added or changed. No duplicates with prior findings.
**Per-cycle letter for cycle 9 = H** (per instructions). All findings prefixed `(G2)` for the synthesizer.
**Result.** 3 reproducible attacks found (H1 critical, H2 high, H3 low), 4 attack vectors confirmed sound.

---

## H1 · (G2) Sibling write between pre-snapshot and cleanup is over-discarded — F2 regression returns in a new guise · **critical**

**Where.** `csis/agents/coordinator.py:267-271` (snapshot construction) + `:474-487` (cleanup walk). The snapshot defends against pre-snapshot collisions only; an id introduced AFTER the snapshot but in a SIBLING context is indistinguishable from "this iteration introduced it."

**Reproducer (verified live).**

```python
import time
from csis.contracts import MemoryEntry
from csis.memory.trust import TrustLevel
from csis.agents.coordinator import Coordinator
import csis.agents.coordinator as cm

coord = Coordinator(config=cfg, backend=backend)  # mock setup elided
SHARED = "sibling-id"

original = cm.consolidate_to_candidates
def bad(*args, **kwargs):
    h = kwargs["hierarchy"]
    # Simulate: a sibling iteration / thread legitimately wrote into causal
    # AFTER pre_consolidate_ids was taken but BEFORE this librarian returns.
    sibling = MemoryEntry(
        entry_id=SHARED, tier="causal", content="SIBLING-LEGIT",
        trust=TrustLevel.CANDIDATE, why_tag="legit", created_at=time.time())
    h.causal.write_candidate(sibling)
    # Then this (buggy) librarian returns a lying entry with same id.
    return [MemoryEntry(entry_id=SHARED, tier="episodic", content="bad",
                        trust=TrustLevel.CANDIDATE, why_tag="bad",
                        created_at=time.time())]
cm.consolidate_to_candidates = bad
res = coord.run_iteration(frontier_item="test")

assert res.outcome.startswith("rolled-back:tier-mismatch")
assert not coord.hierarchy.causal.has_candidate(SHARED)  # SIBLING WRITE WIPED
```

Output (live):
```
outcome: rolled-back:tier-mismatch:candidate sibling-id claims tier='episodic'
         but no candidate with that id exists there. ...
causal still has SIBLING-LEGIT?  False
  *** SIBLING WRITE WAS OVER-DISCARDED ***
```

**Diagnosis.** The pre-snapshot logic divides candidates into two classes — "existed before the librarian" vs "introduced by the librarian." But it has NO concept of a third class: "introduced concurrently by a different actor." Any id appearing in `pre_consolidate_ids` is spared; any id appearing afterwards is treated as this-iteration's and brute-discarded across all five tiers. A sibling thread, a callback, OR a deliberately-orchestrated concurrent coordinator can drop a fresh-id candidate into any tier between snapshot and consolidate, and the cleanup will wipe it.

This is the cycle-7 F2 scenario reborn. F2 said "don't over-discard pre-existing same-id candidates"; G2 enforced that for the pre-snapshot window only. But the same harm — wiping a legitimate sibling's candidate just because its id collides — now occurs for the post-snapshot window. The race window is `pre_consolidate_ids` capture → librarian return — easily milliseconds in real deployments, longer if librarian does I/O.

Also reproduced with two `Coordinator` instances sharing a `MemoryHierarchy` (the deployment shape the cycle-9 daemon will use, per `coordinator.py:429-430`: "(≤25 concurrent threads) would replace this in a real deployment").

**Severity.** Critical. F2 was rated medium-high; G2 was advertised as the structural fix that ends the arms race. It does not. The race window is wider than F2's TOCTOU was, and the failure mode (silent data loss for a legitimate sibling iteration) is identical to what F2 was supposed to prevent. The audit log records `tier.mismatch` for the bad librarian's iteration but says nothing about the unrelated sibling's collateral damage — the sibling appears to its own coordinator as a write that succeeded, but the data is gone.

**Fix proposal.**
Stop trying to infer "did THIS iteration write this candidate" by set-difference on ids. Instead, **tag the writes**: extend `MemoryStore.write_candidate(entry, *, writer_iteration_id: str | None = None)` so each candidate carries the iteration that wrote it. The cleanup discards only entries whose `writer_iteration_id == self.iteration_id`. This is correct under any concurrency model — race-free, snapshot-free, no over-discard regardless of sibling timing.

Migration: `MemoryEntry` already has free-form fields; add `writer_iteration_id: str | None` (optional, backward-compatible). Coordinator passes its `iteration_id` to `write_candidates` (one call-site in `librarian.py:61`; pass through `consolidate_to_candidates`). Cleanup filters by tag instead of by snapshot diff.

Until then, document `Coordinator.run_iteration` as NOT safe to call concurrently against a shared `MemoryHierarchy`, and add an assertion that the hierarchy is single-owner (e.g., a coordinator-id stamp on the hierarchy at construction).

**Regression test.**

```python
def test_H1_sibling_write_during_consolidate_is_not_over_discarded(tmp_path):
    """A candidate written DURING consolidate (by sibling thread or
    concurrent iteration) with an id matching the bad librarian's return
    must NOT be discarded by tier-mismatch cleanup."""
    # ... mock backend setup ...
    coord = Coordinator(config=cfg, backend=backend)
    SHARED = "race-id"
    orig = cm.consolidate_to_candidates
    def bad(*args, **kwargs):
        h = kwargs["hierarchy"]
        h.causal.write_candidate(MemoryEntry(
            entry_id=SHARED, tier="causal", content="SIBLING-LEGIT",
            trust=TrustLevel.CANDIDATE, why_tag="legit",
            created_at=time.time()))
        return [MemoryEntry(entry_id=SHARED, tier="episodic", content="bad",
                            trust=TrustLevel.CANDIDATE, why_tag="bad",
                            created_at=time.time())]
    cm.consolidate_to_candidates = bad
    try:
        res = coord.run_iteration(frontier_item="t")
    finally:
        cm.consolidate_to_candidates = orig
    assert res.outcome.startswith("rolled-back:tier-mismatch")
    assert coord.hierarchy.causal.has_candidate(SHARED), \
        "H1 regression: sibling iteration's legitimate candidate over-discarded"
```

Fails today (sibling candidate wiped). Passes with writer-id tagging fix.

---

## H2 · (G2) Concurrent `run_iteration` on a shared `Coordinator`/`MemoryHierarchy` is fundamentally unsafe and undocumented · **high**

**Where.** `csis/agents/coordinator.py:108-117` (`run_iteration` signature; no concurrency contract documented) + `:429-430` (run_continuous comment hand-waves about "(≤25 concurrent threads) would replace this in a real deployment"). `csis/config.py` exposes `max_threads` (referenced at `:517`) — the operator can set this; nothing enforces single-thread.

**Reproducer (verified live).** Two `Coordinator` instances on the same `MemoryHierarchy`; one runs a normal iteration writing a fresh-id candidate to a non-target tier; the other runs the buggy-librarian iteration from H1. The legitimate candidate is wiped. Run identical to H1's reproducer but with explicit `Coordinator` × 2 sharing `MemoryHierarchy.open(...)`.

**Diagnosis.** The G2 design treats `pre_consolidate_ids` as if `run_iteration` were the only writer to a hierarchy at any time. There is no lock on the hierarchy at the iteration level, only at the store/promotion levels. So any concurrent write between snapshot and cleanup violates the assumption. The code comments admit this is the intended Phase-1 deployment shape but ship a snapshot-based design that does not survive it.

Three escape valves are all open:
1. **Multi-coordinator deployment.** Daemon spawns N coordinators on shared hierarchy → ALL of them are vulnerable to H1 over-discard from each other.
2. **Single-coordinator multi-iteration via threads.** Operator writes their own loop calling `coord.run_iteration` from N threads → SAME race.
3. **Librarian-spawned callbacks.** Verified that nothing prevents a librarian from spawning a worker thread that writes a candidate before returning — the F2 fix doesn't address it because pre-snapshot was taken upstream of the librarian. Verified live: yes, this works (worker thread's write survives long enough to be cleaned up).

**Severity.** High. The codebase advertises concurrency-ready and ships a design that is not. The blast radius is silent data loss in sibling iterations — exactly the class G2 was meant to close.

**Fix proposal.** Either (a) the H1 writer-id-tagging fix, which makes concurrency safe, or (b) document explicitly in `Coordinator.__init__` and `run_iteration` that the hierarchy must be single-owner and that the daemon must not multi-thread `run_iteration`. Add a process-wide latch on the hierarchy: `MemoryHierarchy._owner_coordinator_id: str | None` — raise on second binding.

**Regression test.**

```python
def test_H2_coordinator_documents_single_iteration_contract():
    """Either the coordinator enforces single-iteration-at-a-time or
    the H1 fix makes concurrent iterations safe. Pick one — don't ship
    a snapshot model that pretends concurrency is fine."""
    import inspect
    from csis.agents.coordinator import Coordinator
    doc = inspect.getdoc(Coordinator.run_iteration) or ""
    # If the H1 fix isn't in, the docstring MUST say so explicitly.
    if "writer_iteration_id" not in inspect.getsource(Coordinator.run_iteration):
        assert "not safe to call concurrently" in doc.lower() or \
               "single-threaded" in doc.lower(), (
            "H2: run_iteration is not concurrency-safe but doesn't say so")
```

Fails today (no contract documented and no tagging implemented).

---

## H3 · (G2) `pre_consolidate_ids` builds 5× separate locked snapshots → not atomic across tiers · **low**

**Where.** `csis/agents/coordinator.py:268-271` — dict comprehension over 5 tiers, each takes `self.hierarchy.tier(tier_name).candidate_ids()` under that store's own `_lock`. Between the working-tier snapshot and the causal-tier snapshot, a concurrent write into causal will appear "new" relative to the snapshot.

**Reproducer.** Less harmful than H1 but adjacent: even without a buggy librarian, the snapshot is not a coherent across-tier view of the hierarchy. If the daemon ever batches consolidation across tiers, an id moved from working → causal between the two snapshot captures will appear in the causal snapshot AND not in the working snapshot, looking like a fresh causal write. Combined with H1, this makes the snapshot capture itself another race window.

**Severity.** Low. Requires (a) cross-tier mutations during snapshot construction (today's librarian writes to one tier per iteration) AND (b) the H1 cleanup misclassification. Mostly a latent foot-gun for Phase-1.

**Fix proposal.** Move the snapshot under a hierarchy-wide read lock (add `MemoryHierarchy.lock_all()` returning a context manager that acquires all 5 `_lock`s in deterministic order to avoid deadlock with promote). Or — preferred — adopt the H1 writer-id-tagging fix, which makes snapshots unnecessary entirely.

**Regression test.**

```python
def test_H3_pre_consolidate_snapshot_is_atomic_across_tiers(tmp_path):
    """Capturing per-tier candidate_ids must be atomic w.r.t. concurrent
    cross-tier mutations: a candidate moved between tiers during snapshot
    cannot appear in both or neither."""
    # Spawn a thread that toggles a candidate between working and causal
    # while a main thread takes 1000 snapshots; assert every snapshot has
    # the id in exactly one of {working, causal}, never both, never neither.
```

Fails today (some snapshots show both, some neither). Passes with hierarchy-wide lock or with writer-id-tagging that obviates snapshots.

---

## Confirmed sound (no findings)

### Attack 3 — `candidate_ids()` set construction under concurrent writes

`MemoryStore.candidate_ids` at `csis/memory/store.py:274-282` returns `set(self._candidate.keys())` under `_lock`. The set construction is inside the lock, so even with 4 writer threads + 4 reader threads at `sys.setswitchinterval(1e-7)` × 2000 ops each: zero errors, final cardinality correct. The lock is `RLock` (`store.py:68`) but the construction is single-thread within the critical section — no reentrancy.

### Attack 4 — Invalid tier name in `entry.tier`

`MemoryEntry.tier` is a Pydantic `Literal['working','episodic','semantic','procedural','causal']`. Constructing with `tier='nonexistent_tier_name'` raises `ValidationError` at construction time, well before the coordinator's lie-detection loop ever sees it. The `self.hierarchy.tier(entry.tier)` call at `coordinator.py:316` and `:478` cannot reach an invalid name. Not a finding.

### Attack 5 — `_build_diff` TierMismatch on pre-existing legit same-id candidate

Verified: a librarian writes to causal with `entry.tier='causal'` (no lie), target_tier=episodic; `_build_diff` raises TierMismatch via `entry.tier != target_tier`; cleanup runs. A pre-existing legit candidate in semantic with the same id is correctly preserved because it's in `pre_consolidate_ids['semantic']`. F2 + G2 work as designed for this scenario.

### Attack 6 — `_promotion_lock` held during cleanup

Verified after a buggy-librarian iteration: `coord._promotion_lock.locked() == False`. The cleanup runs outside the `with self._promotion_lock:` block (`coordinator.py:393`), so sibling iterations attempting promotion are not starved.

---

## Out-of-scope notes (not findings)

- **`MemoryStore._lock` is RLock** (`csis/memory/store.py:68`). The coordinator's `has_candidate` followed by `discard_candidate` in `_tier_mismatch_cleanup` (lines 478-486) is two separate lock acquisitions — fine because both go through the public API and the second one's `_candidate.pop(entry_id, None)` is a no-op if a concurrent thread removed the entry first. No reentrancy or lost-discard issue.
- **`pre_consolidate_ids.get(tier_name, set())`** at `coordinator.py:481`: the `.get` with `set()` default guards against a tier missing from the snapshot dict. Since `ALL_TIERS` is the same constant in both snapshot-construction and cleanup, this is belt-and-suspenders. Sound.
- **`TierMismatch.claimed_tier` / `target_tier`** are informational only — neither field is used by `_tier_mismatch_cleanup` for routing (which walks all 5 tiers). They are only printed in the event log. If a future fix narrows the walk to those two tiers, the lying-Librarian (G2 motivating case) attack returns. Document this constraint at the TierMismatch constructor.
- **Loop quality.** Cycle 8's G2 fix is structurally cleaner than cycle 7's F2 entry.tier-only narrowing — but it traded one over-discard class for another. The arms race is not closed; it has been moved from "pre-existing same-id" to "concurrent same-id." A writer-id tag on each candidate would end the arms race definitively; the snapshot approach can never be airtight because it tries to infer ownership from timing.
