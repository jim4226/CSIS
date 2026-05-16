"""MockBackend — deterministic, scriptable per role.

This is the default. It lets the whole CSIS prototype run with `pip install
pydantic pytest` and no API key — tests, demos, CI all use it. The bytes
moved between agents are real; only the LLM is faked.

How scripting works:
    backend = MockBackend()
    backend.script("researcher", "ckpt-A", lambda req: "...plan json...")
    # or fixed:
    backend.script("verifier", "ckpt-B", "ok")

Per-role scripts can be:
    - a string (returned verbatim)
    - a callable (LLMRequest -> str)
    - a list (consumed FIFO; raises when empty)
"""
from __future__ import annotations

import threading
from collections import deque
from typing import Any, Callable, Union

from csis.backends.base import LLMBackend, LLMRequest, LLMResponse


Script = Union[str, Callable[[LLMRequest], str], list[Union[str, Callable[[LLMRequest], str]]]]


class MockBackend(LLMBackend):
    name = "mock"

    def __init__(self) -> None:
        self._scripts: dict[tuple[str, str], Script] = {}
        self._calls: list[LLMRequest] = []
        self._lock = threading.Lock()
        # F1 mitigation: scripted hint for what "model id" the cert should
        # record. Defaults to the checkpoint id but can be overridden so
        # we can simulate same-model-different-prompt drift in tests.
        self._model_id_for_checkpoint: dict[str, str] = {}
        # F6 mitigation: tools the backend will expose for a given checkpoint.
        self._tools_for_checkpoint: dict[str, list[str]] = {}

    # ---- scripting -----------------------------------------------------

    def script(self, role: str, checkpoint_id: str, response: Script) -> "MockBackend":
        with self._lock:
            self._scripts[(role, checkpoint_id)] = response
        return self

    def set_model_id(self, checkpoint_id: str, model_id: str) -> None:
        with self._lock:
            self._model_id_for_checkpoint[checkpoint_id] = model_id

    def set_tools(self, checkpoint_id: str, tools: list[str]) -> None:
        with self._lock:
            self._tools_for_checkpoint[checkpoint_id] = list(tools)

    def calls(self) -> list[LLMRequest]:
        """All LLMRequests this backend has seen, in order."""
        with self._lock:
            return list(self._calls)

    # ---- backend interface ---------------------------------------------

    def complete(self, req: LLMRequest) -> LLMResponse:
        with self._lock:
            self._calls.append(req)
            script = self._scripts.get((req.role, req.checkpoint_id))

        if script is None:
            # Default response: an empty placeholder, but include the request
            # echo so test failures are informative.
            text = (
                f"[mock:no-script role={req.role} ckpt={req.checkpoint_id}] "
                f"prompt-prefix={req.prompt[:80]!r}"
            )
        elif isinstance(script, str):
            text = script
        elif callable(script):
            text = script(req)
        elif isinstance(script, list):
            with self._lock:
                if not script:
                    raise RuntimeError(
                        f"mock script exhausted for role={req.role} ckpt={req.checkpoint_id}"
                    )
                item = script.pop(0)
            text = item(req) if callable(item) else str(item)
        else:
            raise TypeError(f"unsupported script type for role={req.role}: {type(script)}")

        return LLMResponse(
            role=req.role,
            checkpoint_id=req.checkpoint_id,
            text=text,
            tokens_in=len(req.prompt) // 4,
            tokens_out=len(text) // 4,
            raw={"backend": "mock"},
        )

    def checkpoint_identity(self, checkpoint_id: str) -> dict[str, str]:
        with self._lock:
            model_id = self._model_id_for_checkpoint.get(checkpoint_id, checkpoint_id)
            tools = list(self._tools_for_checkpoint.get(checkpoint_id, ["sandbox", "memory"]))
        # F1 mitigation: include model_id + tools as part of identity so the
        # certificate records distinct values even when the prompt-level
        # behavior happens to be the same.
        return {
            "checkpoint_id": checkpoint_id,
            "backend": self.name,
            "model_id": model_id,
            "tool_set": ",".join(sorted(tools)),
        }
