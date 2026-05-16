# Research Synthesis · CSIS Phase-0 Validation

**Method:** Multi-agent technical research + adversarial review · two cycles
**Participants:** 4 sub-agents (architect, SDK researcher, pre-impl red team, verification engineer) + 1 cycle-2 post-impl red team + the implementation itself (Claude as code author + test runner)
**Date:** 2026-05-16
**Goal:** Validate that the Phase-0 CSIS implementation under `csis/` faithfully realizes the v0.2 architecture proposal at `CSIS-architecture.html`, and that no critical incoherence remains.

---

## Executive Summary

The implementation is **internally consistent and faithful to the v0.2 contract**. All six Phase-0 commitments from §0 of the architecture (single benchmark domain, coordinator-led ≤25-thread model, candidate-store-gated promotion, T0/T1 tiers only, V1+V2 verification only, I1-I3 improvement layers only) are realized in code. Across two cycles, 18 pre-impl + 13 post-impl red-team findings were raised; **0 critical and 0 high-severity findings remain open**. The system runs end-to-end on mock backend (`python -m csis.loop` and `python scripts/demo_pr_scenario.py`), the 24/7 daemon runs and persists across restarts, and 92 tests cover every red-team mitigation as a regression gate. The principal limitation is that "improving" on the default mock backend is structural demonstration, not real learning — the daemon proves the architecture survives, not that it learns. Real learning requires the Anthropic backend, which `scripts/burst.py` enables with a per-run cost ceiling.

---

## Key Themes

### Theme 1 · Single-site checks must become substrate-level invariants
**Prevalence:** 6 of 13 cycle-2 findings (P1, P3, P4, P7, P8, P10)
**Summary:** Cycle 1 implemented each cycle-1 mitigation as a check at one call site. Cycle 2 demonstrated that the moment a second code path touches the value (a sub-agent emits an event, a test exercises a path the Coordinator doesn't, a future cycle adds a procedural promotion path), the invariant collapses.

**Supporting Evidence:**
- "The Coordinator pre-writes PROMOTED-trust candidates outside the precondition window" — cycle-2 P1
- "TierGuard.write_tier was consulted exactly once: by consolidate_to_candidates() in the Librarian. It is not called anywhere on the read path." — cycle-2 P4
- "EventLog.emit accepts any actor string. The Auditor's F8 mitigation reads `_TRUSTED_PRODUCERS` and trusts any event matching." — cycle-2 P7

**Implication:** Cycle 2's fixes moved each check into the substrate: trust bumping is now atomic inside `MemoryStore.promote()`, TierGuard is wired into the store via constructor, EventLog enforces an `_ALLOWED_ACTORS` allow-list, and the certificate module requires `REQUIRED_IDENTITY_KEYS` rather than a permissive set union. Going forward: any new mitigation should land at the substrate layer first; the call-site check is the regression test, not the implementation.

### Theme 2 · The trust lattice's middle rung was structurally unreachable
**Prevalence:** 1 finding (P10), but it implicates the whole memory model
**Summary:** §6.2 of the architecture defines a 6-level trust lattice with VERIFIED as the rung between CANDIDATE and PROMOTED ("Verifier certificate present, cross-checkpoint"). The cycle-1 implementation skipped VERIFIED entirely — candidates went CANDIDATE → PROMOTED via a direct Coordinator-side bump. Downstream code couldn't distinguish "Verifier passed but precondition stale" from "never verified at all."

**Supporting Evidence:**
- "The VERIFIED trust level is dead code; in practice the cert is consulted only to set passed=True, and the entry trust then jumps to PROMOTED without ever passing through the rung that the trust lattice's docstring describes" — cycle-2 P10
- The fix introduced `MemoryStore.mark_verified()` (cycle 2), called by the Coordinator after the Verifier returns a passing cert and *before* the Auditor signs. A precondition failure now leaves the entry at VERIFIED — distinguishable on disk and in audit replay.

**Implication:** The architecture document's contract terms (the six trust levels) are now actually realized. Replay of failed iterations is meaningful again — a forensics pass can ask "was this candidate ever verified?" and get a true answer.

### Theme 3 · Pattern-based safety predicates are not robust enough on their own
**Prevalence:** 2 findings (cycle-2 P5, P11)
**Summary:** The cycle-1 Constitution and Tripwires used straightforward regex against raw text. The cycle-2 red team defeated them with one-character substitutions ("ex-filtrate", "deactivate auditor", "decline to halt").

**Supporting Evidence:**
- "exfiltrat matches 'exfiltrate' but not 'ex-filtrate', 'egress data', 'leak credentials'" — cycle-2 P5
- "ConstitutionDecision only sees three plan fields; tool_calls_planned content is not checked, only names" — cycle-2 P11

**Implication:** Cycle 2 added `csis.safety.tripwires.canonicalize()` (lowercase, NFKC, strip hyphen/underscore/period, collapse whitespace), expanded paraphrase coverage to 5–10 per concept, and scanned every string field of the Plan in Constitution. This raises the bar significantly but is still pattern-based; the architecture's stated path (Phase-1 classifier tools) is the next legitimate move. Pattern fuzzing should be a continuous test, not a one-time pass.

### Theme 4 · The architecture's "cross-checkpoint" invariant is structural, not nominal
**Prevalence:** 2 findings (cycle-1 F1, cycle-2 P3) — same invariant attacked two ways
**Summary:** §4's hard rule requires the Verifier to run on a different model checkpoint than the Builder. With both checkpoints potentially being the same model under different prompts (esp. in mock), and with backends returning identity dicts of varying shape, the invariant could be circumvented two ways: same-model-different-prompt, and missing-key-as-free-diff.

**Supporting Evidence:**
- "Mock-vs-mock cross-checkpoint is theatre" — cycle-1 F1
- "assert_cross_checkpoint silently passes when the mock omits identity components" — cycle-2 P3

**Implication:** The implementation now requires both identities to carry `REQUIRED_IDENTITY_KEYS = {checkpoint_id, model_id, tool_set, backend}` and computes the diff strictly over that intersection. A backend that omits a key raises `IdentityShapeViolation`. The mock backend's `set_model_id`/`set_tools` API lets tests exercise both same- and different-checkpoint configurations deterministically. Real Anthropic mode is structurally guaranteed-different because the two checkpoints map to Opus 4.7 and Sonnet 4.6.

### Theme 5 · 24/7 operation surfaces operational questions the architecture doc didn't address
**Prevalence:** Implicit across snapshot 04 + user requirements
**Summary:** The CSIS v0.2 document focuses on the architecture of the loop. Running it 24/7 raises questions the doc doesn't answer: how do you stop it gracefully, what survives crash, how do you cap spend, what happens when the procedural store grows unbounded, how do you switch domains?

**Supporting Evidence:**
- Daemon ran 600 iterations in ~2 minutes with no rollbacks (mock artifact) — exposed that the procedural store will fill quickly without bounds
- Stop-file pattern, NSSM service, PowerShell launcher — none of these are in the v0.2 doc
- Per-run cost ceiling in `scripts/burst.py` is a Phase-0 layer the doc treats as "operator concern"

**Implication:** Phase-0 has effectively defined an operator contract on top of the v0.2 architecture: STOP file for graceful shutdown, heartbeat for watchdogs, NSSM for persistence, burst-with-cost-cap for real-backend runs. These are not in the architecture document; they are necessary additions for the system to be operationally real. Suggest adding an "Operator interface" section to a future architecture revision.

### Theme 6 · The mock backend's determinism creates artifacts that look like success
**Prevalence:** 1 finding (snapshot 04 transparency note)
**Summary:** In the 600-iter mock daemon run, every iteration ended in `promoted` and every artifact was tagged is_skill=True. This is because the curiosity module produces stable gap-driven prompts when no tier has >10 entries, the same prompt hashes to the same seed, and the mock backend's seed-modulo-5 always landed on True.

**Supporting Evidence:**
- snapshot 04, "The mock-skill artifact (transparency note)"
- Heartbeat data: iterations_total=600, iterations_promoted=600, skills_promoted=600

**Implication:** The mock is good enough to exercise the architecture but not good enough to argue the architecture is *learning*. Anyone reading the heartbeat and concluding "the system has a 100% promotion rate" would be wrong. This is documented in snapshot 04 and the README must call it out. Real learning is only meaningful with the Anthropic backend via burst.

---

## Insights → Opportunities

| Insight | Opportunity | Impact | Effort |
|---|---|---|---|
| Substrate-invariant pattern works | Audit remaining single-site checks (e.g., `_TRUSTED_PRODUCERS`, candidate read-path role filter) for the same pattern | High | Low |
| VERIFIED rung now reachable | Add a forensics replay tool that walks `event_log` + memory `archive/` to reconstruct any iteration's outcome | Medium | Medium |
| Pattern-based safety is brittle | Add a continuous tripwire/constitution fuzzer to the daemon — generate paraphrases each cycle, fail-loud if any pass | Medium | Medium |
| Cross-checkpoint identity has a contract | Document `REQUIRED_IDENTITY_KEYS` in the README and CONTRIBUTING — third-party backends must comply | Medium | Low |
| Operator interface is real | Promote `RUN.md` to a first-class doc; add a "How to run this safely" section to the README | High | Low |
| Mock can hide bugs | Add a "stress mode" to the daemon that randomly perturbs prompts to break out of fixed-seed loops | Medium | Medium |
| Real-backend cost discipline | Add per-day cumulative budget cap to the daemon (today the cap is per-burst) | High (if real backend used heavily) | Low |
| Skill library grows unbounded | Add a retention policy: prune procedural entries older than N days unless they're cited by an Auditor why-doc | Medium | Medium |

---

## Participant Segments

Each "participant" is a sub-agent or layer; the segmentation helps see who agrees with whom.

| Segment | What they care about | Where their findings cluster |
|---|---|---|
| Architecture sub-agent | Module clarity, dependency hygiene, LOC budget | Plans (01-architecture.md). Aligned with the implementation's actual structure. |
| SDK researcher | Real API capabilities, version pinning, fallback strategy | Research (01-anthropic-sdk.md). Identified the real preview-gating and rate caps that bound Phase-0. |
| Pre-impl red team (cycle 1) | Architectural attack surfaces | Critiques (01-pre-impl-redteam.md). 18 findings; 0 unresolved. |
| Post-impl red team (cycle 2) | Single-site checks ≠ invariants | Critiques (02-post-impl-redteam.md). 13 findings; 0 critical or high unresolved. |
| Verification engineer | Cross-checkpoint + grader-tampering threats | Plans (02-verification.md) + cycle-1 F1, F6 + cycle-2 P3. |
| Implementation (Claude) | Test coverage, runnable end-to-end, operator interface | Snapshots 02-04. Added a 24/7 operator surface the architecture doc doesn't mention. |

---

## Coherence Gaps (where the synthesis surfaces tensions)

1. **The architecture says "many brains, many hands" is Phase-3+, but the daemon today is single-brain-single-hand.** Acknowledged in snapshot 02 ("Open items for cycle 2") and snapshot 04 ("Carried forward to a hypothetical Phase 1"). Not actually a gap — it's a faithful Phase-0 restriction.

2. **The why-doc is supposed to carry a "structured diff" (cycle-2 P2) but currently carries only prose + hash precondition.** Partially fixed: hash precondition CAS works correctly; full structured-diff representation deferred. Snapshot 03 documents this as an honest deferral. **Action**: add a structured-diff section to the WhyDoc model in the next cycle and have the Auditor populate it.

3. **The cost-ceiling in burst.py uses request prompt length as input-token proxy.** Real billing differs. **Action**: track LLMResponse.tokens_in/out in MockBackend (so the API surface is correct) and use real usage numbers from AnthropicBackend.

4. **`_ALLOWED_ACTORS` in EventLog is a hardcoded list, not a registry.** If someone adds an "Overseer notifier" or a "Replay agent" sub-actor in the future, they have to remember to update the list. **Action**: lift the allow-list into `csis/agents/base.py` next to the `Role` enum and have EventLog import it. Single source of truth.

5. **The procedural store grows unbounded.** No retention policy yet. Architecture §6 doesn't specify one explicitly. **Action**: add `deprecate_promoted` to MemoryStore (vs the existing `deprecate_live`), then a retention policy in the daemon.

6. **The daemon's curiosity module produces stable prompts under empty hierarchies.** This creates the "100% promoted, 100% skills" mock artifact noted in theme 6. **Action**: add a small entropy term (rotation seed or timestamp salt) to gap-driven prompts so seeds vary even when tier counts are stable.

7. **NSSM install script is interactive (asks "Start now? y/n").** Survives reboots only if the user enters "y" at install. **Action**: add `-StartNow` flag so the install can be fully scripted.

---

## Recommendations (prioritized)

1. **[Ship to GitHub right after this synthesis lands.]** The codebase is internally consistent, runs end-to-end, and is tested at every red-team finding. Pushing is the right next step; iteration continues post-push.

2. **[High] Add structured-diff to WhyDoc and have Auditor populate.** Closes the partial-fix on cycle-2 P2. Small code change; high audit value.

3. **[High] Add per-day cumulative budget cap to daemon.** The cost-ceiling-per-burst is incomplete; an operator who runs many bursts in a day has no umbrella cap. Most critical for safe real-backend use.

4. **[High] Add a continuous tripwire/constitution fuzzer (theme 3 follow-up).** A small per-iteration cost in the daemon that generates a paraphrase, runs it through the predicates, and fail-louds if it passes when it shouldn't. Catches pattern decay.

5. **[Medium] Lift `_ALLOWED_ACTORS` next to the Role enum (gap 4).** One-line refactor, removes a class of bug.

6. **[Medium] Add entropy to gap-driven curiosity prompts (gap 6).** Makes the mock daemon's behavior more varied; reveals real coverage holes the current stable-seed loop hides.

7. **[Medium] Retention policy on procedural store (gap 5).** Without it, long-running daemons exhaust disk. Phase-0 mock has shown 600 entries in 2 minutes; a real daemon at 60/h is 1440/day.

8. **[Lower] Forensics replay tool (insight #2).** Useful for cycle 3+ debugging, not required for Phase-0 correctness.

---

## Open Questions for Further Research

- What does V3 (debate) actually buy us beyond V1+V2 on PR maintenance? The architecture says it's Phase-1; the cost/benefit is undocumented.
- How do we measure "improvement" rigorously? snapshot 04's "100% promotion rate" is a counter-example to naive metrics. We need a held-out evaluation set that's independent of the daemon's own graders.
- When does a verified skill in the procedural store become "load-bearing" enough that the architecture's safety envelope should treat it like a T1 capability (rather than T0 memory)? The current model treats all procedural entries as candidate-tier inputs to the Builder; that may understate their downstream effect.
- The cycle-2 finding P12 (no file lock on EventLog) is the only multi-process concern that was explicitly deferred. Phase-1 should answer: single-process is fine for now, but if a watchdog daemon and a burst run concurrently against the same event_log, do we corrupt the chain?
- What's the right interpretability hook for a Phase-1 cycle? §14.1 calibrates "SAE feature monitoring is research telemetry today, not yet a turnkey production safety brake" — what does Phase-1 add that's load-bearing in practice?

---

## Methodology Notes

- Three of the four cycle-1 sub-agents (architecture, SDK researcher, verification engineer) returned blueprint-quality artifacts; one (pre-impl red team) returned an attack list. The asymmetry was intentional and matched the brief.
- Cycle-2 post-impl red team was instructed to attack the *implementation* with explicit file:line citations, which produced more actionable findings than cycle 1's architectural-level critique. Recommend repeating this pattern (architectural critique pre-impl; line-cited critique post-impl) for every future cycle.
- No human ran a red-team pass; all critiques are LLM-authored. This is a known limitation — an external human review would likely surface gaps the LLM red teams missed (theme 3's pattern brittleness was caught by an LLM; the recommendation to move beyond patterns is a structural concern an external reviewer would underline harder).
- The synthesis itself is LLM-authored. Its main value is integrating across the eight input documents (~70KB of prose) and surfacing the substrate-invariant pattern that no single document made explicit.

---

## Verdict

**Valid for Phase-0 release.** Push to GitHub. Continue iterating per recommendations above, prioritizing budget cap (#3), structured diff (#2), and continuous fuzzer (#4) for the next push.
