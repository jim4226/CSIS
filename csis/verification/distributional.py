"""Distributional V1 graders — threshold + rolling baseline + held-out sample.

V1 graders ship in two flavors. The existing PR-maintenance set is binary:
``tests_pass``, ``lint``, ``typecheck``, ``diff_scope`` — the artifact either
typechecks or it doesn't. This module adds the second flavor: a scalar
metric computed over a held-out sample (Dice score, anatomical landmark
RMSE, ROC-AUC, F1 over a slice). The pass criterion is "the metric
distribution clears a threshold AND does not regress vs the rolling
baseline of recent promoted artifacts." The ``GraderResult`` carries every
summary statistic, so the Critic (V2) and the Auditor get a real handle on
*how* the artifact passed, not just *that* it did.

Why this lives at V1, not V5
-----------------------------
V5 (calibration scoring against held-out outcomes — Brier / log-loss,
``CSIS-architecture.html`` §10) is the right home for predictive-confidence
calibration over long horizons. V1 is the per-iteration gate. A
distributional metric on a fixed held-out set is V1 — it is a programmatic
check on the artifact's behavior. The two compose: V1 produces the
per-iteration metric, the rolling baseline keeps the threshold honest
across promotions, and V5 (Phase 2) reads the same persisted log to
compute calibration drift.

This pattern unblocks the architecture's Open Research Question #1
("Verifier-grade for fuzzy domains") for domains where ground truth is a
distribution over outcomes rather than a yes/no check — clinical imaging
(Dice, Hausdorff95, boundary F-score), search ranking (nDCG@k),
forecasting (CRPS), recommendation (MRR), and similar.

Linking back to the loop
------------------------
Each promoted artifact appends its summary stats to the per-metric
``RollingBaseline``. The next iteration's grader reads from the same
baseline, so the threshold tightens as the system improves. The Auditor's
why-doc records the delta vs baseline; if the threshold drifts in the
wrong direction, V5 calibration (Phase 2) sees the same trail. The
baseline is persisted as JSON so a fresh-process daemon resumes cold.
"""
from __future__ import annotations

import json
import math
import operator
import statistics
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Literal

from csis.contracts import Artifact, GraderResult
from csis.verification.graders import Grader, GraderRegistry


# ---- Sample + summary stats -----------------------------------------------


@dataclass(frozen=True)
class DistributionalSample:
    """A per-sample scalar payload for one metric on one artifact.

    ``values`` is the held-out evaluation distribution (one number per
    sample). ``sample_ids`` is optional but recommended — if downstream
    tooling needs to find which specific cases regressed, it has to join
    on these.
    """

    metric: str
    values: tuple[float, ...]
    sample_ids: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if self.sample_ids and len(self.sample_ids) != len(self.values):
            raise ValueError(
                f"sample_ids length ({len(self.sample_ids)}) must match "
                f"values length ({len(self.values)}) for metric {self.metric!r}"
            )

    def stats(self) -> dict[str, float]:
        vs = self.values
        n = len(vs)
        if n == 0:
            return {"n": 0.0}
        s = sorted(vs)

        def _pct(p: float) -> float:
            if n == 1:
                return s[0]
            k = (n - 1) * p
            lo = math.floor(k)
            hi = math.ceil(k)
            if lo == hi:
                return s[int(k)]
            return s[lo] + (s[hi] - s[lo]) * (k - lo)

        return {
            "n": float(n),
            "mean": statistics.fmean(vs),
            "median": _pct(0.5),
            "p10": _pct(0.10),
            "p90": _pct(0.90),
            "stdev": statistics.pstdev(vs) if n > 1 else 0.0,
            "min": float(s[0]),
            "max": float(s[-1]),
        }


# ---- Rolling baseline (persisted to disk so the loop sees it) ------------


@dataclass
class RollingBaseline:
    """Per-metric history of recent promoted artifacts.

    Persisted as JSON so the next iteration's grader (potentially in a
    fresh process — daemons restart, bursts are short-lived) reads the
    same series. Bounded to ``window`` most-recent entries; older ones
    drop off the front so a regression that happened months ago doesn't
    hold the threshold hostage.
    """

    metric: str
    window: int = 50
    history: list[dict] = field(default_factory=list)
    path: Path | None = None

    @classmethod
    def load(cls, *, metric: str, path: Path, window: int = 50) -> "RollingBaseline":
        if path.exists():
            data = json.loads(path.read_text("utf-8"))
            return cls(
                metric=metric,
                window=int(data.get("window", window)),
                history=list(data.get("history", [])),
                path=path,
            )
        return cls(metric=metric, window=window, path=path)

    def append(
        self,
        stats: dict[str, float],
        *,
        artifact_id: str,
        ts: float | None = None,
    ) -> None:
        self.history.append({
            "artifact_id": artifact_id,
            "ts": ts if ts is not None else time.time(),
            "stats": stats,
        })
        if len(self.history) > self.window:
            self.history = self.history[-self.window:]
        if self.path is not None:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            self.path.write_text(
                json.dumps(
                    {"metric": self.metric, "window": self.window, "history": self.history},
                    indent=2,
                ),
                encoding="utf-8",
            )

    def baseline_stats(self, key: str = "p10") -> float | None:
        """Aggregate one summary stat across history. Default = median of
        the recent per-iteration p10s — a robust lower-tail watermark
        that is insensitive to a single outlier promoted iteration.
        Returns None if no history has been recorded yet.
        """
        xs = [
            h["stats"].get(key)
            for h in self.history
            if h.get("stats", {}).get(key) is not None
        ]
        if not xs:
            return None
        return statistics.median(xs)


# ---- Threshold rule ------------------------------------------------------


CompOp = Literal[">=", ">", "<=", "<"]
_OPS: dict[CompOp, Callable[[float, float], bool]] = {
    ">=": operator.ge,
    ">": operator.gt,
    "<=": operator.le,
    "<": operator.lt,
}


@dataclass
class DistributionalThreshold:
    """Pass criterion for a distributional metric.

    A grader passes iff:

    1. ``summary_stat`` of the sample (default mean) clears ``floor``
       under ``op``.
    2. AND ``min_samples`` is met (defends against zero-sample
       fake-passes from an artifact that ran on the wrong fold).
    3. AND (if a baseline is provided and ``max_regression`` is set) the
       sample's ``regression_stat`` is not worse than the rolling
       baseline by more than ``max_regression`` (in the same units as
       the metric).

    Defaults follow the orthopedic-imaging case raised in conversation
    with Jaron Mohammed (Bone Vision): Dice / F-score-like metrics use
    ``op=">="`` with a floor and "p10 must not regress more than 0.02
    below baseline p10." For error-style metrics (Hausdorff95, landmark
    RMSE) flip ``op`` to ``"<="``, summary_stat to ``"mean"`` or
    ``"p90"``, and the regression check naturally inverts (the new p90
    must not exceed baseline p90 by more than X mm).
    """

    floor: float
    op: CompOp = ">="
    summary_stat: str = "mean"
    min_samples: int = 1
    max_regression: float | None = None
    # For higher-is-better metrics, p10 is the canonical "tail
    # watermark." For lower-is-better (errors), flip to p90.
    regression_stat: str = "p10"

    def evaluate(
        self,
        sample: DistributionalSample,
        baseline: RollingBaseline | None,
    ) -> tuple[bool, str, dict[str, float]]:
        stats = sample.stats()
        n = int(stats.get("n", 0.0))
        op = _OPS[self.op]
        details: list[str] = []
        out_metrics: dict[str, float] = dict(stats)

        if n < self.min_samples:
            return (
                False,
                f"too few samples: n={n} < min_samples={self.min_samples}",
                out_metrics,
            )

        primary = stats.get(self.summary_stat)
        if primary is None:
            return (
                False,
                f"summary_stat {self.summary_stat!r} not produced for sample",
                out_metrics,
            )
        primary_ok = op(primary, self.floor)
        details.append(
            f"{self.summary_stat}={primary:.4f} {self.op} floor={self.floor:.4f} "
            f"-> {'pass' if primary_ok else 'FAIL'}"
        )

        regression_ok = True
        if self.max_regression is not None and baseline is not None:
            base = baseline.baseline_stats(self.regression_stat)
            current = stats.get(self.regression_stat)
            if base is not None and current is not None:
                # Higher-is-better: regression = baseline - current.
                # Lower-is-better: regression = current - baseline.
                if self.op in (">=", ">"):
                    regression = base - current
                else:
                    regression = current - base
                out_metrics[f"baseline_{self.regression_stat}"] = base
                out_metrics[f"regression_{self.regression_stat}"] = regression
                regression_ok = regression <= self.max_regression
                details.append(
                    f"{self.regression_stat}={current:.4f} vs baseline={base:.4f} "
                    f"(regression={regression:+.4f}, allowed={self.max_regression:+.4f}) "
                    f"-> {'pass' if regression_ok else 'FAIL'}"
                )
            else:
                details.append(
                    f"no baseline yet for {self.regression_stat!r}; "
                    f"skipping regression check"
                )
        passed = primary_ok and regression_ok
        return (passed, " | ".join(details), out_metrics)


# ---- Distributional grader factory --------------------------------------


def distributional_grader(
    *,
    name: str,
    threshold: DistributionalThreshold,
    baseline: RollingBaseline | None = None,
) -> Grader:
    """Build a closure that reads ``artifact.extra['metrics_payload'][name]``
    as a ``DistributionalSample`` (or a serialized dict with ``values`` +
    ``sample_ids``), runs the threshold rule, and returns a
    ``GraderResult``.

    The closure does NOT mutate the baseline at evaluate time.
    ``update_baselines_after_promotion`` runs that AFTER the artifact is
    promoted — touching the rolling watermark pre-decision would let a
    failing artifact contaminate the very baseline its successor will be
    measured against.
    """

    def _grader(artifact: Artifact) -> GraderResult:
        payload = (artifact.extra or {}).get("metrics_payload", {})
        raw = payload.get(name)
        if raw is None:
            return GraderResult(
                grader=name,
                passed=False,
                detail=f"missing distributional sample for metric {name!r}",
            )
        if isinstance(raw, DistributionalSample):
            sample = raw
        elif isinstance(raw, dict):
            try:
                values = tuple(float(x) for x in raw.get("values", ()))
                sample_ids = tuple(str(x) for x in raw.get("sample_ids", ()))
            except (TypeError, ValueError) as exc:
                return GraderResult(
                    grader=name,
                    passed=False,
                    detail=f"malformed payload for metric {name!r}: {exc!r}",
                )
            sample = DistributionalSample(
                metric=name, values=values, sample_ids=sample_ids,
            )
        else:
            return GraderResult(
                grader=name,
                passed=False,
                detail=(
                    f"metric {name!r} payload must be DistributionalSample or "
                    f"dict, got {type(raw).__name__}"
                ),
            )
        passed, detail, metrics = threshold.evaluate(sample, baseline)
        return GraderResult(grader=name, passed=passed, detail=detail, metrics=metrics)

    _grader.__name__ = f"distributional_{name}_grader"
    _grader.__qualname__ = _grader.__name__
    return _grader


# ---- Clinical-imaging example registry ----------------------------------


def make_clinical_imaging_registry(
    *,
    baseline_root: Path | None = None,
) -> tuple[GraderRegistry, dict[str, RollingBaseline]]:
    """A V1 grader set tuned for the Bone-Vision-style problem: 2D-to-3D
    orthopedic reconstruction at sub-mm precision.

    Four metrics, all distributional, all running through the same
    threshold + rolling-baseline pattern:

    - ``dice_score`` — segmentation overlap (higher is better)
    - ``landmark_rmse`` — anatomical landmark localization error, mm (lower)
    - ``hausdorff_95`` — 95th-percentile surface distance, mm (lower)
    - ``boundary_f1`` — boundary F-score (higher is better)

    ``baseline_root`` is the directory where per-metric rolling histories
    persist. Pass ``None`` for an in-memory baseline (test mode); pass a
    repo-relative path under ``brain/`` for production so daemons resume
    cold.

    Returns ``(registry, baselines)``. The Coordinator (or a daemon
    wrapping it) calls :func:`update_baselines_after_promotion` against
    ``baselines`` once ``store.promote()`` has succeeded; the next
    iteration's grader then sees the tighter watermark.
    """
    baselines: dict[str, RollingBaseline] = {}

    def _baseline(metric: str) -> RollingBaseline:
        if baseline_root is None:
            b = RollingBaseline(metric=metric)
        else:
            b = RollingBaseline.load(
                metric=metric,
                path=baseline_root / f"{metric}.baseline.json",
            )
        baselines[metric] = b
        return b

    reg = GraderRegistry()

    # Higher-is-better metrics.
    reg.pin("dice_score", distributional_grader(
        name="dice_score",
        threshold=DistributionalThreshold(
            floor=0.85, op=">=", summary_stat="mean", min_samples=20,
            max_regression=0.02, regression_stat="p10",
        ),
        baseline=_baseline("dice_score"),
    ))
    reg.pin("boundary_f1", distributional_grader(
        name="boundary_f1",
        threshold=DistributionalThreshold(
            floor=0.70, op=">=", summary_stat="median", min_samples=20,
            max_regression=0.03, regression_stat="p10",
        ),
        baseline=_baseline("boundary_f1"),
    ))

    # Lower-is-better metrics (errors in millimeters).
    reg.pin("landmark_rmse", distributional_grader(
        name="landmark_rmse",
        threshold=DistributionalThreshold(
            floor=1.0, op="<=", summary_stat="p90", min_samples=20,
            max_regression=0.10, regression_stat="p90",
        ),
        baseline=_baseline("landmark_rmse"),
    ))
    reg.pin("hausdorff_95", distributional_grader(
        name="hausdorff_95",
        threshold=DistributionalThreshold(
            floor=2.5, op="<=", summary_stat="p90", min_samples=20,
            max_regression=0.20, regression_stat="p90",
        ),
        baseline=_baseline("hausdorff_95"),
    ))

    return reg, baselines


def update_baselines_after_promotion(
    *,
    baselines: dict[str, RollingBaseline],
    artifact: Artifact,
) -> dict[str, dict[str, float]]:
    """Append summary stats for each known metric to the matching
    rolling baseline. Intended to be called by the Coordinator (or a
    daemon wrapping it) AFTER ``store.promote()`` succeeds.

    Reads ``artifact.extra['metrics_payload']``; silently skips metrics
    that the artifact did not report (the registry can carry metrics the
    artifact-producer doesn't compute for every iteration — e.g., a
    cheap-mode build that only runs Dice).

    Returns the per-metric stats dict that got recorded, so the event log
    can show the watermark movement and the Auditor's why-doc can cite
    it.
    """
    payload = (artifact.extra or {}).get("metrics_payload", {})
    recorded: dict[str, dict[str, float]] = {}
    for name, baseline in baselines.items():
        raw = payload.get(name)
        if raw is None:
            continue
        if isinstance(raw, DistributionalSample):
            sample = raw
        elif isinstance(raw, dict):
            try:
                values = tuple(float(x) for x in raw.get("values", ()))
                sample_ids = tuple(str(x) for x in raw.get("sample_ids", ()))
            except (TypeError, ValueError):
                continue
            sample = DistributionalSample(
                metric=name, values=values, sample_ids=sample_ids,
            )
        else:
            continue
        stats = sample.stats()
        baseline.append(stats, artifact_id=artifact.artifact_id)
        recorded[name] = stats
    return recorded
