"""Shutdownability — Overseer halt enforced at substrate, not asked of agents.

If `halt()` is called, every subsequent `check()` raises. The Coordinator
checks before each iteration. Resistance to shut-down is a separate
tripwire (`shutdown_evasion`) caught in safety.tripwires.
"""
from __future__ import annotations

import threading


class HaltSignal(Exception):
    """Raised when an iteration is attempted past a halt() call."""


class ShutdownToken:
    def __init__(self) -> None:
        self._halted = threading.Event()
        self._reason: str = ""

    def halt(self, reason: str = "operator halt") -> None:
        self._reason = reason
        self._halted.set()

    def is_halted(self) -> bool:
        return self._halted.is_set()

    def reason(self) -> str:
        return self._reason

    def check(self) -> None:
        if self._halted.is_set():
            raise HaltSignal(self._reason or "halted")

    def clear(self) -> None:
        """For tests only. Don't call from agent code."""
        self._halted.clear()
        self._reason = ""
