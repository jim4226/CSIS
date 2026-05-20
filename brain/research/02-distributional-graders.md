# 02 — Distributional V1 Graders

**Where it lives in the architecture.** `CSIS-architecture.html` §10 (verification stack) splits the Verifier into V1 (programmatic graders) → V5 (calibration). The PR-maintenance grader set in `csis/verification/graders.py` is V1, binary: `tests_pass`, `lint`, `typecheck`, `coverage_delta`, `diff_scope`, `perf_regression`. That covers the "code and math" domains where ground truth is yes/no. It does not cover the "fuzzy domain" §16 explicitly flags as Open Research Question #1.

This doc specifies a second flavor of V1 grader — *distributional* — that handles the case where the "good" criterion is a scalar metric over a held-out sample. The same primitive applies across at least six domains we've sketched configs for: clinical imaging, search ranking, forecasting, classification, LLM eval, and recommendation. Clinical is one example of the shape, not the special case.

---

## 1. The gap

A binary grader collapses an artifact to a single bit. That is the right abstraction when the underlying check is mechanical: pytest exit code is 0 or it isn't; mypy errors or it doesn't.

Many real eval problems are not mechanical. They all share the same shape — central tendency + tail watermark + held-out sample — but the units, direction, and tail-relevant statistic differ:

| Domain | Metric (one of many) | Direction | Tail statistic | Why the tail matters |
|---|---|---|---|---|
| Clinical imaging | Dice score | higher | p10 | The worst-segmented cases are the ones that hurt patients |
| Clinical imaging | Landmark RMSE (mm) | lower | p90 | Sub-mm precision must hold on the hardest scans |
| Search ranking | nDCG@10 | higher | p10 | The lowest-served queries drive user churn |
| Forecasting | MAE | lower | p90 | The worst-forecast windows blow up inventory |
| Classification | F1-macro | higher | p10 | The worst-served class is a fairness failure |
| LLM eval | win-rate vs baseline | higher | mean | Per-prompt 0/1 — mean *is* the tail signal |
| Recommendation | Hit@10 | higher | p10 | The lowest-served user segments are the churn cohort |

Median-of-50 Dice = 0.93 with a p10 = 0.55 is a different model than median 0.92 / p10 = 0.88, even if the means are identical. Same logic for every row above.

The binary V1 graders cannot express "the metric's distribution clears a threshold AND does not regress vs the rolling baseline of recent promoted artifacts." V5 calibration (Phase 2 — Brier / log-loss against held-out outcomes) is the right home for long-horizon confidence calibration, not for the per-iteration gate.

**The pattern that closes the gap is V1 — a programmatic check on the artifact's behavior on a fixed held-out set — with two additions:**

1. The grader returns *summary statistics*, not just `passed: bool`. (`csis/contracts.py:GraderResult` already carries `metrics: dict[str, float]` — this just exercises it.)
2. The grader compares against a *rolling baseline* persisted across iterations, so the threshold tightens as the system improves.

---

## 2. The implementation (this branch)

[`csis/verification/distributional.py`](../../csis/verification/distributional.py)

### 2.1 Three types

```python
@dataclass(frozen=True)
class DistributionalSample:
    metric: str
    values: tuple[float, ...]
    sample_ids: tuple[str, ...] = ()    # for join-on-regression debugging
    def stats(self) -> dict[str, float]: ...   # n, mean, median, p10, p90, stdev, min, max

@dataclass
class RollingBaseline:
    metric: str
    window: int = 50
    history: list[dict] = ...
    path: Path | None = None
    @classmethod
    def load(...) -> "RollingBaseline": ...
    def append(stats, *, artifact_id, ts=None) -> None: ...
    def baseline_stats(key="p10") -> float | None: ...   # median of recent per-iter p10s

@dataclass
class DistributionalThreshold:
    floor: float
    op: Literal[">=", ">", "<=", "<"] = ">="
    summary_stat: str = "mean"
    min_samples: int = 1
    max_regression: float | None = None
    regression_stat: str = "p10"   # flip to "p90" for error metrics
    def evaluate(sample, baseline) -> (passed, detail, metrics_dict): ...
```

### 2.2 The grader factory

`distributional_grader(name=..., threshold=..., baseline=...)` returns a closure that:

- Reads `artifact.extra["metrics_payload"][name]` as a `DistributionalSample` or serialized dict.
- Calls `threshold.evaluate(sample, baseline)`.
- Returns a `GraderResult` with all summary statistics in `metrics`, including `baseline_<stat>` and `regression_<stat>` so the Critic (V2) and the Auditor's why-doc have a real handle on the verdict.

Crucially: the closure does NOT mutate the baseline at evaluate time. Promoting the baseline pre-decision would let a failing artifact contaminate the very watermark its successor will be measured against.

### 2.3 The generic registry builder + preset spec packs

```python
@dataclass
class DistributionalGraderSpec:
    name: str
    threshold: DistributionalThreshold

def make_distributional_registry(
    specs: list[DistributionalGraderSpec],
    *,
    baseline_root: Path | None = None,
    window: int = 50,
) -> tuple[GraderRegistry, dict[str, RollingBaseline]]: ...
```

A "spec pack" is a list of `(name, threshold)` pairs. The builder pairs each spec with a `RollingBaseline` (in-memory or persisted under `baseline_root/<name>.baseline.json`) and pins the resulting grader into a fresh `GraderRegistry`. Adding a new domain = adding a new spec pack.

Six preset packs ship in this module, with thin convenience factories around the generic builder:

| Factory | Spec pack | Metrics |
|---|---|---|
| `make_clinical_imaging_registry` | `CLINICAL_IMAGING_SPECS` | `dice_score`, `boundary_f1`, `landmark_rmse`, `hausdorff_95` |
| `make_search_ranking_registry` | `SEARCH_RANKING_SPECS` | `ndcg_at_10`, `mrr`, `recall_at_10` |
| `make_forecasting_registry` | `FORECASTING_SPECS` | `mae`, `crps`, `pinball_loss_p90` |
| `make_classification_registry` | `CLASSIFICATION_SPECS` | `f1_macro`, `roc_auc`, `precision_at_recall_90` |
| `make_llm_eval_registry` | `LLM_EVAL_SPECS` | `pass_at_1`, `win_rate_vs_baseline`, `judge_score` |
| `make_recommendation_registry` | `RECOMMENDATION_SPECS` | `hit_at_10`, `ndcg_at_10`, `catalog_coverage` |

Floors and regression budgets in the presets are conservative-typical, not authoritative — adopters copy the closest pack and tune to their problem.

Note on **binary-valued metrics** (LLM `pass_at_1`, `win_rate_vs_baseline`): per-prompt outcomes are 0/1, so per-iteration p10 is degenerate. For these the regression watermark is `mean` (= pass rate / win rate), and the spec pack reflects that. The same `DistributionalThreshold` primitive handles continuous Dice scores and binary win-rates without branching.

All pinned graders compose with the existing Verifier — F6 (pinned-grader source-hash drift), cross-checkpoint signing, V2 critic, cert build, and auditor why-doc all keep working unchanged. The `test_every_preset_registry_pins_cleanly_and_passes_drift_check` test enforces this structurally.

---

## 3. Link to the loop

The `run_iteration` 8-step loop in `csis/agents/coordinator.py` does not change. What changes is the data that flows through it:

```
researcher ──► plan ──► builder ──► artifact ───────────────────────┐
                                       │                            │
                                       └─ extra.metrics_payload     │
                                                                    ▼
verifier ◄── V1 graders (distributional + binary) ── V2 critic ── cert
   │
   │ if cert.passed:
   ▼
librarian ──► candidate ──► auditor ──► why-doc ──► PROMOTE
                                                       │
                                                       ▼
                              update_baselines_after_promotion(...)
                                                       │
                                                       ▼
                              rolling baseline JSON on disk
                                                       │
                                                       ▼
                              next iteration's grader reads tighter watermark
```

`update_baselines_after_promotion()` is the explicit link from this iteration's verified gain to the next iteration's threshold. The Coordinator does not auto-call it (intentional — the registry is domain-specific and consumers shouldn't pay for it if they don't use it). A daemon or test harness calls it after `coord.run_iteration()` returns `outcome == "promoted"`. The next iteration's grader instance reads the updated baseline JSON cold.

This is the *continuous* part of "continuous self-improving system" with teeth: every promoted artifact tightens the bar the next one has to clear, and the bar's lower-tail watermark (median of per-iteration p10s) is robust to a single outlier promoted iteration. A regression event is detectable, attributable, and replayable: the persisted baseline file is the audit trail.

Composition with V5 (Phase 2): the same persisted baselines feed calibration scoring. A model whose stated confidence does not predict its measured Dice tail is a calibration failure V5 catches even if individual iterations passed V1.

---

## 4. What this doesn't solve (yet)

- **Per-cohort stratification.** A single Dice distribution can hide that one demographic subgroup regressed while another improved. Phase 1 should add cohort-keyed sub-baselines.
- **Adversarial sample selection.** A buggy/malicious Builder could ship a curated held-out set that flatters the artifact. The same defense as F6 applies — pin the held-out manifest hash at task start and refuse the cert if the manifest drifts. Easy follow-up, not done in this branch.
- **Multi-objective Pareto.** Dice up, landmark RMSE up is currently two independent grader verdicts AND-ed together. A real Bone-Vision build wants Pareto bookkeeping: a strict improvement on one axis with no regression on others is the canonical "verified gain."
- **Confidence-aware metrics.** Brier / log-loss / sharpness checks. Phase 2 — that's V5.

---

## 5. Tests

[`tests/test_distributional_graders.py`](../../tests/test_distributional_graders.py) — 30 tests, covering:

**Primitives**
- Summary statistics correctness (mean, median, p10, p90, single-value edge case)
- Rolling-baseline window enforcement and JSON persistence (write → fresh process → load → baseline survives)
- Median-of-p10s robust to a single outlier promoted iteration
- Higher-is-better and lower-is-better threshold paths
- The silent-regression case (mean still clears floor, p10 collapsed → regression check fails)
- "No baseline yet" first-iteration case
- F6 pinning + drift detection holds with distributional graders in the registry

**Cross-domain registries**
- Generic builder accepts any spec list, pins cleanly, evaluates end-to-end
- Search-ranking happy path + nDCG-below-floor failure
- Forecasting happy path + lower-is-better p90 regression check fires correctly
- Classification happy path
- LLM eval happy path on `pass_at_1` + win-rate regression-against-baseline failure (binary-valued metric path)
- Recommendation happy path
- Clinical imaging happy path + sub-mm-precision-broken failure case
- **Structural invariant:** every preset registry pins cleanly AND every pinned grader's source hash verifies — catches regressions where a new preset shadows an existing grader name with a structurally different closure

**Loop integration**
- Baseline persists across promotions; fresh-process registry reads the watermark cold
- Coordinator runs the full 8-step loop with the clinical registry, the cert carries every distributional grader's full metrics dict, the artifact promotes, the baseline updates, the next iteration's grader sees the tighter watermark

Full suite: 247 passing (217 → 247).
