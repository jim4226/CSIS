# CSIS Phase-0 Cycle-6 Red Team

**Target:** Cycle-6 fixes (commits e47ba9b Phase A + just-pushed Phase B) for E1-E10. **E8 deferred — out of scope.**
**Posture:** attack what cycle-6 added/changed. No duplicates with F1-F18, P1-P12, C1-C11, D1-D11, E1-E10. Real `file:line`.

---

## F1 · E4 `__init_subclass__` guard is bypassed by `__wrapped` due to Python name-mangling · **critical**

**Where.** `csis/budget.py:429-436` — `forbidden = {"_wrapped", "__wrapped", "_BackendTracker__wrapped"}`.

**Attack.** Reproduced live:
```python
class Evil(_BackendTracker):
    __wrapped = "smuggled"   # mangled to _Evil__wrapped at class-body
```
Result: `GUARD BYPASSED. Evil class created. dir(Evil): ['_Evil__wrapped']`.

The guard inspects `cls.__dict__` for literal names `_wrapped`, `__wrapped`, `_BackendTracker__wrapped`. But when the source says `__wrapped` inside a subclass body, the **class-body compiler** rewrites the identifier to `_Evil__wrapped` BEFORE `cls.__dict__` is populated — so `__wrapped` is never a key in `cls.__dict__` for ANY subclass; only literal-mangled-target `_BackendTracker__wrapped` or unmangled-via-getattr `_wrapped` get caught. Any subclass named anything other than `_BackendTracker` evades. The fix's own docstring at csis/budget.py:415 acknowledges the limit ("known guard limit"); cycle-6 shipped it anyway. tests/test_cycle6_fixes.py:179-183 tests only `_BackendTracker__wrapped`, never `__wrapped` from a subclass with a different name.

**Fix.** Walk `cls.__mro__` looking for ANY attribute whose underlying mangled form is `_<anycls>__wrapped`, or scan `cls.__dict__` for names matching `_[A-Za-z_]\w*__wrapped`. Better: use the original closure design without `__init_subclass__`, then mark the wrapper class `@final` (typing.final) and refuse `isinstance(x, _BackendTracker) and type(x) is not _BackendTracker` at the daemon's wrap site.

**Test.** `test_F1_subclass_with_dunder_wrapped_field_rejected` — define `class X(_BackendTracker): __wrapped = "y"`; assert TypeError raised at class creation. Fails today.

---

## F2 · E1 walk-all-tiers cleanup nukes legitimate cross-tier candidates that happen to share an `entry_id` · **high**

**Where.** `csis/agents/coordinator.py:317-322`.

**Attack.** On TierMismatch, code computes `bad_ids = {entry.entry_id for entry in candidates}` and discards from EVERY tier any candidate matching those ids. Reproduced:
```
ep.write_candidate(MemoryEntry(entry_id='e-shared', tier='episodic', ...))
sm.write_candidate(MemoryEntry(entry_id='e-shared', tier='semantic', ... 'legit'))
# Simulate E1 cleanup on a TierMismatch from one Librarian call:
→ episodic candidates: []   # expected discard
→ semantic candidates: []   # *** legit unrelated candidate nuked ***
```
Librarian uses `uuid.uuid4().hex[:10]` (csis/agents/librarian.py) — 10-hex collision probability is small but non-zero, AND the whole reason E1 exists is to handle a buggy Librarian. A bug that produces a TierMismatch could equally produce a duplicate-id write. Cleanup widens blast radius from "this iteration's bad candidates" to "any candidate anywhere with this id," potentially destroying a parallel iteration's verified work.

**Fix.** Restrict discard to the tier the Librarian's bad write went into (`exc.actual_tier` if TierMismatch carries it) plus `target_tier`; OR match on (entry_id, tier, why_tag) tuple, not bare entry_id. Reaching into `tier_store._candidate.keys()` (private attr at csis/agents/coordinator.py:320) is also an API surface gap — add `MemoryStore.candidate_ids() -> set[str]` (public).

**Test.** `test_F2_tier_mismatch_cleanup_does_not_destroy_unrelated_candidate` — preseed semantic with same-id entry; trigger TierMismatch on episodic; assert semantic candidate survives.

---

## F3 · E5 conditional locking lies — `__init__` skips lock but every runtime method still calls `_file_lock` unconditionally · **high**

**Where.** `csis/budget.py:229-236` (init guards on `_needs_locking()`); but `reserve_or_raise` csis/budget.py:333, `record` csis/budget.py:367, `cancel_reservation` csis/budget.py:392, `check_or_raise` csis/budget.py:310, `snapshot` csis/budget.py:291 all enter `_file_lock(...)` regardless.

**Attack.** Docstring at csis/budget.py:226-228 promises: *"Mock daemons with no cap can run on systems without fcntl/msvcrt by falling through to a best-effort load."* Reality:
```
t = BudgetTracker(path=...)          # no cap → init succeeds, no lock
t.reserve_or_raise(0.001)            # enters _file_lock → LockUnavailable on POSIX-no-fcntl
```
Every `_BackendTracker.complete()` call invokes `reserve_or_raise` (csis/budget.py:449), so the FIRST LLM call kills the daemon with `LockUnavailable`. A mock daemon on a stripped-stdlib container appears to start, then crashes one iteration in — far worse than the cycle-5 hard fail-at-init the cycle-6 fix was supposed to soften. tests/test_cycle6_fixes.py only tests no-cap init, never a no-cap `record()`.

**Fix.** Apply the same `_needs_locking()` guard to reserve/record/cancel/snapshot/check. When no cap, fall through to direct `_load()`/`_save()` (the data race only matters for cap enforcement; under no cap, lost-update is a metering accuracy issue but not a safety one).

**Test.** `test_F3_no_cap_daemon_runs_full_iteration_without_lock` — monkeypatch `fcntl`/`msvcrt` to None; instantiate no-cap BudgetTracker, then call `reserve_or_raise` and `record`. Must succeed today; currently raises.

---

## F4 · E10 salt extraction misattributes literal `[salt=N]` substrings in legitimate frontier text · **medium**

**Where.** `csis/agents/coordinator.py:131` — `salt_match = re.search(r"\[salt=(\d+)\]", frontier_item)`.

**Attack.** Reproduced:
```
real (gap-driven):  '...produce one more [salt=4711]'             → salt=4711  ✓
poisoned/innocent:  'investigate paper Smith2020 [salt=99] correction factor' → salt=99 (FALSE)
```
The Coordinator attaches `salt=99` to the `iter.start` event payload, but no curiosity prompt with that salt was ever generated. Forensic replay (the whole point of D9/E10) reconstructs the wrong prompt — operator believes salt 99 was the active RNG state when it was 14823 or whatever. Worse on rollback-followup frontier items: the followup text is `f"re-investigate '{frontier_item}': previous attempt failed (...)"` (csis/curiosity.py:90) — a prior poisoned frontier embeds and propagates the wrong salt across iterations.

**Fix.** Don't regex-extract from text. Daemon `_tick` (csis/daemon.py:198-199) should pass the full `FrontierItem` object to `run_iteration`; coord reads `item.salt` directly. Only gap-driven items have `salt`; others get `None`. This was E10's intent — the regex was a shortcut that re-introduced the parse-from-text smell.

**Test.** `test_F4_salt_only_from_FrontierItem_not_regex` — feed `frontier_item="paper [salt=99]"` with no curiosity context; assert iter.start payload has `salt=None`.

---

## F5 · E7 `_history_keys` set is unbounded — 50k entries already ~7 MB and growing forever · **medium**

**Where.** `csis/safety/tripwires.py:147` (`self._history_keys: set[tuple[str, str]] = set()`), grown in scan_text csis/safety/tripwires.py:177.

**Attack.** Measured live (this critique session):
```
50,000 firings → len(_history_keys) = 50000, sys.getsizeof() = 2.1 MB
                  total memory with key tuples + strings ≈ 7.5 MB
```
At 1M unique firings (a year of gap-driven prompts with rotating salts each firing a unique snippet on `re.escape`-leaking text), the set grows to ~150 MB live RAM, never freed. `clear()` exists (csis/safety/tripwires.py:196) but is only called manually — daemon never invokes it. Cycle-5 D9 critique's suggestion of `deque(maxlen=N)` for `_fired_history` was sidestepped in favor of the keyed set; cycle-6 fixed dedupe latency but reintroduced the memory growth.

**Fix.** Either (a) bound `_history_keys` with an LRU eviction (`collections.OrderedDict` with `move_to_end`, cap at e.g. 10k recent keys; oldest evicted entries may re-fire and re-append once, but cost is bounded), or (b) periodically clear the keys set when `len(_history_keys) > 10_000` (accepts duplicate firings after rollover but bounds RAM). Document the chosen trade in the docstring.

**Test.** `test_F5_history_keys_set_is_bounded` — fire 20k distinct snippets; assert `len(tw._history_keys) <= 10_000`.

---

## F6 · `Constitution.add_pattern` lost-update race when two threads add concurrently · **medium**

**Where.** `csis/safety/constitution.py:82` — `self._patterns = self._patterns + (pattern,)`.

**Attack.** Read-modify-write across the GIL boundary. Under CPython 3.11 with default `sys.setswitchinterval(0.005)` this rarely manifests (tested 1000 concurrent adds, zero losses), but **PyPy, future free-threaded Python (PEP 703), or CPython with lower switch interval can lose additions silently.** Two operators (or Phase-1 tools acting as add_pattern clients) racing to widen the constitution mid-attack can see only one of two new patterns persist. The "auditable extension" docstring (csis/safety/constitution.py:80) implies safety; the implementation is non-atomic. `remove_pattern` (csis/safety/constitution.py:84-90) has the same issue.

**Fix.** Add `self._patterns_lock = threading.Lock()` in `__init__`; wrap the RMW in `with self._patterns_lock:`. Cheap, eliminates dependency on GIL semantics.

**Test.** `test_F6_add_pattern_atomic_under_free_threaded_simulation` — spin a tiny C-extension or use `sys.setswitchinterval(1e-9)` and run 1000 concurrent `add_pattern`; assert all 1000 land.

---

## F7 · `safety.fuzz_false_positives` event emitted every 25 iterations forever — but the cycle-6 corpus has zero FPs · **low (cleanup, not security)**

**Where.** `csis/daemon.py:252-258` — emits the event when `rep.false_positives` is non-empty at each snapshot boundary.

**Attack.** Cycle-5 D1 left two corpus rows acknowledged-FP (`docs_or_attack_tier2_sandbox`, `docs_or_attack_auditor_config` at csis/safety/fuzzer.py:97-98), both marked `expect_blocked=False`. Cycle-6 dropped the lookaheads that caused those to over-catch; verified live: `SafetyFuzzer().check()` returns zero failures, zero FPs. So the `safety.fuzz_false_positives` branch never fires today — DEAD CODE PATH. The bigger issue is the inverse: if cycle-7+ ever re-introduces a benign row that the patterns trip, the daemon spams the event log every 25 iterations × 24h = 5760+ entries/day per FP. The current code has no rate-limit or one-shot per pattern-set.

**Fix.** Hash the (corpus_id, pattern_set_hash, set-of-FP-labels); cache last-emitted hash; only emit on change. OR: emit once at boot if FPs exist, then never again until pattern_set changes.

**Test.** `test_F7_false_positive_event_deduplicated` — inject one FP; call `_tick` 100 times; assert at most 1 `safety.fuzz_false_positives` event emitted.

---

## Out-of-scope notes (not findings)

- **E3 token format collision**: `f"res-{pid}-{int(time.time()*1_000_000)}-{len(pending)}"` (csis/budget.py:345). Two different pids cannot collide; same-pid sub-microsecond collision is theoretically possible but the `len(pending)` differs because both calls hit the lock serially. Real but vanishingly unlikely; flagged here without finding rank.
- **E6 prune knob** is correctly configurable now, but defaults at 3600s still strand a 90-min real Opus + extended-thinking + tool-loop call. Phase-1 should default to None (never prune; require heartbeat to clear).
- **Archive filename prefix-truncation**: csis/memory/store.py:314 truncates to 80 chars but the final path includes `_{stamp}_{salt}` (csis/memory/store.py:317), making collision impossible. Not a finding.
- **`_BackendTracker.name` exposure** (csis/budget.py:443): `name = getattr(wrapped, "name", "wrapped")` leaks the wrapped backend's `name` attribute through to consumers. Cosmetic, but a hint to attackers that wrapping is happening.
- **D8 `add_pattern` audit-event gap (cycle-5 deferred)**: still missing in cycle-6; no `constitution.pattern_added` event emitted when patterns mutate. Carries through.
