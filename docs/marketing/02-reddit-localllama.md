# r/LocalLLaMA post draft

**Subreddit**: r/LocalLLaMA
**Flair**: Resources (or Discussion if Resources isn't allowed for repos)
**Why this subreddit**: the audience here is people running agent infrastructure locally — they care about (a) does it actually run on a mock backend so they can poke at it without burning API credits, and (b) does the architecture handle real failure modes. This repo fits both criteria.

---

## Title (subreddit caps at 300 chars; keep under 100)

**A multi-agent system you can poke at with no API key — and the public 9-cycle bug audit log we ran against it**

## Body

> Built a Phase-0 prototype of a long-running, self-improving multi-agent system on what would map to Anthropic's Managed Agents primitives. Runs end-to-end on a mock backend by default (no API key needed) or against the real Anthropic backend when you want to spend cents on actual iterations.
>
> ## Quick start
>
> ```bash
> git clone https://github.com/jim4226/CSIS
> cd CSIS
> pip install pydantic pytest
> python -m pytest tests/ -v          # 213 tests
> python -m csis.loop                  # one full 8-step iteration, mock backend
> python -m csis.daemon --backend mock --rate-per-hour 60   # 24/7 mock daemon
> ```
>
> Want to spend real money on real iterations? `python scripts/burst.py --iters 5 --backend anthropic --max-cost-usd 2` — hard cost ceiling, WAL-backed budget metering, drops out cleanly when the cap fires.
>
> ## Why this might interest r/LocalLLaMA
>
> 1. **The 8-step loop is the whole show.** Researcher → Builder → Verifier → Librarian → Auditor → Promote. Each role is a separate prompt to a backend you swap out. The mock backend ships scripted JSON responses for every role so you can study the loop's control flow without an LLM call. (`csis/backends/mock.py` is ~80 lines; trivial to swap in your own local backend.)
> 2. **Memory is hash-preconditioned and reversible.** 6 trust levels (`raw → untrusted → candidate → verified → promoted → deprecated`). Writes go to candidate stores. Promotion is a CAS-style atomic flip with a hash precondition; if the live store moved between why-doc signing and promote attempt, the promotion is rolled back atomically.
> 3. **Cross-checkpoint verification is structural.** The Verifier and Auditor run on a checkpoint with a different `model_id` than the Builder (Sonnet-class vs Opus-class in the Anthropic config, mock-sonnet vs mock-opus locally). Self-confirmation by the same model is rejected at the cert build site.
> 4. **It has its own bug audit log.** I ran 9 cycles of parallel-red-team → fix → regression-test against the system. 99 findings closed, 0 open, 2 honestly deferred (closure-cell mutation, POSIX unlink-during-lock — neither closeable in pure-Python in-process). Full trail: [CYCLES.md](https://github.com/jim4226/CSIS/blob/main/CYCLES.md).
>
> ## What this is NOT
>
> - **Not a working production agent.** Mock-by-default. Real backend opt-in.
> - **Not a framework to depend on.** Phase-0 prototype. Architecture document drives the implementation, not the other way around.
> - **Not running Llama locally yet.** Backend layer is generic (`csis/backends/base.py`) so swapping in vLLM/llama.cpp/Ollama is one ~80-LOC file, but I haven't written that adapter. Would love a PR.
>
> ## What I'm curious about from this sub
>
> - Has anyone built something similar against a local backend? The Anthropic adapter is the only "real" one shipped; I'd love to know what breaks if you point this at a Llama-3-70B-Instruct via vLLM.
> - The "writer_iteration_id" pattern from cycle 9 (stamp ownership on the candidate at write time, instead of inferring from snapshot timing) — has anyone seen prior art for that in agent-system or distributed-system literature? Feels rediscovered, not novel.
>
> Repo: https://github.com/jim4226/CSIS

## Why this framing should work on r/LocalLLaMA

- **Code-first.** Quick start is the second section, after a one-line lead. r/LocalLLaMA scrolls past projects without a runnable command.
- **Local-friendly.** Emphasizes the mock backend so people without credits can try it. The "PR for vLLM/llama.cpp adapter" invitation surfaces the backend abstraction.
- **No "self-improving AI" hype.** Calls itself a "prototype" twice; explicit "what this is NOT" section.
- **Asks the subreddit a real question.** r/LocalLLaMA upvotes posts that engage them, not just announce.

## Best time to post

Weekday afternoons US time (subreddit is most active 1-5pm PT). Avoid posting same content to multiple AI subreddits within an hour — Reddit's spam filter cross-checks.
