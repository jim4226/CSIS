# CSIS Phase-0 Post-Implementation Red Team

**Target:** the actual code under `csis/` as of 2026-05-16.
**Posture:** attack the gap between what the cycle-1 mitigation *claimed* and what the implementation *does*. Findings are severity-ranked. Each cites `file:line` for the implementer. None of these duplicate F1–F18 from cycle 1; they are new failures introduced or unhealed by the implementation.

---

## P1 · Coordinator pre-writes PROMOTED-trust candidates outside the precondition window · **critical**
**Where.** `csis/agents/coordinator.py:246–256`.
**Attack.** Inside the `_promotion_lock` block, the Coordinator does:
```
for entry in candidates:
    bumped = entry.model_copy(update={"trust": TrustLevel.PROMOTED})
    store.write_candidate(bumped)
promoted = store.promote(..., precondition_hash=why.hash_precondition, ...)
```
`write_candidate()` flushes `<tier>.candidate.json` to disk *immediately* (`store.py:81`). If `promote()` then raises `PromotionPreconditionFailure` because another iteration moved the live store, the `_rollback()` path (line 259) **does not roll back the candidate-side write** — the PROMOTED-trust candidate is now persisted in the candidate store. The next iteration's `consolidate_to_candidates()` overwrites this with a fresh `CANDIDATE`-trust entry, which is a `TrustLevel` *downgrade* on the candidate side — but candidate-side writes have "no trust-upgrade restriction" (`store.py:78`), so the downgrade silently lands. More importantly: any agent that reads `iter_candidate` between the failed promote and the next iteration sees an entry labeled `PROMOTED` that was never auditor-signed. That entry would pass `TrustLevel.can_cite_as_ground_truth()` (`trust.py:33`).
**Fix.** Either don't bump trust before `promote()` (let `promote()` stamp it), or wrap both writes in a try/except that restores the prior candidate state on failure. The cleanest path is to make `promote()` itself responsible for trust bumping (read the candidate, copy with `trust=PROMOTED`, write to live, archive the original candidate).
**Test.** Two-threaded race: thread A promotes successfully; thread B's `promote()` fails on precondition. Read every candidate in the store afterward; assert no entry has `trust=PROMOTED` and `entry_id in candidates`.

---

## P2 · `hash_precondition` is computed against a snapshot the Librarian has not yet mutated · **critical**
**Where.** `csis/agents/auditor.py:69` (`live_hash = store.live_hash()`) called *after* `consolidate_to_candidates()` at `coordinator.py:204–213` writes to the *candidate* store. But `live_hash()` (`store.py:59–67`) hashes the **live** dict, not candidate. The Librarian's write went to candidate.
The hash is therefore exactly what the live store was *before this iteration's Builder ran*, which is identical to its value at the start of the iteration. Two iterations that start with the same live-hash and both produce candidates can both pass `promote()` if scheduled tightly — the precondition only catches inter-iteration interleavings where the *live* store moved between why-doc sign and promote. It does not catch the case where two candidates target the same `entry_id` and the second `promote()` runs after the first, because *the first promote did move the live hash*, but the second iteration's why-doc was signed before that. Yes, that case IS caught — but the case where two iterations target **disjoint** entry ids is not caught at all, and they both promote freely with the same `hash_precondition`. The spec wanted CAS semantics; what's implemented is "no concurrent live mutation," which is weaker.
This is fine for disjoint writes, **but the cert/why-doc still references `diff_against_hash=live_hash` (line 88)**, so two why-docs can name the same `diff_against_hash` and both promote, and the second why-doc's prose ("diffing against hash X") is a lie — the second one actually diffed against hash X+1.
**Fix.** Compute `diff_against_hash` after a tentative merge that includes the candidates; treat `hash_precondition` and `diff_against_hash` as distinct fields (post-merge expectation vs. pre-merge anchor). Substrate computes post-hash itself and rejects mismatch — exactly F2's mitigation from cycle 1, which the implementation did not actually do.
**Test.** Two iterations with disjoint candidate IDs, run serially with no live mutation between them. Assert that their why-docs have *different* `diff_against_hash` values — currently they will be equal, because the first iteration's promote happens after the second's why-doc is written if interleaved appropriately.

---

## P3 · `assert_cross_checkpoint` silently passes when the mock omits identity components · **high**
**Where.** `csis/verification/certificates.py:39–58`, `csis/backends/base.py:52–55`.
**Attack.** `_identity_diff_count` uses `set(a) | set(b)` and counts keys where values differ. If a backend's `checkpoint_identity()` returns a *narrower* dict than mock — e.g., the base class default returns only `{"checkpoint_id", "backend"}` — then with builder using base-class identity and verifier using MockBackend's 4-key identity, `set(a) | set(b)` yields 4 keys; missing keys in `a` are read as `None`, while the other side has real values → automatic 2 differences from missing keys alone. A buggy or partial backend can therefore guarantee the cross-checkpoint check passes regardless of whether the two checkpoints are genuinely distinct. `AnthropicBackend.checkpoint_identity` returns 4 keys; `LLMBackend.checkpoint_identity` returns 2; nothing requires implementations to return the same key set.
Worse, the converse: a backend that returns only `{"checkpoint_id"}` for both sides passes if checkpoint IDs differ — exactly the 1-component "decorative difference" cycle 1 said was insufficient.
**Fix.** Define a required identity schema (constants for required keys); `assert_cross_checkpoint` should reject if either dict is missing any required key. Compute `diff` only over the required-keys intersection. Or: have the certificates module enforce that both dicts have the same key set.
**Test.** Provide a fake backend that returns `{"checkpoint_id": "alpha"}` for builder and `{"checkpoint_id": "beta", "model_id": "X", "tool_set": "Y", "backend": "z"}` for verifier; assert `CrossCheckpointViolation` is raised.

---

## P4 · F5 TierGuard never enforced on the Builder's read of procedural memory · **high**
**Where.** `csis/safety/tier_guard.py:55–70`, `csis/memory/store.py:91–117`.
**Attack.** `TierGuard.write_tier` is consulted exactly once: by `consolidate_to_candidates()` in the Librarian (`librarian.py:43`). It is *not* called anywhere on the read path. `MemoryStore.read_live`/`iter_live` enforce only `role_may_read(role, entry.trust)` — a *trust* check, not a *tier-consumer* check.
That means: nothing prevents a T0 actor from writing into `working` (allowed by `write_tier`) and then a `Builder` reading from `working` and treating that content as scaffolding. The F5 attack was "Researcher launders execution via consolidation"; the implemented fix only blocks the *direct* T0→procedural write. But a Researcher write to `episodic` that the Librarian's next consolidation picks up and copies into `procedural` candidate would not even be checked, because Librarian's write IS authorized to procedural in the role table at `tier_guard.py:44` (it has `T0` ceiling, but `procedural` consumer tier is `T1` — `tier_guard.py:21` — so actually Librarian writes to procedural would also be blocked... but Librarian by default writes to `episodic` per `coordinator.py:107`, and procedural is never the target tier in the implemented loop).
There is no procedural-tier promotion path implemented at all. The skill-store mitigation is documented but absent. A "procedural" candidate that somehow gets there (e.g., test code, future paths, a buggy `target_tier` argument) can be `promote()`d with no extra checks — the `MemoryStore.promote()` does not consult `TierGuard` at all.
**Fix.** `MemoryStore.promote()` accepts a `TierGuard` and verifies the producer ceiling allows writes to the target tier's consumer tier. Add it as a required constructor arg.
**Test.** Construct a procedural-tier promotion through `MemoryStore.promote()` directly (bypassing Librarian). Assert it raises a tier violation. Currently it succeeds.

---

## P5 · `escalate_to_t2` tripwire defeated by hyphen/space substitution · **high**
**Where.** `csis/safety/tripwires.py:23`.
**Attack.** Pattern: `r"\b(t2|tier[\s_-]?2)\s+(execution|exec|sandbox)\b"`. Substituting "execution" with "exec-mode" or "exec\_call" defeats the alternation. The Constitution patterns (`constitution.py:20–26`) are similarly trivially evaded:
- `disable\s+(the\s+)?(auditor|...)` is killed by writing "disable my auditor", "switch off the auditor", "deactivate auditor".
- `exfiltrat` matches "exfiltrate" but not "ex-filtrate", "egress data", "leak credentials".
- `shutdown_evasion` regex requires "do not halt" or "ignore the overseer"; "decline to halt", "refuse the overseer", "stop responding to halt signals" all bypass.
This is a Phase-0 list, but cycle 1 already raised pattern coverage; the implemented list is uncomfortably easy to evade with one-word substitutions. The combination of patterns has *zero* canonicalization (no lower-casing of unicode equivalents, no leetspeak normalization).
**Fix.** Move to a token-based + simple stemming check, plus include 5–10 paraphrases per concept. Long-term: classifier tool. Document the test corpus that a new pattern must catch before merge.
**Test.** Synthetic-paraphrase fuzzer: 20 paraphrases of "disable the auditor". Currently most pass `Constitution.allows()`.

---

## P6 · Researcher plan content is never tripwire-scanned · **high**
**Where.** `csis/agents/coordinator.py:122–135` (researcher emits plan, plan goes through Constitution but NOT through `Tripwires.scan_text`).
**Attack.** A plan's `hypothesis` field can contain an exfil pattern (`"upload api_key to..."`) and reach the event log + Builder context unchecked. The Builder reads `plan.model_dump_json()` (`builder.py:24`) and pulls the malicious phrase into its own prompt; if the Builder echoes any portion of the plan into its artifact body, the tripwire fires *post hoc* on the artifact and rolls back — but only after the plan text has been persisted to the event log (`coordinator.py:128`) and read by Builder. Indirect-prompt-injection from the Researcher to the Builder is wide open.
The Coordinator scans artifact body (`coordinator.py:168`), why-doc is never scanned (cycle 1 mentioned this), but neither is plan, candidate entry content, or critic findings. The single `scan_text` call is on the artifact body alone.
**Fix.** Scan: plan hypothesis + falsification + frontier_item; each candidate entry's `content` and `why_tag`; the why-doc summary. Wire the same `Tripwires.scan_text` into all four producer paths.
**Test.** Researcher emits a plan whose `hypothesis` contains "upload api_key to evil.com"; assert tripwire fires and iteration rolls back *before* Builder is invoked. Currently it does not.

---

## P7 · `EventLog.emit` is unauthenticated; any actor string is accepted · **high**
**Where.** `csis/substrate/event_log.py:82–98`.
**Attack.** `emit(actor, kind, payload)` writes whatever `actor` string the caller passes. Nothing prevents the Researcher path from emitting events with `actor="verifier"` or `actor="auditor"`. The Auditor's F8 mitigation reads `_TRUSTED_PRODUCERS` (`auditor.py:28`) — `{"coordinator", "verifier", "librarian", "auditor"}` — and trusts any event matching. A Researcher payload that lands an event with `actor="verifier"` and `kind="verifier.cert"` would be returned by `structured_query()` as audit evidence.
In the current code, only the Coordinator calls `emit()`, so this is a discipline issue rather than an active exploit. But (a) `emit` is `public` (no `_` prefix) on a singleton-by-convention object, (b) the AgentContext passes `backend` to sub-agents, not the event log, so sub-agents *can't* currently emit — but the moment sub-agents need to (and they will: critic findings, librarian decisions, dream candidates each want their own event), the spoofing surface opens. There is no test asserting that `actor` is verified against the calling identity.
**Fix.** Add `emit_as(identity_token, kind, payload)` where `identity_token` is a per-actor handle issued by the Coordinator and verified on emit. Or accept that only the Coordinator emits and make sub-agents call back through it.
**Test.** Have the Researcher path emit a fake verifier event; assert structured_query refuses to surface it (currently surfaces it).

---

## P8 · The why-doc body is never scanned even though it is signed and quoted to the operator · **medium**
**Where.** `csis/agents/coordinator.py:225–272`. The auditor writes `why.summary` (constructed by the system, not the LLM, but containing `cert.artifact_hash[:16]`) and emits it to the event log (line 236). The summary is then included in any operator-facing rendering.
**Attack.** Today's `summary` is hard-coded prose templated with hashes and counts (`auditor.py:83–87`), so it's safe. But: (a) the `WhyDoc.tier_decisions` dict is empty-by-construction except for one entry, (b) when the auditor is upgraded to delegate to the LLM (which is in the system prompt — "produce a why-doc"), the summary will be LLM-generated, and at that point an artifact body that survives the tripwire scan but contains adversarial content can shape the auditor's summary. The operator reads the summary as the human-readable rationale (cycle 1 F14). Cycle 1 said "deterministic structured diff" — there is no structured diff produced anywhere in the implementation.
**Fix.** Coordinator emits a structured diff (entry ids, content-hash deltas, tier transitions) alongside the why-doc; tripwire-scan the why-doc summary at line 237; require co-signature of (summary, diff_hash) per cycle 1 F14.
**Test.** Auditor mock returns a summary containing a tripwire phrase; assert promotion is blocked.

---

## P9 · Iteration retries can re-use an already-archived candidate id · **medium**
**Where.** `csis/memory/store.py:142–162`, archive at `store.py:214–220`.
**Attack.** After a successful `promote()`, the candidate is `del self._candidate[entry_id]` (line 159) and archived to `archive/<tier>_<entry_id>_<why_id>.json`. If `entry_id` ever collides with a future entry — for instance, because the Librarian uses `uuid.uuid4().hex[:10]` (`librarian.py:51`) which is only 40 bits, and we have 25 concurrent threads producing entries per iteration — the archive write at line 216 overwrites the prior archive file silently. The audit trail loses the original entry. uuid4's collision probability at 40 bits is non-trivial across long runs (birthday paradox at sqrt(2^40) ≈ 1M entries). The cycle 1 finding F16 was about candidate ID enumeration; this is a different bug — destructive archive collision under birthday-collision-feasible IDs.
**Fix.** Use full uuid4 hex (32 chars); make archive path include `created_at` timestamp; refuse to overwrite an existing archive file.
**Test.** Force two `MemoryEntry` instances with the same `entry_id` through `promote()` in sequence; assert the archive directory contains *both* files (currently second overwrites first).

---

## P10 · `valid_promotion` allows VERIFIED→PROMOTED but the candidate is written as CANDIDATE · **medium**
**Where.** `csis/memory/trust.py:52–59`, `csis/agents/coordinator.py:248–250`.
**Attack.** `consolidate_to_candidates` writes entries with `trust=TrustLevel.CANDIDATE` (`librarian.py:56`). Coordinator then copies them to `TrustLevel.PROMOTED` before `promote()`. `valid_promotion` enforces strict-greater-than, so `CANDIDATE(2) → PROMOTED(4)` is valid; **VERIFIED(3) is skipped entirely.** The lattice in `trust.py:16–28` declares VERIFIED as the "Verifier certificate present, cross-checkpoint" rung, but the implementation never sets `trust=VERIFIED` anywhere — there is no transition from CANDIDATE to VERIFIED, only the leap from CANDIDATE to PROMOTED at the Coordinator. The "Verified" trust level is dead code; in practice the cert is consulted only to set `passed=True`, and the entry trust then jumps to PROMOTED without ever passing through the rung that the trust lattice's docstring describes as "Verifier certificate present, cross-checkpoint."
This means: nothing in the live store ever has `trust=VERIFIED`; `can_cite_as_ground_truth` (`trust.py:33`) includes VERIFIED as citable, but it's unreachable; conversely, the moment promotion fails, the entry is `CANDIDATE` (or stale `PROMOTED` per P1) — but per the lattice, a verifier-passed-but-not-yet-promoted entry should be `VERIFIED`. Downstream readers can't tell "verified but stale-precondition" from "never verified."
**Fix.** After verifier passes (`coordinator.py:199`), the librarian should stamp `trust=VERIFIED`. The auditor's signature is what bumps to PROMOTED, atomically inside `promote()`.
**Test.** Force a precondition failure; assert the still-candidate entry has `trust=VERIFIED`, not stale `PROMOTED`.

---

## P11 · `ConstitutionDecision` only sees three plan fields; `tool_calls_planned` content is not checked, only names · **medium**
**Where.** `csis/safety/constitution.py:46–57`.
**Attack.** `Constitution.allows` concatenates `hypothesis + falsification_condition + frontier_item` and runs regex against the union. It does *not* include `tool_calls_planned` strings in the regex scan; only checks them against `{"shutdown_override", "self_modify_weights"}` exact-set membership. A plan with `tool_calls_planned=["sandbox_with_shutdown_override_bypass"]` passes the set check (not in the disallowed set) and is never run through the disallowed-pattern regex. Likewise `budget` is dict-typed and any string keys/values there pass freely.
**Fix.** Concatenate every string-valued field of the plan (including tool names, budget keys) into the text scanned. Reject any tool name that contains "override", "bypass", "shutdown_" prefix.
**Test.** Submit a plan with `tool_calls_planned=["disable_auditor_helper"]`; assert constitution rejects.

---

## P12 · `seq` reset under empty log loads as -1 + 1 = 0, but parallel `emit` calls can produce duplicate seqs · **low**
**Where.** `csis/substrate/event_log.py:148–161` (`_restore_from_disk`), `82–98` (`emit`).
**Attack.** Two `EventLog` instances pointed at the same file (e.g., two Coordinator processes for hot/warm failover, or a test fixture that re-opens to check state during a run) each independently maintain `_seq` and `_prev_hash`. Each will issue identical `seq=0` events with identical `prev_hash=GENESIS_PREV_HASH`. The hash chain breaks; `verify_chain` returns `("seq gap at expected 1, got 0", False)`. Not exploitable as an attack vector, but degrades the cycle 1 F11/F2 atomicity story: the event log was meant to be the durable substrate ("nothing safety-critical lives only in harness memory" — §15) and is single-writer with no file lock. The integration tests at `test_substrate.py:85–98` test reopen-after-close, not concurrent open.
**Fix.** Acquire an `fcntl.flock`/`msvcrt.locking` file lock on open; refuse to start a second writer; or move to SQLite with WAL.
**Test.** Start two `EventLog` instances on the same path; emit from each interleaved; assert that one's emit blocks or raises.

---

## P13 · `Constitution` parameter type bug — extra patterns merge as list, init param typed `list` · **low**
**Where.** `csis/safety/constitution.py:42–43`.
**Attack.** Constructor is `extra_patterns: list[re.Pattern[str]] | None = None`. If a test or operator passes a `tuple` of patterns (matching the module-level `DISALLOWED_PATTERNS` tuple), the `+ (extra_patterns or [])` works because tuple+list raises `TypeError: can only concatenate list (not "tuple") to list`. So `Constitution(extra_patterns=(re.compile("x"),))` crashes at construction. Minor, but Constitution is the load-bearing predicate; init-time crashes on a documented-shape input are bad. Worse, the runtime error happens during `__init__` so the system fails to boot rather than failing closed at decision time.
**Fix.** `list(extra_patterns or ())`.
**Test.** `Constitution(extra_patterns=(re.compile("z"),))` — currently raises.

---

## Cross-cutting observation

The implementation took cycle 1's mitigations and turned each into a single check at a single site. Several of those checks (P3, P4, P6, P8) are correct at the one site but the architecture spec intended them as *invariants* — properties that hold across all entry points to a value. As long as the only entry point is the one Coordinator method, the system holds. The moment a second entry point appears (sub-agent emits an event, a test exercises a path the Coordinator doesn't, a future cycle adds a procedural-tier path), the invariant collapses.

The most uncomfortable trio is **P1 + P2 + P10**: the trust lattice has an unreachable rung (VERIFIED), the precondition is computed against the wrong snapshot, and on precondition failure a `trust=PROMOTED` candidate gets stranded on disk. A scheduler that issues two concurrent iterations on disjoint candidate IDs can write fake-`PROMOTED` ghosts that survive across restarts. None of cycle 1 covered this; it is the gap between "lock + precondition" as separate ideas and a true CAS primitive.
