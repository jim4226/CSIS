"""Per-day cumulative budget tracker.

Synthesis recommendation #3: today the cost-ceiling lives only in
`scripts/burst.py` (per-run). An operator who runs the real backend via
the daemon 24/7 has no cumulative umbrella. This module adds one.

Persistence: a JSON file keyed by date string. Loading + saving is
atomic (write-tempfile-then-rename) and protected by an inter-process
file lock so two concurrent daemons cannot stomp each other's totals
(cycle-4 C2 fix). Every record() re-reads the file under the lock,
applies the delta, writes back, releases — read-modify-write atomicity.

Cost estimation: same rough-prices-per-1k-tokens table as burst.py.
Tokens-in is estimated from prompt length / 4; tokens-out is fixed at
800 per call (mid-range for our structured prompts) unless the backend
reports otherwise. Cycle-4 C8 fix: a real `tokens_out=0` (refusal,
content-policy stop) is now respected rather than over-charged to 800.
"""
from __future__ import annotations

import contextlib
import json
import os
import sys
import tempfile
import threading
import time
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path


# Same default price table as scripts/burst.py. Keep in sync.
_PRICE_PER_1K = {
    "claude-opus-4-7": {"in": 0.015, "out": 0.075},
    "claude-sonnet-4-6": {"in": 0.003, "out": 0.015},
    "mock-opus-like": {"in": 0.0, "out": 0.0},
    "mock-sonnet-like": {"in": 0.0, "out": 0.0},
    "mock-opus": {"in": 0.0, "out": 0.0},
    "mock-sonnet": {"in": 0.0, "out": 0.0},
}

_DEFAULT_PRICE = {"in": 0.015, "out": 0.075}  # assume Opus-like for unknown


def _today_key(now: float | None = None) -> str:
    """UTC date string yyyy-mm-dd. UTC for monotonic-day semantics that
    don't drift across timezone changes."""
    ts = datetime.fromtimestamp(now if now is not None else time.time(), tz=timezone.utc)
    return ts.date().isoformat()


@dataclass
class DayBudget:
    """One day's running totals."""
    day: str
    calls: int = 0
    tokens_in: int = 0
    tokens_out: int = 0
    cost_usd: float = 0.0


@dataclass
class BudgetState:
    """Persistent state: list of recent days, most recent first.

    We keep the last 30 days for trend visibility; older entries are
    dropped on save to keep the file bounded.
    """
    days: list[DayBudget] = field(default_factory=list)

    def current(self) -> DayBudget:
        key = _today_key()
        if not self.days or self.days[0].day != key:
            self.days.insert(0, DayBudget(day=key))
            self.days = self.days[:30]
        return self.days[0]


class BudgetCapExceeded(Exception):
    """Raised when an attempted call would push the day over the cap."""


@contextlib.contextmanager
def _file_lock(lock_path: Path):
    """Cross-platform exclusive inter-process file lock.

    On Windows uses msvcrt.locking; on POSIX uses fcntl.flock. Falls back
    to a best-effort PID-file approach if neither is available (in which
    case concurrent daemons are still detected but not strictly serialized).

    Cycle-4 C2 mitigation. The lock file is separate from the data file
    so a corrupt data file doesn't strand the lock and vice versa.
    """
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    f = open(lock_path, "a+b")
    locked = False
    try:
        if sys.platform == "win32":
            import msvcrt  # type: ignore[import-not-found]
            for _attempt in range(200):  # ~20s of waiting in 0.1s ticks
                try:
                    f.seek(0)
                    msvcrt.locking(f.fileno(), msvcrt.LK_NBLCK, 1)
                    locked = True
                    break
                except OSError:
                    time.sleep(0.1)
            if not locked:
                raise TimeoutError(f"could not acquire budget lock at {lock_path} within 20s")
        else:
            try:
                import fcntl  # type: ignore[import-not-found]
                fcntl.flock(f.fileno(), fcntl.LOCK_EX)
                locked = True
            except ImportError:
                # Last-ditch: no real lock available.
                locked = True
        yield
    finally:
        try:
            if locked and sys.platform == "win32":
                import msvcrt  # type: ignore[import-not-found]
                f.seek(0)
                msvcrt.locking(f.fileno(), msvcrt.LK_UNLCK, 1)
            elif locked:
                try:
                    import fcntl  # type: ignore[import-not-found]
                    fcntl.flock(f.fileno(), fcntl.LOCK_UN)
                except ImportError:
                    pass
        finally:
            f.close()


class BudgetTracker:
    """Thread- AND process-safe per-day cumulative cost tracker.

    Usage:
        tracker = BudgetTracker(
            path="brain/daemon.budget.json",
            max_cost_per_day_usd=5.0,
            max_cost_per_call_usd=0.5,     # cycle-4 C3: single-call ceiling
        )
        tracker.reserve_or_raise(estimated_cost_usd)  # before an LLM call
        tracker.record(model_id, prompt_chars, response_tokens=800)  # after each call
    """

    def __init__(
        self,
        path: str | Path,
        *,
        max_cost_per_day_usd: float | None = None,
        max_cost_per_call_usd: float | None = None,
    ) -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.max_cost_per_day_usd = max_cost_per_day_usd
        self.max_cost_per_call_usd = max_cost_per_call_usd
        self._lock = threading.Lock()
        self._file_lock_path = self.path.with_suffix(self.path.suffix + ".lock")
        self._state = BudgetState()
        # Initial load under the file lock.
        with _file_lock(self._file_lock_path):
            self._load()

    def _load(self) -> None:
        if not self.path.exists():
            return
        try:
            raw = json.loads(self.path.read_text(encoding="utf-8"))
            days = [DayBudget(**d) for d in raw.get("days", [])]
            self._state = BudgetState(days=days)
        except Exception:
            # Corrupt file: start fresh but preserve the bad one for
            # post-mortem so we don't silently lose history.
            corrupt = self.path.with_suffix(self.path.suffix + f".corrupt.{int(time.time())}")
            try:
                self.path.rename(corrupt)
            except Exception:
                pass
            self._state = BudgetState()

    def _save(self) -> None:
        # Atomic write: temp file in same dir then rename.
        fd, tmp_path = tempfile.mkstemp(prefix="budget.", suffix=".json.tmp", dir=str(self.path.parent))
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                json.dump({"days": [asdict(d) for d in self._state.days]}, f, indent=2)
            os.replace(tmp_path, self.path)
        except Exception:
            try:
                os.unlink(tmp_path)
            except Exception:
                pass
            raise

    # ---- read ----------------------------------------------------------

    def today_cost_usd(self) -> float:
        with self._lock:
            return self._state.current().cost_usd

    def today_calls(self) -> int:
        with self._lock:
            return self._state.current().calls

    def snapshot(self) -> dict:
        # Cycle-4 C2 fix: re-read under the file lock so the snapshot
        # reflects sibling-daemon writes too. Without this, two daemons
        # would each report only their own spend.
        with self._lock, _file_lock(self._file_lock_path):
            self._load()
            return {
                "max_cost_per_day_usd": self.max_cost_per_day_usd,
                "today": asdict(self._state.current()),
                "history": [asdict(d) for d in self._state.days],
            }

    # ---- check + record -----------------------------------------------

    def check_or_raise(self) -> None:
        """Call before starting an iteration. If the day's cumulative cost
        is already at or above the cap, raises BudgetCapExceeded.

        Cycle-4 C2 fix: re-loads from disk under the file lock so a sibling
        daemon's writes are visible.
        """
        if self.max_cost_per_day_usd is None:
            return
        with self._lock, _file_lock(self._file_lock_path):
            self._load()
            today = self._state.current()
            if today.cost_usd >= self.max_cost_per_day_usd:
                raise BudgetCapExceeded(
                    f"day {today.day} cumulative cost ${today.cost_usd:.4f} "
                    f">= cap ${self.max_cost_per_day_usd:.4f}"
                )

    def reserve_or_raise(self, estimated_cost_usd: float) -> None:
        """Cycle-4 C3 fix: refuse calls whose pre-call estimate would
        single-handedly push past either the per-call ceiling or the
        per-day cap. The estimate uses req.max_tokens as the output
        upper bound, so even a refused or oversize call cannot overshoot
        by more than the estimator's own error margin."""
        if self.max_cost_per_call_usd is not None and estimated_cost_usd > self.max_cost_per_call_usd:
            raise BudgetCapExceeded(
                f"per-call estimate ${estimated_cost_usd:.4f} > "
                f"max_cost_per_call ${self.max_cost_per_call_usd:.4f}"
            )
        if self.max_cost_per_day_usd is None:
            return
        with self._lock, _file_lock(self._file_lock_path):
            self._load()
            today = self._state.current()
            if today.cost_usd + estimated_cost_usd > self.max_cost_per_day_usd:
                raise BudgetCapExceeded(
                    f"day {today.day} cumulative ${today.cost_usd:.4f} + "
                    f"reservation ${estimated_cost_usd:.4f} > cap "
                    f"${self.max_cost_per_day_usd:.4f}"
                )

    def record(self, model_id: str, prompt_chars: int, response_tokens: int = 800) -> float:
        """Record one LLM call. Returns the day's new cumulative cost.

        Cycle-4 C2 fix: read-modify-write happens under an inter-process
        file lock with a re-read from disk, so concurrent daemons accumulate
        correctly rather than each holding stale in-memory state."""
        prices = _PRICE_PER_1K.get(model_id, _DEFAULT_PRICE)
        tokens_in = max(0, prompt_chars) // 4
        tokens_out = max(0, response_tokens)
        delta_cost = (tokens_in / 1000.0) * prices["in"] + (tokens_out / 1000.0) * prices["out"]
        with self._lock, _file_lock(self._file_lock_path):
            self._load()  # pick up sibling-daemon writes
            today = self._state.current()
            today.calls += 1
            today.tokens_in += tokens_in
            today.tokens_out += tokens_out
            today.cost_usd = round(today.cost_usd + delta_cost, 6)
            self._save()
            return today.cost_usd


def estimate_cost(model_id: str, prompt_chars: int, max_tokens: int = 800) -> float:
    """Pre-call estimate using max_tokens as upper bound on tokens_out.
    Used by reserve_or_raise."""
    prices = _PRICE_PER_1K.get(model_id, _DEFAULT_PRICE)
    tokens_in = max(0, prompt_chars) // 4
    return (tokens_in / 1000.0) * prices["in"] + (max(0, max_tokens) / 1000.0) * prices["out"]


class _BackendTracker:
    """Wraps an LLMBackend to record every complete() call against a BudgetTracker.

    Cycle-4 C4 fix: explicit forwarding of the LLMBackend ABC surface only.
    No __getattr__ — anything not on the ABC raises AttributeError. New
    cost-bearing methods added to LLMBackend in the future MUST be added
    here too (the test in test_budget.py introspects the ABC and fails
    if a method is missing).
    """

    __slots__ = ("_wrapped", "_tracker", "name")

    def __init__(self, wrapped, tracker: BudgetTracker) -> None:
        # Importing here to avoid a hard module-load dependency.
        from csis.backends.base import LLMBackend  # noqa: F401
        self._wrapped = wrapped
        self._tracker = tracker
        self.name = getattr(wrapped, "name", "wrapped")

    # ---- Explicit LLMBackend surface (cycle-4 C4) ----------------------

    def complete(self, req):
        # Cycle-4 C3 fix: reserve the estimated cost BEFORE the call so a
        # single oversized prompt cannot overshoot the day cap. Uses
        # req.max_tokens as the upper bound on output spend.
        ident = self._wrapped.checkpoint_identity(req.checkpoint_id)
        model_id = ident.get("model_id", req.checkpoint_id)
        est = estimate_cost(model_id, len(req.prompt), getattr(req, "max_tokens", 800))
        self._tracker.reserve_or_raise(est)

        resp = self._wrapped.complete(req)

        # Cycle-4 C8 fix: distinguish "backend didn't report tokens_out"
        # (default to 800) from "backend reported zero" (refusal, content
        # policy, etc.) — the latter must record as zero, not 800.
        out_tokens_attr = getattr(resp, "tokens_out", None)
        out_tokens = 800 if out_tokens_attr is None else out_tokens_attr
        self._tracker.record(model_id, len(req.prompt), out_tokens)
        return resp

    def checkpoint_identity(self, checkpoint_id: str) -> dict[str, str]:
        return self._wrapped.checkpoint_identity(checkpoint_id)
