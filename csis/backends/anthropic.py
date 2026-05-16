"""AnthropicBackend — optional, lazy-imported.

Wraps the official anthropic SDK. If the SDK isn't installed or no API key
is set, instantiation raises immediately — the prototype falls back to
MockBackend in that case (handled at config-load time).

Mapping from CSIS checkpoint labels to Anthropic models:
    "alpha"  ->  claude-opus-4-7
    "beta"   ->  claude-sonnet-4-6
Custom labels can override via the constructor mapping.
"""
from __future__ import annotations

import os
from typing import Any

from csis.backends.base import LLMBackend, LLMRequest, LLMResponse


_DEFAULT_MODEL_MAP = {
    "mock-alpha": "claude-opus-4-7",
    "mock-beta": "claude-sonnet-4-6",
    "alpha": "claude-opus-4-7",
    "beta": "claude-sonnet-4-6",
}


class AnthropicBackend(LLMBackend):
    name = "anthropic"

    def __init__(
        self,
        api_key: str | None = None,
        model_map: dict[str, str] | None = None,
    ) -> None:
        try:
            import anthropic  # type: ignore  # noqa: F401
        except ImportError as exc:
            raise RuntimeError(
                "anthropic SDK not installed. Run `pip install anthropic` "
                "or set CSIS_BACKEND=mock."
            ) from exc

        from anthropic import Anthropic  # type: ignore

        key = api_key or os.environ.get("ANTHROPIC_API_KEY")
        if not key:
            raise RuntimeError(
                "ANTHROPIC_API_KEY not set. Export it or set CSIS_BACKEND=mock."
            )
        self._client = Anthropic(api_key=key)
        self._model_map = {**_DEFAULT_MODEL_MAP, **(model_map or {})}

    def _resolve_model(self, checkpoint_id: str) -> str:
        return self._model_map.get(checkpoint_id, "claude-opus-4-7")

    def complete(self, req: LLMRequest) -> LLMResponse:
        model = self._resolve_model(req.checkpoint_id)
        msg = self._client.messages.create(
            model=model,
            max_tokens=req.max_tokens,
            system=req.system,
            messages=[{"role": "user", "content": req.prompt}],
        )
        # Extract text content blocks.
        text_parts: list[str] = []
        for block in getattr(msg, "content", []):
            text = getattr(block, "text", None)
            if isinstance(text, str):
                text_parts.append(text)
        usage = getattr(msg, "usage", None)
        return LLMResponse(
            role=req.role,
            checkpoint_id=req.checkpoint_id,
            text="".join(text_parts),
            tokens_in=getattr(usage, "input_tokens", 0) or 0,
            tokens_out=getattr(usage, "output_tokens", 0) or 0,
            raw={"backend": "anthropic", "model": model, "stop_reason": getattr(msg, "stop_reason", None)},
        )

    def checkpoint_identity(self, checkpoint_id: str) -> dict[str, str]:
        return {
            "checkpoint_id": checkpoint_id,
            "backend": self.name,
            "model_id": self._resolve_model(checkpoint_id),
            "tool_set": "anthropic-native",
        }


def make_default_backend() -> LLMBackend:
    """Try AnthropicBackend; fall back to MockBackend if missing key/SDK."""
    try:
        return AnthropicBackend()
    except Exception:
        from csis.backends.mock import MockBackend
        return MockBackend()
