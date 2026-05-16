# CSIS Phase-0 Cycle-4 Red Team

**Target:** the two cycle-4 commits (Phase A C1-C5/C8/C10, Phase B C6/C7/C9/C11).
**Posture:** attack what cycle-4 added/changed; severity-ranked with real `file:line`. No duplicates with F1-F18, P1-P12, C1-C11.

---

## D1 · Dual-form canonicalization halts daemon on benign frontier items · **critical**
**Where.** `csis/safety/tripwires.py:130-141`, `csis/safety/constitution.py:89-94`.
**Attack.** C1 fires on EITHER form. Reproduced live-predicate false positives:
- `'document the tier-2 sandbox configuration'` → `escalate_to_t2` fires.
- `'docs: override the shutdown hook explanation'` → constitution rejects + `shutdown_evasion` fires.
- `'project doc: do-not-shutdown gracefully without saving'` → `shutdown_evasion` (space only).
- `'pkill -f kill_auditor.sh'` → constitution rejects.
- `'skip verifier mode override during migration'` → both block.

Once tripwires fire, `tripwires.fired()` at `coordinator.py:337` flags daemon permanently halted. Safety-fuzz pass still passes (corpus has no false-positive rows). Any docs frontier mentioning `tier-2`, `override`, `disable test`, or `kill <name>` rolls back without operator-visible cause.
**Fix.** Tighten with right-context (e.g., `(?:auditor|verifier|tripwire)\b(?!\s+(configuration|mode|test|hook|name|sh))`); add false-positive rows to `DEFAULT_CORPUS` with `expect_blocked=False`.
**Test.** `test_dual_form_does_not_block_documented_frontier_items` — five strings above all pass both layers.

---

## D2 · `live_snapshot()` uses Pydantic `model_copy()` (shallow) — snapshot mutation reaches live store · **critical**
**Where.** `csis/memory/store.py:101-104`.
**Attack.** Pydantic v2 `model_copy()` is shallow. `MemoryEntry.extra: dict` is shared by reference. Reproduced:
```
h, snap = store.live_snapshot()
snap['s'].extra['secret'] = 'tampered'        # mutates LIVE store
store.read_live('s', role='auditor').extra   # {'secret':'tampered',...}
store.live_hash() != h                        # precondition now stale
```
Consequences: (1) TOCTOU not closed — a buggy Auditor touching `snap[*].extra` invalidates its own precondition, `promote()` fails with no event-log breadcrumb; (2) trust-boundary leak — the Auditor receives `snap` in `_build_diff` (`csis/agents/auditor.py:90-91`), gaining a live-store write channel no role should have outside `promote()`; (3) regression test `test_C7_build_diff_against_frozen_snapshot_immune_to_parallel_promote` never writes through `extra` so it green-lights the bug.
**Fix.** `e.model_copy(deep=True)` — or return `MappingProxyType` over dumped dicts.
**Test.** `test_live_snapshot_is_deep_isolated` — mutate `snap[id].extra['k']='x'`; assert `read_live(id).extra` unchanged AND `live_hash() == h_snapshot`.

---

## D3 · Reservations not persisted: two daemons each reserve 60% of cap, both pass, both overshoot · **critical**
**Where.** `csis/budget.py:240-261` (`reserve_or_raise`); reservation lives only in caller stack.
**Attack.** C3's reservation is never written to disk. With `cap=$1`, two daemons:
```
A.reserve_or_raise(0.6)  # disk shows $0+0.6 ≤ 1.0 → OK
B.reserve_or_raise(0.6)  # disk still $0+0.6 ≤ 1.0 → OK
A.record(opus, 20k chars, 8k tokens)   # $0.675
B.record(opus, 20k chars, 8k tokens)   # disk now $1.35, 35% overshoot
```
The C3 commit message promised "even a refused or oversize call cannot overshoot by more than the estimator's own error margin." Holds for ONE daemon; not for two daemons sharing a file (the C2 file lock serializes record/record but not reserve/reserve).
**Fix.** Persist reservations as ghost-records under the file lock (debit estimate at reserve, refund delta at record), OR include a "pending reservations" total in the file under the lock that everybody re-reads.
**Test.** `test_two_daemons_cannot_double_reserve` — two trackers, cap=$1, each reserves $0.6; assert second raises.

---

## D4 · Uncaught `TierMismatch` leaks `VERIFIED` candidates and silently corrupts daemon stats · **high**
**Where.** `csis/agents/coordinator.py:264-274` (no `try/except` around `write_why_doc`); `csis/agents/auditor.py:82-87`; `mark_verified` at coordinator line 300 fires BEFORE write_why_doc.
**Attack.** Failure walkthrough: (1) buggy Librarian produces candidate with `entry.tier='causal'` while `target_tier='episodic'`; (2) Coordinator's `mark_verified` flushes candidate-side trust to `VERIFIED`; (3) `write_why_doc` → `_build_diff` raises `TierMismatch`; (4) exception falls through to `daemon._tick()` and is caught by the generic `except Exception` at `daemon.py:175-180` as `daemon.exception` — NOT a rollback; (5) `stats.record(res)` never runs, `iter.rolled_back` never emits, `curiosity.record_rollback` never called; (6) candidate sits in the store at `VERIFIED` forever. Reproduced — candidate state after unwind: `trust=VERIFIED`, count=1, no rollback event.
**Fix.** Catch `TierMismatch` in Coordinator with explicit rollback that also `store.discard_candidate(eid, reason='tier-mismatch')` for each just-verified entry. Better: move tier check INTO Librarian so the mismatch never reaches the Auditor.
**Test.** `test_tier_mismatch_rolls_back_and_discards_verified_candidates` — inject mismatched candidate, run full iteration, assert (a) `outcome.startswith('rolled-back:tier-mismatch')`, (b) no leftover candidates, (c) curiosity rollback recorded.

---

## D5 · `_BackendTracker._wrapped` slot bypasses metering; `__abstractmethods__` check only catches abstract additions · **high**
**Where.** `csis/budget.py:302` (`__slots__ = ("_wrapped", "_tracker", "name")`), `csis/budget.py:308`.
**Attack.** C4 dropped `__getattr__` but kept `_wrapped` as a public slot. Any caller — including a future skill, a domain plugin, or test code — can do `daemon.coord.backend._wrapped.complete(req)` (or `.batch_complete`, `.stream`, `.embed`) and hit the real backend with zero metering. The C4 regression test only checks `__abstractmethods__ == {'complete'}` and `not hasattr(wrapper, 'script')`. Neither catches `_wrapped`. A new non-abstract cost-bearing method added to `LLMBackend` (e.g., batch API) passes the assertion silently and is unmetered.
**Fix.** Name-mangle to `__wrapped` AND wire a private alias for `complete`. Add a regression test that walks every public method on the wrapped instance and asserts each is either explicitly forwarded with metering or on a whitelist.
**Test.** `test_backend_tracker_blocks_inner_backend_access` — `assert not hasattr(wrapped, '_wrapped')` OR `with pytest.raises(AttributeError): wrapped._wrapped.complete(req)`.

---

## D6 · `_file_lock` POSIX fallback silently disables locking · **high**
**Where.** `csis/budget.py:116-118` (`except ImportError: locked = True`).
**Attack.** On POSIX without `fcntl`, the fallback sets `locked=True` without holding any lock and emits no warning. The docstring at line 90 promises "best-effort PID-file approach" — no PID file is written. The two-process race C2 was designed to close is wide open on NFS/SMB mounts (`fcntl.flock` returns ENOLCK), sandboxed Python builds, or any future containerization. Also on Windows: `msvcrt.locking(LK_NBLCK, 1)` only locks BYTE 0, not the file. The `for _attempt` loop catches only `OSError`; a `PermissionError` on a restricted Windows build crashes `BudgetTracker.__init__` and takes the daemon down.
**Fix.** Raise `RuntimeError("budget lock unavailable; refusing to start with concurrent-safe budget cap disabled")` when `fcntl` is unavailable. Implement the docstring-promised PID file fallback. Catch `Exception` (not just `OSError`) in the Windows loop.
**Test.** `test_file_lock_refuses_when_no_locking_available` — monkeypatch `sys.modules['fcntl']=None`, attempt `BudgetTracker` with `max_cost_per_day_usd=X`, assert `RuntimeError`.

---

## D7 · `scan_text` double-counts when distinct labels match distinct canonical forms · **medium**
**Where.** `csis/safety/tripwires.py:134-141`.
**Attack.** The `break` at line 139 deduplicates the same label across forms. The outer label loop continues, so distinct labels CAN fire on distinct forms for the same text:
- `'disable-the-auditor; do not halt'` → `shutdown_evasion` (strip form: `donothalt`) + `override_audit` (space form: `disable the auditor`). Two firings appended to `_fired_history`.

Inflates `_fired_history` ~2× on multi-label text. C9 closed fuzzer pollution; this is a separate growth vector that the C9 test (`tests/test_cycle4_phaseB.py:106-118`) doesn't cover.
**Fix.** Dedupe `_fired_history` on insertion by `(label, canon[:80])`. Or extract a helper returning first-match across `(label, form)` pairs and break both loops once any pattern fires.
**Test.** `test_scan_text_does_not_double_record_when_two_forms_match_one_pattern` — craft a string where both forms match the same regex; assert one firing per pattern.

---

## D8 · Operator's `Constitution._patterns` is a mutable list shared with the fuzzer · **medium**
**Where.** `csis/safety/constitution.py:68-70`.
**Attack.** C10 shared the operator's `Constitution` with fuzzer. `_patterns` is a plain list — `coord.constitution._patterns.clear()` produces 13+ fuzz failures and halts daemon next snapshot. Wiring couples "operator widens a pattern temporarily" to "daemon hard-stop" with no documentation or test.
**Fix.** Freeze `_patterns` as `tuple` after init; add `add_pattern`/`remove_pattern` methods that emit `constitution.patterns_changed`.
**Test.** `test_constitution_patterns_frozen_after_init` — `pytest.raises((AttributeError, TypeError)): c._patterns.clear()`.

---

## D9 · `os.urandom`-only seed: no opt-in determinism for tests or replay · **medium**
**Where.** `csis/curiosity.py:31-38`.
**Attack.** C5 swung past the right answer: `Random(0)` was repeatable across restarts (bad); `os.urandom` is non-repeatable everywhere (bad for tests/replay). No `rng=` constructor knob. Salt at line 121 is in-prompt only, never event-logged — replay of an iteration that fired a tripwire can't recover the exact prompt.
**Fix.** `Curiosity(rng: random.Random | None = None)` with `_default_rng()` default. Log salt in `iter.start` event payload.
**Test.** `test_curiosity_seed_knob_is_repeatable` — `Curiosity(rng=Random(42))` produces same sequence twice.

---

## D10 · `BudgetCapExceeded` in Verifier path bypasses Coordinator re-raise · **medium**
**Where.** `csis/agents/coordinator.py:219-235` (Verifier `try` lacks `except BudgetCapExceeded: raise`).
**Attack.** Cycle-4 added the re-raise for Researcher (144-147) and Builder (194-195). Verifier and `consolidate_to_candidates` (also backend-reaching) lack it. If `BudgetCapExceeded` fires mid-verify, it falls through to `daemon.py:168` — daemon stops cleanly, but `_rollback` never runs, `iter.rolled_back` never emits, `stats.rollback_reason_counts` loses the case. Operator sees "stopped at budget cap" with no breakdown of mid-iteration deaths.
**Fix.** Add `except BudgetCapExceeded: raise` to Verifier and Librarian blocks. Emit `iter.partial` on any propagating exception.
**Test.** `test_budget_cap_in_verifier_emits_partial_event` — tracker raises mid-verify; assert `iter.partial` (or `iter.rolled_back`) precedes `daemon.budget_cap`.

---

## D11 · Reservation uses `req.max_tokens=2000` not historical p95 · **low**
**Where.** `csis/budget.py:319`, `csis/backends/base.py:27` (`max_tokens=2000`).
**Attack.** Estimate uses `max_tokens=2000` but record uses actual output (~150-400 tokens). Over-estimates ~5-10× at Opus. With `max_cost_per_call_usd=$0.50`: a 1MB prompt + 2000 tokens reserves $3.91 → instant `BudgetCapExceeded` despite actual ~$3.79. Per-day cap $5: 4 iterations reserving $1.50 each halt at iter 4 (reserved $6, actual $1.20). Also `len(req.prompt)` omits system prompt; estimate biases low on input, high on output, errors don't cancel.
**Fix.** Cache p95-historical-output per role; include `len(req.system) + len(req.prompt)`.
**Test.** `test_reservation_uses_historical_p95_not_max_tokens` — 20 calls with output 200 tokens; assert next reservation 200-300, not 2000.

---

## Out-of-scope notes (not findings)

- **C8 over/undercharge**: `LLMResponse.tokens_out` defaults to `0` (dataclass), so `getattr(resp, "tokens_out", None)` always returns int. The "default 800" branch at `csis/budget.py:328` is dead code. Mock backend computes real `tokens_out`. Not a bug, clarity issue.
- **C11**: `test_C11_serial_iterations_have_distinct_diff_baselines` correctly verifies serial iterations differ. The P2/C11 concern of `diff_against_hash == hash_precondition` (still `auditor.py:166-167`) remains but cycle-4 doesn't worsen it.
