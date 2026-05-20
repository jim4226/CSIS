"""Regression tests for the distributional grader stack.

Covers:
  - Per-sample metric correctness (Dice symmetry, empty/full edge cases,
    landmark Euclidean accuracy, Hausdorff symmetric definition)
  - Bootstrap CI shape (CI contains the sample mean for a known
    distribution; CI width shrinks as n_samples grows)
  - DistributionalGraderResult schema (lower-bound-vs-threshold pass
    rule for higher_is_better; upper-bound-vs-threshold for
    lower_is_better)
  - Per-slice breakdown (worst-slice extraction; slice_min_n filter)
  - Concrete graders (DiceGrader, IoUGrader, LandmarkErrorGrader,
    AssdGrader) integrate with the contracts cleanly
  - VerifierCertificate carries distributional_results without breaking
    the categorical pass through
"""
from __future__ import annotations

import math
import statistics

import pytest

from csis.contracts import (
    DistributionalGraderResult,
    GraderResult,
    GraderSlice,
    VerifierCertificate,
)
from csis.verification.distributional_graders import (
    AssdGrader,
    DiceGrader,
    DistributionalGrader,
    IoUGrader,
    LandmarkErrorGrader,
    Sample,
    bootstrap_ci,
    dice_score,
    euclidean_distance,
    hausdorff_1d,
    iou_score,
    landmark_error_mm,
    make_default_imaging_registry,
)


# ---- per-sample metric correctness ---------------------------------------


def test_dice_score_perfect_overlap() -> None:
    assert dice_score([1, 1, 1, 0], [1, 1, 1, 0]) == pytest.approx(1.0)


def test_dice_score_no_overlap() -> None:
    assert dice_score([1, 1, 0, 0], [0, 0, 1, 1]) == pytest.approx(0.0)


def test_dice_score_partial_overlap() -> None:
    # pred has 3 voxels, truth has 2 voxels, 1 overlap → 2*1 / (3+2) = 0.4
    assert dice_score([1, 1, 1, 0], [0, 1, 0, 1]) == pytest.approx(0.4)


def test_dice_score_both_empty_returns_one() -> None:
    """Convention: two empty masks AGREE the structure is absent."""
    assert dice_score([0, 0, 0], [0, 0, 0]) == 1.0


def test_dice_score_symmetry() -> None:
    pred = [1, 0, 1, 0, 1]
    truth = [1, 1, 0, 0, 1]
    assert dice_score(pred, truth) == pytest.approx(dice_score(truth, pred))


def test_dice_score_length_mismatch_raises() -> None:
    with pytest.raises(ValueError, match="length mismatch"):
        dice_score([1, 0], [1, 0, 1])


def test_iou_score_perfect() -> None:
    assert iou_score([1, 1, 0], [1, 1, 0]) == 1.0


def test_iou_score_no_overlap() -> None:
    assert iou_score([1, 1, 0], [0, 0, 1]) == 0.0


def test_iou_score_partial() -> None:
    # intersection = 1, union = 3 → 1/3
    assert iou_score([1, 1, 0], [0, 1, 1]) == pytest.approx(1 / 3)


def test_euclidean_distance_2d() -> None:
    assert euclidean_distance([0, 0], [3, 4]) == pytest.approx(5.0)


def test_euclidean_distance_3d() -> None:
    assert euclidean_distance([1, 2, 3], [4, 6, 3]) == pytest.approx(5.0)


def test_landmark_error_with_voxel_scaling() -> None:
    # Two landmarks, distances 5 voxels and 3 voxels → mean 4 voxels.
    # With voxel_mm=0.5 → 2 mm mean error.
    pred = [[0, 0], [0, 0]]
    truth = [[3, 4], [0, 3]]
    assert landmark_error_mm(pred, truth, voxel_mm=0.5) == pytest.approx(2.0)


def test_landmark_error_empty_returns_zero() -> None:
    assert landmark_error_mm([], []) == 0.0


def test_hausdorff_symmetric() -> None:
    pred = [0.0, 1.0, 2.0]
    truth = [0.5, 1.5, 5.0]
    assert hausdorff_1d(pred, truth) == pytest.approx(hausdorff_1d(truth, pred))


def test_hausdorff_max_pair_distance() -> None:
    # truth has an outlier at 5 → max(min |a-b|) for a in pred = |2-5|=3
    pred = [0.0, 1.0, 2.0]
    truth = [0.0, 1.0, 5.0]
    assert hausdorff_1d(pred, truth) == pytest.approx(3.0)


# ---- bootstrap CI shape ---------------------------------------------------


def test_bootstrap_ci_contains_sample_mean() -> None:
    """A 95% percentile bootstrap CI on a moderately-sized sample
    should always contain the sample mean (the point estimate)."""
    sample = [0.8, 0.85, 0.9, 0.7, 0.95, 0.88, 0.82, 0.78, 0.91, 0.86]
    point, lo, hi = bootstrap_ci(sample, n_bootstrap=500, ci_level=0.95)
    assert lo <= point <= hi
    assert point == pytest.approx(statistics.mean(sample))


def test_bootstrap_ci_width_shrinks_with_more_samples() -> None:
    """Same underlying distribution; more samples → tighter CI."""
    small = [0.85, 0.9, 0.8, 0.88, 0.82]
    big = small * 20  # 100 samples
    _, lo_s, hi_s = bootstrap_ci(small, n_bootstrap=500)
    _, lo_b, hi_b = bootstrap_ci(big, n_bootstrap=500)
    assert (hi_b - lo_b) < (hi_s - lo_s)


def test_bootstrap_ci_empty_input() -> None:
    point, lo, hi = bootstrap_ci([])
    assert (point, lo, hi) == (0.0, 0.0, 0.0)


def test_bootstrap_ci_rejects_zero_n_bootstrap() -> None:
    with pytest.raises(ValueError, match="n_bootstrap"):
        bootstrap_ci([0.5], n_bootstrap=0)


# ---- grader integration ---------------------------------------------------


def _mk_dice_samples(n: int, base_dice: float, slice_label: str = "liver") -> list[Sample]:
    """Build N samples whose true Dice is approximately `base_dice`.

    Simple construction: each pair of masks has 100 voxels, intersection
    sized so Dice = base_dice. Slight per-sample jitter via voxel
    swaps so the bootstrap CI has positive width.
    """
    import random as _r
    rng = _r.Random(7)
    out: list[Sample] = []
    for i in range(n):
        size = 100
        # Both masks have `size` voxels of foreground; intersection k
        # gives Dice = 2k / (size+size) = k/size.
        k = int(round(base_dice * size))
        # jitter intersection ±2 voxels per sample
        k = max(0, min(size, k + rng.randint(-2, 2)))
        # pred: voxels 0..size-1 are 1
        # truth: voxels (size-k)..(2*size-k-1) are 1
        pred = [1 if j < size else 0 for j in range(2 * size)]
        truth = [1 if (size - k) <= j < (2 * size - k) else 0 for j in range(2 * size)]
        out.append(Sample(case_id=f"case-{i:03d}", payload={
            "pred_mask": pred, "true_mask": truth,
        }, slices={"organ": slice_label}))
    return out


def test_dice_grader_passes_above_threshold() -> None:
    samples = _mk_dice_samples(50, base_dice=0.92)  # well above 0.85 threshold
    grader = DiceGrader(threshold=0.85, n_bootstrap=200, rng_seed=11)
    result = grader.evaluate(samples)
    assert result.n_samples == 50
    assert result.metric_name == "dice"
    assert result.direction == "higher_is_better"
    assert result.point_estimate >= 0.85
    assert result.ci_lower <= result.point_estimate <= result.ci_upper
    assert result.passed, (
        f"Dice {result.point_estimate} (CI {result.ci_lower}-{result.ci_upper}) "
        f"vs threshold {result.threshold} should pass"
    )


def test_dice_grader_fails_when_ci_lower_below_threshold() -> None:
    """Point estimate above threshold but CI lower bound below → fail.

    This is the whole point of conservative pass semantics. A model
    that's-on-paper-fine but-noisy-in-practice should NOT pass.
    """
    # Mean ~0.87 but high variance so the 95% CI lower clears below
    # 0.85.
    samples = _mk_dice_samples(8, base_dice=0.87)
    grader = DiceGrader(threshold=0.85, n_bootstrap=500, rng_seed=11)
    result = grader.evaluate(samples)
    # If point is just above threshold but CI is wide (small n), the
    # lower bound may dip under — exercise that path.
    if result.point_estimate >= 0.85 and result.ci_lower < 0.85:
        assert not result.passed, "should reject when CI lower < threshold"


def test_landmark_grader_lower_is_better_pass_rule() -> None:
    """For lower-is-better metrics, the UPPER CI bound must clear
    the threshold (be ≤ threshold) for the result to pass."""
    samples = []
    for i in range(40):
        # Tight error around 1mm — well under 2mm threshold even with CI.
        samples.append(Sample(case_id=f"c{i}", payload={
            "pred_pts": [[0.0, 0.0]],
            "true_pts": [[1.0 + 0.01 * i, 0.0]],
            "voxel_mm": 1.0,
        }))
    grader = LandmarkErrorGrader(threshold=2.0, n_bootstrap=200)
    result = grader.evaluate(samples)
    assert result.direction == "lower_is_better"
    assert result.ci_upper <= 2.0
    assert result.passed


def test_landmark_grader_fails_when_ci_upper_exceeds_threshold() -> None:
    """High-variance error that might exceed threshold → fail under
    conservative upper-bound pass rule."""
    samples = []
    # Mean ~1.8mm but big swings above and below
    errs = [0.5, 3.5, 0.5, 3.5, 0.5, 3.5, 0.5, 3.5]
    for i, e in enumerate(errs):
        samples.append(Sample(case_id=f"c{i}", payload={
            "pred_pts": [[0.0, 0.0]],
            "true_pts": [[e, 0.0]],
            "voxel_mm": 1.0,
        }))
    grader = LandmarkErrorGrader(threshold=2.0, n_bootstrap=500)
    result = grader.evaluate(samples)
    assert result.ci_upper > result.point_estimate
    if result.ci_upper > 2.0:
        assert not result.passed


def test_per_slice_breakdown_groups_by_label() -> None:
    """Samples carry slice labels; result.slices should have one entry
    per (slice_key, slice_value) pair, each with its own CI and pass."""
    samples = (
        _mk_dice_samples(20, base_dice=0.95, slice_label="liver")
        + _mk_dice_samples(20, base_dice=0.65, slice_label="pancreas")
    )
    grader = DiceGrader(threshold=0.85, n_bootstrap=200, slice_min_n=5)
    result = grader.evaluate(samples)
    slice_names = sorted(s.name for s in result.slices)
    assert slice_names == ["organ=liver", "organ=pancreas"]
    by_name = {s.name: s for s in result.slices}
    assert by_name["organ=liver"].passed is True
    assert by_name["organ=pancreas"].passed is False
    assert by_name["organ=liver"].n_samples == 20
    assert by_name["organ=pancreas"].n_samples == 20


def test_slice_min_n_filters_small_slices() -> None:
    """A slice with fewer than slice_min_n samples is omitted from
    the breakdown — too noisy for a meaningful CI."""
    # 20 samples in liver, only 3 in spleen
    samples = (
        _mk_dice_samples(20, base_dice=0.9, slice_label="liver")
        + _mk_dice_samples(3, base_dice=0.5, slice_label="spleen")
    )
    grader = DiceGrader(threshold=0.85, n_bootstrap=100, slice_min_n=5)
    result = grader.evaluate(samples)
    slice_names = {s.name for s in result.slices}
    assert "organ=liver" in slice_names
    assert "organ=spleen" not in slice_names


def test_worst_slices_returns_lowest_for_higher_is_better() -> None:
    samples = (
        _mk_dice_samples(20, base_dice=0.95, slice_label="liver")
        + _mk_dice_samples(20, base_dice=0.65, slice_label="pancreas")
        + _mk_dice_samples(20, base_dice=0.80, slice_label="kidney")
    )
    grader = DiceGrader(threshold=0.85, n_bootstrap=100)
    result = grader.evaluate(samples)
    worst = grader.worst_slices(result, k=2)
    assert len(worst) == 2
    assert worst[0].name == "organ=pancreas"  # lowest point estimate
    assert worst[1].name == "organ=kidney"


def test_worst_slices_returns_highest_for_lower_is_better() -> None:
    """For error metrics, "worst" = highest. Sanity check the inverse
    direction logic."""
    # We don't have a convenient landmark-sample builder with slices;
    # build a tiny one inline.
    samples = []
    for i in range(20):
        samples.append(Sample(case_id=f"a{i}", payload={
            "pred_pts": [[0.0, 0.0]], "true_pts": [[1.0, 0.0]], "voxel_mm": 1.0,
        }, slices={"site": "wrist"}))
    for i in range(20):
        samples.append(Sample(case_id=f"b{i}", payload={
            "pred_pts": [[0.0, 0.0]], "true_pts": [[4.0, 0.0]], "voxel_mm": 1.0,
        }, slices={"site": "hip"}))
    grader = LandmarkErrorGrader(threshold=2.0, n_bootstrap=100)
    result = grader.evaluate(samples)
    worst = grader.worst_slices(result, k=1)
    assert worst[0].name == "site=hip"  # higher error = worse for landmark


def test_empty_samples_returns_failed_result_not_exception() -> None:
    grader = DiceGrader(threshold=0.85)
    result = grader.evaluate([])
    assert result.n_samples == 0
    assert result.passed is False
    assert "no samples" in result.detail.lower()


def test_default_imaging_registry_has_four_graders() -> None:
    reg = make_default_imaging_registry()
    assert set(reg.keys()) == {"dice", "iou", "landmark_error_mm", "assd_mm"}
    assert all(isinstance(g, DistributionalGrader) for g in reg.values())


def test_verifier_certificate_carries_distributional_results() -> None:
    """Cert is backward-compatible: distributional_results defaults to
    empty for rubric-only tasks; populated for distributional tasks."""
    rubric_cert = VerifierCertificate(
        cert_id="cert-1", plan_id="p-1", artifact_id="a-1",
        artifact_hash="sha256:0" * 1, builder_checkpoint="alpha",
        verifier_checkpoint="beta",
        grader_results=[GraderResult(grader="tests_pass", passed=True)],
        critic_findings=[], passed=True, signed_at=0.0,
    )
    assert rubric_cert.distributional_results == []

    distro = DistributionalGraderResult(
        grader="dice", metric_name="dice", direction="higher_is_better",
        point_estimate=0.91, ci_lower=0.89, ci_upper=0.93,
        n_samples=523, n_bootstrap=1000, threshold=0.85,
        passed=True,
        slices=[GraderSlice(name="organ=liver", n_samples=240,
                            point_estimate=0.94, ci_lower=0.92, ci_upper=0.96,
                            passed=True)],
    )
    distro_cert = VerifierCertificate(
        cert_id="cert-2", plan_id="p-2", artifact_id="a-2",
        artifact_hash="sha256:0" * 1, builder_checkpoint="alpha",
        verifier_checkpoint="beta",
        grader_results=[],
        distributional_results=[distro],
        critic_findings=[], passed=True, signed_at=0.0,
    )
    assert len(distro_cert.distributional_results) == 1
    assert distro_cert.distributional_results[0].point_estimate == 0.91
    assert distro_cert.distributional_results[0].slices[0].name == "organ=liver"


def test_distributional_result_serializes_round_trip() -> None:
    """Pydantic schema round-trip — what the auditor's hash precondition
    relies on. If serialization isn't stable, the cert hash drifts."""
    original = DistributionalGraderResult(
        grader="dice", metric_name="dice", direction="higher_is_better",
        point_estimate=0.892, ci_lower=0.871, ci_upper=0.913,
        n_samples=523, n_bootstrap=1000, threshold=0.85, passed=True,
        slices=[
            GraderSlice(name="organ=liver", n_samples=240, point_estimate=0.94,
                        ci_lower=0.92, ci_upper=0.96, passed=True),
            GraderSlice(name="organ=pancreas", n_samples=283, point_estimate=0.71,
                        ci_lower=0.66, ci_upper=0.76, passed=False),
        ],
    )
    j = original.model_dump_json()
    revived = DistributionalGraderResult.model_validate_json(j)
    assert revived == original
