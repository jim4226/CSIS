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
import os
import sys
import time
from pathlib import Path


# S1 (cycle-10): bound on the open/lock/inode-recheck retry loop. The swap
# window (unlink + recreate between two holders) is tiny; if we re-detect a
# mismatch this many times the path is being churned pathologically and we
# refuse rather than spin forever.
_INODE_RECHECK_MAX_TRIES = 50


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
            # S1 (cycle-10): fcntl.flock binds to the inode of the open fd,
            # NOT the path. If the lock file is unlinked+recreated (stale-lock
            # cleanup, tmpreaper, `rm *.lock`) between our open() and another
            # holder's open(), both processes flock DIFFERENT inodes of the
            # same path and both enter the critical section — mutual exclusion
            # silently broken (the deferred H11, verified reproducible on
            # Linux). After acquiring the flock we therefore validate that the
            # inode we hold is still the inode the path resolves to. If a swap
            # happened (st(path) != fstat(fd)) we are holding a now-orphaned
            # inode that protects nothing: drop it, reopen the live file, and
            # re-lock. Bounded retries so a pathologically churned path can't
            # spin us forever.
            for _attempt in range(_INODE_RECHECK_MAX_TRIES):
                try:
                    fcntl.flock(f.fileno(), fcntl.LOCK_EX)
                except OSError as exc:
                    # ENOLCK on NFS / SMB — refuse rather than silently disable.
                    raise LockUnavailable(
                        f"flock failed at {lock_path}: {exc!r} (NFS/SMB?)"
                    ) from exc
                st_fd = os.fstat(f.fileno())
                try:
                    st_path = os.stat(lock_path)
                except FileNotFoundError:
                    # Path was unlinked out from under us while we held the
                    # flock — the inode we locked is orphaned. Re-create and
                    # re-lock.
                    st_path = None
                if st_path is not None and (
                    (st_path.st_dev, st_path.st_ino) == (st_fd.st_dev, st_fd.st_ino)
                ):
                    # We hold the flock on the inode the path resolves to:
                    # genuine mutual exclusion.
                    locked = True
                    break
                # Inode was swapped under the path. Release the orphaned
                # inode's flock, close it, reopen the live path, and retry.
                try:
                    fcntl.flock(f.fileno(), fcntl.LOCK_UN)
                except OSError:
                    pass
                f.close()
                f = open(lock_path, "a+b")
            if not locked:
                raise LockUnavailable(
                    f"could not pin a stable inode for lock file {lock_path} "
                    f"after {_INODE_RECHECK_MAX_TRIES} reopen attempts "
                    f"(path being churned/swapped concurrently?)"
                )
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
