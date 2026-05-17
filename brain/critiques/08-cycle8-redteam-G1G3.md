# CSIS Phase-0 Cycle-8 Red Team · G1 + G3 scope

**Target:** the cycle-8 architectural pivots — G1 (wrap-site exact-type
check in `Daemon.__init__`) and G3 (`BudgetTracker._maybe_locked`
always-try-lock). The cycle-7 critique recommended "constrain the
wrap site" and "always lock when fcntl/msvcrt is available." Cycle-8
implemented both. This red team attacks them live.

**Posture.** No theoretical hand-waving. Every finding has a
`file:line` reference and a Python reproducer that the author actually
ran. Tag-letter for cycle-8 findings is `H` per the per-cycle scheme.

---

## H1 · G1 wrap-site check is bypassed by every non-Daemon entry point — `scripts/burst.py` runs the **real** Anthropic backend with **zero** budget enforcement · **critical**

**Where.**
- `csis/agents/coordinator.py:69-78` — `Coordinator.__init__` takes
  `backend: LLMBackend` and stores it on `self.backend` with **no
  wrap-site check**.
- `scripts/burst.py:85-90` — constructs `Coordinator(config=cfg,
  backend=backend, registry=registry)` directly. The backend is the
  result of `_select_backend(args.backend, cfg)` (line 85), which
  returns a raw `AnthropicBackend()` (see `csis/daemon.py:393-396`)
  when `args.backend == "anthropic"` (the **default**, line 75).
- `scripts/demo_pr_scenario.py:150` — same direct construction.
- `csis/loop.py:61` — same direct construction.

**Attack.** Verified by source inspection plus runtime check:

```python
import inspect, scripts.burst
src = inspect.getsource(scripts.burst)
assert "_BackendTracker" not in src
assert "BudgetTracker" not in src
# → True; burst.py never wraps the backend, never instantiates a tracker.
```

Run `python scripts/burst.py --iters 100` (default `--backend
anthropic`). Every iteration's Researcher / Builder / Critic /
Verifier / Auditor call goes through the raw `AnthropicBackend`. The
only cost guard is `burst.py:105-109`'s `hasattr(backend, "calls")`
post-hoc estimator — which is False for `AnthropicBackend` (only
`MockBackend` exposes `calls()`), so the entire cost ceiling check is
silently a no-op:

```python
from csis.backends.anthropic import AnthropicBackend
assert hasattr(AnthropicBackend, "calls") is False
```

Cycle-8's thesis is "the wrap site is the only entry point of a
wrapper-typed value into the trusted runtime, so constraining it
defeats every subclass-shaped bypass." That is only true if **the
wrap site is the only entry point**. It isn't: `Coordinator.__init__`
is itself a wrap site (it stores the backend) and accepts any
`LLMBackend`, including raw unwrapped ones. The Daemon's check
protects exactly one of four production-relevant Coordinator
constructors.

The structural form of this bug is the cycle-7 critique's exact
complaint: each cycle moves the guard, the next cycle finds the
guard is on only one of the entry points.

**Fix.** Move the check INTO `Coordinator.__init__`. Either:

1. Coordinator refuses any backend that is not `_BackendTracker`,
   and `burst.py` / `demo_pr_scenario.py` / `csis/loop.py` must
   construct a `BudgetTracker` and wrap explicitly; OR
2. Coordinator constructs its own `BudgetTracker` and wraps any
   backend it receives, so wrapping is centralized at the
   *Coordinator* level — which is the actual single chokepoint for
   every LLM call in the system.

Option 2 closes the entire surface in one place. Cycle-8's pivot was
correct in spirit but located one level too high in the call graph.

**Test.** `test_H1_burst_wraps_backend_in_budget_tracker` — invoke
`scripts/burst.main(["--iters", "1", "--backend", "mock"])` with the
Coordinator constructor monkey-patched to record `type(backend)`;
assert it is `_BackendTracker`. Fails today (it is `MockBackend`).

---

## H2 · G1 closure cells are mutable from Python — swap `wrapped` post-construction and `type(self.backend) is _BackendTracker` still passes · **critical**

**Where.** `csis/budget.py:465-492` — `_BackendTracker.__init__`
captures `wrapped` and `tracker` in closures bound to `_call_complete`
and `_call_identity`. Closure cells are first-class Python objects;
their `cell_contents` is a writable attribute since CPython 3.7.

**Attack.** Reproduced live (`python -c "..."`):

```python
import tempfile
from pathlib import Path
from csis.budget import _BackendTracker, BudgetTracker
from csis.backends.mock import MockBackend
from csis.backends.base import LLMRequest, LLMResponse

tmp = Path(tempfile.mkdtemp())
real = MockBackend()
real.set_model_id("builder", "claude-opus-4-7")  # REAL Opus pricing
real.script("researcher", "builder", "real response")
tracker = BudgetTracker(tmp / "b.json", max_cost_per_day_usd=0.10)
wrapper = _BackendTracker(real, tracker)

# Step 1: legitimate use — confirm cap engages on real path
req = LLMRequest(role="researcher", checkpoint_id="builder",
                 system="", prompt="x" * 100000, max_tokens=10)
try:
    wrapper.complete(req)
except Exception as e:
    print("real call refused:", type(e).__name__)  # BudgetCapExceeded ✓

# Step 2: swap closure cells
class EvilBackend:
    name = "evil"; call_count = 0
    def complete(self, req):
        EvilBackend.call_count += 1
        return LLMResponse(role=req.role, checkpoint_id=req.checkpoint_id,
                           text="LEAKED", tokens_in=999999, tokens_out=999999)
    def checkpoint_identity(self, ck):
        return {"model_id": "mock-opus",   # ← lies: report as $0 model
                "checkpoint_id": ck, "backend": "evil", "tool_set": "x"}

fn = wrapper._call_complete
fn.__closure__[fn.__code__.co_freevars.index("wrapped")].cell_contents = EvilBackend()
fn2 = wrapper._call_identity
fn2.__closure__[fn2.__code__.co_freevars.index("wrapped")].cell_contents = EvilBackend()

# Step 3: type still passes the daemon check.
assert type(wrapper) is _BackendTracker  # ✓ ARCHITECTURAL CHECK PASSES

# Step 4: hammer 100 calls — all succeed; cap never engages.
for _ in range(100):
    wrapper.complete(req)
print("EvilBackend received:", EvilBackend.call_count, "calls")  # 100
print("tracker recorded cost: $", tracker.today_cost_usd())       # 0.0
# Genuine cost of 100 calls at this prompt size would be ~$37.50 + output.
```

Output captured live:

```
real call refused: BudgetCapExceeded
EvilBackend.call_count: 100
tracker.today_cost_usd: 0.0
```

The exact-type check `type(self.backend) is _BackendTracker` is a
*nominal* check. The instance's runtime behaviour is entirely
determined by the contents of two cells the check cannot see. Cycle-8
moved the guard from `__init_subclass__` (a class-time hook) to a
`type(...) is ...` test in `Daemon.__init__` (an instance-time hook).
Neither hook observes closure contents.

The lie about `model_id="mock-opus"` exploits the price table at
`csis/budget.py:34-43`: a non-table model gets `_DEFAULT_PRICE` of
Opus-like, but the *explicit* entry `"mock-opus": {"in": 0.0, "out":
0.0}` zero-prices anything that asserts that identity. Combined with
the closure swap, this routes through `_do_complete` legitimately
(`reserve_or_raise` succeeds for $0; `record` adds $0) while real
calls happen to the swapped backend.

**Fix.** Two options (do both):

1. Make `_BackendTracker.__init__` store `wrapped` and `tracker`
   as `__slots__` attributes on the instance with a `__setattr__`
   override that raises after the first set. This eliminates the
   closure-cell mutation primitive because there are no closures
   to mutate. Then keep the `type(...) is _BackendTracker` check.
2. After binding closures, *delete* the freevar names from the
   instance scope by binding them to a tombstone in a final
   `__init__` line — this doesn't help because cells are still
   reachable via `fn.__closure__`. So slot-and-freeze is the actual
   defense.

Alternatively, abandon the closure-capture pattern and use a
private `_wrapped`/`_tracker` attribute with `__getattribute__`
override that blocks reflection — but this is what cycles 4-7 tried
and the surface always reopens. The slot-and-freeze pattern is
*structurally* immutable.

The price-lookup side of the attack is also worth narrowing: a
backend whose `checkpoint_identity` self-reports a free model when
it is in fact a paid model is a confused-deputy on its own. Consider
maintaining a server-side allowlist of `model_id` values trusted to
self-report, or recording the **backend's** name alongside model_id
for cost lookup.

**Test.** `test_H2_closure_cell_mutation_rejected` — perform the swap
above; expect either `TypeError` on the mutation attempt (preferred)
or a runtime error on the subsequent `complete()` call. Today the
attack succeeds silently with 100 unmetered real-backend calls.

---

## H3 · G1 `Daemon.backend` and `Daemon.coord.backend` are plain attributes — `setattr` after construction silently swaps the wrapper · **critical**

**Where.** `csis/daemon.py:130-140` — the type check runs **once**
inside `Daemon.__init__`. There is no `__setattr__`, no slot, no
property guarding `self.backend` or `self.coord.backend`. The
Coordinator's backend (`csis/agents/coordinator.py:78`) is likewise
plain.

**Attack.** Reproduced live:

```python
from csis.daemon import Daemon, DaemonBudget
from csis.config import CSISConfig
from csis.backends.mock import MockBackend
from csis.backends.base import LLMResponse
import tempfile; from pathlib import Path

cfg = CSISConfig.for_tests(Path(tempfile.mkdtemp()))
real = MockBackend()
real.set_model_id(cfg.builder_checkpoint, "mock-opus")
real.set_model_id(cfg.auditor_checkpoint, "mock-sonnet")

d = Daemon(config=cfg, backend=real,
           budget=DaemonBudget(max_iterations_per_hour=10),
           max_total_iterations=1, max_cost_per_day_usd=0.01)

assert type(d.backend) is __import__("csis.budget", fromlist=["_BackendTracker"])._BackendTracker
assert type(d.coord.backend) is __import__("csis.budget", fromlist=["_BackendTracker"])._BackendTracker

class EvilBackend:
    name = "evil"
    def complete(self, req):
        return LLMResponse(role=req.role, checkpoint_id=req.checkpoint_id,
                           text="X", tokens_in=999999, tokens_out=999999)
    def checkpoint_identity(self, ck):
        return {"model_id": "claude-opus-4-7", "checkpoint_id": ck,
                "backend": "evil", "tool_set": "x"}

# Direct setattr — type check is in __init__, no re-validation.
d.coord.backend = EvilBackend()
# All agent calls now route through EvilBackend, unmetered.
```

Subclassing `Daemon` and overriding `__init__` to call `super()`
then `self.coord.backend = EvilBackend()` is identical and observed
live. The cycle-7 G1 finding was about `__init_subclass__` running
only at class-body completion; cycle-8 moved the check to
`__init__`, which runs only at construction — same class of weakness,
different lifecycle moment.

**Fix.** Make `Daemon.backend` a property whose setter rejects
non-`_BackendTracker` values:

```python
@property
def backend(self): return self._backend
@backend.setter
def backend(self, v):
    if type(v) is not _BackendTracker:
        raise TypeError(...)
    self._backend = v
```

Same for `Coordinator.backend`. Combined with H1's fix (Coordinator
owns the wrap), this gives a single chokepoint guarded at every set.

**Test.** `test_H3_daemon_backend_setattr_rejected_post_init` —
construct `Daemon`; perform `d.backend = MockBackend()`; expect
`TypeError`. Today the setattr silently succeeds and the daemon
runs unmetered.

---

## H4 · G3 `_maybe_locked` raises `LockUnavailable` after 20s under genuine sibling contention — real call completes, `record()` fails, spend is lost · **high**

**Where.** `csis/budget.py:147-161` — `_file_lock` retries
`msvcrt.locking` for ~20 seconds, then raises `LockUnavailable`.
`csis/budget.py:316-320` — `_maybe_locked` propagates
`LockUnavailable` when `_needs_locking()` is true (any cap set).
`csis/budget.py:388-403` — `record()` is `with self._lock,
self._maybe_locked(): ...` so a 20s-blocked record raises **after**
the real backend call has happened (because `_do_complete` runs
`resp = wrapped.complete(req)` before `tracker.record(...)`).

**Attack.** Reproduced live on Windows. A slow-running real call
(simulated with `time.sleep(2)`) plus an external lock holder that
appears 1.5s into the call:

```python
import threading, time, tempfile
from pathlib import Path
from csis.budget import BudgetTracker, _BackendTracker, _file_lock, LockUnavailable
from csis.backends.base import LLMRequest, LLMResponse

tmp = Path(tempfile.mkdtemp())
class SlowReal:
    name = "real"
    def complete(self, req):
        time.sleep(2)  # simulate real LLM call (Opus extended thinking >2s)
        return LLMResponse(role=req.role, checkpoint_id=req.checkpoint_id,
                           text="response", tokens_in=100, tokens_out=100)
    def checkpoint_identity(self, ck):
        return {"model_id": "claude-opus-4-7", "checkpoint_id": ck,
                "backend": "real", "tool_set": "x"}

tracker = BudgetTracker(tmp / "b.json", max_cost_per_day_usd=10.0)
wrapper = _BackendTracker(SlowReal(), tracker)
req = LLMRequest(role="researcher", checkpoint_id="builder",
                 system="", prompt="hi", max_tokens=10)

def delayed_holder():
    time.sleep(1.5)  # let reserve+real-call begin
    with _file_lock(tmp / "b.json.lock"):
        time.sleep(25)
threading.Thread(target=delayed_holder, daemon=True).start()

try:
    resp = wrapper.complete(req)
except LockUnavailable:
    pass
print("today_cost_usd:", tracker.today_cost_usd())
print("pending:", tracker._state.pending)
```

Captured output:

```
LockUnavailable raised at 22.1 s
today_cost_usd: 0.0
pending: [PendingReservation(pid=29212, amount_usd=0.00075, ts=..., token=...)]
```

The wrapper has actually billed the real backend (the SlowReal call
ran to completion) but `tracker.record` failed to acquire the lock,
so the cost was never written. The pending reservation remains and
will be pruned at `prune_stale_pending_s=3600s`, so for the next hour
every sibling daemon sees a phantom pending reservation eating cap
space.

In the daemon loop (`csis/daemon.py:184-200`), `LockUnavailable` is
not `BudgetCapExceeded`, so it goes to the generic
`except Exception as exc:` branch — daemon logs `daemon.exception`,
sleeps `sleep_between_iterations_s`, and continues. Real spend
*accumulates* against the operator's actual Anthropic bill but
`today_cost_usd` returns 0, the cap NEVER triggers, and the daemon
keeps making more real calls.

Cycle-7 F3's no-cap-skip-lock fallback was an over-correction. Cycle
8 G3 removed it but kept the 20s ceiling. Under heavy contention (an
operator running cap'd daemon + cap'd burst + cap'd
demo_pr_scenario sharing one budget file, or a stuck process holding
the lock) the ceiling fires.

**Fix.** Two changes in one:

1. `_file_lock` should support an unbounded blocking wait by
   parameter; the daemon's lock should block indefinitely (with a
   periodic stop-file check via `_stopped.wait`) rather than ceiling
   at 20s. Stale-holder cleanup is the prune mechanism already in
   place (PIDs + timestamps in `pending`).
2. `_do_complete` should call `tracker.record(...)` in a `finally`-
   style block that, on `LockUnavailable`, writes the cost-debit
   record to a write-ahead-log file (atomic append) and replays at
   next successful lock acquire. Or — simpler — `record()` retries
   forever (with stop-file check) instead of raising. Losing one
   real-backend spend record is more dangerous than blocking 30s.

Either way, the daemon must never accept `today_cost_usd == 0.0`
when it has just made real calls.

**Test.** `test_H4_record_does_not_lose_spend_under_lock_timeout` —
build `_BackendTracker` over a `SlowReal`-style backend; from a
sidecar thread, hold `_file_lock` for >20s starting mid-call; assert
either the wrapper does not return (it retries), or upon raising,
`tracker.today_cost_usd()` reflects the call cost (write-ahead-log
replay). Today the wrapper raises and the cost is lost.

---

## H5 · G3 `_file_lock` open-handle keeps the lockfile alive but `_maybe_locked` does NOT release the lock on `LockUnavailable`-from-inside-the-yielded-block · **low** (defensive)

**Where.** `csis/budget.py:301-320`. The `_file_lock` context
manager (`csis/budget.py:179-192`) does correctly release in its
own `finally`. Verified.

**Attack attempted, not exploitable.** I wrote a reproducer that
deletes the lockfile while a sibling holds it. Windows file-in-use
semantics block the delete with `WinError 32`, so the
"lockfile-deleted-mid-lock" scenario can't be triggered on Windows.
On POSIX, deletion succeeds but `fcntl.flock` is tied to the file
descriptor, not the directory entry, so the lock remains; a second
opener creates a *new* file at the same path and `fcntl.flock` on
its own fd does not synchronize with the deleted-then-recreated
holder. This IS a POSIX race surface — but no POSIX environment is
exercised by this red team, and the cycle-8 attacks I was asked to
target are about Windows behavior.

**Finding rating:** I could not produce a working live POSIX
reproducer in this Windows session. Flagging as `low` for follow-up
on a Linux runner; not a confident enough finding to recommend a
production fix without that verification.

**Fix.** If verified on POSIX: open the lockfile with `O_TMPFILE` or
re-open and re-flock-after-stat-check pattern. Or `flock` an
unlink-resistant resource (a process-local pipe with a known
canonical name).

**Test.** `test_H5_posix_unlink_during_lock_does_not_desync` — only
run when `sys.platform != "win32"`; thread-1 acquires lock; thread-2
unlinks the file; thread-3 attempts lock and asserts it blocks until
thread-1 releases. Mark `xfail` until verified.

---

## Out-of-scope notes (not findings)

- **Closure-cell mutation against `tracker` cell:** the closure also
  captures `tracker` (`csis/budget.py:476`). An attacker swapping
  the `tracker` cell can route accounting to a no-op tracker, but
  this requires the same mutation primitive as H2 and the fix
  (slot + freeze) closes both.
- **`_maybe_locked` exception release:** verified to correctly
  unlock when a `RuntimeError` is raised inside the `with` block
  (tested live: another thread acquires the lock immediately after).
  Not a finding.
- **Trailing-slash path desync (two trackers on `b.json` vs
  `sub/../b.json`):** the lock files have distinct string
  representations (`b.json.lock` vs `sub/../b.json.lock`), so two
  cap'd trackers on path-equivalent paths use disjoint locks. In a
  400-call hammer test on Windows I could not produce lost updates
  (os.replace appears to serialize on the data file via OS
  semantics). Theoretical race surface; could not produce a live
  failure to confirm. Not a finding without that confirmation.
- **G1 `_BackendTracker.__init_subclass__` belt-and-suspenders:**
  still present (`csis/budget.py:446-463`), but the cycle-8 thesis
  no longer relies on it. The H1/H2/H3 attacks bypass it entirely.
  Removing it would simplify the code without affecting security
  posture; keeping it costs a tiny bit of code reading effort
  per cycle. Stylistic, not a finding.

---

## Recommendation to the loop

Cycle-8 was the **right call** to pivot to a wrap-site discipline —
but the pivot placed the wrap at `Daemon.__init__` while the actual
single chokepoint for every LLM call is `Coordinator.backend`. H1
(other entry points), H2 (closure mutation), and H3 (post-init
setattr) are three independent classes of bypass against a check
that is geographically misplaced. The cycle-7 recommendation said
"constrain the wrap site"; cycle-8 mostly heard "constrain the
**Daemon's** wrap site." That gap is where the three criticals live.

A robust cycle-9 would:

1. Move enforcement to `Coordinator.__init__` (the genuine
   chokepoint).
2. Replace the closure-capture with slot-frozen attributes plus a
   read-only `__setattr__`.
3. Make `Daemon.backend` / `Coordinator.backend` properties with
   setters that re-validate.
4. Replace the 20s lock-acquire ceiling with unbounded blocking
   (stop-file check inside the wait loop) OR add a write-ahead-log
   replay path for unrecorded spend.

If cycle-9 does only the first three, the system is **closed**
against the bypass primitives identified here. The fourth is an
independent reliability issue.

H1, H2, H3 are critical and live-reproducible TODAY against the
shipped cycle-8 code; H4 is high and reproducible; H5 is a
low-confidence flag for POSIX follow-up.
