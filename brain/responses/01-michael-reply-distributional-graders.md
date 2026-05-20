# Draft reply to Michael Cohen — distributional graders

**Context.** Michael asked for elaboration on the question about graders for distributional outcomes (Dice score, anatomical landmark error, etc.) in clinical workflows. This draft links the question to a concrete place in CSIS where it lives, and to code on this branch (`claude/link-evals-response-loop-YKoOo`) that implements the pattern end-to-end so the email is more than hand-waving.

---

## Draft reply

Subject: Re: Managed Agents — graders for distributional outcomes

Hey Michael,

Sure — let me ground it a bit. Two grader shapes to disambiguate, because the answer's different:

**1. Rubric-style.** Per-criterion checklists with an LLM judge in the loop. Useful for free-form writing, customer-support eval, anything where the "is it good?" answer is a structured natural-language judgment. Managed Agents handles this well today and the V2 critic in our continuously-improving system framing is basically this with adversarial framing.

**2. Distributional.** Scalar metric over a held-out sample, where you care about (a) the central tendency clearing a threshold, (b) the lower-tail watermark (p10 for Dice / F-score, p90 for error metrics like landmark RMSE or Hausdorff95) not regressing vs the previous deployed model, and (c) sample size sufficient to defend against a single curated-set fake-pass. Clinical imaging is the canonical case — sub-mm landmark precision means a p90 ≤ 1 mm bound that has to hold against a held-out cohort, not a single number from a single scan.

The distributional case is the one I was chewing on, and I think it sits at a really specific layer of the verifier stack — not the same place as the rubric / LLM-judge work, and not the same place as long-horizon calibration scoring (Brier / log-loss). It's a per-iteration programmatic gate; it just happens to return a scalar plus summary stats instead of a bit.

I wired it up end-to-end on the CSIS Phase-0 prototype this morning to make sure the pattern actually composes with the loop instead of sitting next to it:

- **The module:** `csis/verification/distributional.py` — three types (`DistributionalSample`, `RollingBaseline`, `DistributionalThreshold`) plus a closure factory `distributional_grader(name=..., threshold=..., baseline=...)` that returns a `GraderResult` carrying the full summary stats. Pins into the same `GraderRegistry` the existing V1 graders use, so the F6 (pinned-source-hash drift) check, cross-checkpoint cert signing, V2 critic, and auditor why-doc all keep working unmodified.
- **The clinical example:** `make_clinical_imaging_registry()` ships a four-metric V1 set tuned for the Bone Vision case — `dice_score`, `boundary_f1`, `landmark_rmse`, `hausdorff_95`. Each metric gets `(floor, op, summary_stat, min_samples, max_regression, regression_stat)`. The regression rule is "this iteration's p10 must not drop more than X below the median of recent promoted iterations' p10s" (or p90 for error metrics). Median-of-p10s is robust to a single outlier promoted iteration.
- **The loop linkage:** the key thing I wanted to prove out is that this gives the system a "continuous" property that's actually load-bearing. Each promoted artifact calls `update_baselines_after_promotion()` which appends summary stats to a per-metric `RollingBaseline` persisted as JSON under `brain/`. The next iteration's grader instance — possibly in a fresh process after a daemon restart — reads the updated baseline cold and the threshold tightens. The persisted baseline file is the audit trail; a regression event is detectable, attributable, and replayable. V5 calibration (Phase 2 in our spec) reads the same series to compute drift.
- **20 new tests, full suite 237 passing**, including end-to-end: Coordinator runs the 8-step loop with the clinical registry, the cert carries every distributional grader's full metrics dict, promotion happens, baseline updates, next iteration sees the tighter watermark. Files:
  - Module: [`csis/verification/distributional.py`](https://github.com/jim4226/CSIS/blob/claude/link-evals-response-loop-YKoOo/csis/verification/distributional.py)
  - Tests: [`tests/test_distributional_graders.py`](https://github.com/jim4226/CSIS/blob/claude/link-evals-response-loop-YKoOo/tests/test_distributional_graders.py)
  - Writeup: [`brain/research/02-distributional-graders.md`](https://github.com/jim4226/CSIS/blob/claude/link-evals-response-loop-YKoOo/brain/research/02-distributional-graders.md)

So the concrete ask, if there is one: **rolling-baseline-aware distributional thresholds as a first-class grader pattern in Managed Agents** — not just as a rubric option. The split that matters for clinical (and search ranking, forecasting, recommendation) is "summary statistic + tail watermark vs the prior deployed model," and that's a structurally different shape from a rubric checklist. Two specific things would be unblocking on the platform side:

1. A way for a grader to declare "I am distributional, here's my metric series" so the harness can persist + version the baseline next to the eval (rather than each project rolling its own JSON file as I did).
2. A hook the verifier can call post-promotion so the rolling baseline updates atomically with the artifact landing — without that, the regression check is honest-but-not-strictly-CAS-safe. I worked around it by keeping the baseline update outside the Coordinator and calling it from the daemon path, but the right place is structurally in the promote primitive.

I know it's a small slice — happy to either dig further on it from my end, or punt and just use what's there if you all are already cooking this. Either way the prototype is on the branch above so you can run `pytest tests/test_distributional_graders.py -v` and see whether the framing tracks with what you're building.

Thanks again.

Best,
Jaron

---

## Notes for sending

- Length is on the longer side for a cold-meet follow-up. If Michael's reply was short on time, an alternative tighter version: keep the two-bullet rubric vs distributional split, drop the implementation paragraphs, link the branch and one file, end with the two-item platform ask. The prototype is the proof that the framing isn't speculative; it doesn't need to be quoted in full.
- If Michael wants a call, the right artifact to walk through is `test_coordinator_runs_clinical_registry_end_to_end_and_baseline_updates` in `tests/test_distributional_graders.py:267` — that's the full link-to-the-loop in one test.
- If he replies "out of scope for now," the polite close is: the pattern sits inside the prototype anyway, happy to share what we learn from running it against real Bone Vision data over the summer.
