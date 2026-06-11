"""Cycle-10 verification-stack regression tests.

One (or more) test per red-team finding Vf1..Vf7. Each test asserts the
EFFECT of the fix (cycle-6 E1 lesson): it FAILS on the unfixed code and
PASSES once the corresponding chokepoint fix is in place.

Findings:
  Vf1 — cross-checkpoint separation was spoofable by a checkpoint-label
        rename (model_id mirrors checkpoint_id by default; checkpoint_id
        counted toward the distinctness bar).
  Vf2 — distributional verdict was non-deterministic (shared, never-reset
        RNG across the main estimate, every slice, and every evaluate()).
  Vf3 — a NaN per-sample metric laundered into passed=True.
  Vf4 — inf/nan metric broke cert JSON round-trip (inf -> null) and
        silently corrupted a signed object.
  Vf5 — slice CIs used min(n_bootstrap, 200) but the cert reported the
        main n_bootstrap.
  Vf6 — both-empty masks auto-score 1.0; an all-empty-truth eval passed
        anything with no visible signal.
  Vf7 — critic min-attempts was satisfiable with duplicate/blank attempts.
"""
from __future__ import annotations

import math

import pytest

from csis.backends.mock import MockBackend
from csis.contracts import (
    Artifact,
    CriticFinding,
    DistributionalGraderResult,
    GraderResult,
    GraderSlice,
    Plan,
)
from csis.substrate.capability import CapabilityTier
from csis.substrate.hashing import hash_artifact
from csis.verification.certificates import (
    CrossCheckpointViolation,
    assert_cross_checkpoint,
    build_certificate,
)
from csis.verification.distributional_graders import (
    DiceGrader,
    DistributionalGrader,
    IoUGrader,
    Sample,
    bootstrap_ci,
    hausdorff_1d,
)


# ---- shared helpers ------------------------------------------------------


def _plan() -> Plan:
    return Plan(
        plan_id="p-10",
        frontier_item="cycle10",
        hypothesis="x",
        falsification_condition="y",
        tier=CapabilityTier.T0,
    )


def _artifact(body: str = "# clean patch\n") -> Artifact:
    return Artifact(
        artifact_id="a-10",
        plan_id="p-10",
        kind="patch",
        body=body,
        body_hash=hash_artifact(body),
    )


class _ScalarGrader(DistributionalGrader):
    """Grader whose per-sample metric is the literal payload['x']. Lets a
    test inject an exact distribution (including a NaN) without going
    through a mask/landmark builder."""

    name = "scalar"
    metric_name = "scalar"
    direction = "higher_is_better"
    threshold = 0.0  # everything passes unless a non-finite poisons it

    def per_sample_metric(self, sample: Sample) -> float:
        return float(sample.payload["x"])


def _scalar_samples(values, slice_label: str | None = None) -> list[Sample]:
    out: list[Sample] = []
    for i, v in enumerate(values):
        slices = {"organ": slice_label} if slice_label else {}
        out.append(Sample(case_id=f"c{i:03d}", payload={"x": v}, slices=slices))
    return out


def _dice_sample(pred, truth, case_id: str = "c0", slice_label: str = "liver") -> Sample:
    return Sample(
        case_id=case_id,
        payload={"pred_mask": list(pred), "true_mask": list(truth)},
        slices={"organ": slice_label},
    )


# ======================================================================
# Vf1 — cross-checkpoint separation must not be spoofable by a rename
# ======================================================================


def test_vf1_single_backend_label_rename_is_rejected() -> None:
    """The classic spoof: ONE backend, identities differ ONLY by the
    checkpoint label. Because the default mirrors checkpoint_id into
    model_id, the un-fixed code saw 2 diffs (checkpoint_id + model_id) and
    PASSED — letting a single backend self-confirm. After Vf1 it must RAISE.
    """
    backend = MockBackend()
    # No set_model_id: the un-overridden default has model_id == checkpoint_id.
    builder = backend.checkpoint_identity("builder")
    auditor = backend.checkpoint_identity("auditor")
    # Sanity: only the label (and mirrored model_id) differ — backend + tools
    # are identical because it's one backend with default tools.
    assert builder["backend"] == auditor["backend"]
    assert builder["tool_set"] == auditor["tool_set"]
    with pytest.raises(CrossCheckpointViolation):
        assert_cross_checkpoint(builder, auditor)


def test_vf1_undeclared_model_id_is_rejected() -> None:
    """An identity whose model_id == checkpoint_id (the un-overridden
    default) must be rejected as 'model identity not declared', even if the
    OTHER side is fully distinct."""
    undeclared = {"checkpoint_id": "alpha", "model_id": "alpha", "tool_set": "T", "backend": "mock"}
    declared = {"checkpoint_id": "beta", "model_id": "real-sonnet", "tool_set": "U", "backend": "other"}
    with pytest.raises(CrossCheckpointViolation):
        assert_cross_checkpoint(undeclared, declared)
    with pytest.raises(CrossCheckpointViolation):
        assert_cross_checkpoint(declared, undeclared)


def test_vf1_genuinely_distinct_models_pass() -> None:
    """Two genuinely distinct checkpoints (real, differing model_ids AND
    tools — the production loop/daemon/demo convention) must still PASS."""
    backend = MockBackend()
    backend.set_model_id("builder", "mock-opus")
    backend.set_model_id("auditor", "mock-sonnet")
    backend.set_tools("builder", ["sandbox.execute", "web_search"])
    backend.set_tools("auditor", ["pinned_graders"])
    builder = backend.checkpoint_identity("builder")
    auditor = backend.checkpoint_identity("auditor")
    assert_cross_checkpoint(builder, auditor)  # no raise


def test_vf1_checkpoint_id_alone_insufficient_but_model_id_suffices() -> None:
    """checkpoint_id is decorative: differing ONLY in the label (same model)
    must RAISE. A different model_id — even with the SAME tool_set and backend,
    which is exactly what the real AnthropicBackend reports for every
    checkpoint — is the binding cross-checkpoint signal and must PASS."""
    same_model_a = {"checkpoint_id": "alpha", "model_id": "M", "tool_set": "T", "backend": "mock"}
    same_model_b = {"checkpoint_id": "beta", "model_id": "M", "tool_set": "T", "backend": "mock"}
    with pytest.raises(CrossCheckpointViolation):
        assert_cross_checkpoint(same_model_a, same_model_b)
    # Production shape: same backend + same tool_set, only the model differs.
    diff_model = {"checkpoint_id": "beta", "model_id": "N", "tool_set": "T", "backend": "mock"}
    assert_cross_checkpoint(same_model_a, diff_model)  # no raise


# ======================================================================
# Vf2 — distributional verdict must be deterministic across reruns
# ======================================================================


def _jitter_dice_samples(n: int, base: float, label: str, seed: int = 3) -> list[Sample]:
    import random as _r
    rng = _r.Random(seed)
    out: list[Sample] = []
    for i in range(n):
        size = 100
        k = max(0, min(size, int(round(base * size)) + rng.randint(-3, 3)))
        pred = [1 if j < size else 0 for j in range(2 * size)]
        truth = [1 if (size - k) <= j < (2 * size - k) else 0 for j in range(2 * size)]
        out.append(Sample(case_id=f"{label}-{i}", payload={"pred_mask": pred, "true_mask": truth}, slices={"organ": label}))
    return out


def test_vf2_same_grader_same_data_byte_identical_across_calls() -> None:
    """The SAME grader instance, evaluated TWICE on the SAME data, must
    produce byte-identical (point, ci_lower, ci_upper, passed). The shared
    never-reset RNG made consecutive calls diverge."""
    samples = _jitter_dice_samples(40, base=0.9, label="liver")
    grader = DiceGrader(threshold=0.85, n_bootstrap=300, rng_seed=11)
    r1 = grader.evaluate(samples)
    r2 = grader.evaluate(samples)
    assert (r1.point_estimate, r1.ci_lower, r1.ci_upper, r1.passed) == (
        r2.point_estimate, r2.ci_lower, r2.ci_upper, r2.passed
    )
    # And the slices too, since a per-slice CI must be reproducible.
    assert [(s.name, s.ci_lower, s.ci_upper, s.passed) for s in r1.slices] == [
        (s.name, s.ci_lower, s.ci_upper, s.passed) for s in r2.slices
    ]


def test_vf2_slice_ci_independent_of_sibling_ordering() -> None:
    """A slice's CI must depend ONLY on its own data + the fixed seed, never
    on sibling slices or the order they appear. Evaluate the same two slices
    presented in two different orders; each slice's CI must match across the
    two runs."""
    liver = _jitter_dice_samples(30, base=0.95, label="liver")
    pancreas = _jitter_dice_samples(30, base=0.7, label="pancreas")
    grader = DiceGrader(threshold=0.85, n_bootstrap=200, rng_seed=7)

    r_forward = grader.evaluate(liver + pancreas)
    r_reverse = grader.evaluate(pancreas + liver)

    by_name_fwd = {s.name: (s.ci_lower, s.ci_upper, s.point_estimate) for s in r_forward.slices}
    by_name_rev = {s.name: (s.ci_lower, s.ci_upper, s.point_estimate) for s in r_reverse.slices}
    assert by_name_fwd == by_name_rev


# ======================================================================
# Vf3 — a NaN sample must never launder into passed=True
# ======================================================================


def test_vf3_nan_sample_never_passes() -> None:
    """49 good samples + 1 NaN. The point estimate (mean incl. NaN) is NaN;
    the un-fixed sort-based percentile could still hand back a finite CI and
    read passed=True for some seeds. After Vf3 this must NOT pass for ANY
    seed — deterministically (it raises)."""
    values = [0.95] * 49 + [float("nan")]
    for seed in range(8):
        grader = _ScalarGrader(threshold=0.5, n_bootstrap=200, rng_seed=seed)
        with pytest.raises(ValueError):
            grader.evaluate(_scalar_samples(values))


def test_vf3_bootstrap_ci_rejects_non_finite_directly() -> None:
    with pytest.raises(ValueError):
        bootstrap_ci([0.9, 0.8, float("inf"), 0.85], n_bootstrap=100)
    with pytest.raises(ValueError):
        bootstrap_ci([0.9, float("nan")], n_bootstrap=100)


def test_vf3_passed_requires_finite_bounds() -> None:
    """_passed must return False if either bound is non-finite, regardless of
    direction."""
    g = _ScalarGrader(threshold=0.5)
    assert g._passed(float("nan"), 0.9) is False
    assert g._passed(0.9, float("inf")) is False
    assert g._passed(float("-inf"), float("inf")) is False
    # finite + clears threshold still passes
    assert g._passed(0.9, 0.95) is True


# ======================================================================
# Vf4 — inf/nan must be rejected at the contract (no unloadable cert)
# ======================================================================


@pytest.mark.parametrize("bad", [float("inf"), float("-inf"), float("nan")])
def test_vf4_result_rejects_non_finite_at_construction(bad: float) -> None:
    """A DistributionalGraderResult must refuse a non-finite point/CI at
    construction — otherwise model_dump_json writes null and the cert is
    unloadable (and the signed value is silently corrupted)."""
    base = dict(
        grader="dice", metric_name="dice", direction="higher_is_better",
        point_estimate=0.9, ci_lower=0.88, ci_upper=0.92,
        n_samples=10, n_bootstrap=100, threshold=0.85, passed=True,
    )
    for field in ("point_estimate", "ci_lower", "ci_upper"):
        kwargs = dict(base)
        kwargs[field] = bad
        with pytest.raises(Exception):  # pydantic ValidationError wraps ValueError
            DistributionalGraderResult(**kwargs)


def test_vf4_slice_rejects_non_finite_at_construction() -> None:
    with pytest.raises(Exception):
        GraderSlice(name="organ=liver", n_samples=10, point_estimate=float("inf"))


def test_vf4_finite_result_round_trips() -> None:
    """A finite result still round-trips through cert JSON byte-for-byte."""
    r = DistributionalGraderResult(
        grader="dice", metric_name="dice", direction="higher_is_better",
        point_estimate=0.892, ci_lower=0.871, ci_upper=0.913,
        n_samples=523, n_bootstrap=1000, threshold=0.85, passed=True,
        slices=[GraderSlice(name="organ=liver", n_samples=240, point_estimate=0.94,
                            ci_lower=0.92, ci_upper=0.96, passed=True, n_bootstrap=200)],
    )
    revived = DistributionalGraderResult.model_validate_json(r.model_dump_json())
    assert revived == r


def test_vf4_hausdorff_empty_raises_not_inf() -> None:
    """The inf source: hausdorff_1d on an empty point set must raise (so the
    sample is quarantined) rather than emit float('inf')."""
    with pytest.raises(ValueError):
        hausdorff_1d([], [1.0, 2.0])
    with pytest.raises(ValueError):
        hausdorff_1d([1.0], [])
    # non-empty still works
    assert hausdorff_1d([0.0, 1.0, 2.0], [0.0, 1.0, 5.0]) == pytest.approx(3.0)


# ======================================================================
# Vf5 — slice must report the n_bootstrap it actually used
# ======================================================================


def test_vf5_slice_reports_actual_n_bootstrap() -> None:
    """Operator sets n_bootstrap=1000; slice CIs are computed at
    min(1000,200)=200. The slice's reported resolution must be the 200 it
    actually used, not the main 1000."""
    samples = _jitter_dice_samples(30, base=0.9, label="liver")
    grader = DiceGrader(threshold=0.85, n_bootstrap=1000, rng_seed=5)
    result = grader.evaluate(samples)
    assert result.n_bootstrap == 1000  # main is reported as-is
    assert result.slices, "expected at least one slice"
    for s in result.slices:
        assert s.n_bootstrap == 200, (
            f"slice {s.name} reported n_bootstrap={s.n_bootstrap}, "
            f"but the slice CI was computed at min(1000,200)=200"
        )


def test_vf5_slice_n_bootstrap_tracks_small_main() -> None:
    """When the main n_bootstrap is BELOW 200, the slice uses (and reports)
    that smaller value."""
    samples = _jitter_dice_samples(30, base=0.9, label="liver")
    grader = DiceGrader(threshold=0.85, n_bootstrap=120, rng_seed=5)
    result = grader.evaluate(samples)
    for s in result.slices:
        assert s.n_bootstrap == 120


# ======================================================================
# Vf6 — all-empty-truth batch must not silently pass with full evidence
# ======================================================================


def test_vf6_all_empty_truth_reports_degenerate_count() -> None:
    """An all-empty-ground-truth batch scores Dice=1.0 for ANY prediction.
    The result must SURFACE the degenerate count rather than report a clean
    perfect pass with no signal."""
    # Empty truth, arbitrary (even wrong/non-empty) predictions.
    samples = []
    for i in range(10):
        pred = [1, 0, 1, 0] if i % 2 == 0 else [0, 0, 0, 0]
        samples.append(_dice_sample(pred, [0, 0, 0, 0], case_id=f"c{i}"))
    grader = DiceGrader(threshold=0.85, n_bootstrap=200, slice_min_n=5)
    result = grader.evaluate(samples)
    # The degeneracy MUST be visible in detail.
    assert "degenerate_cases" in result.detail
    assert "empty_truth" in result.detail or "both_empty" in result.detail
    assert "nonempty_truth=0/10" in result.detail


def test_vf6_guard_can_reject_all_empty_truth() -> None:
    """With the optional min-nonempty-truth-fraction guard configured, an
    all-empty-truth batch CANNOT pass even though every per-case score is
    1.0."""
    samples = [_dice_sample([0, 0, 0, 0], [0, 0, 0, 0], case_id=f"c{i}") for i in range(10)]
    # Without the guard: legacy convention -> would pass (1.0 >= 0.85).
    permissive = DiceGrader(threshold=0.85, n_bootstrap=200)
    assert permissive.evaluate(samples).passed is True
    # With the guard requiring >=50% non-empty ground truth: must NOT pass.
    guarded = DiceGrader(threshold=0.85, n_bootstrap=200, min_nonempty_truth_fraction=0.5)
    guarded_result = guarded.evaluate(samples)
    assert guarded_result.passed is False
    assert "GUARD_FAILED" in guarded_result.detail


def test_vf6_normal_batch_has_no_degeneracy_noise() -> None:
    """A healthy batch (all non-empty truth) reports no degenerate cases and
    an empty detail, so the signal stays meaningful."""
    samples = _jitter_dice_samples(20, base=0.95, label="liver")
    result = IoUGrader(threshold=0.7, n_bootstrap=100).evaluate(samples)
    assert "degenerate_cases" not in result.detail


# ======================================================================
# Vf7 — min-attempts must measure DISTINCT, non-trivial attempts
# ======================================================================


def _build_with_attempts(findings: list[CriticFinding]):
    builder = {"checkpoint_id": "alpha", "model_id": "mock-opus", "tool_set": "T", "backend": "mock"}
    verifier = {"checkpoint_id": "beta", "model_id": "mock-sonnet", "tool_set": "U", "backend": "mock"}
    return build_certificate(
        plan=_plan(),
        artifact=_artifact(),
        builder_identity=builder,
        verifier_identity=verifier,
        grader_results=[GraderResult(grader="g", passed=True)],
        critic_findings=findings,
        min_critic_attempts=3,
    )


def test_vf7_duplicate_attempts_do_not_satisfy_min() -> None:
    """Three IDENTICAL attempts must NOT clear min_critic_attempts=3."""
    findings = [CriticFinding(attempt="same", falsified=False)] * 3
    cert = _build_with_attempts(findings)
    assert cert.passed is False
    assert "minimum" in cert.notes


def test_vf7_blank_and_unspecified_attempts_do_not_count() -> None:
    """Blank and '<unspecified>' attempts (the forgiving-parser default) are
    not real work and must not count toward the floor."""
    findings = [
        CriticFinding(attempt="<unspecified>", falsified=False),
        CriticFinding(attempt="   ", falsified=False),
        CriticFinding(attempt="", falsified=False),
    ]
    cert = _build_with_attempts(findings)
    assert cert.passed is False


def test_vf7_three_distinct_real_attempts_satisfy_min() -> None:
    """Three DISTINCT, non-trivial attempts DO satisfy the floor (the fix
    must not over-reject legitimate work)."""
    findings = [
        CriticFinding(attempt="off-by-one in loop bound", falsified=False),
        CriticFinding(attempt="missing null check on input", falsified=False),
        CriticFinding(attempt="race on shared counter", falsified=False),
    ]
    cert = _build_with_attempts(findings)
    assert cert.passed is True


def test_vf7_mixed_duplicates_count_distinct_only() -> None:
    """5 raw findings collapsing to 2 distinct non-trivial attempts must NOT
    clear min=3."""
    findings = [
        CriticFinding(attempt="dup-A", falsified=False),
        CriticFinding(attempt="dup-A", falsified=False),
        CriticFinding(attempt="dup-B", falsified=False),
        CriticFinding(attempt="dup-B", falsified=False),
        CriticFinding(attempt="<unspecified>", falsified=False),
    ]
    cert = _build_with_attempts(findings)
    assert cert.passed is False
