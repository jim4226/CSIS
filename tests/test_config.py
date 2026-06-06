"""Tests for CSISConfig version gate (min_csis_version / max_csis_version).

Claude Code v2.1.163 introduced requiredMinimumVersion / requiredMaximumVersion
managed settings: an operator-controlled deployment gate that refuses startup
when the running version is outside an allowed range. This mirrors that pattern
at the CSIS layer — CSISConfig.__post_init__ now validates against csis.__version__.
"""
from __future__ import annotations

import pytest
from pathlib import Path

from csis.config import CSISConfig
from csis import __version__ as _CSIS_VERSION


def _base_cfg(tmp_path: Path, **overrides) -> CSISConfig:
    return CSISConfig(
        event_log_path=tmp_path / "el" / "s.jsonl",
        memory_root=tmp_path / "mem",
        brain_root=tmp_path / "brain",
        backend="mock",
        **overrides,
    )


def test_no_gate_passes(tmp_path: Path) -> None:
    cfg = _base_cfg(tmp_path)
    assert cfg.min_csis_version is None
    assert cfg.max_csis_version is None


def test_min_version_exact_passes(tmp_path: Path) -> None:
    cfg = _base_cfg(tmp_path, min_csis_version=_CSIS_VERSION)
    assert cfg.min_csis_version == _CSIS_VERSION


def test_max_version_exact_passes(tmp_path: Path) -> None:
    cfg = _base_cfg(tmp_path, max_csis_version=_CSIS_VERSION)
    assert cfg.max_csis_version == _CSIS_VERSION


def test_min_version_below_running_passes(tmp_path: Path) -> None:
    _base_cfg(tmp_path, min_csis_version="0.0.0")


def test_max_version_above_running_passes(tmp_path: Path) -> None:
    _base_cfg(tmp_path, max_csis_version="999.0.0")


def test_min_version_above_running_raises(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="below required minimum"):
        _base_cfg(tmp_path, min_csis_version="999.0.0")


def test_max_version_below_running_raises(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="exceeds required maximum"):
        _base_cfg(tmp_path, max_csis_version="0.0.0")


def test_both_gates_running_version_in_range(tmp_path: Path) -> None:
    _base_cfg(tmp_path, min_csis_version="0.0.0", max_csis_version="999.0.0")


def test_existing_checkpoint_check_still_fires(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="builder_checkpoint must differ"):
        CSISConfig(
            event_log_path=tmp_path / "el" / "s.jsonl",
            memory_root=tmp_path / "mem",
            brain_root=tmp_path / "brain",
            backend="mock",
            builder_checkpoint="same",
            auditor_checkpoint="same",
        )
