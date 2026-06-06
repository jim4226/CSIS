"""AnthropicBackend — optional, lazy-imported.

Wraps the official anthropic SDK. If the SDK isn't installed or no API key
is set, instantiation raises immediately — the prototype falls back to
MockBackend in that case (handled at config-load time).

Mapping from CSIS checkpoint labels to Anthropic models:
    "alpha"  ->  claude-opus-4-7
    "beta"   ->  claude-sonnet-4-6
Custom labels can override via the constructor mapping.

Monitoring instrumentation (added for the live-dashboard work):
  - Per-call latency captured in LLMResponse.raw['latency_ms']
  - Retry count + retry reasons captured in LLMResponse.raw['retries']
  - Exponential backoff on RateLimitError / APIStatusError 5xx
  - Real token counts always taken from the API response (not estimated)
"""
from __future__ import annotations

import os
import random
import time
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
        fallback_models: list[str] | None = None,
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
        # Fallback chain: tried in order after primary exhausts capacity retries.
        self._fallback_models: list[str] = list(fallback_models or [])

    def _resolve_model(self, checkpoint_id: str) -> str:
        return self._model_map.get(checkpoint_id, "claude-opus-4-7")

    # Retry policy for transient API failures. Tuned conservatively because
    # the BudgetTracker reservation is already debited; we want the call to
    # eventually succeed so the reservation doesn't expire as a phantom.
    _MAX_RETRIES = 4
    _BASE_BACKOFF_S = 1.0  # exponential: 1, 2, 4, 8 with jitter

    def complete(self, req: LLMRequest) -> LLMResponse:
        primary = self._resolve_model(req.checkpoint_id)
        retries: list[dict] = []
        msg = None
        last_exc = None
        current_model = primary
        started = time.monotonic()

        # Lazy-import the SDK error types so the module still loads if the
        # caller swapped in a fake client (e.g. unit tests).
        try:
            from anthropic import APIStatusError, RateLimitError  # type: ignore
        except ImportError:  # pragma: no cover - sdk shape changed
            APIStatusError = Exception  # type: ignore
            RateLimitError = Exception  # type: ignore

        # Outer loop: primary model, then each fallback on capacity errors.
        # Fallbacks get one attempt each; only capacity failures (429 / 5xx)
        # advance to the next model. Caller errors (4xx) raise immediately.
        for model_idx, current_model in enumerate([primary] + self._fallback_models):
            max_retries = self._MAX_RETRIES if model_idx == 0 else 0
            capacity_failed = False

            for attempt in range(max_retries + 1):
                try:
                    msg = self._client.messages.create(
                        model=current_model,
                        max_tokens=req.max_tokens,
                        system=req.system,
                        messages=[{"role": "user", "content": req.prompt}],
                    )
                    break
                except RateLimitError as exc:  # 429
                    last_exc = exc
                    capacity_failed = True
                    if attempt >= max_retries:
                        break
                    backoff = self._BASE_BACKOFF_S * (2 ** attempt) + random.uniform(0, 0.5)
                    retries.append({"attempt": attempt + 1, "model": current_model, "reason": "rate_limit", "backoff_s": round(backoff, 3)})
                    time.sleep(backoff)
                except APIStatusError as exc:  # 5xx / other status errors
                    status = getattr(exc, "status_code", 0)
                    if status < 500:
                        # 4xx: caller error; don't retry or fall back.
                        last_exc = exc
                        raise
                    last_exc = exc
                    capacity_failed = True
                    if attempt >= max_retries:
                        break
                    backoff = self._BASE_BACKOFF_S * (2 ** attempt) + random.uniform(0, 0.5)
                    retries.append({"attempt": attempt + 1, "model": current_model, "reason": f"http_{status}", "backoff_s": round(backoff, 3)})
                    time.sleep(backoff)

            if msg is not None or not capacity_failed:
                break  # success, or non-capacity failure already raised above

        latency_ms = int((time.monotonic() - started) * 1000)

        if msg is None:
            n = len(self._fallback_models) + 1
            raise RuntimeError(
                f"Anthropic backend exhausted retries across {n} model(s) "
                f"after {latency_ms} ms; last error: {type(last_exc).__name__}: {last_exc}"
            ) from last_exc

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
            raw={
                "backend": "anthropic",
                "model": current_model,
                "stop_reason": getattr(msg, "stop_reason", None),
                "latency_ms": latency_ms,
                "retries": retries,
            },
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
