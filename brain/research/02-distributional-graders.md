# Distributional graders for outcomes-based evaluation

> **Research thread:** what would Anthropic's Managed Agents graders need to ship to support evaluation tasks whose acceptance criterion is a distributional quantity (Dice score, Hausdorff distance, landmark Euclidean error, calibration error) rather than a rubric-style pass/fail?

**Status.** Implemented in this repo at [`csis/verification/distributional_graders.py`](../../csis/verification/distributional_graders.py) with 31 regression tests at [`tests/test_distributional_graders.py`](../../tests/test_distributional_graders.py). This document is the design rationale, the literature anchor, and the platform proposal.

**Audience.** Anyone building an LLM-driven agent system whose downstream domain is clinical imaging, scientific reconstruction, structural biology, robotics, or any task where the right answer to "is the model good?" is a *number with uncertainty* rather than a checkbox.

---

## 1. The shape of the problem

### 1.1 What rubric eval does well

The dominant LLM-eval paradigm right now is **rubric-shaped**. Examples:

- **HealthBench** (OpenAI, 2025) — over 260 physicians authored 48,562 unique criteria; each model answer is graded against an Instance-Specific Rubric of 5-30 binary checks.
- **LLM-Rubric** (Hashemi et al., 2025) — multi-dimensional rubric calibrated to human judgment via a few-shot judge; reports RMS error vs. human < 0.5 on overall user satisfaction.
- **Dental short-answer grading** (Liu et al., 2026) — DeepSeek-3 ICC 0.87 vs. 3 calibrated SMEs (ICC 0.84); exact-match 43.3% of cases, ±1 point in 62.4%.
- **Anthropic's Managed Agents `Cert`** — a `VerifierCertificate` carrying `grader_results: list[GraderResult]` where each result is binary (`passed: bool`) with optional auxiliary metrics. (This is also the shape CSIS shipped pre-cycle-10.)

Rubric eval is the right shape when:
1. The task has discrete acceptance criteria ("did the tests pass?", "does the SQL return the expected row count?", "is the diff scoped to non-grader files?").
2. The acceptance criterion is naturally categorical or low-ordinal ("did the LLM follow each of the 7 documented citation rules?").
3. Single-sample evaluation is meaningful ("for this one patient interaction, did the model express empathy?").

CSIS's existing graders are all rubric-shaped: `tests_pass_grader`, `lint_grader`, `typecheck_grader`, `coverage_delta_grader`, `diff_scope_grader`, `perf_regression_grader`. Each takes one artifact and returns one bool. This works perfectly for the PR-maintenance benchmark domain.

### 1.2 What rubric eval cannot do

Now consider Jaron's actual day job at **Bone Vision**: 2D X-ray → 3D bone reconstruction at sub-mm precision via custom transformers. The "is this model good?" question has answers like:

> Mean ASSD = 0.412 mm, 95% CI [0.398, 0.427] across N=523 cases. Per-anatomy breakdown: vertebra L3 0.31mm [0.28, 0.34]; femoral neck 0.58mm [0.54, 0.63]; pelvic inlet 0.71mm [0.65, 0.78]. Mean landmark Euclidean error 1.42mm [1.36, 1.48] with max-landmark-error > 2mm in 4.3% of cases.

That sentence cannot be collapsed to a single boolean without throwing away the parts a clinician cares about. Specifically:

1. **Point estimate vs. distribution.** A model with mean Dice 0.89 could be 0.89 ± 0.02 (excellent) or 0.89 ± 0.18 (one of three cases is dangerous). The rubric `passed: bool` can't carry the variance.
2. **Slice-level breakdown.** A global mean of 0.89 can hide a 0.71 on the pancreas — clinically lethal. A rubric grader doesn't naturally support "this passes overall but fails on the slice that matters most for downstream use."
3. **Confidence intervals.** When n=523 (clinically meaningful sample) vs. n=12 (toy validation set), the same point estimate carries vastly different evidence weight. A `passed: bool` doesn't surface n.
4. **Direction.** Dice/IoU are higher-is-better; Hausdorff/ASSD/error-in-mm are lower-is-better. Rubric graders elide the direction; the conservative pass rule depends on it.
5. **Tail behavior.** Mean ASSD = 0.4mm is fine; max ASSD = 5mm on 2% of cases is a recall (the FDA cares about the tail, not the mean). A boolean grader can't enforce both.

These five gaps are not unique to medical imaging. They appear in:
- **Robotics:** trajectory error in mm; success rate ± CI across N trial environments
- **Structural biology:** RMSD on protein structure prediction; per-residue confidence
- **Climate modeling:** RMSE on temperature reconstruction with per-region breakdown
- **Drug discovery:** binding affinity prediction (Ki, IC50) ± log-units with per-target-class slicing
- **Calibration eval:** ECE (Expected Calibration Error) over a held-out set; not a single rubric question

Any agent system that wants to evaluate outcomes in these domains needs more than `passed: bool`.

---

## 2. The taxonomy

Three layers of grader sophistication, in increasing power and complexity:

| Layer | Output shape | Example | Native in current LLM-eval stacks? |
|---|---|---|---|
| **L1. Binary rubric** | `passed: bool` per criterion | "did the tests pass?" · HealthBench checks | Yes (default everywhere) |
| **L2. Calibrated rubric** | Likert score ∈ {1..5} calibrated against human judges | LLM-Rubric satisfaction prediction · dental ICC grading | Partial — needs a few-shot calibration loop |
| **L3. Distributional** | Point estimate ± CI over N samples, optional per-slice breakdown, direction-aware pass rule | Dice 0.892 [0.871, 0.913] over N=523, liver/pancreas/spleen slices | **No** — the cert shape doesn't carry it |

CSIS shipped L1 in cycle 1, then ran 9 cycles of red-team against the L1 substrate. Cycle 10 (this work) adds L3. L2 is in scope for future work but the existing `GraderResult.metrics: dict[str, float]` channel can carry calibrated scores in the interim.

---

## 3. The structural fixes

### 3.1 Schema (the contract)

A `DistributionalGraderResult` replaces `GraderResult` for outcomes-shaped tasks. Fields:

| Field | Type | Purpose |
|---|---|---|
| `grader: str` | identifier | Same as L1 |
| `metric_name: str` | e.g. "dice", "assd_mm", "landmark_euclidean_mm" | Machine-readable so the dashboard can group |
| `direction: Literal["higher_is_better", "lower_is_better"]` | direction | Determines which CI bound the pass rule uses |
| `point_estimate: float` | central tendency | Sample mean or median |
| `ci_lower / ci_upper: float` | bootstrap percentile CI | The thing rubric eval throws away |
| `ci_level: float = 0.95` | CI width | Documented in the cert, not hidden |
| `n_samples: int` | distribution size | Evidence weight |
| `n_bootstrap: int` | resampling count | Reproducibility |
| `threshold: Optional[float]` | acceptance bar | `None` = report-only |
| `passed: bool` | **conservative** pass rule | See §3.2 |
| `slices: list[GraderSlice]` | per-subset breakdown | See §3.3 |

### 3.2 Conservative pass semantics

The literature on clinical ML eval is unanimous: report the CI, decide on the CI bound. CSIS implements:

```python
def _passed(self, ci_lower: float, ci_upper: float) -> bool:
    if self.threshold is None:
        return True  # report-only mode
    if self.direction == "higher_is_better":
        return ci_lower >= self.threshold   # don't ship if even the bottom of the CI fails
    return ci_upper <= self.threshold       # don't ship if even the top of the CI exceeds the bar
```

This is the **single biggest behavioural difference** vs. point-estimate-vs-threshold rubric graders. A model with mean Dice 0.87 but 95% CI [0.81, 0.93] FAILS against threshold 0.85. The point estimate cleared the bar but the bottom of the CI didn't — and a model that might in truth perform at 0.81 should not be auto-promoted in clinical context.

This rule is reversible: an operator who explicitly wants point-estimate semantics passes `threshold=None` and applies their own check downstream. But the default must be conservative.

### 3.3 Per-slice breakdown

Every sample carries free-form slice labels: `Sample(case_id="c-042", payload={...}, slices={"organ": "liver", "modality": "CT", "cohort": "adult"})`. The grader emits one `GraderSlice` per `(slice_key, slice_value)` pair that has at least `slice_min_n` samples (default 5, configurable; below the minimum, CIs are too wide to be useful).

Slices unlock three downstream behaviors:

1. **Auditor sees disaggregated performance** — the why-doc can mention "passes overall but pancreas slice fails."
2. **Critic (V2) attacks the worst slice** — `grader.worst_slices(result, k=3)` returns the k slices closest to the threshold (or beyond for lower-is-better). The next iteration's critic attempts to falsify the model specifically where it's weakest.
3. **Coverage gap detection** — if a clinically-relevant slice has < `slice_min_n` samples, the result emits without it. The operator sees: "this slice was not graded; expand the eval set."

### 3.4 Bootstrap CI without numpy

The standard literature method is **percentile bootstrap**: resample with replacement N times, compute the statistic on each resample, take the (2.5%, 97.5%) percentiles. The CSIS implementation:

- Pure Python `random.Random` + `statistics.mean` — no numpy / scipy dependency
- 1000 resamples by default (Efron-Tibshirani 1993 recommendation for publication-grade); operator can lower to 200 for faster CI builds
- Seedable RNG for reproducibility — cert hash stays stable across reruns
- Returns `(point, ci_lower, ci_upper)` triple; the grader wraps it with the direction + threshold logic

For production-scale evaluations (>10^5 samples) the operator can swap a numpy-backed bootstrap behind the same `bootstrap_ci()` signature. The contract surface — `DistributionalGraderResult` — is what auditors, dashboards, and the cert hash depend on; the bootstrap is a private implementation detail.

---

## 4. Worked example: Bone Vision's actual eval question

This is the kind of acceptance criterion a real orthopedic-reconstruction model needs to clear before clinical deployment:

> ACCEPT a new model checkpoint iff, on the held-out 523-case validation set:
> 1. Mean ASSD ≤ 0.5mm AND 95% CI excludes 1.0mm
> 2. Mean landmark Euclidean error ≤ 2.0mm
> 3. No anatomical slice (per-vertebra, per-bone) with mean ASSD > 1.5mm
> 4. Worst-case 2.5% of landmarks: error < 5.0mm
> 5. Dice on full bone segmentation ≥ 0.92, CI lower bound ≥ 0.90

Expressed in CSIS:

```python
from csis.verification.distributional_graders import (
    AssdGrader, LandmarkErrorGrader, DiceGrader, Sample,
)

samples = [Sample(case_id=case.id, payload={
    "pred_pts": case.predicted_landmarks,
    "true_pts": case.gold_landmarks,
    "pred_mask": case.predicted_seg,
    "true_mask": case.gold_seg,
    "pred_surface": case.predicted_surface_proj,
    "true_surface": case.gold_surface_proj,
}, slices={"anatomy": case.anatomy, "site": case.scanner_site})
            for case in load_validation_set()]

# Conditions 1, 3 via ASSD with per-anatomy slices
assd = AssdGrader(threshold=0.5, n_bootstrap=1000, slice_min_n=10)
assd_result = assd.evaluate(samples)

# Condition 2 via mean landmark error
lme = LandmarkErrorGrader(threshold=2.0, n_bootstrap=1000)
lme_result = lme.evaluate(samples)

# Condition 5 via Dice with CI-lower-bound pass rule
dice = DiceGrader(threshold=0.92, n_bootstrap=1000)
dice_result = dice.evaluate(samples)

# Condition 4 — worst-tail check — implemented as a custom DistributionalGrader
# that returns the 97.5th percentile of per-sample landmark error
class WorstTailLandmarkGrader(LandmarkErrorGrader):
    name = "landmark_worst_tail"; metric_name = "landmark_p975_mm"
    direction = "lower_is_better"; threshold = 5.0
```

The cert that aggregates these four results is **structurally distinct** from a PR-maintenance cert. Both flow through the same `VerifierCertificate` shape (cross-checkpoint signed, hash-preconditioned, audited) — what changes is which list it populates: `grader_results` (rubric) or `distributional_results` (distributional). The two coexist; a single artifact can have both.

The Auditor's `why-doc` now has factual content like:

> Promote 1 candidate entry from tier=causal. ASSD mean 0.41mm (CI [0.39, 0.43]) PASS · LME 1.34mm (CI [1.28, 1.41]) PASS · Dice 0.93 (CI [0.91, 0.94]) PASS · worst-tail landmark p975 = 4.2mm PASS · slice [anatomy=vertebra-L5] ASSD 1.38mm PASS · slice [anatomy=femoral-neck] ASSD 0.62mm PASS.

That's a cert a regulatory body could read.

---

## 5. What Anthropic's Managed Agents could ship to enable this natively

Three concrete additions to the Managed Agents grader / cert surface, in order of impact:

### 5.1 (must-have) A distributional cert shape

Today `VerifierCertificate.grader_results` is a list of binary verdicts. Add `distributional_results: list[DistributionalGraderResult]` alongside it. Backward-compatible: existing rubric-only graders default to empty. The `DistributionalGraderResult` schema CSIS uses can be copied verbatim — it's seven fields and a list of slices.

The hash-preconditioned promotion semantics carry through unchanged: the cert's content-hash includes the distributional results, so an Auditor signing a why-doc against `cert_hash` is signing against the full evidence including CIs.

### 5.2 (should-have) A `Sample` primitive

Today the grader API is `(artifact) → result`. Distributional eval needs `(samples, artifact) → result` where `samples` is a structured iterable each grader can extract from. Standardizing `Sample(case_id, payload, slices)` (or any equivalent shape) means:

- Multiple distributional graders run over the SAME sample set without each rebuilding the payload (a numpy mask is expensive to construct twice)
- The Critic stage knows which `case_id`s to attack on the next iteration (worst-slice hook returns specific cases, not just scores)
- The Auditor's audit-trail can reference specific samples ("the model failed on cases 042, 113, 217 — the same three that failed last cycle")

### 5.3 (would-be-nice) A native bootstrap-CI fabric

The bootstrap is the part most LLM-eval pipelines reinvent badly. A native `Cert.bootstrap_ci(metric_fn, samples, n=1000, ci=0.95)` utility that returns `(point, lower, upper)` and is reproducible across runs (seeded) would let every distributional grader skip the resampling boilerplate.

Optional later: BCa-corrected (bias-corrected accelerated) CI for skewed distributions; the percentile CI in §3.4 is fine for the symmetric case but mis-covers for distributions with long tails (which medical imaging absolutely has).

### 5.4 The "worst-slice critic" hook

The V2 critic stage's natural shape for distributional outcomes: instead of asking "can you falsify this artifact?" (the rubric framing), ask "the model's worst slice was X with score Y near threshold Z — produce a targeted attack on slice X." The critic gets to focus its falsification budget where the model is weakest. The `DistributionalGrader.worst_slices()` method in CSIS returns exactly this list; an Anthropic-native equivalent on the Managed Agents grader API would let the V2 critic plug in without reinventing the slice-ranking logic.

---

## 6. Why this matters past medical imaging

Three other agent-domains where the distributional shape is the right shape and the rubric shape misleads:

**Coding agents on real software.** SWE-bench measures the binary pass/fail of a single PR. But a real coding agent's downstream owner cares about distributional things: what fraction of bug fixes still pass at HEAD+30 commits (regression rate); how often the PR introduces a different bug elsewhere (collateral failure rate); what the p95 latency of the agent's response is across N issues. None of these are rubric-shaped.

**Scientific reasoning agents.** Drug-discovery agents predict binding affinity (Ki, IC50) — continuous outcomes with per-protein-family slicing matters more than the mean. A model that scores 1.2 log-units MAE overall but 4.7 log-units MAE on kinases (the most therapeutically actionable family) is worse than a model with 1.8 log-units MAE evenly distributed. Rubric eval doesn't say this; distributional with `slice_min_n=10` per family does.

**Robotics agents.** Trajectory error in mm, success rate across N environments with per-environment-type slices. The whole evaluation literature is distributional. Currently this is held outside any LLM eval framework because the LLM eval framework doesn't carry CIs and slices natively.

The general principle: **wherever the right answer to "is the model good" is a number with uncertainty rather than a checkbox, the cert needs to carry the number AND the uncertainty.** This is most agent domains worth caring about beyond chatbots.

---

## 7. What's in this repo now

| What | Where | Lines |
|---|---|---|
| Schema (`DistributionalGraderResult`, `GraderSlice`, cert extension) | [`csis/contracts.py`](../../csis/contracts.py) | +60 |
| Per-sample metrics (Dice, IoU, Euclidean, landmark, Hausdorff) | [`csis/verification/distributional_graders.py`](../../csis/verification/distributional_graders.py) | 80 |
| Bootstrap CI (percentile method, seeded) | same file | 35 |
| `Sample` primitive + `DistributionalGrader` ABC + concrete graders (Dice, IoU, LandmarkError, ASSD) | same file | 200 |
| Regression tests (31 tests covering metric correctness, CI shape, pass semantics, slicing, schema round-trip) | [`tests/test_distributional_graders.py`](../../tests/test_distributional_graders.py) | 270 |

Total: ~640 LOC for a complete, runnable distributional-grader layer that the V1 critic can extend, the V2 auditor can sign, and the live dashboard can render. Pure stdlib — no numpy, no scipy, no plotting dependency. Production users can swap in numpy under the same contract.

## 8. Future work

- **BCa CI** for skewed distributions
- **Permutation tests** for between-model comparisons ("is model B significantly better than A on the worst slice?")
- **Calibration graders** (ECE, MCE) that are themselves distributional
- **Coverage analysis** — when a slice is too small, emit a structured "needs more data on slice X" event instead of silently dropping it
- **Plot artifacts** — the dashboard could render box-and-whisker plots per slice; the simulated demo at `/dashboard-demo.html` is a natural home for showing distributional graders alongside rubric ones

## Sources

- Maier-Hein, L., et al. "Metrics reloaded: pitfalls and recommendations for image analysis validation." *Nature Methods* (2024). [arXiv:2206.01653](https://arxiv.org/abs/2206.01653)
- Reinke, A., et al. "Common Limitations of Image Processing Metrics: A Picture Story." [arXiv:2104.05642](https://arxiv.org/abs/2104.05642) (2023).
- Müller, D., Soto-Rey, I., Kramer, F. "Towards a guideline for evaluation metrics in medical image segmentation." [BMC Research Notes (2022)](https://link.springer.com/article/10.1186/s13104-022-06096-y).
- Mehta, R., Filos, A., et al. "Confidence intervals for performance estimates in brain MRI segmentation." [Medical Image Analysis (2025)](https://www.sciencedirect.com/science/article/abs/pii/S1361841525001124).
- Efron, B., Tibshirani, R. *An Introduction to the Bootstrap.* Chapman & Hall, 1993. (Percentile CI method, ch. 13.)
- Arawjo, I., et al. "LLM-RUBRIC: A Multidimensional, Calibrated Approach to Automated Evaluation of Natural Language Texts." [arXiv:2501.00274](https://arxiv.org/abs/2501.00274) (2025).
- OpenAI HealthBench (2025) — Instance-Specific Rubrics, 260+ physician authors, 48,562 criteria.
- Hashemi, et al. "Calibration of AI large language models with human subject matter experts for grading of clinical short-answer responses in dental education." [PMC12896245 (2026)](https://www.ncbi.nlm.nih.gov/pmc/articles/PMC12896245/).
