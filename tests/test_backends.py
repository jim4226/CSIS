"""Regression tests for csis.backends.anthropic's checkpoint -> model map.

Added 2026-06-30: Claude Sonnet 5 launched and the "beta" checkpoint (the
Sonnet-class checkpoint used by Verifier/Auditor) was bumped to it. This
guards against silently drifting "beta" back onto an Opus-class model,
which would collapse the cross-checkpoint distinction the cycle-9
`assert_cross_checkpoint` invariant depends on.
"""
from __future__ import annotations

from csis.backends.anthropic import AnthropicBackend, _DEFAULT_MODEL_MAP


def test_beta_checkpoint_maps_to_sonnet_5():
    assert _DEFAULT_MODEL_MAP["beta"] == "claude-sonnet-5"
    assert _DEFAULT_MODEL_MAP["mock-beta"] == "claude-sonnet-5"


def test_alpha_and_beta_stay_on_distinct_model_families():
    alpha = _DEFAULT_MODEL_MAP["alpha"]
    beta = _DEFAULT_MODEL_MAP["beta"]
    assert "opus" in alpha
    assert "sonnet" in beta


def test_resolve_model_honors_custom_override_without_touching_default_map():
    backend = object.__new__(AnthropicBackend)
    backend._model_map = {**_DEFAULT_MODEL_MAP, "beta": "claude-sonnet-4-6"}

    assert backend._resolve_model("beta") == "claude-sonnet-4-6"
    assert backend._resolve_model("alpha") == _DEFAULT_MODEL_MAP["alpha"]
    assert _DEFAULT_MODEL_MAP["beta"] == "claude-sonnet-5"
