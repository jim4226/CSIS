# Ranked subreddit targets

Researched May 2026. Member counts and activity from The Hive Index and 2026 marketing-rules surveys. Tier ordering reflects fit × audience-friendliness × likelihood the post survives mod review.

**The 90/10 rule on Reddit**: 90% community engagement, 10% self-promotion. Single-post-launch is borderline acceptable everywhere below tier 5; sustained promotion without participation gets you shadow-banned.

**Universal don'ts**: don't verbatim cross-post (Reddit's spam filter notices), don't post to >2 subs/day, don't reply defensively, don't link your LinkedIn/Twitter in the OP.

---

## Tier 1 — post here first (highest fit)

| Subreddit | Members | Why this fits | Risk | Recommended angle |
|---|---|---|---|---|
| [r/AI_Agents](https://www.reddit.com/r/AI_Agents/) | **309K** | The dominant AI-agent-builder community on Reddit. Recent threads explicitly focus on "failure rates, security problems, and what happens when agents touch real systems" — the cycle-9 critique angle is on-target. LangGraph / CrewAI / AutoGen / PydanticAI users hang out here. | Low. Active community that wants project posts. | Lead with the cycle-9 critique trail; differentiate from framework announcements by emphasizing the audit log. |
| [r/ClaudeAI](https://www.reddit.com/r/ClaudeAI/) | ~200K+ | Anthropic-affiliated. Official "Built with Claude" post flair exists (used in Anthropic's own contest). CSIS's architecture explicitly maps to Anthropic's Managed Agents primitives. | Low-medium. Use the "Built with Claude" flair. Avoid sounding like vendor marketing. | Lead with what was built on Claude (the 8-step loop + cross-checkpoint verification). Mention the cycle log as the proof. |
| [r/LocalLLaMA](https://www.reddit.com/r/LocalLLaMA/) | ~400K | Audience that runs agent infra locally. Mock-by-default backend is a feature here (no API credits needed to try). | Low. Code-first sub; expects runnable examples. | Already drafted in [02-reddit-localllama.md](02-reddit-localllama.md). |

## Tier 2 — solid secondary, post 24-48h after tier 1

| Subreddit | Members | Why this fits | Risk | Recommended angle |
|---|---|---|---|---|
| [r/MachineLearning](https://www.reddit.com/r/MachineLearning/) | ~3M | Research-grade audience. Methodology-first framing fits the 9-cycle self-critique loop. | **Medium-high**. Strict mods; [P] posts removed if they read as project announcements. Must lead with methodology, not project name. | Already drafted in [03-reddit-machinelearning.md](03-reddit-machinelearning.md). |
| [r/SideProject](https://www.reddit.com/r/SideProject/) | **180K** | Explicitly self-promo-friendly for *shipped* products. CSIS qualifies (213 tests, runnable). Best posting Tue-Thu 8-11am EST. | Low. Community celebrates project posts when they're substantive (real numbers, real screenshots). | "I shipped a 4500-LOC self-improving agent prototype with 9 cycles of red-team audit. Looking for feedback on whether the critique-fix-loop methodology generalizes." |
| [r/LLMDevs](https://www.reddit.com/r/LLMDevs/) | ~16K | Smaller but specialized; LLM developer-builder audience. Lower volume = easier to land on the front page. | Low. | Architecture + cycle log angle. Audience appreciates code-level specifics. |
| [r/coolgithubprojects](https://www.reddit.com/r/coolgithubprojects/) | ~50K | Purpose-built for sharing GitHub projects. Self-promo is the whole point. | Low. Will get fewer eyeballs than tier-1 but more durable indexing. | Title format: "[<language>] <project> — <one-line>". Brief body. Heavy lifting done by README. |

## Tier 3 — niche but high-signal

| Subreddit | Members | Why this fits | Risk | Recommended angle |
|---|---|---|---|---|
| [r/Python](https://www.reddit.com/r/Python/) | ~1.4M | Implementation-language community. Friendly to well-engineered Python projects. The code structure itself (213 tests, type-stable contracts, Pydantic v2 throughout) is a real Python engineering story. | Low-medium. Avoid framing as "AI thing"; lead with the Python engineering. | "A multi-agent system with 213 pytest tests and a 9-cycle audit log against itself — what 4500 LOC of pydantic + threading + msvcrt locks looks like." |
| [r/madeinpython](https://www.reddit.com/r/madeinpython/) | ~30K | Python project showcase. Lower volume; gentle audience. | Low. | Same as r/Python but pithier. |
| [r/autonomousagents](https://www.reddit.com/r/autonomousagents/) | small | Autonomous-agent experiments. Tight overlap with CSIS scope. | Low. | Architecture + cycle log. |
| [r/ControlProblem](https://www.reddit.com/r/ControlProblem/) | ~40K | Alignment-aware community. The "safety properties enforced as code, not as prompt" framing + cycle-9 H2/H11 honest-deferral conversation would resonate strongly. | **Medium**. They will pick apart safety claims more rigorously than HN. Don't over-claim. | "Phase-0 prototype with a load-bearing safety table; cycle 9 hit the ceiling of pure-Python in-process guards and deferred H2/H11 to process-level isolation. What's the right next step?" |

## Tier 4 — high-volume but high-noise

| Subreddit | Members | Why this fits | Risk | Recommended angle |
|---|---|---|---|---|
| [r/artificial](https://www.reddit.com/r/artificial/) | ~1M+ | Broad AI audience; default catch-all. | **High noise.** Either gets traction or gets buried under news. | Lead with the cycle log angle to differentiate from typical AI-news posts. |
| [r/ArtificialIntelligence](https://www.reddit.com/r/ArtificialIntelligence/) | ~1M+ | Same shape as r/artificial. | High noise. | Don't cross-post with r/artificial in same week. |
| [r/AutoGPT](https://www.reddit.com/r/AutoGPT/) | **130K** | Agent-framework crowd. | Medium. Audience might react to "yet another framework" — differentiator must be the cycle log, not the architecture. | Lead with the critique-fix loop as a methodology contribution, not the framework. |
| [r/singularity](https://www.reddit.com/r/singularity/) | ~3M | Futurist crowd; will engage with "self-improving" framing. | **High**. The audience tends toward hype-reading; the Phase-0 caveats and honest deferrals may underwhelm. Risk of being read as either too modest or too ambitious. | Optional. If posted, lead with the long-arc framing from `CSIS-architecture.html` Appendix A, not the prototype. |

## Tier 5 — avoid

| Subreddit | Why to skip |
|---|---|
| [r/programming](https://www.reddit.com/r/programming/) | **Banned all LLM content in 2026.** Confirmed via Tom's Hardware coverage. Post will be removed. |
| [r/learnmachinelearning](https://www.reddit.com/r/learnmachinelearning/) | Wrong audience (learners, not project consumers). |
| [r/MLQuestions](https://www.reddit.com/r/MLQuestions/) | Question-only sub; project posts get removed. |
| [r/PromptEngineering](https://www.reddit.com/r/PromptEngineering/) | Wrong angle (CSIS isn't prompt-engineering focused). |
| [r/AIDangers](https://www.reddit.com/r/AIDangers/) | Wrong framing (CSIS isn't a doom warning). The H2/H11 deferrals belong in r/ControlProblem, not here. |

---

## Recommended order of operations

**Week 1 — primary launch:**
1. **Day 0 (Tue)**: Upload the social preview image first (see `04-social-preview.html`).
2. **Day 0 (Tue 7-9am PT)**: Show HN (see `01-show-hn.md`).
3. **Day 0 (Tue 1-3pm PT)** OR **Day 1 (Wed)**: r/AI_Agents — biggest dedicated audience, post separately from HN to avoid throttling.
4. **Day 1 (Wed)**: r/ClaudeAI with "Built with Claude" flair.

**Week 1 — secondaries:**
5. **Day 2 (Thu)**: r/LocalLLaMA + r/SideProject (different framings; can post same day to non-overlapping audiences).
6. **Day 3 (Fri)**: r/MachineLearning [P] (methodology framing; ONLY if you can stay online to engage discussion — mods remove low-engagement [P] posts).

**Week 2 — long-tail:**
7. r/coolgithubprojects (durable indexing, low effort)
8. r/LLMDevs (smaller but specialized)
9. r/Python or r/madeinpython (engineering-story angle)
10. r/ControlProblem (only if you want a serious safety-properties discussion; risks rigorous pushback)

**Skip unless specifically motivated:**
- r/AutoGPT (framework-crowd noise)
- r/singularity (futurist-crowd hype risk)
- r/artificial / r/ArtificialIntelligence (high noise; rarely worth the effort vs. tier 1-2)

## Activity budget

- Spend ~80% of post-launch time engaging substantively with comments (the actual marketing happens in the comment thread, not the OP)
- Spend ~20% drafting/scheduling next post
- If a post in tier 1 lands with real engagement (>50 comments, 100+ upvotes): hold the tier 4 subs in reserve and double down on the engagement
- If a post bombs: that's data, not failure — try a different framing on the same sub 2-4 weeks later, or different sub

## Anti-patterns to avoid

- **Cross-posting verbatim.** Each subreddit has its own framing in the drafts. Reddit's spam filter notices identical text across subs.
- **Posting to >2 AI subs in 1 day.** Auto-throttled by Reddit. Spread across the week.
- **Replying defensively to every "but what about X".** Engage the substantive ones; ignore the rest. Defensive engagement reads as desperation.
- **Linking LinkedIn / Twitter / email in the OP.** Self-promo signal; gets downvoted.
- **Posting Friday afternoon / weekends.** Front pages rotate slower; harder to accumulate upvotes during the active window.
- **Editing the post heavily after publication.** Looks like reputation laundering. If a critique is correct, reply with an edit acknowledgment instead.

## Tracking what works

Don't measure stars or upvote count alone. The real signal is:
- GitHub issues filed by people who actually ran the code (highest signal)
- Inbound PRs or fork-and-modify (highest signal)
- Substantive comments asking architectural questions (medium signal)
- Stars from accounts with prior history in agent-systems work (medium signal)
- Raw upvote count (low signal; mostly tells you the title worked)

Stars + bare upvotes are vanity metrics. Engineering engagement is the lagging indicator that actually correlates with the project mattering.

## Sources

- [Top AI Agent subreddits — The Hive Index, April 2026](https://thehiveindex.com/topics/ai-agents/platform/reddit/)
- [r/AI_Agents profile — Agents Index, 2026](https://agentsindex.ai/r-ai-agents)
- [Best AI subreddits in 2026 — Oku](https://oku.io/blog/best-ai-subreddits-in-2026)
- [r/SideProject marketing guide — Reddit Radar](https://www.reddit-radar-marketing.com/guides/r/sideproject)
- [Reddit self-promotion rules 2026 — KarmaGuy](https://karmaguy.io/en/blog/reddit-self-promotion-rules)
- [r/programming bans LLM content — Tom's Hardware coverage](https://www.tomshardware.com/tech-industry/artificial-intelligence/the-largest-programming-community-on-reddit-just-banned-all-content-related-to-ai-llms-r-programming-is-prioritizing-only-high-quality-discussions-about-ai)
- [Built with Claude contest — ClaudeLog](https://claudelog.com/claude-reddit-contest/)
