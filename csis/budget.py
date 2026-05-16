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
class PendingReservation:
    """A reservation written to disk before the call runs.

    D3 (cycle-5) mitigation: without persisted reservations, two daemons
    could each reserve 60% of the cap and both overshoot. PendingReservations
    are written under the file lock, visible to siblings, and cleared by
    record() once the call lands.

    E3 (cycle-6) fix: token field added so multi-call same-pid daemons
    can cancel/record the RIGHT reservation, not the first one matching pid.
    Without this, a 3-concurrent-call daemon mis-cancels and either
    over-reserves or under-reserves siblings.
    """
    pid: int
    amount_usd: float
    ts: float
    token: str = ""


@dataclass
class BudgetState:
    """Persistent state: list of recent days, most recent first.

    We keep the last 30 days for trend visibility; older entries are
    dropped on save to keep the file bounded.
    """
    days: list[DayBudget] = field(default_factory=list)
    pending: list[PendingReservation] = field(default_factory=list)

    def current(self) -> DayBudget:
        key = _today_key()
        if not self.days or self.days[0].day != key:
            self.days.insert(0, DayBudget(day=key))
            self.days = self.days[:30]
        return self.days[0]

    def prune_stale_pending(self, max_age_s: float = 3600.0) -> None:
        """Drop reservations older than max_age_s (cycle-6 E6: default
        bumped from 600s to 3600s). A process that crashed mid-call would
        otherwise hold its reservation forever and starve siblings; but a
        too-aggressive timeout strands long-running real API calls
        (Anthropic Opus with extended thinking can run >10 min)."""
        now = time.time()
        self.pending = [p for p in self.pending if (now - p.ts) <= max_age_s]

    def pending_total(self) -> float:
        return sum(p.amount_usd for p in self.pending)


class BudgetCapExceeded(Exception):
    """Raised when an attempted call would push the day over the cap."""


class LockUnavailable(RuntimeError):
    """D6 (cycle-5) mitigation: raised when the OS doesn't support real
    inter-process file locking. We refuse to start with a budget cap
    enabled rather than silently disabling concurrency safety."""


@contextlib.contextmanager
def _file_lock(lock_path: Path):
    """Cross-platform exclusive inter-process file lock.

    On Windows uses msvcrt.locking; on POSIX uses fcntl.flock. If neither
    is available we raise LockUnavailable (D6 fix — was: silently set
    locked=True and pretend).

    Cycle-4 C2 + cycle-5 D6 mitigation. The lock file is separate from
    the data file so a corrupt data file doesn't strand the lock and
    vice versa.
    """
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    f = open(lock_path, "a+b")
    locked = False
    try:
        if sys.platform == "win32":
            try:
                import msvcrt  # type: ignore[import-not-found]
            except ImportError as exc:
                raise LockUnavailable(
                    "msvcrt module unavailable on Windows; "
                    "cannot enforce inter-process budget locking"
                ) from exc
            for _attempt in range(200):  # ~20s of waiting in 0.1s ticks
                try:
                    f.seek(0)
                    msvcrt.locking(f.fileno(), msvcrt.LK_NBLCK, 1)
                    locked = True
                    break
                # D6: catch broader exceptions, not just OSError. A
                # PermissionError on a restricted Windows build used to
                # crash __init__; now we retry then raise LockUnavailable.
                except (OSError, PermissionError):
                    time.sleep(0.1)
            if not locked:
                raise LockUnavailable(
                    f"could not acquire budget lock at {lock_path} within 20s"
                )
        else:
            try:
                import fcntl  # type: ignore[import-not-found]
            except ImportError as exc:
                raise LockUnavailable(
                    "fcntl module unavailable on this POSIX build; "
                    "cannot enforce inter-process budget locking"
                ) from exc
            try:
                fcntl.flock(f.fileno(), fcntl.LOCK_EX)
                locked = True
            except OSError as exc:
                # ENOLCK on NFS / SMB — refuse rather than silently disable.
                raise LockUnavailable(
                    f"flock failed at {lock_path}: {exc!r} (NFS/SMB?)"
                ) from exc
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
        prune_stale_pending_s: float = 3600.0,
    ) -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.max_cost_per_day_usd = max_cost_per_day_usd
        self.max_cost_per_call_usd = max_cost_per_call_usd
        # E6 (cycle-6) fix: prune timeout configurable; default 1 hour
        # so legitimately slow API calls don't get stranded.
        self.prune_stale_pending_s = prune_stale_pending_s
        self._lock = threading.Lock()
        self._file_lock_path = self.path.with_suffix(self.path.suffix + ".lock")
        self._state = BudgetState()
        # E5 (cycle-6) fix: only require the lock when a cap is set.
        # Mock daemons with no cap can run on systems without fcntl/msvcrt
        # by falling through to a best-effort load.
        if self._needs_locking():
            with _file_lock(self._file_lock_path):
                self._load()
        else:
            try:
                self._load()
            except Exception:
                self._state = BudgetState()

    def _needs_locking(self) -> bool:
        """Lock only matters when there's a budget cap to enforce."""
        return self.max_cost_per_day_usd is not None or self.max_cost_per_call_usd is not None

    def _load(self) -> None:
        if not self.path.exists():
            return
        try:
            raw = json.loads(self.path.read_text(encoding="utf-8"))
            days = [DayBudget(**d) for d in raw.get("days", [])]
            pending = [PendingReservation(**p) for p in raw.get("pending", [])]
            self._state = BudgetState(days=days, pending=pending)
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
                json.dump({
                    "days": [asdict(d) for d in self._state.days],
                    "pending": [asdict(p) for p in self._state.pending],
                }, f, indent=2)
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

    def reserve_or_raise(self, estimated_cost_usd: float) -> str:
        """Cycle-4 C3 + cycle-5 D3 + cycle-6 E3 fix: refuse calls whose
        pre-call estimate plus any sibling daemons' PENDING reservations
        would push past either the per-call ceiling or the per-day cap.

        Reservations are persisted under the file lock (cycle-5 D3) and
        tagged with a unique token (cycle-6 E3) so multi-call same-pid
        daemons can match the right reservation in cancel/record.
        """
        if self.max_cost_per_call_usd is not None and estimated_cost_usd > self.max_cost_per_call_usd:
            raise BudgetCapExceeded(
                f"per-call estimate ${estimated_cost_usd:.4f} > "
                f"max_cost_per_call ${self.max_cost_per_call_usd:.4f}"
            )
        with self._lock, _file_lock(self._file_lock_path):
            self._load()
            self._state.prune_stale_pending(self.prune_stale_pending_s)
            today = self._state.current()
            pending = self._state.pending_total()
            if self.max_cost_per_day_usd is not None:
                if today.cost_usd + pending + estimated_cost_usd > self.max_cost_per_day_usd:
                    raise BudgetCapExceeded(
                        f"day {today.day} cumulative ${today.cost_usd:.4f} + "
                        f"pending ${pending:.4f} + reservation ${estimated_cost_usd:.4f} "
                        f"> cap ${self.max_cost_per_day_usd:.4f}"
                    )
            token = f"res-{os.getpid()}-{int(time.time()*1_000_000)}-{len(self._state.pending)}"
            self._state.pending.append(PendingReservation(
                pid=os.getpid(),
                amount_usd=float(estimated_cost_usd),
                ts=time.time(),
                token=token,
            ))
            self._save()
            return token

    def record(self, model_id: str, prompt_chars: int, response_tokens: int = 800,
               reservation_token: str | None = None) -> float:
        """Record one LLM call. Returns the day's new cumulative cost.

        Cycle-4 C2 + cycle-5 D3 + cycle-6 E3: read-modify-write under
        inter-process lock; reservation cleared by TOKEN (not pid) so
        same-pid concurrent calls don't mis-cancel each other.
        """
        prices = _PRICE_PER_1K.get(model_id, _DEFAULT_PRICE)
        tokens_in = max(0, prompt_chars) // 4
        tokens_out = max(0, response_tokens)
        delta_cost = (tokens_in / 1000.0) * prices["in"] + (tokens_out / 1000.0) * prices["out"]
        with self._lock, _file_lock(self._file_lock_path):
            self._load()  # pick up sibling-daemon writes
            self._state.prune_stale_pending(self.prune_stale_pending_s)
            today = self._state.current()
            today.calls += 1
            today.tokens_in += tokens_in
            today.tokens_out += tokens_out
            today.cost_usd = round(today.cost_usd + delta_cost, 6)
            if reservation_token is not None:
                # E3: match by token, not pid.
                for i, p in enumerate(self._state.pending):
                    if p.token == reservation_token:
                        del self._state.pending[i]
                        break
            self._save()
            return today.cost_usd

    def cancel_reservation(self, reservation_token: str) -> None:
        """Clear a reservation without recording a real call. Used when
        the wrapped backend raises before a response is produced.

        E3 (cycle-6): match by token. Previous pid-match removed the
        first matching entry, mis-cancelling other concurrent reservations
        on the same daemon.
        """
        with self._lock, _file_lock(self._file_lock_path):
            self._load()
            self._state.prune_stale_pending(self.prune_stale_pending_s)
            for i, p in enumerate(self._state.pending):
                if p.token == reservation_token:
                    del self._state.pending[i]
                    self._save()
                    return


def estimate_cost(model_id: str, prompt_chars: int, max_tokens: int = 800) -> float:
    """Pre-call estimate using max_tokens as upper bound on tokens_out.
    Used by reserve_or_raise."""
    prices = _PRICE_PER_1K.get(model_id, _DEFAULT_PRICE)
    tokens_in = max(0, prompt_chars) // 4
    return (tokens_in / 1000.0) * prices["in"] + (max(0, max_tokens) / 1000.0) * prices["out"]


class _BackendTracker:
    """Wraps an LLMBackend to record every complete() call against a BudgetTracker.

    Cycle-4 C4 + cycle-5 D5 + cycle-6 E4: the wrapped backend is held in
    a CLOSURE captured at __init__, NOT in an instance attribute. There
    is no `_wrapped`, `__wrapped`, or `_BackendTracker__wrapped` reachable
    via attribute access or `dir()`. The only way to call the backend is
    via the explicitly-forwarded `complete()` and `checkpoint_identity()`
    methods on this wrapper.

    Subclasses that try to re-introduce a `_wrapped` attribute (the cycle-6
    E4 attack) raise TypeError at class definition time via
    __init_subclass__.
    """

    def __init_subclass__(cls, **kwargs):
        super().__init_subclass__(**kwargs)
        # E4 (cycle-6) fix: refuse subclasses that re-introduce the
        # bypass attribute, no matter what name they use.
        forbidden = {"_wrapped", "__wrapped", "_BackendTracker__wrapped"}
        for name in cls.__dict__:
            if name in forbidden:
                raise TypeError(
                    f"_BackendTracker subclass {cls.__name__} cannot define "
                    f"{name!r} — it would re-expose the wrapped backend "
                    f"and bypass metering"
                )

    def __init__(self, wrapped, tracker: BudgetTracker) -> None:
        from csis.backends.base import LLMBackend  # noqa: F401
        # Capture wrapped+tracker in closures. Instance attributes hold
        # ONLY the bound closures, not the wrapped object itself. dir(self)
        # will not list the wrapped backend.
        self.name = getattr(wrapped, "name", "wrapped")

        def _do_complete(req):
            ident = wrapped.checkpoint_identity(req.checkpoint_id)
            model_id = ident.get("model_id", req.checkpoint_id)
            est = estimate_cost(model_id, len(req.prompt), getattr(req, "max_tokens", 800))
            token = tracker.reserve_or_raise(est)
            try:
                resp = wrapped.complete(req)
            except Exception:
                tracker.cancel_reservation(token)
                raise
            # C8: distinguish missing-attr (default 800) from real zero.
            out_tokens_attr = getattr(resp, "tokens_out", None)
            out_tokens = 800 if out_tokens_attr is None else out_tokens_attr
            tracker.record(model_id, len(req.prompt), out_tokens, reservation_token=token)
            return resp

        def _do_checkpoint_identity(checkpoint_id):
            return wrapped.checkpoint_identity(checkpoint_id)

        self._call_complete = _do_complete
        self._call_identity = _do_checkpoint_identity

    # ---- Explicit LLMBackend surface (cycle-4 C4) ----------------------

    def complete(self, req):
        return self._call_complete(req)

    def checkpoint_identity(self, checkpoint_id: str) -> dict[str, str]:
        return self._call_identity(checkpoint_id)
