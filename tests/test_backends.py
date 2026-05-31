"""Tests for csis/backends/anthropic.py — model-map resolution.

These tests exercise AnthropicBackend._resolve_model() without hitting the
real API; they import the backend class and call the private helper directly
so no API key or SDK is required.
"""
from __future__ import annotations

import pytest

from csis.backends.anthropic import AnthropicBackend, _DEFAULT_MODEL_MAP


class TestDefaultModelMap:
    """_DEFAULT_MODEL_MAP contract: known labels → correct model IDs."""

    def test_alpha_maps_to_opus_4_7(self):
        assert _DEFAULT_MODEL_MAP["alpha"] == "claude-opus-4-7"

    def test_alpha_4_8_maps_to_opus_4_8(self):
        # Added 2026-05-31: Opus 4.8 opt-in checkpoint (same pricing as 4.7,
        # ~4x lower flaw-overlooking rate per Anthropic May-2026 launch notes).
        assert _DEFAULT_MODEL_MAP["alpha-4.8"] == "claude-opus-4-8"

    def test_beta_maps_to_sonnet_4_6(self):
        assert _DEFAULT_MODEL_MAP["beta"] == "claude-sonnet-4-6"

    def test_mock_alpha_maps_to_opus_4_7(self):
        assert _DEFAULT_MODEL_MAP["mock-alpha"] == "claude-opus-4-7"

    def test_mock_beta_maps_to_sonnet_4_6(self):
        assert _DEFAULT_MODEL_MAP["mock-beta"] == "claude-sonnet-4-6"


class _StubClient:
    """Stand-in for anthropic.Anthropic; lets us instantiate the backend
    without a real API key."""

    class messages:
        @staticmethod
        def create(**kwargs):  # pragma: no cover
            raise AssertionError("not expected in unit tests")


class TestResolveModel:
    """AnthropicBackend._resolve_model falls back to claude-opus-4-7 for
    unknown labels and correctly surfaces every label in _DEFAULT_MODEL_MAP."""

    def _make_backend(self, extra: dict | None = None) -> AnthropicBackend:
        backend = object.__new__(AnthropicBackend)
        backend._client = _StubClient()
        backend._model_map = {**_DEFAULT_MODEL_MAP, **(extra or {})}
        return backend

    def test_known_label_alpha(self):
        assert self._make_backend()._resolve_model("alpha") == "claude-opus-4-7"

    def test_known_label_alpha_4_8(self):
        assert self._make_backend()._resolve_model("alpha-4.8") == "claude-opus-4-8"

    def test_known_label_beta(self):
        assert self._make_backend()._resolve_model("beta") == "claude-sonnet-4-6"

    def test_unknown_label_falls_back_to_opus_4_7(self):
        # The fallback default is intentionally conservative: if a new
        # checkpoint label is introduced without a matching map entry, the
        # backend uses the most capable Opus model rather than silently
        # producing a weaker / wrong model.
        assert self._make_backend()._resolve_model("nonexistent") == "claude-opus-4-7"

    def test_custom_override_takes_precedence(self):
        backend = self._make_backend(extra={"alpha": "claude-opus-4-8"})
        assert backend._resolve_model("alpha") == "claude-opus-4-8"
