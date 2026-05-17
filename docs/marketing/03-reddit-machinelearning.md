# r/MachineLearning post draft

**Subreddit**: r/MachineLearning
**Flair**: [P] Project
**Why this subreddit**: the audience is researchers + engineers who care about methodology over hype. The novel-ish angle here isn't the architecture; it's the *evaluation regime* — 9 cycles of red-team-self → fix → regression-test as a way of measuring the maturity of an agent system rather than just running benchmarks.

**Note on subreddit rules**: r/MachineLearning is moderated strictly. [P] posts must include code/results, can't be ad-shaped, can't lead with the project name. Posts that read as "Show HN: <my project>" get removed. Lead with the methodology, then the implementation.

---

## Title (subreddit caps at 300 chars; flair takes ~10)

**[P] Using parallel red-team agents as a maturity signal for multi-agent systems: 9 cycles, 99 findings, 213 regression tests**

## Body

> I've been experimenting with a methodology for measuring whether a multi-agent system is mature enough to ship vs. demo: instead of running it against external benchmarks, I run *itself* against itself. Each cycle dispatches a few parallel red-team agents whose only job is to find reproducible attacks on the prior cycle's fixes, with `file:line` evidence and a Python attack snippet. Findings get triaged into a critique document; fixes land in code with regression tests; results snapshot to disk.
>
> The system under test is a Phase-0 prototype of a long-running multi-agent system on what would map to Anthropic's Managed Agents primitives — Researcher / Builder / Verifier / Librarian / Auditor roles around a hash-preconditioned memory hierarchy and cross-checkpoint verification. But the SUT is incidental; the loop methodology is the part I'm trying to find prior art for.
>
> ## What the cycle log shows
>
> | Cycle | Findings | Critical | High | Tests after |
> |---:|---:|---:|---:|---:|
> | 1 (pre-impl) | 18 | 2 | 6 | 52 |
> | 2 (post-impl) | 13 | 2 | 6 | 78 |
> | 3 | 11 | 2 | 4 | 114 |
> | 4 | 11 | 2 | 4 | 141 |
> | 5 | 11 | 3 | 3 | 165 |
> | 6 | 10 | 3 | 3 | 186 |
> | 7 | 7 | 1 | 2 | 195 |
> | 8 | 6 | 2 | 2 | 202 |
> | 9 | 12 | 4 | 3 | **213** |
> | **Total** | **99** | **21** | **33** | — |
>
> Cycle 8 had the lowest finding count and shipped two architectural pivots; I'd predicted that signaled diminishing returns. Cycle 9 returned 12 findings (four critical), three of which independently showed that the cycle-8 pivots were the right concept at the wrong abstraction layer.
>
> ## Two patterns the cycles kept teaching
>
> **Identity beats timing.** Cycle 8 detected "did THIS iteration write this candidate" via pre-consolidate snapshot diff. Cycle 9 found a sibling-write race window. The fix wasn't a wider snapshot — it was a `writer_iteration_id` field on the candidate itself, stamped atomically at `write_candidate` time. Cleanup filters by stamp.
>
> **Chokepoints beat perimeters.** Cycle 8 added a `type(...) is _BackendTracker` check at the Daemon boundary to defeat subclass-shaped bypasses of LLM metering. Cycle 9 found three production scripts constructed the inner Coordinator directly, bypassing the Daemon. The fix moved the check into `Coordinator.__init__` (the single chokepoint every LLM call passes through) plus property setters that re-validate on assignment.
>
> ## What this is NOT a claim about
>
> - **Not safety certification.** 213 tests + 99 findings closed are evidence of careful engineering, not proof of safe behavior under adversarial conditions. Cycle 9 has two honest deferrals (H2 closure-cell mutation, H11 POSIX unlink-during-lock) that pure-Python in-process guards can't close — both flagged for process-level isolation in Phase 1.
> - **Not an evaluation method.** I have no claim that the finding rate would generalize to other agent systems. The methodology might just be telling me how well this particular prototype was engineered.
> - **Not a paper.** It's a runnable repo with a public bug audit log. Genuinely curious whether the loop methodology has prior art in agent-system or software-engineering literature that I missed.
>
> ## Repo
>
> Code, all 9 critique docs, all snapshots, 213 tests: https://github.com/jim4226/CSIS
> Cycle trail summary: https://github.com/jim4226/CSIS/blob/main/CYCLES.md
>
> ## Questions I'd love this sub's input on
>
> 1. The "identity beats timing" pattern from cycle 9 — has anyone seen this written up in the agent-systems or distributed-systems literature? Feels rediscovered, not novel.
> 2. Has anyone used a parallel-red-team-self loop as the *primary* maturity signal for a research-grade agent system, instead of external benchmarks? I'm looking for prior art on the methodology specifically.
> 3. Cycle-8 finding-count drop (6 vs cycles-7/9's 7 and 12) misled me into thinking I'd hit diminishing returns. Is there a better signal than finding-count to know when to stop the loop?

## Why this framing should hold up on r/ML

- **Methodology lead, project follow.** Sub mod rules require this; otherwise removed.
- **Concrete numbers + concrete deferrals.** r/ML's bar is "show me the table; show me what you don't know yet."
- **No hype, no novelty claim.** Explicit "not a paper", "rediscovered, not novel", "questions I'd love input on."
- **Asks for prior art.** Highest-value engagement; turns the post from announcement into question.

## Cross-posting note

DO NOT cross-post the same body verbatim to multiple subreddits. The /r/MachineLearning version (methodology-led) and /r/LocalLLaMA version (code-led) are different framings on purpose. Reddit's spam filter and mods both notice verbatim cross-posts.

## Best time to post

Weekday mornings US time (sub is most active 8am-12pm ET). [P] posts need to be self-contained — links don't drive engagement; in-post tables and code snippets do.
