# GRAM (Gradient-Routed Auxiliary Modules) and CSIS's capability-tier ceiling

> **Research thread:** Anthropic's July 8, 2026 research post ["An off switch for dual-use knowledge in AI models"](https://www.anthropic.com/research/off-switch-dual-use) describes GRAM, a training-time technique that isolates dual-use knowledge (e.g. virology, cybersecurity, nuclear physics) into dedicated model modules that can be switched on or off independently of the rest of the model. Does this technique change anything about CSIS's Phase-0 capability-tier substrate (`csis/safety/tier_guard.py`)?

**Status.** Not implemented. This is a design note, not a code change — see "Why this is a note, not a PR" below.

**Audience.** Anyone extending CSIS's L7 safety envelope (`csis/safety/`) or thinking about Phase-1 capability-tier work.

---

## 1. What GRAM actually does

GRAM is a **training-time** technique: dual-use knowledge is routed into isolated auxiliary modules during training (tested on a 5B-parameter model by Anthropic and AE Studio), and those modules can be physically removed or deactivated before deployment. In their initial tests, removing the cybersecurity/virology/nuclear-physics modules disabled the related capabilities without measurably degrading general performance, and the isolation held up under adversarial fine-tuning — unlike post-hoc unlearning, which tends to suppress rather than remove the knowledge. Anthropic is explicit that this is preliminary research, not deployed on production models.

## 2. Where this rhymes with CSIS, and where it doesn't

CSIS's capability substrate (`csis/safety/tier_guard.py`, `CSIS-architecture.html` §9) enforces a **call-site ceiling**: every primitive call is tagged with a capability tier (T0/T1/T2+), and Phase-0 hard-caps the system at T1 — a T2+ request is rejected where the call happens, regardless of which actor asked. That's an **inference-time, orchestration-layer** gate: it doesn't know or care what the underlying model "knows," only what action it's trying to invoke.

GRAM operates one layer down and earlier in the pipeline — it changes what the *model itself* can produce, at training time, by isolating knowledge into modules rather than gating actions at a call site. The two are complementary, not overlapping: GRAM answers "can this model generate dangerous content at all," while CSIS's tier guard answers "can this orchestration step invoke a dangerous action." A system could have both: a GRAM-gated model as the substrate, wrapped by a CSIS-style tier guard for orchestration-level actions.

## 3. Why this is a note, not a PR

CSIS is an orchestration prototype — it calls Anthropic models over the API and constrains what the *loop* does with the responses. It has no path to retrain or module-gate the underlying model; that's Anthropic's territory, not something `csis/safety/` can implement. There is no concrete `file:line` chokepoint in this repo that a GRAM-shaped feature would touch today, so this doesn't clear the bar for even a trivial code PR.

The one place this could eventually matter: if a future Anthropic API surface exposes which knowledge-modules are active for a given model/session (e.g. as a capability-tier-like flag in the response), `csis/safety/tier_guard.py` would be the natural place to consume it — the tier guard already has the single chokepoint every primitive call passes through, so a model-reported capability flag would slot into the existing `enforce()` check rather than requiring a new one. That's speculative and not tracked as a roadmap item until such a surface exists.

## Pointer back

← [ROADMAP.md](../../ROADMAP.md) for what's actually scheduled
← [CSIS-architecture.html §9](../../CSIS-architecture.html#9) for the capability-tier enforcement schema
