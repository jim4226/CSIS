"""Invalid geometric evidence must not become a passing evaluation."""
import math

import pytest

from csis.verification.distributional_graders import LandmarkErrorGrader, Sample, bootstrap_ci


@pytest.mark.parametrize("payload", [
    {"pred_pts": [], "true_pts": []},
    {"pred_pts": [[]], "true_pts": [[]]},
    {"pred_pts": [[0.0]], "true_pts": [[1.0]], "voxel_mm": 0.0},
    {"pred_pts": [[0.0]], "true_pts": [[1.0]], "voxel_mm": -1.0},
    {"pred_pts": [[math.nan]], "true_pts": [[1.0]]},
    {"pred_pts": [[math.inf]], "true_pts": [[1.0]]},
    {"pred_pts": [[0.0]], "true_pts": [[1.0]], "voxel_mm": math.inf},
])
def test_landmark_grader_rejects_invalid_evidence(payload: dict) -> None:
    with pytest.raises(ValueError):
        LandmarkErrorGrader().evaluate([Sample(case_id="invalid", payload=payload)])


@pytest.mark.parametrize("level", [0.0, 1.0, -0.1, 1.1, math.nan, math.inf])
def test_bootstrap_rejects_invalid_confidence_level(level: float) -> None:
    with pytest.raises(ValueError, match="ci_level"):
        bootstrap_ci([0.1, 0.2], ci_level=level)


@pytest.mark.parametrize("value", [math.nan, math.inf, -math.inf])
def test_bootstrap_rejects_nonfinite_metrics(value: float) -> None:
    with pytest.raises(ValueError, match="finite"):
        bootstrap_ci([0.0, value])
