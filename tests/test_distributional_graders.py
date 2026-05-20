"""Distributional V1 grader tests.

Covers:
  - DistributionalSample summary stats (mean, median, p10, p90, n).
  - DistributionalThreshold pass/fail for higher-is-better and
    lower-is-better metrics, with and without a rolling baseline.
  - RollingBaseline append + window enforcement + JSON persistence
    + cold-load on a fresh process.
  - distributional_grader composes into the existing GraderRegistry
    (F6 pinning, drift detection, evaluate() all keep working).
  - The clinical-imaging registry behaves correctly on realistic
    Dice / landmark-RMSE payloads.
  - End-to-end: the Coordinator runs a full iteration against a
    clinical-imaging registry, promotes, the baseline updates, and
    the next iteration's grader reads the tighter watermark.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from csis.agents.coordinator import Coordinator
from csis.backends.mock import MockBackend
from csis.config import CSISConfig
from csis.contracts import Artifact
from csis.substrate.hashing import hash_artifact
from csis.verification.distributional import (
    DistributionalGraderSpec,
    DistributionalSample,
    DistributionalThreshold,
    RollingBaseline,
    distributional_grader,
    make_classification_registry,
    make_clinical_imaging_registry,
    make_distributional_registry,
    make_forecasting_registry,
    make_llm_eval_registry,
    make_recommendation_registry,
    make_search_ranking_registry,
    update_baselines_after_promotion,
)
from csis.verification.graders import GraderRegistry

from tests._helpers import wrap_for_test


# ---- helpers ------------------------------------------------------------


def _artifact_with_payload(payload: dict, *, artifact_id: str = "a-1") -> Artifact:
    body = f"# body for {artifact_id}\n"
    return Artifact(
        artifact_id=artifact_id,
        plan_id="p-1",
        kind="report",
        body=body,
        body_hash=hash_artifact(body),
        extra={"metrics_payload": payload},
    )


# ---- DistributionalSample ----------------------------------------------


def test_sample_stats_basic() -> None:
    s = DistributionalSample(metric="dice", values=tuple(range(11)))  # 0..10
    stats = s.stats()
    assert stats["n"] == 11.0
    assert stats["mean"] == pytest.approx(5.0)
    assert stats["median"] == pytest.approx(5.0)
    assert stats["p10"] == pytest.approx(1.0)
    assert stats["p90"] == pytest.approx(9.0)
    assert stats["min"] == 0.0 and stats["max"] == 10.0


def test_sample_stats_single_value() -> None:
    s = DistributionalSample(metric="m", values=(0.42,))
    stats = s.stats()
    assert stats["n"] == 1.0
    assert stats["mean"] == stats["median"] == stats["p10"] == stats["p90"] == 0.42
    assert stats["stdev"] == 0.0


def test_sample_id_length_must_match_values() -> None:
    with pytest.raises(ValueError, match="sample_ids length"):
        DistributionalSample(metric="m", values=(0.1, 0.2), sample_ids=("only-one",))


# ---- RollingBaseline ---------------------------------------------------


def test_rolling_baseline_appends_and_bounds_window(tmp_path: Path) -> None:
    b = RollingBaseline(metric="dice", window=3, path=tmp_path / "dice.json")
    for i in range(5):
        b.append({"n": 10.0, "mean": 0.9, "p10": 0.80 + i * 0.01}, artifact_id=f"a-{i}")
    # window kept the latest 3.
    assert len(b.history) == 3
    assert [h["artifact_id"] for h in b.history] == ["a-2", "a-3", "a-4"]


def test_rolling_baseline_persists_and_reloads(tmp_path: Path) -> None:
    path = tmp_path / "dice.json"
    b = RollingBaseline(metric="dice", window=10, path=path)
    b.append({"mean": 0.92, "p10": 0.88}, artifact_id="a-1")
    b.append({"mean": 0.93, "p10": 0.89}, artifact_id="a-2")
    assert path.exists()

    # Fresh load == fresh process / restarted daemon.
    reloaded = RollingBaseline.load(metric="dice", path=path)
    assert len(reloaded.history) == 2
    assert reloaded.baseline_stats("p10") == pytest.approx(0.885)  # median of 0.88, 0.89


def test_rolling_baseline_median_of_p10s_is_robust_to_outlier() -> None:
    b = RollingBaseline(metric="dice")
    for v in [0.88, 0.89, 0.05, 0.91, 0.90]:  # 0.05 is the outlier iteration
        b.append({"p10": v}, artifact_id="x")
    # Median is robust → 0.89 — the outlier doesn't tank the watermark.
    assert b.baseline_stats("p10") == pytest.approx(0.89)


def test_rolling_baseline_returns_none_when_empty() -> None:
    assert RollingBaseline(metric="dice").baseline_stats("p10") is None


# ---- DistributionalThreshold -------------------------------------------


def test_threshold_higher_is_better_clears_floor() -> None:
    sample = DistributionalSample(metric="dice", values=tuple([0.9] * 30))
    t = DistributionalThreshold(floor=0.85, op=">=", summary_stat="mean", min_samples=20)
    ok, detail, metrics = t.evaluate(sample, baseline=None)
    assert ok
    assert "pass" in detail
    assert metrics["mean"] == pytest.approx(0.9)


def test_threshold_higher_is_better_below_floor_fails() -> None:
    sample = DistributionalSample(metric="dice", values=tuple([0.80] * 30))
    t = DistributionalThreshold(floor=0.85, op=">=", summary_stat="mean", min_samples=20)
    ok, detail, _ = t.evaluate(sample, baseline=None)
    assert not ok and "FAIL" in detail


def test_threshold_lower_is_better_error_metric() -> None:
    # Landmark RMSE in mm: sub-mm precision target.
    sample = DistributionalSample(
        metric="landmark_rmse", values=(0.4, 0.5, 0.7, 0.8, 0.9) * 6,
    )
    t = DistributionalThreshold(
        floor=1.0, op="<=", summary_stat="p90", min_samples=20,
    )
    ok, _, metrics = t.evaluate(sample, baseline=None)
    assert ok
    assert metrics["p90"] <= 1.0


def test_threshold_too_few_samples_fails_with_reason() -> None:
    sample = DistributionalSample(metric="dice", values=(0.95,) * 5)
    t = DistributionalThreshold(floor=0.85, min_samples=20)
    ok, detail, _ = t.evaluate(sample, baseline=None)
    assert not ok
    assert "too few samples" in detail


def test_threshold_regression_vs_baseline_blocks_silent_drift() -> None:
    """Mean still clears the floor but p10 dropped well below baseline p10
    — this is the silent-regression case distributional graders exist
    to catch."""
    baseline = RollingBaseline(metric="dice")
    # Established history: p10 ~ 0.88.
    for _ in range(5):
        baseline.append({"p10": 0.88, "mean": 0.92}, artifact_id="prev")

    # Current iteration: mean is still 0.91 (above floor 0.85), but the
    # lower tail collapsed — p10 = 0.55.
    sample_vals = [0.55] * 5 + [0.95] * 25
    sample = DistributionalSample(metric="dice", values=tuple(sample_vals))
    t = DistributionalThreshold(
        floor=0.85, op=">=", summary_stat="mean", min_samples=20,
        max_regression=0.02, regression_stat="p10",
    )
    ok, detail, metrics = t.evaluate(sample, baseline)
    assert not ok, detail
    # The mean-vs-floor check passed; the regression check failed.
    assert "p10=" in detail and "FAIL" in detail
    assert metrics["regression_p10"] > 0.02


def test_threshold_no_baseline_yet_still_evaluable() -> None:
    """First iteration has no baseline; the threshold must still produce
    a verdict from the floor check alone."""
    sample = DistributionalSample(metric="dice", values=(0.95,) * 30)
    empty_baseline = RollingBaseline(metric="dice")
    t = DistributionalThreshold(
        floor=0.85, max_regression=0.02, regression_stat="p10", min_samples=20,
    )
    ok, detail, _ = t.evaluate(sample, empty_baseline)
    assert ok
    assert "no baseline yet" in detail


# ---- distributional_grader composes with the GraderRegistry -----------


def test_distributional_grader_returns_grader_result_with_metrics() -> None:
    grader = distributional_grader(
        name="dice_score",
        threshold=DistributionalThreshold(floor=0.85, min_samples=10),
    )
    art = _artifact_with_payload({"dice_score": {"values": [0.95] * 20}})
    res = grader(art)
    assert res.passed
    assert res.grader == "dice_score"
    assert res.metrics["n"] == 20.0
    assert res.metrics["mean"] == pytest.approx(0.95)


def test_distributional_grader_handles_missing_payload() -> None:
    grader = distributional_grader(
        name="dice_score",
        threshold=DistributionalThreshold(floor=0.85),
    )
    art = _artifact_with_payload({})  # no dice_score
    res = grader(art)
    assert not res.passed
    assert "missing" in res.detail


def test_distributional_grader_pins_via_registry_and_drift_check_holds() -> None:
    reg = GraderRegistry()
    reg.pin("dice_score", distributional_grader(
        name="dice_score",
        threshold=DistributionalThreshold(floor=0.85, min_samples=10),
    ))
    ok, drifted = reg.verify_pinned_hashes()
    assert ok and not drifted, f"unexpected drift: {drifted}"

    art = _artifact_with_payload({"dice_score": {"values": [0.9] * 15}})
    results = reg.evaluate(art)
    assert len(results) == 1 and results[0].passed


# ---- Clinical-imaging registry happy path ------------------------------


def _clinical_payload(*, dice: float = 0.93, rmse_p90: float = 0.7) -> dict:
    """20 samples each, mean of dice and p90 of rmse hit the targets."""
    return {
        "dice_score": {"values": [dice] * 20},
        "boundary_f1": {"values": [0.78] * 20},
        "landmark_rmse": {
            "values": [rmse_p90 - 0.2] * 18 + [rmse_p90] * 2,
        },
        "hausdorff_95": {"values": [1.5] * 20},
    }


def test_clinical_registry_clean_artifact_passes() -> None:
    reg, _ = make_clinical_imaging_registry()
    art = _artifact_with_payload(_clinical_payload())
    results = {r.grader: r for r in reg.evaluate(art)}
    failed = [r for r in results.values() if not r.passed]
    assert not failed, [(r.grader, r.detail) for r in failed]


def test_clinical_registry_rejects_below_sub_mm_target() -> None:
    """Push landmark RMSE p90 above 1mm — sub-mm precision target broken."""
    reg, _ = make_clinical_imaging_registry()
    payload = _clinical_payload(rmse_p90=1.5)
    art = _artifact_with_payload(payload)
    results = {r.grader: r for r in reg.evaluate(art)}
    assert not results["landmark_rmse"].passed
    assert "FAIL" in results["landmark_rmse"].detail


def test_clinical_registry_baseline_persists_across_promotions(tmp_path: Path) -> None:
    """Promote three artifacts; verify the baseline file accumulates
    them and a fresh registry reading from disk sees the watermark."""
    reg, baselines = make_clinical_imaging_registry(baseline_root=tmp_path)

    for i in range(3):
        art = _artifact_with_payload(_clinical_payload(), artifact_id=f"a-{i}")
        recorded = update_baselines_after_promotion(baselines=baselines, artifact=art)
        assert set(recorded.keys()) == {"dice_score", "boundary_f1", "landmark_rmse", "hausdorff_95"}

    # On-disk baseline file is real, parseable, and has the expected count.
    dice_file = tmp_path / "dice_score.baseline.json"
    assert dice_file.exists()
    data = json.loads(dice_file.read_text("utf-8"))
    assert len(data["history"]) == 3

    # Fresh registry instance (cold-load) sees the same history.
    fresh_reg, fresh_baselines = make_clinical_imaging_registry(baseline_root=tmp_path)
    assert len(fresh_baselines["dice_score"].history) == 3
    assert fresh_baselines["dice_score"].baseline_stats("p10") is not None


# ---- Cross-domain registries ------------------------------------------


def test_generic_builder_accepts_any_spec_list(tmp_path: Path) -> None:
    """The generic builder is the load-bearing API; the per-domain
    factories are thin wrappers. Verify a hand-rolled spec list works
    end-to-end."""
    specs = [
        DistributionalGraderSpec(
            name="custom_metric",
            threshold=DistributionalThreshold(
                floor=0.50, op=">=", summary_stat="mean", min_samples=5,
                max_regression=0.05, regression_stat="p10",
            ),
        ),
    ]
    reg, baselines = make_distributional_registry(specs, baseline_root=tmp_path)
    ok, drifted = reg.verify_pinned_hashes()
    assert ok and not drifted
    assert "custom_metric" in baselines

    art = _artifact_with_payload({"custom_metric": {"values": [0.6] * 10}})
    results = {r.grader: r for r in reg.evaluate(art)}
    assert results["custom_metric"].passed


def test_search_ranking_registry_clean_artifact_passes() -> None:
    reg, _ = make_search_ranking_registry()
    art = _artifact_with_payload({
        "ndcg_at_10": {"values": [0.70] * 100},
        "mrr": {"values": [0.55] * 100},
        "recall_at_10": {"values": [0.80] * 100},
    })
    failed = [r for r in reg.evaluate(art) if not r.passed]
    assert not failed, [(r.grader, r.detail) for r in failed]


def test_search_ranking_registry_rejects_ndcg_below_floor() -> None:
    reg, _ = make_search_ranking_registry()
    art = _artifact_with_payload({
        "ndcg_at_10": {"values": [0.40] * 100},  # below 0.55 floor
        "mrr": {"values": [0.55] * 100},
        "recall_at_10": {"values": [0.80] * 100},
    })
    results = {r.grader: r for r in reg.evaluate(art)}
    assert not results["ndcg_at_10"].passed
    assert "FAIL" in results["ndcg_at_10"].detail


def test_forecasting_registry_clean_artifact_passes() -> None:
    reg, _ = make_forecasting_registry()
    art = _artifact_with_payload({
        "mae": {"values": [3.0] * 30},          # below 5.0 floor
        "crps": {"values": [1.5] * 30},         # below 2.0
        "pinball_loss_p90": {"values": [1.2] * 30},  # below 1.5
    })
    failed = [r for r in reg.evaluate(art) if not r.passed]
    assert not failed, [(r.grader, r.detail) for r in failed]


def test_forecasting_registry_lower_is_better_op_inverts_correctly() -> None:
    """Forecasting metrics are all lower-is-better; a MAE that doubles
    over baseline must trip the regression check even if it still clears
    the absolute floor."""
    reg, baselines = make_forecasting_registry()
    # Seed baseline with strong history: p90 ~ 3.0
    for _ in range(5):
        baselines["mae"].append({"p90": 3.0, "mean": 2.5}, artifact_id="prev")
    # Current artifact: mean 4.5 (below 5.0 floor — passes mean check)
    # but p90 = 6.0 (regression of 3.0 from baseline p90, way over 0.5 budget)
    vs = [4.0] * 27 + [6.0] * 3
    art = _artifact_with_payload({
        "mae": {"values": vs},
        "crps": {"values": [1.5] * 30},
        "pinball_loss_p90": {"values": [1.2] * 30},
    })
    results = {r.grader: r for r in reg.evaluate(art)}
    assert not results["mae"].passed
    assert "regression=" in results["mae"].detail


def test_classification_registry_clean_artifact_passes() -> None:
    reg, _ = make_classification_registry()
    art = _artifact_with_payload({
        "f1_macro": {"values": [0.85] * 10},
        "roc_auc": {"values": [0.90] * 10},
        "precision_at_recall_90": {"values": [0.80] * 10},
    })
    failed = [r for r in reg.evaluate(art) if not r.passed]
    assert not failed, [(r.grader, r.detail) for r in failed]


def test_llm_eval_registry_passes_on_pass_at_1_above_floor() -> None:
    reg, _ = make_llm_eval_registry()
    # 60 of 100 prompts pass = 0.60 pass rate (exactly at the floor with >=).
    pass_vals = [1.0] * 60 + [0.0] * 40
    # win rate above baseline
    win_vals = [1.0] * 55 + [0.0] * 45
    # judge scores median = 8.0
    judge_vals = [8.0] * 50
    art = _artifact_with_payload({
        "pass_at_1": {"values": pass_vals},
        "win_rate_vs_baseline": {"values": win_vals},
        "judge_score": {"values": judge_vals},
    })
    results = {r.grader: r for r in reg.evaluate(art)}
    assert results["pass_at_1"].passed
    assert results["win_rate_vs_baseline"].passed
    assert results["judge_score"].passed


def test_llm_eval_registry_catches_win_rate_regression_against_baseline() -> None:
    """LLM eval pass_at_1 / win_rate are 0/1 — regression check fires on
    mean, not p10 (per-prompt p10 is degenerate on binary data)."""
    reg, baselines = make_llm_eval_registry()
    # Established baseline: win rate ~ 0.65
    for _ in range(5):
        baselines["win_rate_vs_baseline"].append(
            {"mean": 0.65, "p10": 0.0}, artifact_id="prev",
        )
    # Current artifact: 55 wins (mean 0.55, still at floor) — drop of 0.10
    # vs baseline mean of 0.65, exceeds the 0.05 regression budget.
    win_vals = [1.0] * 55 + [0.0] * 45
    art = _artifact_with_payload({
        "pass_at_1": {"values": [1.0] * 60 + [0.0] * 40},
        "win_rate_vs_baseline": {"values": win_vals},
        "judge_score": {"values": [8.0] * 50},
    })
    results = {r.grader: r for r in reg.evaluate(art)}
    assert not results["win_rate_vs_baseline"].passed
    assert "regression=" in results["win_rate_vs_baseline"].detail


def test_recommendation_registry_clean_artifact_passes() -> None:
    reg, _ = make_recommendation_registry()
    art = _artifact_with_payload({
        "hit_at_10": {"values": [0.35] * 200},
        "ndcg_at_10": {"values": [0.45] * 200},
        "catalog_coverage": {"values": [0.30]},  # single number, min_samples=1
    })
    failed = [r for r in reg.evaluate(art) if not r.passed]
    assert not failed, [(r.grader, r.detail) for r in failed]


def test_every_preset_registry_pins_cleanly_and_passes_drift_check() -> None:
    """Cycle-9-style structural check: every preset registry must be
    pinnable AND every pinned grader's source hash must verify. Catches
    regressions where a new preset accidentally shadows an existing
    grader name with a structurally different closure."""
    for factory in (
        make_clinical_imaging_registry,
        make_search_ranking_registry,
        make_forecasting_registry,
        make_classification_registry,
        make_llm_eval_registry,
        make_recommendation_registry,
    ):
        reg, baselines = factory()
        ok, drifted = reg.verify_pinned_hashes()
        assert ok and not drifted, f"{factory.__name__}: drift={drifted}"
        assert len(reg.pinned) == len(baselines), factory.__name__


# ---- End-to-end: Coordinator runs the loop with the clinical registry --


def _wire_clinical_backend(cfg: CSISConfig, *, payload: dict) -> MockBackend:
    backend = MockBackend()
    backend.set_model_id(cfg.builder_checkpoint, "mock-opus")
    backend.set_model_id(cfg.auditor_checkpoint, "mock-sonnet")
    backend.set_tools(cfg.builder_checkpoint, ["sandbox.execute"])
    backend.set_tools(cfg.auditor_checkpoint, ["pinned_graders"])

    backend.script(
        "researcher", cfg.builder_checkpoint,
        '{"plan_id":"p-clinical","frontier_item":"clinical-itest",'
        '"hypothesis":"new reconstruction net holds dice >= 0.85",'
        '"falsification_condition":"any distributional grader fails",'
        '"budget":{"time_s":10,"tokens":500},'
        '"tier":"T0","tool_calls_planned":[]}'
    )
    body = '{"artifact_id":"a-clinical","plan_id":"p-clinical","kind":"report",' \
           '"body":"# bone-vision reconstruction eval report\\n",' \
           '"body_hash":"sha256:placeholder","sandbox_logs":[],' \
           f'"extra":{{"metrics_payload":{json.dumps(payload)}}}}}'
    backend.script("builder", cfg.builder_checkpoint, body)
    backend.script(
        "critic", cfg.auditor_checkpoint,
        '[{"attempt":"did test set leak","falsified":false,"detail":"folds disjoint"},'
        '{"attempt":"is sample size adequate","falsified":false,"detail":"n=20"},'
        '{"attempt":"could a single outlier carry mean","falsified":false,"detail":"p10 check guards"},'
        '{"attempt":"is landmark calibration sub-mm","falsified":false,"detail":"yes"}]'
    )
    return backend


def test_coordinator_runs_clinical_registry_end_to_end_and_baseline_updates(
    tmp_path: Path,
) -> None:
    cfg = CSISConfig.for_tests(tmp_path)
    payload = _clinical_payload()
    backend = _wire_clinical_backend(cfg, payload=payload)
    registry, baselines = make_clinical_imaging_registry(baseline_root=tmp_path / "baselines")
    coord = Coordinator(
        config=cfg, backend=wrap_for_test(backend, tmp_path), registry=registry,
    )

    res = coord.run_iteration(frontier_item="clinical integration test")
    assert res.outcome == "promoted", res.outcome
    assert res.cert is not None and res.cert.passed
    # Every distributional grader landed a metrics dict in the cert.
    by_grader = {g.grader: g for g in res.cert.grader_results}
    for name in ("dice_score", "boundary_f1", "landmark_rmse", "hausdorff_95"):
        assert name in by_grader, by_grader.keys()
        assert by_grader[name].metrics.get("n") == 20.0
        assert by_grader[name].passed, by_grader[name].detail

    # Baseline update is the link from this iteration's verified gain to
    # the next iteration's threshold. The Coordinator doesn't auto-call
    # it (clean separation: it's a domain-specific hook), so a daemon /
    # caller does it explicitly here.
    assert res.artifact is not None
    recorded = update_baselines_after_promotion(baselines=baselines, artifact=res.artifact)
    assert "dice_score" in recorded
    assert baselines["dice_score"].baseline_stats("p10") is not None
