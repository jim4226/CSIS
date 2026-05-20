# Snapshot 12 — Event-log chain integrity, cross-process fix

**Date:** 2026-05-20
**Trigger:** Auto-snapshot 002200 reported `chain integrity: BROKEN: seq gap at expected 5710, got 5693`. Investigation found 5 cumulative breaks in the historical `event_log/session.jsonl`, all at `coordinator iter.start` events.

## What broke

The pre-snapshot-12 `EventLog` used a `threading.Lock()` to serialize emits, which protects callers in the **same Python process** but not across processes. The repo's default `event_log_path` is shared (`REPO_ROOT/event_log/session.jsonl`), so two daemon instances — or `python -m csis.daemon` + `python scripts/burst.py` running concurrently — would both:

1. Open the same JSONL file
2. Cache their own `_seq` counter on init via `_restore_from_disk()`
3. Take turns appending lines, each using its locally-cached `_seq`
4. Stomp each other: process B's emit at "seq 5710" lands AFTER process A has already written seqs up to 5709, but process B's seq counter was last refreshed when only 5693 events existed → process B writes seq=5693 (a backward jump)

This is the same race shape as cycle-7 F2 / cycle-8 G2 / cycle-9 H4 (sibling-write race on candidate stores) but in the substrate layer one floor below. Cycle 9's H4 fix landed on `MemoryStore`; this snapshot lands the equivalent on `EventLog`.

### The 5 historical breaks

Detected by walking the historical file:

| Line | Expected seq | Got seq | Prev seq | Event | Timestamp |
|---:|---:|---:|---:|---|---|
|  5711 |  5710 |  5693 |  5709 | `coordinator iter.start` | 2026-05-12 04:07 UTC |
|  5945 |  5927 |  5903 |  5926 | `coordinator iter.start` | 2026-05-12 05:37 UTC |
|  9099 |  9057 |  9025 |  9056 | `coordinator iter.start` | 2026-05-13 01:09 UTC |
|  9350 |  9276 |  9235 |  9275 | `coordinator iter.start` | 2026-05-13 02:09 UTC |
| 10213 | 10098 | 10089 | 10097 | `coordinator iter.start` | 2026-05-13 06:10 UTC |

Every break is "next line's seq is LESS than the line above it" — the unambiguous signature of two writers each caching their own seq.

## What changed

**1. Extracted the cross-process lock primitive** (`csis/substrate/file_lock.py`)

`LockUnavailable` + `file_lock(path)` context manager — msvcrt byte-range lock on Windows, fcntl flock on POSIX. Refuses to silently degrade if neither is available (NFS/SMB ENOLCK, missing module).

This is the same pattern `csis/budget.py` already used internally; promoting it to `csis.substrate` makes it available to `EventLog` without introducing an import cycle, since `substrate/` has no dependencies on `budget/` or `agents/`. `budget.py` now imports the primitive from the shared location; public surface (`LockUnavailable`, `_file_lock`) preserved as re-exports so out-of-tree callers don't break.

**2. EventLog.emit acquires the inter-process file lock**

```python
def emit(self, actor, kind, payload=None):
    ...
    with self._lock, file_lock(self._lock_path):
        self._restore_from_disk_unlocked()   # re-sync to live file state
        event = Event(seq=self._seq, ...)
        ...
        self._seq += 1
        self._prev_hash = event_hash
```

The critical new line is `_restore_from_disk_unlocked()` inside the locked section: before writing, we re-read the file's tail under the lock so our cached `_seq` reflects any sibling process's writes. This is what closes the race — once we hold the lock, our view of the file is authoritative.

Lock file is `session.jsonl.lock` (separate from the data file so a corrupt data file doesn't strand the lock and vice versa).

**3. Quarantined the broken historical log**

`event_log/session.jsonl` → `event_log/session.broken-pre-snap12-2026-05-20.jsonl` (12.0 MB, 20,811 lines, 5 chain breaks, never deleted — kept as evidence). The next daemon start creates a fresh `session.jsonl` from genesis.

Since `event_log/` is gitignored, this is a local-only operation; no commit churn. Operators on other checkouts have not (and could not have) accumulated the same race because they have not run this specific daemon-process pair pattern.

**4. Two new regression tests**

`tests/test_substrate.py`:

- `test_event_log_two_instances_same_file_share_chain` — two in-process `EventLog` instances interleave 5 emits to the same file; final chain verifies and seqs are `[0,1,2,3,4]`. Pre-fix this failed (each instance had a stale cache).
- `test_event_log_cross_process_serialization` — spawns **4 subprocesses × 25 emits each** to the same JSONL via `subprocess.Popen`. Chain verifies, seqs are contiguous `0..99`. This is the actual condition the historical log failed; the test now gates against regression.

## Test status

- **246 passed** (was 244, +2 new), 4 skipped (POSIX-only), 0 failures.
- New `test_event_log_cross_process_serialization` adds ~2s to suite runtime (spawns Python subprocesses).
- All pre-existing event-log + budget-tracker tests pass unmodified — the budget.py import re-shuffle is API-preserving.

## Why this is the right fix at the right layer

Cycle 9 closed the candidate-store sibling-write race with "identity beats timing" (`writer_iteration_id` on each entry). That works for memory stores where each entry has its own identity. The event log's hash chain is the inverse: identity *is* sequence — there's exactly one canonical seq=N event, so the only correct fix is mutual exclusion at the write site.

The cycle-9 lesson "chokepoints beat perimeters" applies cleanly: `EventLog.emit` is THE chokepoint for every event in the system. Lock there once; nothing downstream needs to know.

## What this does NOT fix (honest open items)

1. **Operator UX for double-start.** With the fix, two concurrent daemons no longer corrupt the chain — but they DO race to do duplicate work. A PID lockfile in `Daemon.run_forever()` that refuses startup when a sibling daemon is alive would be cleaner. Deferred; the substrate fix is the safety-critical layer.
2. **The historical broken file is not repaired**, only quarantined. Repairing it (renumbering seqs, recomputing hashes) would destroy the only evidence of the race; the .broken file is more useful as a forensic artifact than as recovered history.
3. **Daemon `iterations_total=2246` does not reset.** Stats live in `brain/daemon.stats.json` (not the event log), so the cumulative counters survive the event-log restart. This is intentional — `iterations_total` is operator-visible state, not a chain-anchored claim.

## Cumulative state

- **csis/** +~110 LOC (file_lock module + EventLog refactor + budget.py import shuffle).
- **tests/** 246 passing (+2 new), 4 skipped POSIX-only.
- **brain/snapshots/** 12 numbered snapshots + 12 auto-snapshots (latest 002200).
- **event_log/** fresh `session.jsonl` (genesis) + quarantined `.broken-pre-snap12-2026-05-20.jsonl`.

The system is now safe to run with `python scripts/burst.py --backend anthropic` alongside (or instead of) the daemon — the cross-process chain integrity that the architecture page claims is now actually enforced.
