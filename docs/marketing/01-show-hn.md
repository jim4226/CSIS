# Show HN draft

## Title options (pick one; HN's title field caps at 80 chars)

1. **Show HN: 9 cycles of red-teaming my own self-improving agent system**
2. **Show HN: I shipped a multi-agent system and 9 critique cycles against it**
3. **Show HN: A self-improving agent prototype, with its own bug audit log**

Recommendation: **option 1**. It's the most distinctive framing (critique-first, not framework-first), the verb "red-teaming" filters for the audience that will read carefully, and "my own" signals it's not vendor marketing.

## URL field

`https://github.com/jim4226/CSIS`

## Show HN post body (OP's first comment — required on HN)

> CSIS is a Phase-0 prototype of a long-running, self-improving multi-agent system. The interesting part isn't the architecture — it's the public bug audit log next to it. Across nine cycles, parallel red-team agents attacked the prior cycle's fixes; findings landed in code with regression tests; cycles 4-9 each found the previous cycle had patched the right concept at the wrong abstraction layer, and moved it.
>
> Two patterns that kept reappearing:
>
> **Identity beats timing.** Cycle 8 tried to detect "which iteration wrote this candidate?" with a pre-consolidate snapshot diff. Cycle 9 found a sibling-write race in that approach. The fix wasn't a wider snapshot — it was a `writer_iteration_id` field stamped on every candidate at write time. The cleanup filters by stamp, not by timing.
>
> **Chokepoints beat perimeters.** Cycle 8 added a `type(...) is _BackendTracker` check at `Daemon.__init__` to defeat subclass-shaped bypasses of LLM metering. Cycle 9 found three production scripts (`burst.py`, `loop.py`, `demo_pr_scenario.py`) constructed the inner `Coordinator` directly with a raw backend — `--backend anthropic` ran unmetered. The fix moved the check into `Coordinator.__init__` and added property setters that re-validate on assignment.
>
> Honest about what doesn't work yet: real Anthropic backend is opt-in (mock by default, no API key needed); the dreams/consolidation layer is locally mocked; cycle 9 deferred two findings (closure-cell mutation, POSIX unlink-during-lock race) because pure-Python in-process guards have a ceiling — those need process-level isolation to close, which is Phase 1.
>
> Quick start: `pip install pydantic pytest && python -m pytest tests/ -v && python -m csis.loop`. 213 tests, 99 findings closed, 0 open. Full cycle trail: github.com/jim4226/CSIS/blob/main/CYCLES.md
>
> Curious what HN thinks about the "identity vs timing" pattern in particular — feels like the kind of thing that generalizes outside agent systems, but I haven't seen it called out in those words elsewhere. Also genuinely want to know if the H2 closure-mutation deferral is right or if I should be doing more in-process before kicking it to process isolation.

## Why this framing should hold up under HN scrutiny

- **Lead with the work, not the vision.** The first sentence is "Phase-0 prototype"; the most-quoted thing is "the bug audit log next to it." HN punishes hype openers.
- **Concrete examples with code-level specifics.** "writer_iteration_id field stamped at write time" + "moved into Coordinator.__init__" are checkable claims, not vibes.
- **Honest deferrals listed.** HN respects "here's what doesn't work yet" more than "production-ready."
- **End with a real question.** "Curious what HN thinks about X" invites a comment that isn't just "interesting, will check out."
- **No emojis, no marketing language, no bullet-pointed feature list.**

## What to do *after* posting

- Don't engineer-bait by replying to every "but what about Y" — pick the substantive critiques and engage; ignore the rest
- If someone reproduces a real bug, file it as a GitHub issue with their handle credited; that's the highest-signal HN engagement
- Don't auto-respond from a script; HN moderates aggressively against that
- HN's "Show HN" guidelines: only post once, can be reposted in 48h-window if no engagement; weekdays 9-11am PT historically best

## Best time to post (heuristic)

Tuesday-Thursday, 7-9am Pacific. Avoid Friday afternoon and weekends (front page rotates slower; harder to gather upvotes).
