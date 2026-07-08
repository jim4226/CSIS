# 03 — Dual-use knowledge compartmentalization (GRAM) vs. CSIS's call-site tier guard

**Date:** 2026-07-08 · **Scope:** does Anthropic/AE Studio's GRAM technique change anything about `csis/safety/tier_guard.py`?

**Source:** [Anthropic Alignment research — "An off switch for dual use knowledge in AI models"](https://www.anthropic.com/research/off-switch-dual-use), published 2026-07-08. Theme 3 (constitutional / safety primitives — capability tiers).

---

## 1. What GRAM does

GRAM (Gradient-Routed Auxiliary Modules) is a training method, not a runtime API. It adds extra neurons organized into per-topic modules at every transformer layer. During training, the base model can *use* its general knowledge to predict dual-use text (virology, cybersecurity, etc.), but only the matching auxiliary module is allowed to *learn* from it — general weights never absorb the dual-use signal. The modules are deletable post-training, so a single training run can ship as many differently-capable variants as there are modules ("sixteen different ways" from one run, per the source). The authors are explicit this is early research, not shipped in production Claude models.

## 2. Why this doesn't touch CSIS's tier guard today

`TierGuard` (`csis/safety/tier_guard.py`) and the tripwire layer (`csis/safety/tripwires.py`) both operate at the **call-site / prompt layer** — they gate what a role is *authorized to request* (`CapabilityTier` ceiling per role, `TIER_MAP` per memory tier) and pattern-match on *text already produced*. GRAM operates one layer down, inside the model's weights, before any call-site check could run. A T1 Builder calling a GRAM-trained model with the dual-use module deleted would simply get a model that can't produce that knowledge at all — no call-site gate is involved, and none of CSIS's existing enforcement code changes.

## 3. Where it would matter, if it ever does

The Phase-0 architecture's honest framing is "capability cannot grow faster than oversight," enforced today entirely by the call-site ceiling (`test_enforce_rejects_above_phase_0_ceiling_even_if_actor_authorized`). GRAM-style compartments are a second, independent axis: not "what is this role allowed to ask for," but "does the underlying model even have this knowledge available to answer with." If Anthropic ever exposes compartment selection as a model-id or request parameter (there is no such API today — GRAM is a research result, not a product), `TierGuard` would gain a natural second dimension: pair a `CapabilityTier` ceiling with a required compartment configuration per role, so a T0 Researcher's calls could be routed to a model variant with high-risk compartments removed, independent of the prompt-level tripwire check. That's a Phase-1-or-later idea, not something actionable with today's API surface — recorded here so it isn't reinvented from scratch if/when Anthropic ships a consumable version.

## 4. Bottom line

No code change today. This is a watch-list entry: re-read `tier_guard.py`'s design if GRAM (or a similarly-shaped compartmentalization technique) ever ships as something callable via the Messages API or Claude Managed Agents, since it would be the first capability-tier control CSIS's call-site guard.
