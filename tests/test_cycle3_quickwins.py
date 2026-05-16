"""Regression tests for cycle-3 phase-A quick wins (synthesis gaps #4, #6, #7)."""
from __future__ import annotations

from pathlib import Path

import pytest

from csis.agents.base import ALLOWED_EMIT_ACTORS, Role
from csis.curiosity import Curiosity
from csis.memory.store import MemoryHierarchy
from csis.substrate.event_log import EventLog, UnknownActorError


# ---- synthesis gap #4: ALLOWED_EMIT_ACTORS lives next to Role enum ------


def test_allowed_emit_actors_contains_every_role() -> None:
    """Adding a new Role automatically extends the allow-list."""
    for role in Role:
        assert role.value in ALLOWED_EMIT_ACTORS, (
            f"Role {role.value} missing from ALLOWED_EMIT_ACTORS — "
            f"the single source of truth must include every Role."
        )


def test_allowed_emit_actors_includes_non_role_actors() -> None:
    """Substrate + Overseer can emit even though they aren't Role members."""
    assert "overseer" in ALLOWED_EMIT_ACTORS
    assert "substrate" in ALLOWED_EMIT_ACTORS


def test_event_log_uses_central_allowlist(tmp_path: Path) -> None:
    """EventLog rejects unknown actors via the central allow-list, not a
    local copy that could drift."""
    log = EventLog(tmp_path / "events.jsonl")
    # Any role name passes.
    for role in Role:
        log.emit(role.value, "tick", {})
    # Unknown actor still rejected.
    with pytest.raises(UnknownActorError):
        log.emit("attacker_role", "x", {})


# ---- synthesis gap #6: entropy in gap-driven curiosity prompts ----------


def test_gap_driven_prompts_vary_under_stable_state(tmp_path: Path) -> None:
    """Two consecutive gap-driven picks must produce DIFFERENT prompts
    even when the hierarchy state is identical (i.e., still empty)."""
    h = MemoryHierarchy.open(tmp_path)
    cur = Curiosity()
    a = cur.next(h)
    b = cur.next(h)
    # Both gap-driven (empty hierarchy), but text must differ via salt.
    assert a.source == "gap-driven" and b.source == "gap-driven"
    assert a.text != b.text, f"entropy not injected: a={a.text!r} b={b.text!r}"
    assert "salt=" in a.text and "salt=" in b.text
