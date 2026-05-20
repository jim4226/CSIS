"""Cross-platform exclusive inter-process file lock.

Snapshot-12 fix (extracted from csis.budget): EventLog needed the same
cross-process serialization that BudgetTracker already had. Moving the
primitive into substrate/ makes it available to any module without an
import cycle (substrate has no dependents in csis/).

Behavior:
  - On Windows: ``msvcrt.locking`` byte-range lock (~20s retry budget).
  - On POSIX: ``fcntl.flock`` exclusive blocking lock.
  - If neither module is available (or flock errors with ENOLCK on NFS/SMB),
    we raise :class:`LockUnavailable` rather than silently degrading.

Usage:
    from csis.substrate.file_lock import file_lock, LockUnavailable
    with file_lock(Path("foo.lock")):
        ...read-modify-write...

The data file and lock file should be distinct paths so a corrupt data
file doesn't strand the lock (or vice versa).
"""
from __future__ import annotations

import contextlib
import sys
import time
from pathlib import Path


class LockUnavailable(RuntimeError):
    """Raised when the OS doesn't support real inter-process file locking.

    Callers that need cross-process safety must refuse to operate rather
    than silently disable concurrency protection. Cycle-5 D6 originated
    this convention for the budget tracker; snapshot-12 promotes it to
    the event log too.
    """


@contextlib.contextmanager
def file_lock(lock_path: Path):
    """Cross-platform exclusive inter-process file lock.

    On Windows uses ``msvcrt.locking``; on POSIX uses ``fcntl.flock``.
    Raises :class:`LockUnavailable` if the platform module is missing
    or the filesystem (NFS/SMB) refuses byte-range locks.
    """
    lock_path = Path(lock_path)
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
                    "cannot enforce inter-process file locking"
                ) from exc
            for _attempt in range(200):  # ~20s of waiting in 0.1s ticks
                try:
                    f.seek(0)
                    msvcrt.locking(f.fileno(), msvcrt.LK_NBLCK, 1)
                    locked = True
                    break
                except (OSError, PermissionError):
                    time.sleep(0.1)
            if not locked:
                raise LockUnavailable(
                    f"could not acquire file lock at {lock_path} within 20s"
                )
        else:
            try:
                import fcntl  # type: ignore[import-not-found]
            except ImportError as exc:
                raise LockUnavailable(
                    "fcntl module unavailable on this POSIX build; "
                    "cannot enforce inter-process file locking"
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
