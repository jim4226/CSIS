"""Shared test helpers (not a conftest — importable from any test file).

`wrap_for_test`: H1 (cycle-9) added a Coordinator constructor check that
refuses any backend that isn't exactly a `_BackendTracker`. Tests that
want to construct a Coordinator with a mock backend wrap it via this
helper, which centralizes the boilerplate.
"""
from __future__ import annotations

import tempfile
from pathlib import Path

from csis.budget import BudgetTracker, _BackendTracker


def wrap_for_test(backend, tmp_path: Path | str | None = None):
    """Wrap a raw backend in a no-cap `_BackendTracker` so the Coordinator
    accepts it. Pass `tmp_path` to keep the tracker file scoped to the
    test (default: in-memory-like tmp path under the system temp dir).
    """
    root = Path(tmp_path) if tmp_path is not None else Path(tempfile.mkdtemp())
    return _BackendTracker(backend, BudgetTracker(root / "test.budget.json"))
