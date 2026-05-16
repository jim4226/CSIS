# CSIS Phase-0 Cycle-7 Red Team

**Target:** the single cycle-7 commit landing F1-F7 against the cycle-6 critique.
**Posture:** attack only what cycle-7 added or changed. No duplicates with F1-F18, P1-P12, C1-C11, D1-D11, E1-E10, or cycle-6's F1-F7. Real `file:line` only. The loop is at diminishing returns — six findings, each verified live.

---

## G1 · F1 guard runs at class-definition only; `type(...)` + post-hoc `__init__` swap leaks the real backend · **critical**

**Where.** `csis/budget.py:438-455` — `__init_subclass__` inspects `cls.__dict__` once at class-body completion.

**Attack.** Reproduced live in this session:

```python
from csis.budget import _BackendTracker, BudgetTracker
from csis.backends.mock import MockBackend

cls = type("Sneaky", (_BackendTracker,), {})    # guard fires on empty dict — passes
real = MockBackend()

def sneaky_init(self, wrapped, tracker):
    super(cls, self).__init__(wrapped, tracker)
    self._wrapped = wrapped       # also store the real backend

cls.__init__ = sneaky_init        # POST-HOC; no guard runs
inst = cls(real, BudgetTracker(path=...))
assert inst._wrapped is real      # → True. Bypass metering via inst._wrapped.complete(req).
```

The cycle-6 critique correctly diagnosed `__wrapped` name-mangling; F1 patched THAT path. But the guard fires exactly once. Any class-object mutation after that — `cls.__init__ = ...`, `cls._wrapped = ...`, `setattr(cls, ...)` — is invisible. The bound-closure design from cycle-4 C4 was the correct defense; F1 added a guard with no enforcement window beyond `class` body.

**Fix.** Drop the guard. Mark the class `@typing.final` and have `Daemon.__init__` (`csis/daemon.py:130`) assert `type(self.backend) is _BackendTracker`, not `isinstance(...)`. The closure capture is already secure; the guard gives a false sense of one.

**Test.** `test_G1_post_hoc_init_swap_rejected_at_wrap_site` — perform the pattern above; pass instance to `Daemon`; assert refusal. Passes today (no refusal).

---

## G2 · F2 cleanup walks `entry.tier` but the bad Librarian is exactly the actor that *lies about entry.tier* · **high**

**Where.** `csis/agents/coordinator.py:318-323`. Handler iterates `candidates` and discards from `self.hierarchy.tier(entry.tier)`.

**Attack.** Reproduced live:

```python
# Buggy Librarian writes to causal store but stamps entry.tier='episodic':
h.tier('causal').write_candidate(MemoryEntry(entry_id='e1', tier='episodic', ...))

# F2 cleanup:
tier_store = h.tier(entry.tier)        # → episodic store (empty)
if tier_store.has_candidate('e1'):     # False — episodic has nothing
    tier_store.discard_candidate(...)  # never called

h.tier('causal').has_candidate('e1')   # → True. Misplaced candidate stuck forever.
```

The cycle-6 critique objected that walk-all-tiers nuked legitimate same-id candidates. F2 narrowed to `entry.tier` — but the *whole point* of TierMismatch is "Librarian routed to a tier the entry contract said it shouldn't go to." The entry's self-declared tier is exactly the field the buggy Librarian got wrong. Cleanup now misses the actual misplaced write.

**Fix.** TierMismatch should carry `actual_tier` (the store written to) plus `claimed_tier` (entry.tier). Handler walks `{actual_tier, claimed_tier, target_tier}` — three at most, not five (cycle-6's complaint), but not just the one the lying entry self-declares.

**Test.** `test_G2_cleanup_finds_misplaced_candidate_in_actual_tier` — preseed causal with `entry.tier=='episodic'`; raise TierMismatch; assert causal candidate discarded. Fails today.

---

## G3 · F3 cross-tracker corruption: cap and no-cap trackers on same file race → `PermissionError` mid-record · **critical (Windows) / high (POSIX)**

**Where.** `csis/budget.py:301-312` (`_maybe_locked` skips when no cap). Same `BudgetTracker.path` opened by two trackers with mismatched cap settings.

**Attack.** Reproduced live on Windows:

```python
a = BudgetTracker(path=p, max_cost_per_day_usd=5.0)   # cap → locks
b = BudgetTracker(path=p)                              # no cap → skips lock
# 100 concurrent record() from each thread:
# Thread-1 (a.record) crashes:
#   PermissionError: [WinError 5] Access is denied:
#     'budget.<rand>.json.tmp' -> 'budget.json'
# Expected 200 calls; actual 100. 100 lost.
```

Windows `os.replace` requires an exclusive handle; the no-cap tracker's write blocks the cap tracker's rename. On POSIX the rename succeeds but the unlocked write interleaves between locked `_load`→mutate→`_save`, silently dropping updates.

Cycle-6 F3 was correct for "no-cap tracker in isolation" but introduced this cross-tracker mode. An operator running the daemon with cap and `scripts/burst.py` (no cap by default) on the same `brain/daemon.budget.json` produces exactly this.

**Fix.** `_maybe_locked` should take the lock when the FILE has ever been opened by a cap-bearing tracker — record a header marker on first cap-bearing write, check on subsequent opens. Or simpler: always lock when fcntl/msvcrt is available; only fall through for environments where they're literally absent.

**Test.** `test_G3_mixed_cap_and_no_cap_trackers_on_same_file` — start one tracker with cap and one without on the same path; record concurrently; assert no `PermissionError` and `calls == 200`. Crashes today.

---

## G4 · F5 deque/OrderedDict desync under thread race; ghost keys permanently suppress recordable firings · **high**

**Where.** `csis/safety/tripwires.py:176-194` — `scan_text` does check-pop-append without a lock.

**Attack.** Reproduced live with `sys.setswitchinterval(1e-9)`, 16 threads, `history_max=50`:

```
Trial  2: deque=50  keys=49  desync=-1
Trial  6: deque=50  keys=49  desync=-1
Trial 12: deque=50  keys=49  desync=-1
Trial 13: deque=50  keys=49  desync=-1
```

Two threads both observe `len(_fired_history) >= max` is False (deque at maxlen-1), both skip the `popitem(last=False)`, both append. The deque silently drops oldest at maxlen+1; the OrderedDict key for that dropped snippet was never popped. Result: an orphan key in `_history_keys` for a snippet no longer in history. Subsequent scans of THAT snippet hit `if key in self._history_keys: continue` — permanently deduped without ever appearing in history. A recurring real attack signature ends up in the orphan set after deque rollover and silently stops being recorded.

F5's docstring claims "eventually consistent" — true for evict-then-resurface, but NOT for this desync class where keys never align because the corresponding deque slot was never visible to popitem.

**Fix.** Wrap `scan_text` in a single `threading.Lock`. The check-pop-append becomes one critical section. Cost: one uncontended lock per scan; tripwires fire rarely.

**Test.** `test_G4_history_keys_in_sync_with_deque_under_race` — 8 threads × 2000 scans, `history_max=50`, `setswitchinterval(1e-9)`; assert `len(_history_keys) == len(_fired_history)`. Fails today.

---

## G5 · F4 salt parameter exists, but `scripts/burst.py` never passes it — gap-driven items lose their salt · **medium**

**Where.** `scripts/burst.py:113` — `res = coord.run_iteration(frontier_item=item.text)`. `scripts/demo_pr_scenario.py:164` same.

**Attack.** By reading. `csis/curiosity.py:136-145` produces `FrontierItem(text=..., source='gap-driven', salt=salt)`; daemon (`csis/daemon.py:212`) passes `salt=item.salt`. But `scripts/burst.py:113` drops `item.salt`; iter.start payload records `salt=None`. The frontier text still contains `[salt=4711]`, so grepping the event log for salt values yields `None` while the LLM actually saw salt 4711.

Worse: F4 deliberately dropped the regex to avoid misattributing `[salt=N]` substrings in research-paper titles. Burst now has the WORST of both worlds — regex gone AND `item.salt` not threaded through. Forensic replay of burst runs is silently broken.

**Fix.** Burst (and demo_pr_scenario) pass `salt=item.salt`. Better: `run_iteration` accepts the `FrontierItem` directly and reads salt off it — every caller correct by construction.

**Test.** `test_G5_burst_passes_salt_to_coordinator` — monkeypatch `Coordinator.run_iteration`; run `scripts/burst.py:main` with `--iters 1 --backend mock`; assert call received `salt=<int>` matching `item.salt`. Fails today.

---

## G6 · F7 dedupe-by-sorted-labels collapses semantically-distinct FP sets that share label names · **medium**

**Where.** `csis/daemon.py:269` — `signature = tuple(sorted(fp["label"] for fp in rep.false_positives))`.

**Attack.** Verified:

```python
fps_a = [{'label': 'A', 'text': 'configure tier-2 sandbox'}]
fps_b = [{'label': 'A', 'text': 'document the auditor configuration'}]
sig_a = tuple(sorted(fp['label'] for fp in fps_a))  # ('A',)
sig_b = tuple(sorted(fp['label'] for fp in fps_b))  # ('A',)  ← collision
```

Today's `DEFAULT_CORPUS` (`csis/safety/fuzzer.py:97-98`) has two distinct labels so signature is unique. But the moment an operator adds two corpus rows sharing a label (a common pattern: `disable_auditor` across hyphen/underscore/period variants), one flipping from blocked → allowed because a pattern relaxed produces an FP set with the same label-signature as a different relaxation. Dedupe suppresses the second emission; operator never sees the new failure mode.

**Fix.** Signature includes text: `tuple(sorted((fp["label"], fp["text"]) for fp in rep.false_positives))`. FP sets are small (≤20 typical), so dedupe is still effective.

**Test.** `test_G6_fuzz_dedupe_distinguishes_different_text_same_label` — emit `[{'label':'A','text':'x'}]`, then `[{'label':'A','text':'y'}]`; assert both emitted. Today only the first emits.

---

## Out-of-scope notes (not findings)

- **G1 false-positive surface**: F1's `name.endswith("__wrapped")` flags benign names like `gift__wrapped` from unrelated subclasses. Narrow — no one names attributes like that.
- **F6 patterns() staleness**: returning a tuple under lock guarantees a coherent immutable snapshot; concurrent `add_pattern` builds a fresh tuple. No race.
- **F5 history() iteration vs scan_text mutation**: tried 4×4 reader/writer threads × 2s with `setswitchinterval(1e-7)`; zero `RuntimeError`. `list(deque)` is GIL-safe enough for Phase-0; revisit under PEP 703.
- **has_candidate lock direction**: `MemoryStore._lock` is RLock (`csis/memory/store.py:68`); coordinator calls `has_candidate` then `discard_candidate` sequentially with no outer lock held. No reentrancy issue.
- **Loop quality**: cycle-7 snapshot 09 acknowledges "two embarrassing cycles in a row" (cycle-6 E1 bare-except NameError; cycle-7 F1 documented-but-shipped mangling escape). G1 is the *third* generation of the same `_wrapped` exposure class; the loop is renaming the bug, not eliminating it. **Recommendation**: stop guarding subclass attribute introduction and instead constrain the wrap site — the only place where a wrapper-typed value enters the trusted Daemon. Until the design shifts, cycle 8+ will keep finding cycle N-1's guard insufficient.
