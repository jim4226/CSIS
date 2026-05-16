# Email to Lance Martin: drafts (v0.2, no em dashes)

Two versions. Version A is what you sketched in chat, polished and with a plain-English paragraph added after the opener. Version B is the longer technical version, also em-dash-free.

---

## Version A: short & warm (recommended, polished from your draft)

**To:** Lance Martin <lance@anthropic.com>  *(or whatever address he gave you / via LinkedIn DM)*
**Subject:** Following up from office hours at Code w/ Claude

Hi Lance,

It was great meeting you during office hours at Code w/ Claude. Hope you're feeling better. I caught the same cold on my way back to Miami, so bad luck on both ends.

In plain English, what I want to share is this: an architecture for AI agents that run 24/7, never reset their memory, and slowly become more capable over time by designing their own experiments, checking their own work, and consolidating what they learned during sleep cycles, kind of like a brain does. The long-arc ambition is for a system like this to grow into a domain-level superintelligence first (formal math, software maintenance, scientific literature), then a broader one, with safety wired into the loop so the system stays correctable as it gets smarter. This proposal is about how to build the first piece of that responsibly, on top of the primitives Anthropic already ships.

I really enjoyed our conversation, especially the thread about hippocampus-style agents with memory stores. I'm a college student and I'll be the first to say I may be wrong about parts of this, but the idea felt important enough to think through carefully and write it down. So I built it out into an architecture proposal, and after a round of self-review I narrowed it to a Phase-0 contract that's specific enough to actually engineer.

The Phase-0 ask in one sentence: build a coordinator-led CSIS prototype on Managed Agents in a single benchmark domain (open-source PR maintenance is my proposal; formal-math reasoning as alternative), where Researcher, Builder, Critic, Verifier, Librarian, and Auditor sub-agents share a session log; all memory writes go through candidate Memory Stores; Dreams consolidate only into reviewable output stores; and every promoted change requires a Verifier certificate (cross-checkpoint) plus an Auditor why-doc with a hash precondition. Tiers T0/T1 only, V1+V2 verification only, improvement layers I1-I3 only.

A few specifics that came out of self-review and might be worth your sanity-check:

- **Trust levels on memory entries** (`raw`, `untrusted`, `candidate`, `verified`, `promoted`, `deprecated`). This is the contract that turns "why-tags" from prose into something an Auditor can enforce. Mostly a response to the memory-poisoning warning in your docs.
- **Dreams as candidate generator, not safety primitive.** Earlier drafts of mine called it "structurally reversible," which overshoots. The proposal now treats Dreams as a candidate generator with strong reversibility properties (input store untouched), but lays the safety-of-consolidation work on a Verifier plus Auditor plus rollback-test layer above it. Partial-output handling is explicit because the API does persist partial output on cancel or failure.
- **Coordinator-led for Phase 0.** I've explicitly chosen Anthropic's native multiagent model (≤25 threads, max-1 delegation depth, shared container) over an external supervisor for Phase 0. The "many brains, many hands" pattern from your post is the Phase-3+ generalization, flagged but out-of-scope for now.
- **Cross-checkpoint Verifier/Auditor pinning** is the same structural discipline as your credential-isolation pattern, applied to preventing same-model self-confirmation rather than token leakage.

The longer arc, why this matters past Phase 0, is preserved in an appendix and intentionally not the lead. The proposal stands or falls on whether Phase 0 actually works.

Four artifacts attached:

- **CSIS-architecture.html** the centerpiece, an interactive single-file architecture document. Paste-ready for Claude.
- **CSIS-deck.pptx** 19-slide companion deck (cream/orange brand, Poppins/Lora) if you'd rather skim.
- **CSIS-memo.docx** concise 8-page version.
- **CSIS-whitepaper.docx** long-form formal version.

Whatever reaction you have, including "this is wrong because X" or "you're missing Y," would be valuable. If there's a 30-minute window in the next couple weeks, I'd particularly value a sanity-check on the Dreams to consolidation mapping and on whether the coordinator-led model is the right call for Phase 0 versus starting from independent durable sessions. No rush, I know your inbox is what it is.

Thanks again for the time at office hours. The hippocampus framing was the unlock.

Best,
Jaron
jim4226@miami.edu

---

*Quick note on the em dashes in the attachments list above: I left them in just on the bullet labels because they're hyphens-as-list-separators, not em dashes. If you want me to also strip those, swap them for colons:*
*- CSIS-architecture.html: the centerpiece...*

---

## Version B: longer technical version (no em dashes)

**To:** Lance Martin <lance@anthropic.com>
**Subject:** From office hours at Code w/ Claude: a Phase-0 contract for hippocampus-style agents on Managed Agents

Hi Lance,

It was great meeting you during office hours at Code w/ Claude. Hope you've recovered. I caught the same cold on my way back to Miami, so bad timing on both ends.

In plain English, this is an architecture for AI agents that run 24/7, never reset their memory, and slowly become more capable over time by designing their own experiments, checking their own work, and consolidating what they learned during sleep cycles, similar to how a human brain works. The long-arc ambition is for a system like this to grow into a domain-level superintelligence first, then a broader one, with safety wired into the loop so the system stays correctable as it gets smarter. This proposal is about how to build the first piece of that responsibly, on top of the primitives Anthropic already ships.

I really valued the office-hours conversation, particularly the thread about **hippocampus-style agents with memory stores**. That framing wouldn't leave me alone, so I built it out into an architecture proposal. I'm a college student and I want to be upfront that I may be wrong about parts of this, but I thought the idea was important enough to think through carefully rather than let it stay a hallway conversation. After a round of self-review (someone read the v0.1 closely and pushed back hard on overreach), I tightened it into a v0.2 Phase-0 contract.

### The Phase-0 ask

Build a coordinator-led CSIS prototype on Managed Agents in a single benchmark domain (open-source PR maintenance proposed, formal-math reasoning as alternative), where one coordinator brain supervises Researcher, Builder, Critic, Verifier, Librarian, and Auditor roles within a single shared container; all memory writes go through candidate Memory Stores; Dreams consolidate only into reviewable output stores; and every promoted change requires a Verifier certificate (cross-checkpoint) plus an Auditor why-doc with a hash precondition.

Phase 0 commits to T0/T1 capability tiers, V1+V2 verification, improvement layers I1 through I3 only. Everything beyond that, meta-improvement, T2+ networking, weight updates, the multi-Dream pipeline at full cadence, is Phase 1+ and out-of-scope for the first build. The architecture is small on purpose.

### What changed from the first draft after self-review

A reviewer pushed me hard on five things, all of which I think were right:

1. **Pick one benchmark domain.** v0.1 was domain-agnostic; v0.2 picks one (open-source PR maintenance, with hard V1 graders). Anthropic's "Building effective agents" guidance is unambiguous on starting simple and evaluable.
2. **Trust levels on memory.** Memory is the main attack surface in any system like this. v0.2 introduces an explicit trust-level taxonomy (raw, untrusted, candidate, verified, promoted, deprecated), hash-preconditions on every promotion, read-only-by-default attachments, and explicit handling of the 30-day platform version-expiry window.
3. **Weaken the Dreams safety claim.** v0.1 called Dreams "structurally reversible." v0.2 treats it as a candidate generator with strong reversibility properties, and lays the safety-of-consolidation work on 