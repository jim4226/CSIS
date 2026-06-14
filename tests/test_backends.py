"""Backend model-map unit tests.

These tests verify that _DEFAULT_MODEL_MAP resolves checkpoint labels to the
correct Anthropic model IDs without requiring the anthropic SDK or an API key.
"""
from __future__ import annotations

import pytest

from csis.backends.anthropic import _DEFAULT_MODEL_MAP


@pytest.mark.parametrize("label,expected", [
    ("alpha", "claude-opus-4-7"),
    ("beta", "claude-sonnet-4-6"),
    ("mock-alpha", "claude-opus-4-7"),
    ("mock-beta", "claude-sonnet-4-6"),
    ("fable", "claude-fable-5"),
    ("mythos", "claude-mythos-5"),
])
def test_default_model_map_labels(label: str, expected: str) -> None:
    assert _DEFAULT_MODEL_MAP[label] == expected


def test_fable_label_present() -> None:
    """Regression: fable checkpoint label must resolve to claude-fable-5."""
    assert "fable" in _DEFAULT_MODEL_MAP
    assert _DEFAULT_MODEL_MAP["fable"] == "claude-fable-5"


def test_mythos_label_present() -> None:
    """Regression: mythos checkpoint label must resolve to claude-mythos-5."""
    assert "mythos" in _DEFAULT_MODEL_MAP
    assert _DEFAULT_MODEL_MAP["mythos"] == "claude-mythos-5"
