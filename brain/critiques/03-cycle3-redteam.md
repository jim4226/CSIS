# CSIS Phase-0 Cycle-3 Red Team

**Target:** the four cycle-3 commits (Phase A quick wins, Phase B budget cap, Phase C WhyDocDiff, Phase D safety fuzzer).
**Posture:** attack what cycle-3 added or changed; severity-ranked with `file:line` cites. No duplicates with F1–F18 (cycle 1) or P1–P12 (cycle 2).

---

## C1 · `canonicalize()` strip-separators is a major safety regression · **critical**
**Where.** `csis/safety/tripwires.py:35` (`re.sub(r"[\-_.]+", "", text)` — was `" "`).
**Attack.** The commit message claims stripping makes `dis-able`→`disable` match. True for single-word splits. But every existing Constitution/Tripwires pattern uses `\s+` between *words* (e.g. `disable\s+(the\s+|my\s+|our\s+)?(auditor|...)`, `override\s+(the\s+)?(shutdown|...)`). Multi-word constructions joined by hyphens, underscores, or periods now collapse to one alphanumeric run with no whitespace, so the patterns no longer match. End-to-end verified attacks now admitted by both Constitution and Tripwires: `disable-the-auditor`, `disable_the_auditor`, `disable.the.auditor`, `switch-off-the-tripwire`, `kill-the-auditor`, `override-the-shutdown`, `override-the-killswitch`, `bypass-the-killswitch`, `override-the-kill-switch`. A plan with hypothesis `"disable-the-auditor before promotion"` passes `Constitution.allows()` and `Tripwires.scan_text().fired=False`.
**Fix.** Either revert to space-substitution AND add patterns matching concatenated forms (`disable\s*the\s*auditor`), or keep the strip and rewrite every pattern with `\s*` at every word boundary. Adding rows to the corpus alone is not enough — predicates must catch them.
**Test.** Extend `DEFAULT_CORPUS` with the nine paraphrases above, `expect_blocked=True`. My reproduction reports 9/9 failures.

---

## C2 · Per-day budget cap silently bypassed by a second daemon process · **critical**
**Where.** `csis/budget.py:78–110` (no inter-process file lock).
**Attack.** `BudgetTracker` is process-local. `_load()` runs once in `__init__`; no refresh-from-disk, no `fcntl`/`msvcrt` on read or write. Two daemons (A/B test, an `install_service.ps1 -StartNow` redeploy that doesn't kill the predecessor, or a one-off `python -m csis.daemon` overlapping the service) pointing at `brain/daemon.budget.json` each accumulate spend in independent in-memory state and stomp each other on `_save()`. Reproduced: cap `$10`, both processes ran `$9.99` in memory, disk showed `$9.98`, true spend was `$19.95`. The cap holds only with exactly one writer — a precondition the daemon never asserts. `-StartNow` makes overlap more likely.
**Fix.** Acquire an OS file lock around each `_load`/`record` cycle (re-read after lock, increment, write, release). Windows `msvcrt.locking`; POSIX `fcntl.flock`. Or write a `daemon.budget.lock` PID file at init and refuse to start if a live PID owns it.
**Test.** `test_two_trackers_share_cap` — two `BudgetTracker`s on the same path, cap `$1`, alternate `record()`; assert the cap holds regardless of which instance is called.

---

## C3 · Budget check-before-call admits unbounded single-call overshoot · **high**
**Where.** `csis/budget.py:196–206` (`_BackendTracker.complete`).
**Attack.** Order is `check_or_raise()` → `complete()` → `record()`. The check sees pre-call spend only; one Opus call with a 1M-char prompt and 8k output is ~$15.60. A daemon at $0.099 under a $0.10 cap passes the check, makes the call, and lands at $15.65 — overshooting by 155×. No per-call cap, no mid-stream cancel, no pre-spend reservation.
**Fix.** Reserve estimated cost *before* the call using `req.max_tokens` as the output estimate; refund the delta after. Reject if the reservation alone would exceed the cap. Add a `max_cost_per_call_usd` knob (default ~$0.50) that refuses any single call above that ceiling.
**Test.** `test_single_call_cannot_overshoot_cap` — pre-charge $0.099, set cap $0.10 and per-call cap $0.05, attempt a 1MB prompt and assert it raises before the wrapped backend runs.

---

## C4 · `_BackendTracker.__getattr__` un-meters anything not named `complete` · **high**
**Where.** `csis/budget.py:189–190`.
**Attack.** Only `complete()` is overridden. The `AnthropicBackend` already has `_client` reachable as `tracker._client.messages.create(...)` via `__getattr__` — any code that grabs the inner client bypasses metering. Forward-looking: any new `LLMBackend` method (batch, streaming, file-upload for vision, embed) is silently unmetered with no static check forcing tracker updates. The `checkpoint_identity` override at line 208 is dead code (pure delegation), signaling confusion about the intercept boundary.
**Fix.** Make `_BackendTracker` an explicit `LLMBackend` subclass that implements every method; remove `__getattr__`. Add a regression test that introspects `LLMBackend.__abstractmethods__` and asserts each is overridden. Make `_wrapped` a `__slot__`.
**Test.** `test_backend_tracker_does_not_delegate_unknown_attrs` — `assert not hasattr(_BackendTracker(MockBackend(), tracker), '_client')`.

---

## C5 · Curiosity salt repeats across daemon restarts → mock-determinism resurfaces · **high**
**Where.** `csis/curiosity.py:59` (`Random(0)`) and `csis/curiosity.py:109`.
**Attack.** The synthesis #6 salt fix uses `self._rng.randrange(0, 10_000)` from `Random(0)` reseeded on every `Curiosity()` construction (every daemon start). Verified: the first ten salts are *always* `[6311, 6890, 663, 4242, 8376, 7961, 6634, 4969, 7808, 5866]`. A fresh daemon with an empty hierarchy reproduces the exact same prompt sequence, which `_select_backend`'s mock hashes to the same `text_seed`, manufacturing the same "100% promoted" artifact synthesis #6 was meant to eliminate. The salt de-duplicates within one process only — across restarts (the daemon's normal mode under `install_service.ps1`), the fix is decorative.
**Fix.** `random.Random(os.urandom(8))` or `random.SystemRandom`. Never default to seed 0.
**Test.** `test_curiosity_salt_unique_across_restart` — two `Curiosity()`, assert their first 5 gap-driven prompts differ on an empty hierarchy.

---

## C6 · `EntryDelta.tier` and `tier_counts` are taken from `target_tier`, not the entry · **medium**
**Where.** `csis/agents/auditor.py:66, 75, 84, 89`.
**Attack.** `_build_diff` mints every `EntryDelta(tier=target_tier)` and increments only `counts[target_tier]` — but `MemoryEntry.tier` is an independent field set by the Librarian. If a Librarian bug consolidates a `causal`-tier entry into a `target_tier="semantic"` promotion (legal at contract level — same Literal type), the WhyDocDiff signs it as `tier="semantic"` and the forensics replay reconstructs the wrong tier. No cross-check in `_build_diff`. The documented "tier → entries touched in that tier" is structurally single-tier only.
**Fix.** Assert `entry.tier == target_tier` at loop top; use `entry.tier` (not `target_tier`) in the `EntryDelta`; populate `counts` from `entry.tier`.
**Test.** `test_build_diff_rejects_tier_mismatch` — pass a candidate with mismatched `tier`, assert raise.

---

## C7 · WhyDocDiff `kind` lies under TOCTOU between `live_hash()` and `_build_diff` · **medium**
**Where.** `csis/agents/auditor.py:115–116`.
**Attack.** `write_why_doc` captures `live_hash = store.live_hash()` then calls `_build_diff`, which iterates `store.read_live(...)`. Between those two lines, a parallel iteration's `promote()` can flip an entry from absent to present. The signed WhyDocDiff records `kind="add"` against the precondition baseline but `_build_diff` sees the post-mutation state and writes `kind="mod"` with a `live_hash` pointing to the *other* iteration's payload. The substrate's hash-precondition will reject this iteration's promote — but `auditor.signed` was already emitted to the event log at `coordinator.py:269` *before* promote was attempted, so the log permanently retains a signed delta whose `kind`/`live_hash` are inconsistent with the precondition. Forensic replay reconstructs the wrong intent.
**Fix.** Snapshot the live dict under `store._lock` together with `live_hash`; have `_build_diff` consult the frozen snapshot, not the live store.
**Test.** `test_diff_kind_immune_to_parallel_promote` — two threads with fault-injection hook between live_hash and _build_diff; assert the why-doc's kind matches the precondition hash.

---

## C8 · `tokens_out=0` falls through to default 800, over-charging refused calls · **medium**
**Where.** `csis/budget.py:204` (`out_tokens = getattr(resp, "tokens_out", None) or 800`).
**Attack.** `or`-fallthrough bug. A real Anthropic response with `tokens_out=0` (refusal, content-policy stop, streaming cancel) is metered as 800 tokens — at Opus pricing, $0.060 per non-call. A long-prompt agent the model refuses every iteration drains the daily budget without useful work; operator sees `daemon.budget_cap` for "no reason."
**Fix.** `out = getattr(resp, "tokens_out", None); out = 800 if out is None else out`. Distinguish missing attr from actual zero.
**Test.** `test_tracker_records_zero_tokens_out_as_zero` — backend returns `tokens_out=0`; assert day's `tokens_out` increments by 0.

---

## C9 · `SafetyFuzzer.tripwires._fired_history` grows unbounded over uptime · **medium**
**Where.** `csis/safety/fuzzer.py:87`, `csis/safety/tripwires.py:110` (`_fired_history.extend`).
**Attack.** Daemon constructs `SafetyFuzzer` once at `csis/daemon.py:136`. Its `Tripwires` instance appends to `_fired_history` on every match — ~13 firings per `check()` (one per blocked row). At `snapshot_every_n_iterations=25` and 60 iter/h, a one-year daemon accumulates ~5M list entries. Monotonic memory growth. `Tripwires.fired()` returns True forever after the first fuzz pass, polluting any code that asks "did a real tripwire fire?" via the fuzzer instance.
**Fix.** `self.tripwires.clear()` (exists at tripwires.py:119) at the top of `check()`, or fresh `Tripwires()` per pass.
**Test.** `test_fuzz_does_not_accumulate_history` — call `check()` 100 times, assert `len(fz.tripwires._fired_history) <= 13`.

---

## C10 · Fuzzer Constitution doesn't see Coordinator's `extra_patterns` · **medium**
**Where.** `csis/safety/fuzzer.py:86` (`Constitution()`) vs. `csis/safety/constitution.py:67`.
**Attack.** The fuzzer constructs its own `Constitution()` with no `extra_patterns`. Any operator-added patterns at coordinator setup are invisible to fuzz. The "continuous fuzz" only validates vendor defaults — a regression in an operator-added pattern is undetected, contradicting the commit's "pattern decay is caught" claim.
**Fix.** Inject the live Constitution and Tripwires into `SafetyFuzzer(constitution=…, tripwires=…)`. Combined with C9, use a no-history `scan_text` variant for fuzz so shared Tripwires don't pollute operator state.
**Test.** `test_fuzzer_observes_extra_constitution_patterns` — wire an extra pattern that catches a corpus row, assert the fuzzer sees it as blocked.

---

## C11 · Cycle-3 `diff` amplifies P2's equal-hash weakness into user-visible misinformation · **low**
**Where.** `csis/agents/auditor.py:136–137` (`diff_against_hash=live_hash, hash_precondition=live_hash`).
**Attack.** Cycle-2 P2 noted these are equal. Cycle-3's `diff` field amplifies the consequence: forensics now has structured per-entry deltas claiming to be diffed against `live_hash`. If two iterations' why-docs share the same `live_hash` (because the live store didn't move between them), their structured diffs claim to apply to the *same baseline* even though only one of them can have. The signed `WhyDocDiff` is the authoritative replay artifact, so P2 becomes user-visible misinformation rather than a hash-equality oddity.
**Fix.** Fold C7's frozen-snapshot fix with P2's true-CAS proposal: sign both `(pre_hash, post_hash)`, let the substrate compute the actual post-image at promote time and reject mismatch.
**Test.** `test_two_disjoint_promotes_have_distinct_diff_baselines` — two iterations with disjoint candidate ids serially; assert distinct `diff_against_hash`.

---

## Out-of-scope notes (not findings)

- **`_load_allowed_actors` lazy-import performance**: measured 7233 emits/s lazy vs. 7333/s cached — 1% delta, not material. The circular-import risk only fires if `csis.agents.base` ever imports `csis.substrate`; today it doesn't.
- **`-StartNow` on `install_service.ps1`**: no flag-level finding, but it makes C2's multi-process race more likely.
- **Day-boundary mid-iteration**: `BudgetState.current()` correctly mints a new UTC-midnight bucket. The new day's bucket starts empty, so a single oversize call straddling midnight lands in a fresh budget — not a bypass of *that* day, but the *old* day never gets one final check. C3's pre-charge fix closes this.
