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

import hashlib
import math
import random
import statistics
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Callable, Iterable, Sequence

from csis.contracts import DistributionalGraderResult, GraderSlice


def _derive_seed(base_seed: int, *parts: object) -> int:
    """Deterministically derive a 32-bit RNG seed from a base seed + parts.

    Vf2 (cycle 10): used to give the main estimate and each slice an
    INDEPENDENT, reproducible RNG. We deliberately avoid the builtin
    ``hash()`` here — it is salted by ``PYTHONHASHSEED`` for str/bytes, so
    ``hash((seed, slice_name))`` would differ across processes and the cert
    hash would NOT stay stable across reruns. ``hashlib.sha256`` over a
    canonical string is process-independent.
    """
    key = "|".join([str(base_seed)] + [str(p) for p in parts])
    digest = hashlib.sha256(key.encode("utf-8")).digest()
    return int.from_bytes(digest[:4], "big")


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

    Vf4 (cycle 10): the distance is UNDEFINED when either point set is
    empty — there is no nearest point to measure to. The previous
    behaviour returned ``float("inf")``, which (a) silently corrupts to
    JSON ``null`` on a signed cert and (b) launders into the aggregate as
    a non-finite metric (Vf3). We now RAISE so the degenerate sample is
    quarantined by the caller rather than emitting a non-finite value.
    """
    if not pred or not truth:
        raise ValueError(
            "hausdorff_1d is undefined for an empty point set "
            f"(pred={len(pred)} pts, truth={len(truth)} pts); the sample must "
            f"be quarantined rather than scored as inf. See cycle-10 Vf4/Vf3."
        )
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
    # Vf3 (cycle 10): a single non-finite per-sample metric used to launder
    # into passed=True. Python's sort is undefined in the presence of NaN, so
    # the percentile slot could return a finite value while the point estimate
    # (mean incl. NaN) was NaN — and _passed did NaN/finite comparisons with no
    # guard. Reject any non-finite sample HERE, before aggregation, as a hard
    # verification failure. (Callers that want drop-and-record semantics should
    # filter + count before calling; this chokepoint refuses to produce a CI
    # from poisoned input.)
    bad = [x for x in sample_metrics if not math.isfinite(x)]
    if bad:
        raise ValueError(
            f"bootstrap_ci received {len(bad)} non-finite sample metric(s) "
            f"(e.g. {bad[0]!r}) out of {len(sample_metrics)}; a NaN/inf sample "
            f"must never be aggregated into a passable CI. See cycle-10 Vf3."
        )
    rng = rng or random.Random(42)
    # verification-K1 (cycle-13): canonicalize the input order before the
    # resample loop. The loop draws a FIXED index sequence from the seeded RNG
    # and maps it through sample_metrics[idx], so a permutation of the input
    # yields a different realized CI even though the statistic (mean) is
    # exchangeable and the TRUE bootstrap distribution is order-invariant.
    # Sorting a local copy makes ci_lower/ci_upper — and thus the signed
    # PASS/FAIL and the cert hash — a pure function of the value multiset + seed,
    # completing the determinism guarantee Vf2 established for evaluate().
    sample_metrics = sorted(sample_metrics)
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
        min_nonempty_truth_fraction: float = 0.0,
        min_main_n: int | None = None,
    ) -> None:
        self.threshold = threshold if threshold is not None else self.threshold
        self.n_bootstrap = n_bootstrap
        self.ci_level = ci_level
        self.slice_min_n = slice_min_n
        # verification-K2 (cycle-13): a minimum-n floor on the MAIN estimate,
        # mirroring slice_min_n. Slices are dropped below slice_min_n precisely
        # because a bootstrap CI over <5 samples is meaningless — but the main
        # estimate had NO such floor, so a single cherry-picked sample produced
        # a zero-width "95% CI" that cleared the threshold, making the
        # conservative-CI guarantee vacuous. Defaults to slice_min_n.
        self.min_main_n = min_main_n if min_main_n is not None else slice_min_n
        # Vf6 (cycle 10): optional guard. Both-empty masks score 1.0 by
        # convention (Dice/IoU agree the structure is absent). An all-empty-
        # ground-truth eval set therefore scores a perfect pass for ANY
        # prediction. When this fraction is > 0, evaluate() refuses to pass a
        # batch unless at least this fraction of cases have NON-EMPTY ground
        # truth. Default 0.0 preserves the legacy convention but the degenerate
        # counts are ALWAYS surfaced in detail so the pass is never silent.
        self.min_nonempty_truth_fraction = min_nonempty_truth_fraction
        # Vf2 (cycle 10): store the SEED, not a long-lived Random. A shared,
        # never-reset Random made the verdict depend on call count and slice
        # ordering — same grader + same data gave different CIs across
        # consecutive evaluate() calls, with a demonstrated PASS<->FAIL flip.
        # evaluate() now derives a fresh, independently-seeded Random for the
        # main estimate and for EACH slice from this fixed seed.
        self._rng_seed = rng_seed
        # Back-compat: keep an attribute named _rng so any external reference
        # still resolves; it is NOT used by evaluate() anymore.
        self._rng = random.Random(rng_seed)

    @abstractmethod
    def per_sample_metric(self, sample: Sample) -> float:
        """Compute the per-sample metric. Subclass-specific."""

    def _degeneracy(self, sample: Sample) -> str | None:
        """Vf6 (cycle 10): classify a sample as degenerate, or None.

        Subclasses whose metric auto-scores a perfect value on empty inputs
        (Dice/IoU return 1.0 when both masks are empty) override this to
        report ``"both_empty"`` / ``"empty_truth"`` etc. The base
        ``evaluate`` counts these and surfaces them in ``detail`` so a batch
        that passes only because the ground truth is empty is never silent.
        Default: no degeneracy notion.
        """
        return None

    # ------------------------------------------------------------------

    def _passed(self, ci_lower: float, ci_upper: float) -> bool:
        """Conservative pass rule using the CI bound, not the point.

        For "higher is better" metrics: lower bound must clear the
        threshold (don't accept a model whose true performance might
        be below the bar even though the point estimate is above).

        For "lower is better": upper bound must stay under the
        threshold (don't accept a model whose true error might exceed
        the bar).

        Vf3 (cycle 10): a non-finite CI bound must NEVER read as a pass. A
        NaN comparison (`nan >= t`) is always False, but `inf <= t` /
        `-inf >= t` can read True and a NaN bound that slipped through must
        not be trusted either. Hard-gate on finiteness of BOTH bounds first.
        """
        if not (math.isfinite(ci_lower) and math.isfinite(ci_upper)):
            return False
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

        # Vf6 (cycle 10): tally degenerate cases (e.g. Dice/IoU both-empty,
        # which auto-score 1.0) so a batch that "passes" only because the
        # ground truth is empty is never silent.
        degeneracy_counts: dict[str, int] = {}
        for s in samples:
            kind = self._degeneracy(s)
            if kind is not None:
                degeneracy_counts[kind] = degeneracy_counts.get(kind, 0) + 1
        n_empty_truth = degeneracy_counts.get("both_empty", 0) + degeneracy_counts.get(
            "empty_truth", 0
        )
        n_nonempty_truth = len(samples) - n_empty_truth
        nonempty_truth_fraction = n_nonempty_truth / len(samples)

        # Vf2 (cycle 10): fresh, independently-seeded RNG for the MAIN estimate
        # derived from the fixed seed. Re-seeding here makes evaluate()
        # byte-reproducible across consecutive calls (no shared mutable state).
        main_rng = random.Random(_derive_seed(self._rng_seed, "__main__"))
        point, lo, hi = bootstrap_ci(
            per_sample,
            n_bootstrap=self.n_bootstrap,
            ci_level=self.ci_level,
            rng=main_rng,
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

        # Vf5 (cycle 10): record the resample count ACTUALLY used per slice.
        slice_n_bootstrap = min(self.n_bootstrap, 200)
        slice_results: list[GraderSlice] = []
        for (k, v), bucket in sorted(slice_buckets.items()):
            if len(bucket) < self.slice_min_n:
                continue  # too few samples for meaningful CI
            slice_name = f"{k}={v}"
            # Vf2: each slice gets its OWN RNG, seeded only from the fixed seed
            # and the slice name — so a slice CI depends only on its own data
            # plus the seed, never on sibling slices or call order.
            slice_rng = random.Random(_derive_seed(self._rng_seed, slice_name))
            s_point, s_lo, s_hi = bootstrap_ci(
                bucket,
                n_bootstrap=slice_n_bootstrap,
                ci_level=self.ci_level,
                rng=slice_rng,
            )
            slice_results.append(GraderSlice(
                name=slice_name,
                n_samples=len(bucket),
                point_estimate=round(s_point, 6),
                ci_lower=round(s_lo, 6),
                ci_upper=round(s_hi, 6),
                passed=self._passed(s_lo, s_hi),
                n_bootstrap=slice_n_bootstrap,
            ))

        passed = self._passed(lo, hi)

        # verification-K2 (cycle-13): floor the MAIN estimate's sample count.
        # A pass on fewer than min_main_n samples is not statistically
        # meaningful (with n=1 the bootstrap can only resample the one value, so
        # ci_lower==ci_upper==that value and any single good sample clears the
        # bar). Only gate when there IS a bar (threshold set); report-only mode
        # stays report-only.
        detail_parts: list[str] = []
        if self.threshold is not None and len(samples) < self.min_main_n:
            passed = False
            detail_parts.append(
                f"GUARD_FAILED: n_samples={len(samples)} < min_main_n="
                f"{self.min_main_n}; a CI on too few samples is degenerate and "
                f"cannot clear the threshold (cycle-13 verification-K2)"
            )

        # Vf6: degeneracy report + optional guard.
        if degeneracy_counts:
            detail_parts.append(
                "degenerate_cases="
                + ",".join(f"{k}:{degeneracy_counts[k]}" for k in sorted(degeneracy_counts))
            )
            detail_parts.append(
                f"nonempty_truth={n_nonempty_truth}/{len(samples)} "
                f"({nonempty_truth_fraction:.3f})"
            )
        if (
            self.min_nonempty_truth_fraction > 0.0
            and nonempty_truth_fraction < self.min_nonempty_truth_fraction
        ):
            passed = False
            detail_parts.append(
                f"GUARD_FAILED: nonempty-truth fraction {nonempty_truth_fraction:.3f} "
                f"< required {self.min_nonempty_truth_fraction:.3f}; an all/mostly-"
                f"empty-ground-truth batch cannot pass (cycle-10 Vf6)"
            )

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
            passed=passed,
            slices=slice_results,
            detail="; ".join(detail_parts),
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


def _mask_degeneracy(pred: Sequence[int], truth: Sequence[int]) -> str | None:
    """Vf6 (cycle 10): classify a (pred, truth) mask pair for Dice/IoU.

    Returns ``"both_empty"`` when neither mask has any foreground (the case
    that auto-scores 1.0), ``"empty_truth"`` when only the ground truth is
    empty (a non-empty prediction is unverifiable against an absent
    structure), else None.
    """
    truth_empty = not any(truth)
    pred_empty = not any(pred)
    if truth_empty and pred_empty:
        return "both_empty"
    if truth_empty:
        return "empty_truth"
    return None


class DiceGrader(DistributionalGrader):
    """Per-case Dice score over a segmentation evaluation set."""

    name = "dice"
    metric_name = "dice"
    direction = "higher_is_better"
    threshold = 0.85

    def per_sample_metric(self, sample: Sample) -> float:
        return dice_score(sample.payload["pred_mask"], sample.payload["true_mask"])

    def _degeneracy(self, sample: Sample) -> str | None:
        # Vf6: surface both-empty / empty-truth cases that auto-score 1.0.
        return _mask_degeneracy(sample.payload["pred_mask"], sample.payload["true_mask"])


class IoUGrader(DistributionalGrader):
    """Per-case IoU (Jaccard) over a segmentation evaluation set."""

    name = "iou"
    metric_name = "iou"
    direction = "higher_is_better"
    threshold = 0.75

    def per_sample_metric(self, sample: Sample) -> float:
        return iou_score(sample.payload["pred_mask"], sample.payload["true_mask"])

    def _degeneracy(self, sample: Sample) -> str | None:
        # Vf6: surface both-empty / empty-truth cases that auto-score 1.0.
        return _mask_degeneracy(sample.payload["pred_mask"], sample.payload["true_mask"])


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
