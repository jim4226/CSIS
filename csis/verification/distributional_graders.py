"""Distributional graders — V1 extension for outcomes-based evaluation.

The original `csis/verification/graders.py` set is **categorical**: each
grader returns `passed: bool` plus optional auxiliary metrics. That
shape works for tasks whose acceptance criterion is naturally
binary — tests pass, lint clean, type-check clean, diff scope
acceptable, perf ratio in band. PR maintenance, lint pipelines, CI
gates: all rubric-shaped.

It does NOT work for **distributional** outcomes — the shape clinical
imaging, scientific reconstruction, calibration, and most regression
tasks actually produce. There, the answer to "is the model good?" is
not a boolean but a distribution: Dice = 0.892 with 95% CI [0.871,
0.913] across N=523 cases, with per-organ breakdown (liver: 0.94,
pancreas: 0.71). A rubric grader that collapses this to one bit
either over-accepts (point estimate above threshold, ignoring CI
width) or over-rejects (any single sample below threshold fails the
whole batch).

This module adds the missing layer. Each `DistributionalGrader`
ingests a sample population, computes a per-sample metric, aggregates
via bootstrap percentile CI, optionally slices by named subsets, and
emits a `DistributionalGraderResult` whose `passed` flag uses
conservative threshold-vs-CI-bound semantics (lower bound clears the
bar for "higher is better"; upper bound stays under the bar for
"lower is better").

Pure stdlib. No numpy / scipy dependency — the CSIS substrate stays
lean. For production-scale evaluations (>10^5 samples) the operator
can swap in numpy-backed implementations; the contract surface is
`DistributionalGraderResult`, which both speak.

Background reading:
- Maier-Hein et al., "Metrics reloaded: pitfalls and recommendations
  for image analysis validation" (2024) — taxonomy of pitfalls in
  segmentation metric selection.
- Reinke et al., "Common Limitations of Image Processing Metrics: A
  Picture Story" (2023) — visual catalog of how naively-chosen
  metrics mislead.
- Bootstrap percentile CI: Efron & Tibshirani 1993, Ch. 13.
"""
from __future__ import annotations

import math
import random
import statistics
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Callable, Iterable, Sequence

from csis.contracts import DistributionalGraderResult, GraderSlice


# ---------------------------------------------------------------------------
# Per-sample metric functions (pure, no I/O)
# ---------------------------------------------------------------------------


def dice_score(pred: Sequence[int], truth: Sequence[int]) -> float:
    """Dice similarity coefficient between two equal-length binary masks.

    Returns a value in [0, 1]: 1 = perfect overlap, 0 = no overlap.
    By convention, two empty masks score 1.0 (both agree the structure
    is absent), not 0/0.

    Inputs are sequences of 0/1 (or any truthy/falsy). Length must
    match — caller's responsibility to align.

        dice([1,1,0,0], [1,0,1,0]) = 2*1 / (2 + 2) = 0.5
    """
    if len(pred) != len(truth):
        raise ValueError(f"length mismatch: pred={len(pred)} truth={len(truth)}")
    sp = sum(1 for x in pred if x)
    st = sum(1 for x in truth if x)
    if sp == 0 and st == 0:
        return 1.0  # convention: both empty = perfect agreement
    inter = sum(1 for p, t in zip(pred, truth) if p and t)
    return (2.0 * inter) / (sp + st)


def iou_score(pred: Sequence[int], truth: Sequence[int]) -> float:
    """Intersection over Union (Jaccard index) for two binary masks."""
    if len(pred) != len(truth):
        raise ValueError(f"length mismatch: pred={len(pred)} truth={len(truth)}")
    inter = sum(1 for p, t in zip(pred, truth) if p and t)
    union = sum(1 for p, t in zip(pred, truth) if p or t)
    if union == 0:
        return 1.0
    return inter / union


def euclidean_distance(p1: Sequence[float], p2: Sequence[float]) -> float:
    """L2 distance between two points of any dimension."""
    if len(p1) != len(p2):
        raise ValueError(f"dim mismatch: {len(p1)} vs {len(p2)}")
    return math.sqrt(sum((a - b) ** 2 for a, b in zip(p1, p2)))


def landmark_error_mm(
    pred_pts: Sequence[Sequence[float]],
    true_pts: Sequence[Sequence[float]],
    voxel_mm: float = 1.0,
) -> float:
    """Mean Euclidean landmark error in millimetres.

    Each input is a list of points (e.g., anatomical landmarks). Same
    landmark must appear at the same index in both lists. `voxel_mm`
    scales from raw coordinate units to mm — useful when landmarks are
    in voxel-space and the scanner's voxel-spacing differs from 1mm.
    """
    if len(pred_pts) != len(true_pts):
        raise ValueError(
            f"landmark count mismatch: pred={len(pred_pts)} true={len(true_pts)}"
        )
    if not pred_pts:
        return 0.0
    errs = [euclidean_distance(p, t) * voxel_mm for p, t in zip(pred_pts, true_pts)]
    return statistics.mean(errs)


def hausdorff_1d(pred: Sequence[float], truth: Sequence[float]) -> float:
    """Symmetric Hausdorff distance on 1-D point sets.

    `max(max_a min_b |a - b|, max_b min_a |a - b|)`. The general N-D
    version takes a distance function; we keep this scalar variant
    for the prototype because most CSIS demos work on extracted
    point clouds at this level of fidelity.
    """
    if not pred or not truth:
        return float("inf")
    def directed(a: Sequence[float], b: Sequence[float]) -> float:
        return max(min(abs(x - y) for y in b) for x in a)
    return max(directed(pred, truth), directed(truth, pred))


# ---------------------------------------------------------------------------
# Bootstrap percentile CI
# ---------------------------------------------------------------------------


def bootstrap_ci(
    sample_metrics: Sequence[float],
    *,
    n_bootstrap: int = 1000,
    ci_level: float = 0.95,
    statistic: Callable[[Sequence[float]], float] = statistics.mean,
    rng: random.Random | None = None,
) -> tuple[float, float, float]:
    """Percentile bootstrap CI for a sample statistic.

    Returns `(point_estimate, ci_lower, ci_upper)`. The bootstrap
    resamples `sample_metrics` with replacement `n_bootstrap` times,
    computes `statistic` on each resample, and returns the requested
    percentiles. 1000 resamples is the conventional default for
    publication-grade reporting (Efron & Tibshirani 1993); 200 is the
    practical minimum.

    The `statistic` callable can be any reduction (mean, median, 25th
    percentile). For symmetric distributions the percentile method
    gives well-calibrated CIs; for very skewed distributions consider
    BCa correction (out of scope here — easy to add as a wrapper).
    """
    if not sample_metrics:
        return 0.0, 0.0, 0.0
    if n_bootstrap < 1:
        raise ValueError(f"n_bootstrap must be >= 1, got {n_bootstrap}")
    rng = rng or random.Random(42)
    point = statistic(sample_metrics)
    resampled_stats: list[float] = []
    n = len(sample_metrics)
    for _ in range(n_bootstrap):
        sample = [sample_metrics[rng.randrange(n)] for _ in range(n)]
        resampled_stats.append(statistic(sample))
    resampled_stats.sort()
    lower_idx = int((1.0 - ci_level) / 2.0 * n_bootstrap)
    upper_idx = int((1.0 - (1.0 - ci_level) / 2.0) * n_bootstrap) - 1
    upper_idx = max(lower_idx, min(n_bootstrap - 1, upper_idx))
    return point, resampled_stats[lower_idx], resampled_stats[upper_idx]


# ---------------------------------------------------------------------------
# Sample populations + grader base class
# ---------------------------------------------------------------------------


@dataclass
class Sample:
    """One observation in a distributional evaluation.

    Carries the raw inputs the grader needs (any shape — depends on the
    grader's per-sample metric), plus optional slice labels and a free-
    form id for traceability. The Verifier passes a list of Samples to
    every `DistributionalGrader`; the grader extracts what it needs.

    The `case_id` is included in the per-slice breakdown's worst-case
    list so the Critic (V2) knows which specific samples to attack on
    the next iteration.
    """

    case_id: str
    payload: dict
    slices: dict[str, str] = field(default_factory=dict)


class DistributionalGrader(ABC):
    """Base class for graders that produce a distribution over samples.

    Subclasses implement `per_sample_metric(sample) -> float`. The base
    `evaluate(samples)` handles aggregation, bootstrap CI, slice
    breakdown, and the threshold-vs-CI-bound pass rule.
    """

    name: str = "distributional"
    metric_name: str = "metric"
    direction: str = "higher_is_better"
    threshold: float | None = None

    def __init__(
        self,
        *,
        threshold: float | None = None,
        n_bootstrap: int = 1000,
        ci_level: float = 0.95,
        slice_min_n: int = 5,
        rng_seed: int = 42,
    ) -> None:
        self.threshold = threshold if threshold is not None else self.threshold
        self.n_bootstrap = n_bootstrap
        self.ci_level = ci_level
        self.slice_min_n = slice_min_n
        self._rng = random.Random(rng_seed)

    @abstractmethod
    def per_sample_metric(self, sample: Sample) -> float:
        """Compute the per-sample metric. Subclass-specific."""

    # ------------------------------------------------------------------

    def _passed(self, ci_lower: float, ci_upper: float) -> bool:
        """Conservative pass rule using the CI bound, not the point.

        For "higher is better" metrics: lower bound must clear the
        threshold (don't accept a model whose true performance might
        be below the bar even though the point estimate is above).

        For "lower is better": upper bound must stay under the
        threshold (don't accept a model whose true error might exceed
        the bar).
        """
        if self.threshold is None:
            return True
        if self.direction == "higher_is_better":
            return ci_lower >= self.threshold
        return ci_upper <= self.threshold

    def evaluate(self, samples: Sequence[Sample]) -> DistributionalGraderResult:
        if not samples:
            return DistributionalGraderResult(
                grader=self.name,
                metric_name=self.metric_name,
                direction=self.direction,  # type: ignore[arg-type]
                point_estimate=0.0,
                ci_lower=0.0,
                ci_upper=0.0,
                ci_level=self.ci_level,
                n_samples=0,
                n_bootstrap=0,
                threshold=self.threshold,
                passed=False,
                slices=[],
                detail="no samples provided",
            )

        per_sample = [self.per_sample_metric(s) for s in samples]
        point, lo, hi = bootstrap_ci(
            per_sample,
            n_bootstrap=self.n_bootstrap,
            ci_level=self.ci_level,
            rng=self._rng,
        )

        # Per-slice breakdown — group by every slice key any sample
        # carried. A sample with slices={"organ": "liver", "modality":
        # "CT"} contributes to TWO slices: ("organ", "liver") and
        # ("modality", "CT").
        slice_buckets: dict[tuple[str, str], list[float]] = {}
        slice_buckets_ids: dict[tuple[str, str], list[str]] = {}
        for s, m in zip(samples, per_sample):
            for k, v in s.slices.items():
                key = (k, v)
                slice_buckets.setdefault(key, []).append(m)
                slice_buckets_ids.setdefault(key, []).append(s.case_id)

        slice_results: list[GraderSlice] = []
        for (k, v), bucket in sorted(slice_buckets.items()):
            if len(bucket) < self.slice_min_n:
                continue  # too few samples for meaningful CI
            s_point, s_lo, s_hi = bootstrap_ci(
                bucket,
                n_bootstrap=min(self.n_bootstrap, 200),
                ci_level=self.ci_level,
                rng=self._rng,
            )
            slice_results.append(GraderSlice(
                name=f"{k}={v}",
                n_samples=len(bucket),
                point_estimate=round(s_point, 6),
                ci_lower=round(s_lo, 6),
                ci_upper=round(s_hi, 6),
                passed=self._passed(s_lo, s_hi),
            ))

        return DistributionalGraderResult(
            grader=self.name,
            metric_name=self.metric_name,
            direction=self.direction,  # type: ignore[arg-type]
            point_estimate=round(point, 6),
            ci_lower=round(lo, 6),
            ci_upper=round(hi, 6),
            ci_level=self.ci_level,
            n_samples=len(samples),
            n_bootstrap=self.n_bootstrap,
            threshold=self.threshold,
            passed=self._passed(lo, hi),
            slices=slice_results,
        )

    def worst_slices(
        self, result: DistributionalGraderResult, *, k: int = 3
    ) -> list[GraderSlice]:
        """Return the k worst-performing slices, for the Critic to attack.

        The V2 critic stage's natural extension for distributional
        outcomes: instead of trying to falsify a single artifact, it
        attacks the slices where the metric is closest to (or below)
        the threshold. This is the "worst-slice hook" the Anthropic
        Managed Agents grader API would benefit from adding natively.
        """
        if self.direction == "higher_is_better":
            return sorted(result.slices, key=lambda s: s.point_estimate)[:k]
        return sorted(result.slices, key=lambda s: -s.point_estimate)[:k]


# ---------------------------------------------------------------------------
# Concrete distributional graders
# ---------------------------------------------------------------------------


class DiceGrader(DistributionalGrader):
    """Per-case Dice score over a segmentation evaluation set."""

    name = "dice"
    metric_name = "dice"
    direction = "higher_is_better"
    threshold = 0.85

    def per_sample_metric(self, sample: Sample) -> float:
        return dice_score(sample.payload["pred_mask"], sample.payload["true_mask"])


class IoUGrader(DistributionalGrader):
    """Per-case IoU (Jaccard) over a segmentation evaluation set."""

    name = "iou"
    metric_name = "iou"
    direction = "higher_is_better"
    threshold = 0.75

    def per_sample_metric(self, sample: Sample) -> float:
        return iou_score(sample.payload["pred_mask"], sample.payload["true_mask"])


class LandmarkErrorGrader(DistributionalGrader):
    """Per-case mean landmark Euclidean error in millimetres.

    The orthopedic reconstruction case — the model emits N landmark
    coordinates per case; the grader computes mean error in mm and
    aggregates. `direction="lower_is_better"` so the pass rule uses
    the upper CI bound.
    """

    name = "landmark_error_mm"
    metric_name = "landmark_euclidean_mm"
    direction = "lower_is_better"
    threshold = 2.0  # mm

    def per_sample_metric(self, sample: Sample) -> float:
        return landmark_error_mm(
            sample.payload["pred_pts"],
            sample.payload["true_pts"],
            voxel_mm=sample.payload.get("voxel_mm", 1.0),
        )


class AssdGrader(DistributionalGrader):
    """Average Symmetric Surface Distance — point-set proxy.

    For the prototype we approximate ASSD with the symmetric
    Hausdorff `hausdorff_1d` on the 1-D projection (extracted along
    the principal axis of the surface). Production should swap in a
    real 3-D ASSD on the full mesh / voxel surface.
    """

    name = "assd_mm"
    metric_name = "assd_mm"
    direction = "lower_is_better"
    threshold = 0.5  # mm

    def per_sample_metric(self, sample: Sample) -> float:
        return hausdorff_1d(
            sample.payload["pred_surface"],
            sample.payload["true_surface"],
        )


# ---------------------------------------------------------------------------
# Registry helpers
# ---------------------------------------------------------------------------


def make_default_imaging_registry() -> dict[str, DistributionalGrader]:
    """Default grader set for medical-imaging / orthopedic-reconstruction
    style evaluations: Dice, IoU, landmark error, ASSD. Each with the
    canonical literature threshold; operators override per task."""
    return {
        "dice": DiceGrader(),
        "iou": IoUGrader(),
        "landmark_error_mm": LandmarkErrorGrader(),
        "assd_mm": AssdGrader(),
    }
