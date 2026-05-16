"""Per-day cumulative budget tracker.

Synthesis recommendation #3: today the cost-ceiling lives only in
`scripts/burst.py` (per-run). An operator who runs the real backend via
the daemon 24/7 has no cumulative umbrella. This module adds one.

Persistence: a JSON file keyed by date string. Loading + saving is
atomic (write-tempfile-then-rename) so a crash doesn't corrupt totals.

Cost estimation: same rough-prices-per-1k-tokens table as burst.py.
Tokens-in is estimated from prompt length / 4; tokens-out is fixed at
800 per call (mid-range for our structured prompts). Real billing
differs; this is a guardrail, not an accountant.
"""
from __future__ import annotations

import json
import os
import tempfile
import threading
import time
from dataclasses import asdict, dataclass, field
from datetime import date, datetime, timezone
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


class BudgetTracker:
    """Thread-safe per-day cumulative cost tracker.

    Usage:
        tracker = BudgetTracker(path="brain/daemon.budget.json", max_cost_per_day_usd=5.0)
        tracker.check_or_raise()                # before an iteration
        tracker.record(model_id, prompt_chars, response_tokens=800)  # after each call
    """

    def __init__(self, path: str | Path, *, max_cost_per_day_usd: float | None = None) -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.max_cost_per_day_usd = max_cost_per_day_usd
        self._lock = threading.Lock()
        self._state = BudgetState()
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
        with self._lock:
            return {
                "max_cost_per_day_usd": self.max_cost_per_day_usd,
                "today": asdict(self._state.current()),
                "history": [asdict(d) for d in self._state.days],
            }

    # ---- check + record -----------------------------------------------

    def check_or_raise(self) -> None:
        """Call before starting an iteration. If the day's cumulative cost
        is already at or above the cap, raises BudgetCapExceeded."""
        if self.max_cost_per_day_usd is None:
            return
        with self._lock:
            today = self._state.current()
            if today.cost_usd >= self.max_cost_per_day_usd:
                raise BudgetCapExceeded(
                    f"day {today.day} cumulative cost ${today.cost_usd:.4f} "
                    f">= cap ${self.max_cost_per_day_usd:.4f}"
                )

    def record(self, model_id: str, prompt_chars: int, response_tokens: int = 800) -> float:
        """Record one LLM call. Returns the day's new cumulative cost."""
        prices = _PRICE_PER_1K.get(model_id, _DEFAULT_PRICE)
        tokens_in = max(0, prompt_chars) // 4
        tokens_out = max(0, response_tokens)
        delta_cost = (tokens_in / 1000.0) * prices["in"] + (tokens_out / 1000.0) * prices["out"]
        with self._lock:
            today = self._state.current()
            today.calls += 1
            today.tokens_in += tokens_in
            today.tokens_out += tokens_out
            today.cost_usd = round(today.cost_usd + delta_cost, 6)
            self._save()
            return today.cost_usd


class _BackendTracker:
    """Wraps an LLMBackend to record every complete() call against a BudgetTracker.

    Use like this in the daemon:
        backend = _BackendTracker(backend, tracker)
    Anything that calls backend.complete(req) goes through the tracker;
    everything else (script(), set_model_id, calls(), checkpoint_identity)
    is delegated unchanged.
    """

    def __init__(self, wrapped, tracker: BudgetTracker) -> None:
        self._wrapped = wrapped
        self._tracker = tracker

    def __getattr__(self, name: str):
        return getattr(self._wrapped, name)

    @property
    def name(self) -> str:
        return getattr(self._wrapped, "name", "wrapped")

    def complete(self, req):
        # Pre-check: refuse if we're at the cap.
        self._tracker.check_or_raise()
        resp = self._wrapped.complete(req)
        # Resolve model_id from the checkpoint identity for pricing.
        ident = self._wrapped.checkpoint_identity(req.checkpoint_id)
        model_id = ident.get("model_id", req.checkpoint_id)
        # Use the actual response tokens if the backend reports them.
        out_tokens = getattr(resp, "tokens_out", None) or 800
        self._tracker.record(model_id, len(req.prompt), out_tokens)
        return resp

    def checkpoint_identity(self, checkpoint_id: str) -> dict[str, str]:
        return self._wrapped.checkpoint_identity(checkpoint_id)
