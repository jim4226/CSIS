"""Shared test helpers.

H1 (cycle-9): the Coordinator now refuses any backend that is not exactly
a `_BackendTracker`. Tests that construct a Coordinator with a mock
backend must wrap it in a no-cap BudgetTracker first. `wrap_for_test`
centralizes the boilerplate so each test stays one line.
"""
from __future__ import annotations

from pathlib import Path

from csis.budget import BudgetTracker, _BackendTracker


def wrap_for_test(backend, tmp_path: Path | str | None = None):
    """Wrap a raw backend in a no-cap `_BackendTracker` so the Coordinator
    accepts it. Pass `tmp_path` to keep the tracker file scoped to the
    test (default: in-memory-like tmp path under the system temp dir)."""
    import tempfile
    root = Path(tmp_path) if tmp_path is not None else Path(tempfile.mkdtemp())
    return _BackendTracker(backend, BudgetTracker(root / "test.budget.json"))
