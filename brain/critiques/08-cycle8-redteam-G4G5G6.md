# CSIS Phase-0 Cycle-8 Red Team — G4 / G5 / G6 + cross-cutting

**Target.** Three cycle-8 fixes that are guards rather than architectural changes — G4 (`Tripwires.scan_text` lock), G5 (salt threading through `scripts/burst.py` and `scripts/demo_pr_scenario.py`), G6 (fuzz-event dedupe signature with `sha256(fp.text)[:16]`). Plus cross-cutting attacks on the wider cycle-8 surface (the `_BackendTracker` wrap-site pivot from G1; `ALL_TIERS` hardcoding from G2).
**Posture.** Attack only what cycle-8 added or changed in G4-G6 (G2 is separately covered by `08-cycle8-redteam-G2.md` H1-H3). Only escapes with live `file:line` evidence and reproducers. No duplicates.
**Per-cycle letter for cycle 9 = H.** G2 critique already used H1-H3. Findings here continue from **H4**. Each prefixed with `(G4)`, `(G5)`, `(G6)`, or `(cross)`.
**Result.** 4 reproducible escapes (H4 critical, H5 high, H6 medium, H7 medium), 1 maintenance trap (H8 low), 6 hypotheses confirmed sound.

---

## H4 · (cross) `Coordinator(backend=...)` wires the raw backend; cycle-8 wrap-site type-check exists only in `Daemon.__init__`, so every burst.py real-backend call bypasses the budget cap · **critical**

**Where.** `csis/agents/coordinator.py:69-78` accepts any `LLMBackend` and stores it as `self.backend` with **no** `type(...) is _BackendTracker` assertion. The cycle-8 G1 architectural pivot (`csis/daemon.py:136-140`) added the check ONLY at the `Daemon.__init__` wrap site. But the codebase has three call sites that construct `Coordinator` directly with a raw, unwrapped backend:

| caller | line | passes `--backend anthropic`? |
|---|---|---|
| `scripts/burst.py:90` | `coord = Coordinator(config=cfg, backend=backend, registry=registry)` | **yes (default)** |
| `scripts/demo_pr_scenario.py:150` | `coord = Coordinator(config=cfg, backend=backend)` | mock-only |
| `csis/loop.py:61` | `coord = Coordinator(config=cfg, backend=backend)` | mock-only |

In `burst.py` the backend selected by `_select_backend("anthropic", cfg)` returns a raw `AnthropicBackend` instance. **It is never wrapped in `_BackendTracker`**, so every `coord.backend.complete(...)` call goes directly to Anthropic with zero metering against the per-day cap and zero per-call cap enforcement.

**Reproducer (verified live, mock to avoid spending real cents).**

```python
import tempfile, sys
sys.path.insert(0, '.')
from pathlib import Path
from csis.config import CSISConfig
from csis.agents.coordinator import Coordinator
from csis.backends.mock import MockBackend
from csis.budget import _BackendTracker

with tempfile.TemporaryDirectory() as tmpd:
    cfg = CSISConfig.for_tests(Path(tmpd))
    backend = MockBackend()
    # ... wire scripted responses (elided) ...
    coord = Coordinator(config=cfg, backend=backend)         # <-- mimics burst.py:90
    assert type(coord.backend) is not _BackendTracker
    n_before = len(backend.calls())
    res = coord.run_iteration(frontier_item='test')
    n_after = len(backend.calls())
    print('LLM calls made:', n_after - n_before)             # 3
    print('coord.backend type:', type(coord.backend).__name__)  # MockBackend
```

Output:
```
LLM calls made: 3
coord.backend type: MockBackend
Has tracker?: False
ESCAPE: Coordinator made N LLM calls with zero budget enforcement.
```

Three LLM calls per iteration (Researcher, Builder, Critic), un-metered. With `--backend anthropic --iters 100` the operator's day cap from `daemon.budget.json` is invisible; only the much weaker `_estimate_cost` post-hoc check (`scripts/burst.py:56-69`) gates spend, and that check runs **between** iterations, not per-call. A misconfigured `--max-cost-usd 1000` permits unbounded spend within an iteration.

**Diagnosis.** The cycle-7 G1 critique recommended: "the only place where a wrapper-typed value enters the trusted Daemon" — and cycle-8 dutifully added the check at one site (`Daemon.__init__`). But the trust boundary in the codebase isn't actually `Daemon`; it's `Coordinator`, because `Coordinator` is what executes LLM calls. `Daemon` is just a long-running loop around `Coordinator`. By moving the guard to the wrong abstraction layer, cycle 8 left a real bypass open in the very script (`burst.py`) that has `--backend anthropic` as its default.

**Severity.** Critical. `scripts/burst.py` defaults to `--backend anthropic`. An operator who blindly trusts the budget cap from a daemon snapshot has no defense if they also run `burst.py` against the same project. Real money loss in a real scenario.

**Fix.** Move the type assertion into `Coordinator.__init__`:

```python
def __init__(self, *, config, backend, ...):
    from csis.budget import _BackendTracker
    if type(backend) is not _BackendTracker:
        raise TypeError(
            f"Coordinator requires a _BackendTracker-wrapped backend "
            f"(metering must be active for any LLM call). got: {type(backend).__name__!r}"
        )
    self.backend = backend
    ...
```

Then `scripts/burst.py`, `scripts/demo_pr_scenario.py`, and `csis/loop.py` must wrap their backend explicitly:

```python
from csis.budget import _BackendTracker, BudgetTracker
backend = _BackendTracker(
    _select_backend(args.backend, cfg),
    BudgetTracker(path=cfg.brain_root / "burst.budget.json",
                  max_cost_per_day_usd=args.max_cost_usd),
)
coord = Coordinator(config=cfg, backend=backend, registry=registry)
```

This is the architectural completion of cycle-8 G1, not another guard.

**Regression test.**

```python
def test_H4_coordinator_rejects_unwrapped_backend(tmp_path):
    """Coordinator is a trust boundary too: every LLM call goes through
    self.backend. Refuse a raw backend at construction (the cycle-8 G1
    wrap-site check was placed at Daemon only — burst.py and loop.py
    construct Coordinator directly with a raw backend)."""
    from csis.agents.coordinator import Coordinator
    from csis.backends.mock import MockBackend
    from csis.config import CSISConfig
    cfg = CSISConfig.for_tests(tmp_path)
    raw = MockBackend()
    with pytest.raises(TypeError, match="_BackendTracker"):
        Coordinator(config=cfg, backend=raw)
```

Fails today. After fix: passes, and `scripts/burst.py` / `scripts/demo_pr_scenario.py` / `csis/loop.py` must be updated to wrap first or they will start raising — exactly the behavior we want.

---

## H5 · (G5) `test_G5_burst_passes_salt` is a source-grep assertion; a comment or docstring containing the literal string `salt=item.salt` passes the test while the live code path drops salt · **high**

**Where.** `tests/test_cycle8_fixes.py:182-191`:

```python
def test_G5_burst_passes_salt(tmp_path):
    burst_path = Path(__file__).resolve().parent.parent / "scripts" / "burst.py"
    source = burst_path.read_text(encoding="utf-8")
    assert "salt=item.salt" in source, (...)
```

This is a *textual* assertion against the source file. It does not verify the live call path actually threads salt into `run_iteration`.

**Reproducer (verified live).** Backup `scripts/burst.py`, then mutate the live call to drop salt while leaving the magic string in a comment/docstring:

```python
import shutil, subprocess, sys
shutil.copy('scripts/burst.py', '/tmp/burst.py.bak')
with open('scripts/burst.py') as f: s = f.read()
new = s.replace(
    'res = coord.run_iteration(frontier_item=item.text, salt=item.salt)',
    '"""see salt=item.salt above"""\n'
    '        res = coord.run_iteration(frontier_item=item.text)'
)
with open('scripts/burst.py','w') as f: f.write(new)

# 1) Source-grep test passes:
r = subprocess.run([sys.executable,'-m','pytest',
    'tests/test_cycle8_fixes.py::test_G5_burst_passes_salt','-q'],
    capture_output=True, text=True)
print(r.stdout[-200:])   # "1 passed in 0.15s"

# 2) Live call observably drops salt:
import burst
burst.main(['--iters','1','--backend','mock','--max-cost-usd','0.01','--sleep-s','0'])
# Inspect event log: last iter.start payload has salt=None even though
# frontier text contains [salt=8973].
```

Live output captured:
```
============================== 1 passed in 0.15s ==============================
Last iter.start payload: {'id': 'iter-7949ec3d75804426be97baece98b58dd',
                          'frontier': 'gap-driven: tier=semantic ... [salt=8973]',
                          'salt': None}
```

The frontier text records `[salt=8973]` but the iter.start payload records `salt: None`. Forensic-replay divergence with the test green.

**Diagnosis.** Cycle-8 G5's gate is a `re.search(r"...salt=item.salt", source)` proxy for "the wire is connected." Proxies that don't exercise the wire are bypassable by any reviewer who's tired enough to silence the live call while leaving the magic string nearby — exactly the regression cycle 7's F4 was supposed to make impossible to ship. A bored junior developer commenting out a line and adding a TODO would re-introduce the cycle-7 G5 bug AND pass CI.

**Severity.** High. The test gives false confidence; the actual escape is what G5 was supposed to prevent (frontier text and event log disagree on salt → replay misleads operator).

**Fix.** Replace the source-grep assertion with a behavior assertion that drives `burst.main()` and reads the actual event log:

```python
def test_H5_burst_threads_salt_to_iter_start_event(tmp_path, monkeypatch):
    """G5 behaviorally: burst.py must propagate FrontierItem.salt into
    the iter.start event payload, not just contain the literal string
    salt=item.salt in source (which the cycle-8 test gates on)."""
    import burst, json
    from csis.config import CSISConfig
    # Force a salt-bearing frontier item via monkeypatched Curiosity.next
    captured = {}
    def fake_next(self, h):
        from csis.curiosity import FrontierItem
        item = FrontierItem(text="forced [salt=4242]", source="gap-driven",
                            priority=3, salt=4242)
        captured['salt'] = item.salt
        return item
    monkeypatch.setattr("csis.curiosity.Curiosity.next", fake_next)
    burst.main(['--iters','1','--backend','mock','--max-cost-usd','0.01','--sleep-s','0'])
    cfg = CSISConfig()
    lines = Path(cfg.event_log_path).read_text().splitlines()
    iter_starts = [json.loads(l) for l in lines if '"iter.start"' in l]
    last = iter_starts[-1]['event']['payload']
    assert last['salt'] == 4242, f"H5: burst dropped salt; got {last['salt']!r}"
```

Fails today if the live call is commented out (passes if it's intact). Passes regardless of what comments/docstrings the source contains.

---

## H6 · (G5) `csis/loop.py:62` and `Coordinator.run_continuous` (`csis/agents/coordinator.py:439`) call `run_iteration` without `salt=`; same forensic-replay loss for any gap-driven item they receive · **medium**

**Where.** Grepped `run_iteration(` across `scripts/`, `csis/`, `tests/`. Two production call sites still drop salt:

```
csis/loop.py:62                  res = coord.run_iteration(frontier_item="demo frontier")
csis/agents/coordinator.py:439   res = self.run_iteration(frontier_item=item, target_tier=target_tier)
```

`csis/loop.py:62` is a static demo, so the missing salt is correct *today* (demo string contains no `[salt=N]`). But `Coordinator.run_continuous` (`csis/agents/coordinator.py:425-447`) iterates a `list[str]` and calls `run_iteration(frontier_item=item)` with no salt parameter. If a caller passes gap-driven frontier strings (which embed `[salt=N]` in their text), the iter.start event records `salt=None` while the LLM saw salt N.

**Reproducer (verified live).**

```python
from csis.agents.coordinator import Coordinator
# ... mock backend setup ...
coord = Coordinator(config=cfg, backend=backend)
gap = "gap-driven: tier=semantic has only 0 promoted entries; produce one more [salt=8973]"
coord.run_continuous([gap])
# Inspect iter.start event: payload.salt == None, payload.frontier contains [salt=8973]
```

The `csis/__init__.py:7` docstring even advertises `run_continuous` as part of the public API (`from csis.loop import run_iteration, run_continuous`). Operators reading that comment may use `run_continuous` with curiosity-generated items and silently lose forensic salt.

**Severity.** Medium. Same forensic-replay loss as cycle-7 G5, but on a path that isn't exercised by the daemon today (so live impact depends on operator use of `run_continuous`).

**Fix.** Change `run_continuous` to accept `list[FrontierItem]` and pass `salt=item.salt`. Or, simpler and consistent with what cycle-7 G5 already established at `csis/daemon.py:222`: pass through both fields:

```python
def run_continuous(self, frontier_items: list[FrontierItem | str], *, ...):
    ...
    for raw in frontier_items:
        item = raw if isinstance(raw, FrontierItem) else FrontierItem(
            text=raw, source="external", priority=0, salt=None)
        ...
        res = self.run_iteration(frontier_item=item.text, salt=item.salt,
                                 target_tier=target_tier)
```

`csis/loop.py:62` continues to work (no salt to thread). Future callers that want forensic-correct salt just pass `FrontierItem`.

**Regression test.**

```python
def test_H6_run_continuous_threads_salt_for_frontier_items(tmp_path):
    """Coordinator.run_continuous must accept FrontierItem and pass salt
    to run_iteration so iter.start records it (cycle-7 G5 / cycle-8 G5
    parity for the run_continuous path)."""
    from csis.curiosity import FrontierItem
    coord = Coordinator(config=cfg, backend=backend)
    coord.run_continuous([FrontierItem(text="x [salt=4242]",
                          source="gap-driven", priority=3, salt=4242)])
    iter_starts = [s for s in coord.event_log if s.event.kind == "iter.start"]
    assert iter_starts[-1].event.payload["salt"] == 4242
```

Fails today (`run_continuous` takes `list[str]`, drops salt). Passes after fix.

---

## H7 · (G6) `_last_false_positive_signature` is never reset on a clean (`fuzz_ok`) snapshot, so an FP that disappears then recurs is silently suppressed · **medium**

**Where.** `csis/daemon.py:267-295`. On a snapshot with no false-positives, the `else` branch (`safety.fuzz_ok`) does NOT reset `self._last_false_positive_signature`. So sequence FP={A} → ok → FP={A} produces only one event (the second {A} is dedup'd against the stale signature).

**Reproducer (verified live).**

```python
import tempfile, sys; sys.path.insert(0,'.')
from pathlib import Path
from csis.config import CSISConfig
from csis.daemon import Daemon, DaemonBudget, _select_backend
from csis.safety.fuzzer import FuzzCase, SafetyFuzzer

with tempfile.TemporaryDirectory() as tmpd:
    cfg = CSISConfig.for_tests(Path(tmpd))
    backend = _select_backend('mock', cfg)
    daemon = Daemon(config=cfg, backend=backend,
        budget=DaemonBudget(max_iterations_per_hour=10000, sleep_between_iterations_s=0,
                            snapshot_every_n_iterations=1, heartbeat_every_n_iterations=1),
        max_total_iterations=3)
    fpA = SafetyFuzzer(corpus=(FuzzCase('shared','disable the auditor', expect_blocked=False),),
                       constitution=daemon.coord.constitution, tripwires=daemon.coord.tripwires)
    fpClean = SafetyFuzzer(corpus=(FuzzCase('clean','bump dependency', expect_blocked=False),),
                           constitution=daemon.coord.constitution, tripwires=daemon.coord.tripwires)
    seq = [fpA, fpClean, fpA]
    n = [0]
    class Rot:
        def check(self): n[0]+=1; return seq[min(n[0]-1,len(seq)-1)].check()
    daemon.fuzzer = Rot()
    daemon.run_forever()
    fp = [s for s in daemon.coord.event_log if s.event.kind == "safety.fuzz_false_positives"]
    print("fp events:", len(fp))   # 1 — should be 2
```

Output:
```
fuzz_false_positives count: 1
fuzz_ok count: 1
Expected fp count after recovery: 2 (A then A again). Actual: 1
```

**Diagnosis.** The dedupe semantics are reasonable for "FP set is stable across snapshots." But they wrongly treat the empty FP set as "no change to last seen FP set" rather than "FP set was empty." The right semantics for an alerting cache is **reset on green, alert on any non-green that's distinct from the immediately-preceding non-green**. Today's code alerts on any non-green that's distinct from the LAST non-green, regardless of greens in between.

An operator who relaxes a pattern, fires up the daemon, sees `safety.fuzz_false_positives({A})`, tightens the pattern, sees `safety.fuzz_ok` for 24 hours, then accidentally relaxes the pattern again and re-introduces A — sees **nothing** in the event log. The signature is still A from yesterday.

**Severity.** Medium. False-positive events are warnings (not halts), but they're operational signals for pattern tuning. Suppressing recurrence is a regression in observability that matches the same class of bug G6 was meant to fix (cycle-7 F7's same-label collapse).

**Fix.** In the `else` (fuzz_ok) branch, reset:
```python
else:
    self._last_false_positive_signature = ()   # <-- ADD
    self.coord.event_log.emit("coordinator", "safety.fuzz_ok", ...)
```

Or, more strictly, emit a `safety.fuzz_false_positives_recovered` event when transitioning from non-empty to empty, then reset.

**Regression test.**

```python
def test_H7_fuzz_dedupe_resets_after_clean_snapshot(tmp_path):
    """An FP set A that disappears (fuzz_ok) and then recurs must emit a
    fresh safety.fuzz_false_positives event. Cycle-8 G6 deduped against
    last-emitted signature without resetting on clean snapshots."""
    # Setup daemon with snapshot_every=1, max_total=3.
    # RotatingFuzzer: FP={A} → no FPs → FP={A again}.
    # Assert: len(fp_events) == 2 (not 1).
```

Fails today (1 event). Passes after the reset.

---

## H8 · (cross) `ALL_TIERS = ("working","episodic","semantic","procedural","causal")` is hardcoded in two places in coordinator.py and one in fuzzer/curiosity; adding a 6th tier silently misses cleanup paths · **low (latent)**

**Where.**
- `csis/agents/coordinator.py:267` — `ALL_TIERS` for pre-consolidate snapshot
- `csis/agents/coordinator.py:474` — `ALL_TIERS` for tier-mismatch cleanup walk
- `csis/agents/coordinator.py:504-505` — auto-snapshot tier listing
- `csis/curiosity.py:121` — gap-driven tier scan
- `csis/memory/store.py:347-351` — actual `MemoryHierarchy` field declarations

Today these all agree on 5 tiers, so no live escape. But adding a new tier to `MemoryHierarchy` without updating each hardcoded list silently:
1. Skips the new tier in pre-consolidate snapshot → its candidates can't be distinguished from "newly written by this iteration" → wrongly discarded on TierMismatch.
2. Skips the new tier in cleanup walk → bad-librarian writes to the new tier are stranded forever (the exact F2/G2 bug class).
3. Skips the new tier in gap-driven curiosity → it never gets refilled.

**Severity.** Low — no current escape; trap for whoever adds the 6th tier.

**Fix.** Replace hardcoded lists with `tuple(MemoryHierarchy.model_fields.keys())` or expose `MemoryHierarchy.tier_names()` as a class method.

**Regression test.**

```python
def test_H8_all_tiers_constant_matches_hierarchy_fields():
    """ALL_TIERS used in coordinator and elsewhere must equal the actual
    MemoryHierarchy field set so adding a tier doesn't silently skip
    cleanup. Today both are ('working','episodic','semantic','procedural',
    'causal') — keep them in sync."""
    from csis.memory.store import MemoryHierarchy
    from csis.agents.coordinator import Coordinator
    import inspect
    src = inspect.getsource(Coordinator)
    # Two occurrences in coordinator.py (snapshot + cleanup).
    assert src.count('ALL_TIERS = ("working"') == 2 or src.count(
        'tuple(MemoryHierarchy.model_fields') >= 2
    actual = tuple(MemoryHierarchy.model_fields.keys())
    assert actual == ("working","episodic","semantic","procedural","causal")
```

Passes today; alerts the next contributor who adds/renames a tier without updating both ALL_TIERS sites.

---

## Confirmed sound (no findings)

### G4 — `Tripwires.history()` returns a list snapshot under lock; concurrent `clear()` cannot invalidate it

`history()` at `csis/safety/tripwires.py:205-209` returns `list(self._fired_history)` — a fully materialized copy — under `_history_lock`. After the lock is released, a concurrent `clear()` mutates the underlying deque, but the caller's list is independent. Iterator invalidation is not possible. 4 reader × 4 clearer threads × 2000 ops at `sys.setswitchinterval(1e-9)`: zero `RuntimeError`. The prompt's hypothesis ("can `clear()` invalidate the iterator?") is wrong because the return is a copy, not a view.

### G4 — `_scan_dual_form` runs outside the lock; no shared mutable state to race

`_scan_dual_form` (`csis/safety/tripwires.py:156-173`) reads only `self._patterns` (a list of (label, Pattern) tuples) and the local `text` argument. Patterns are list-initialized once in `__init__` and never mutated in the tripwires code (verified with `grep _patterns` across `csis/safety/tripwires.py`). Regex compiled `Pattern` objects are thread-safe per the Python docs. So even slow regex matches on large text contend with nothing in another thread.

### G4 — `fired()` reads without the lock; no invariant broken

`fired()` at `csis/safety/tripwires.py:202-203` returns `bool(self._fired_history)`. `bool()` of a deque is a `__len__` call, which is GIL-atomic. A racing `clear()` may flip the return between True and False, but no caller invariant is broken — `fired()` is documented as a state probe, not a transactional guarantee. Tested with 8 readers × 4 clearers × 2000 ops: zero errors.

### G4 — `history_size()` lock acquisition is minimal contention

`history_size()` at `csis/safety/tripwires.py:211-213` takes the lock for a single `len()`. Under the same race conditions as G4's main test, the lock is held for nanoseconds — not measurable contention vs. the bare `len()` even at 16 threads. The lock is correct (no race on partial deque state) and not a hotspot.

### G6 — `fp` missing `"text"` raises `KeyError`, caught by daemon's outer exception handler

If `fp["text"]` is missing (which today's in-tree `SafetyFuzzer` never produces — `csis/safety/fuzzer.py:172-188` always populates `text`), the signature comprehension raises `KeyError` mid-iteration. This is caught by `daemon.py:195` (`except Exception as exc`), emitted as `daemon.exception`, and the daemon survives. The snapshot's safety check is silently skipped that tick — but the next snapshot retries, so no permanent state loss. Not a real escape with the in-tree corpus.

### G6 — 64-bit truncated sha256 collision is not realistically attacker-craftable

Birthday bound for `sha256(text)[:16]` collision is ~2^32 distinct texts. The fuzzer corpus is ~30 entries today, max realistically ~10⁴. No attacker-craftable collision. Even an operator pasting in a malicious 1M-entry corpus from an untrusted source cannot reasonably collide. Hash truncation is fine for this scale.

---

## Out-of-scope notes (not findings)

- **G5 / `test_G5_demo_pr_scenario_explicitly_passes_salt`** (`tests/test_cycle8_fixes.py:194-197`) checks only for the literal substring `salt=` in source — even weaker than the burst test (any `salt=foo` line passes). Same source-grep failure mode as H5, but `demo_pr_scenario.py` is mock-only and salt is hardcoded `None`, so no live impact. H5's behavioral-test fix should be applied to both.
- **G6 same label + same text + different `by_constitution`/`by_tripwires` flags** — yes, the signature collapses these, suppressing the diagnostic that the failure mode shifted from "tripwires-only" to "constitution+tripwires." Operator forensic loss, but not an exploitable escape. Adding `by_constitution` and `by_tripwires` to the signature tuple would fix.
- **`csis/__init__.py:7` advertises `from csis.loop import run_iteration, run_continuous`** — neither name is exported by `csis/loop.py`. Cosmetic docs bug, not a security issue.
- **`MemoryHierarchy.tier(name)`** uses `getattr(self, name)` (`csis/memory/store.py:364-365`). Invalid tier names raise `AttributeError`, caught nowhere in the cleanup path. But `MemoryEntry.tier` is a Pydantic `Literal` so invalid strings never reach the lookup. Sound.
- **Loop quality (cycle 8).** Two of the three guarded fixes have the same class of weakness: G4's `_history_lock` and G6's text-hash signature are local additions that work *in isolation* but leave broader architectural gaps unexamined. The G1 wrap-site pivot was correct in spirit but applied at the wrong abstraction (Daemon, not Coordinator) — H4 reopens what cycle-8 was supposed to close. G5 was supposed to be a five-line wiring fix and ships with a source-grep test that doesn't gate behavior (H5). The pattern is: each cycle's "fix" is narrowly scoped to the exact reproducer from the prior critique, leaving close-relative escapes open. **Recommendation for cycle 9:** stop treating each finding as a single patch and start treating it as a regression class — when G1 lands a wrap-site type check, audit *every* construction site of the wrapped type; when G5 threads a parameter, audit *every* call to the function; when G6 fixes a signature, audit the *full* state machine the signature drives (not just the one transition the critique flagged). H4 / H5 / H7 are all the same metabug.
