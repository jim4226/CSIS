"""Regression tests for csis.safety.containment_audit.

Verifies that `audit_containment` correctly identifies structural defenses (and
their absence) for the four vulnerability patterns from the Anthropic engineering
article "How we contain Claude across products".
"""
from __future__ import annotations

from pathlib import Path

import pytest

from csis.agents.coordinator import Coordinator
from csis.backends.mock import MockBackend
from csis.config import CSISConfig
from csis.safety.containment_audit import ContainmentPosture, audit_containment
from csis.substrate.capability import CapabilityTier

from tests._helpers import wrap_for_test


def _make_coord(tmp_path: Path) -> Coordinator:
    cfg = CSISConfig.for_tests(tmp_path)
    backend = MockBackend()
    backend.set_model_id(cfg.builder_checkpoint, "mock-opus")
    backend.set_model_id(cfg.auditor_checkpoint, "mock-sonnet")
    return Coordinator(config=cfg, backend=wrap_for_test(backend, tmp_path))


# ---- happy-path: all defenses intact ------------------------------------


def test_audit_all_defenses_pass(tmp_path: Path) -> None:
    coord = _make_coord(tmp_path)
    posture = audit_containment(coord)
    assert isinstance(posture, ContainmentPosture)
    assert posture.overall_defended is True
    assert posture.failures == []


def test_audit_returns_four_checks(tmp_path: Path) -> None:
    coord = _make_coord(tmp_path)
    posture = audit_containment(coord)
    assert len(posture.checks) == 4
    names = {c.name for c in posture.checks}
    assert names == {
        "pre_trust_execution",
        "direct_injection",
        "egress_exploitation",
        "visibility_loss",
    }


def test_audit_evidence_strings_are_non_empty(tmp_path: Path) -> None:
    coord = _make_coord(tmp_path)
    posture = audit_containment(coord)
    for check in posture.checks:
        assert len(check.evidence) > 0, f"{check.name!r} has empty evidence"


# ---- failure modes: tampered defenses -----------------------------------


def test_audit_fails_on_cleared_tripwires(tmp_path: Path) -> None:
    """Clearing tripwire patterns is detected as an undefended pre-trust gate."""
    coord = _make_coord(tmp_path)
    coord.tripwires._patterns = []
    posture = audit_containment(coord)
    pre_trust = next(c for c in posture.checks if c.name == "pre_trust_execution")
    assert not pre_trust.defended
    assert not posture.overall_defended


def test_audit_fails_on_cleared_constitution(tmp_path: Path) -> None:
    """Clearing constitution patterns is detected as an undefended injection gate."""
    coord = _make_coord(tmp_path)
    coord.constitution._patterns = ()
    posture = audit_containment(coord)
    direct = next(c for c in posture.checks if c.name == "direct_injection")
    assert not direct.defended
    assert not posture.overall_defended


def test_audit_fails_on_elevated_builder_ceiling(tmp_path: Path) -> None:
    """If tier_guard lets the Builder reach T2+, egress exploitation is open."""
    coord = _make_coord(tmp_path)
    coord.tier_guard._role_ceiling["builder"] = CapabilityTier.T2
    posture = audit_containment(coord)
    egress = next(c for c in posture.checks if c.name == "egress_exploitation")
    assert not egress.defended
    assert not posture.overall_defended


def test_audit_fails_without_event_log(tmp_path: Path) -> None:
    """Removing the event log is detected as a visibility gap."""
    coord = _make_coord(tmp_path)
    coord.event_log = None  # type: ignore[assignment]
    posture = audit_containment(coord)
    visibility = next(c for c in posture.checks if c.name == "visibility_loss")
    assert not visibility.defended
    assert not posture.overall_defended
