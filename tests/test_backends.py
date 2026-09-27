"""Regression tests for backend model-map and budget pricing table.

These do not instantiate AnthropicBackend (requires a live API key) but
assert the module-level constants that govern which Anthropic model ID the
real backend routes each checkpoint to.
"""
from csis.backends.anthropic import _DEFAULT_MODEL_MAP
from csis.budget import _PRICE_PER_1K


def test_alpha_checkpoint_maps_to_opus_4_8() -> None:
    # Routine update 2026-06-13: claude-opus-4-8 is the current flagship.
    # Fable 5 / Mythos 5 were suspended by government directive 2026-06-12.
    assert _DEFAULT_MODEL_MAP["alpha"] == "claude-opus-4-8"
    assert _DEFAULT_MODEL_MAP["mock-alpha"] == "claude-opus-4-8"


def test_beta_checkpoint_maps_to_sonnet_4_6() -> None:
    assert _DEFAULT_MODEL_MAP["beta"] == "claude-sonnet-4-6"
    assert _DEFAULT_MODEL_MAP["mock-beta"] == "claude-sonnet-4-6"


def test_opus_4_8_has_budget_entry() -> None:
    # Prevents silent fallback to _DEFAULT_PRICE when cost is tracked.
    assert "claude-opus-4-8" in _PRICE_PER_1K
    entry = _PRICE_PER_1K["claude-opus-4-8"]
    assert entry["in"] > 0
    assert entry["out"] > 0
