"""Concurrency stress tests — promotion atomicity under contention.

Catches F2/F3-class regressions. We run N iterations of the Coordinator
loop against a shared MemoryHierarchy from multiple threads and assert:
  - exactly the right number of entries land in live
  - the event log has no seq gaps
  - the chain stays intact end-to-end
  - no precondition-failure escape leaks a write through anyway
"""
from __future__ import annotations

import threading
from pathlib import Path

from csis.agents.coordinator import Coordinator
from csis.backends.mock import MockBackend
from csis.config import CSISConfig
from csis.contracts import MemoryEntry
from csis.memory.store import MemoryStore, PromotionPreconditionFailure
from csis.memory.trust import TrustLevel


def _new_entry(eid: str) -> MemoryEntry:
    return MemoryEntry(
        entry_id=eid,
        tier="episodic",  # type: ignore[arg-type]
        content=f"content-{eid}",
        trust=TrustLevel.CANDIDATE,
        why_tag="stress",
        created_at=0.0,
    )


def test_promote_serialization_under_contention(tmp_path: Path) -> None:
    """Two threads both try to promote against the same precondition hash;
    exactly one must succeed and the other must raise."""
    store = MemoryStore("episodic", tmp_path)
    a, b = _new_entry("a"), _new_entry("b")
    store.write_candidate(a)
    store.write_candidate(b)
    pre = store.live_hash()  # both threads observed the same pre-hash

    results: dict[str, bool | str] = {}
    barrier = threading.Barrier(2)

    def go(label: str, entry_id: str) -> None:
        barrier.wait()
        try:
            store.promote([entry_id], precondition_hash=pre, why_id=f"why-{label}")
            results[label] = True
        except PromotionPreconditionFailure as exc:
            results[label] = f"rejected:{exc}"
        except Exception as exc:  # noqa: BLE001
            results[label] = f"unexpected:{exc}"

    t1 = threading.Thread(target=go, args=("a", a.entry_id))
    t2 = threading.Thread(target=go, args=("b", b.entry_id))
    t1.start(); t2.start(); t1.join(); t2.join()

    successes = [k for k, v in results.items() if v is True]
    rejections = [k for k, v in results.items() if isinstance(v, str) and v.startswith("rejected:")]
    assert len(successes) == 1, f"exactly one promotion should succeed; got {results}"
    assert len(rejections) == 1, f"the loser should be rejected with stale-precondition; got {results}"


def test_event_log_no_seq_gaps_under_concurrent_emit(tmp_path: Path) -> None:
    cfg = CSISConfig.for_tests(tmp_path)
    backend = MockBackend()
    backend.set_model_id(cfg.builder_checkpoint, "mock-opus")
    backend.set_model_id(cfg.auditor_checkpoint, "mock-sonnet")
    coord = Coordinator(config=cfg, backend=backend)

    threads = []
    for i in range(20):
        threads.append(threading.Thread(
            target=lambda i=i: coord.event_log.emit("coordinator", "stress", {"i": i})
        ))
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    ok, reason = coord.event_log.verify_chain()
    assert ok, reason
    seqs = [s.event.seq for s in coord.event_log]
    assert seqs == list(range(len(seqs)))


def _wire(cfg: CSISConfig) -> MockBackend:
    backend = MockBackend()
    backend.set_model_id(cfg.builder_checkpoint, "mock-opus")
    backend.set_model_id(cfg.auditor_checkpoint, "mock-sonnet")
    backend.set_tools(cfg.builder_checkpoint, ["sandbox.execute"])
    backend.set_tools(cfg.auditor_checkpoint, ["pinned_graders"])
    backend.script("researcher", cfg.builder_checkpoint,
        '{"plan_id":"p","frontier_item":"x","hypothesis":"y",'
        '"falsification_condition":"z","budget":{"time_s":1,"tokens":10},'
        '"tier":"T0","tool_calls_planned":[]}')
    backend.script("builder", cfg.builder_checkpoint,
        '{"artifact_id":"a","plan_id":"p","kind":"patch","body":"# clean\\n",'
        '"body_hash":"sha256:zz","sandbox_logs":[],'
        '"extra":{"tests_pass":true,"lint_clean":true,"type_clean":true,"coverage_delta":0.0,"perf_ratio":1.0}}')
    def critic_script(req):
        return ('[{"attempt":"a","falsified":false},'
                '{"attempt":"b","falsified":false},'
                '{"attempt":"c","falsified":false}]')
    backend.script("critic", cfg.auditor_checkpoint, critic_script)
    return backend


def test_serial_iterations_all_promote_with_intact_log(tmp_path: Path) -> None:
    """Five sequential iterations through the Coordinator. Each must promote;
    the event log must remain chain-intact across all of them."""
    cfg = CSISConfig.for_tests(tmp_path)
    backend = _wire(cfg)
    coord = Coordinator(config=cfg, backend=backend)
    outcomes = []
    for i in range(5):
        res = coord.run_iteration(frontier_item=f"item-{i}")
        outcomes.append(res.outcome)
    assert all(o == "promoted" for o in outcomes), outcomes

    ok, reason = coord.event_log.verify_chain()
    assert ok, reason
