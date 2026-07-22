"""Cycle-13 regression tests — the Workflow-driven red-team of the loop.

Cycle 13 ran the repo's methodology through the Workflow orchestration
primitive (parallel finders per subsystem, each finding adversarially verified
by 3 diverse-lens skeptics). It hit fresh surface — the agent-role modules and
the deep verification statistics no prior cycle had directly attacked — and
found 15 defects cycles 10-12 missed, including two HIGH security issues. Each
test below asserts the EFFECT and is built to FAIL on the pre-fix code.

  store-K1        promote()/mark_verified() returned live handles (M4 gap)
  store-K2        a flush failure left a promote applied-but-reported-failed ghost
  eventlog-K1     verify_chain reported an honest-crash-longer chain as BROKEN
  eventlog-K2     iter_events raised on a torn final line (no reader lock)
  eventlog-K3     emit re-parsed the whole file (O(n^2)); tail fast path + fallback
  agents-K1  HIGH diff-scope self-mod guard bypassed by // / . / .. in the path
  agents-K2       dreams contradiction detector missed internal negations
  crosscut-K1 HIGH unicode-whitespace separators glued words, defeating patterns
  crosscut-K2     config.phase_ceiling was decorative (not enforced)
  verification-K1 HIGH bootstrap CI depended on sample ROW ORDER
  verification-K2 no min-n floor: a single sample passed with a zero-width CI
  verification-K3 the distributional verdict never gated the cert
  verification-K4 model-declared check false-rejected a legit checkpoint==model pair
  coordinator-K1  an overwritten pre-existing cross-tier candidate survived rollback
  coordinator-K2  post-promote check read STICKY tripwire history
"""
from __future__ import annotations

import random
import tempfile
from pathlib import Path

import pytest

from csis.contracts import (
    Artifact, CriticFinding, DistributionalGraderResult, GraderResult, MemoryEntry, Plan,
)
from csis.memory.store import MemoryStore, content_hash
from csis.memory.trust import TrustLevel


def _mk(eid, content="c", trust=TrustLevel.CANDIDATE, tier="episodic", extra=None):
    return MemoryEntry(entry_id=eid, tier=tier, content=content, trust=trust,
                       why_tag="t", created_at=1.0, extra=extra or {})


# ---- store-K1: mutation-primitive returns must not be live handles ---------


def test_store_k1_promote_return_is_not_a_live_handle(tmp_path: Path) -> None:
    s = MemoryStore("episodic", tmp_path)
    s.write_candidate(_mk("e1", extra={"k": "orig"}))
    s.mark_verified(["e1"])
    p = s.promote(["e1"], precondition_hash=s.live_hash(), why_id="w")
    p[0].extra["evil"] = "X"
    p[0].content = "POISONED"
    live = s.read_live("e1", role="auditor")
    assert "evil" not in live.extra and live.content != "POISONED"


def test_store_k1_mark_verified_return_is_not_a_live_handle(tmp_path: Path) -> None:
    s = MemoryStore("episodic", tmp_path)
    s.write_candidate(_mk("e1"))
    out = s.mark_verified(["e1"])
    out[0].extra["evil"] = "Y"
    assert "evil" not in s.read_candidate("e1", role="auditor").extra
    # idempotent short-circuit branch (already VERIFIED) must also not leak
    out2 = s.mark_verified(["e1"])
    out2[0].extra["evil2"] = "Z"
    assert "evil2" not in s.read_candidate("e1", role="auditor").extra


# ---- store-K2: a flush failure must not leave a ghost ----------------------


def test_store_k2_promote_flush_failure_rolls_back(tmp_path: Path) -> None:
    s = MemoryStore("episodic", tmp_path)
    s.write_candidate(_mk("e1"))
    s.mark_verified(["e1"])
    s._flush = lambda: (_ for _ in ()).throw(OSError("disk full"))  # type: ignore[assignment]
    with pytest.raises(OSError):
        s.promote(["e1"], precondition_hash=s.live_hash(), why_id="w")
    # reported failure -> no in-memory ghost, candidate intact
    del s._flush  # restore the bound method
    assert list(s.iter_live(role="auditor")) == []
    assert "e1" in s.candidate_ids()


# ---- eventlog-K1/K2/K3 -----------------------------------------------------


def _fresh_log(tmp_path: Path):
    from csis.substrate.event_log import EventLog
    return EventLog(tmp_path / "ev.jsonl"), tmp_path / "ev.jsonl"


def test_eventlog_k1_honest_crash_longer_than_anchor_is_intact(tmp_path: Path) -> None:
    from csis.substrate.event_log import EventLog, Event, SignedEvent
    log, p = _fresh_log(tmp_path)
    for i in range(4):
        log.emit("coordinator", "tick", {"i": i})
    # append a valid 5th event WITHOUT advancing the anchor (the fsync->anchor
    # crash window): file has 5 events, anchor records 5-after-4... emulate by
    # appending a correctly-chained event directly.
    ev = Event(seq=4, timestamp=1.0, actor="coordinator", kind="tick", payload={"i": 4})
    eh = SignedEvent.compute_hash(ev, log.latest_hash())
    se = SignedEvent(event=ev, prev_hash=log.latest_hash(), event_hash=eh)
    with p.open("a", encoding="utf-8") as f:
        f.write(se.model_dump_json() + "\n")
    ok, reason = EventLog(p).verify_chain()
    assert ok, f"honest longer-than-anchor chain must verify intact, got {reason}"


def test_eventlog_k2_iter_events_tolerates_torn_final_line(tmp_path: Path) -> None:
    from csis.substrate.event_log import EventLog
    log, p = _fresh_log(tmp_path)
    for i in range(3):
        log.emit("coordinator", "tick", {"i": i})
    with p.open("a", encoding="utf-8") as f:
        f.write('{"event":{"seq":3,"timestamp')  # torn fragment, no newline
    events = list(EventLog(p).iter_events())  # must not raise
    assert len(events) == 3


def test_eventlog_k3_tail_fast_path_and_forged_fallback(tmp_path: Path) -> None:
    from csis.substrate.event_log import EventLog, Event, SignedEvent
    log, p = _fresh_log(tmp_path)
    for i in range(20):
        log.emit("coordinator", "tick", {"i": i})
    assert log.seq() == 20 and EventLog(p).verify_chain()[0]
    # forged non-chaining tail -> full-walk fallback quarantines, never extends
    forged = SignedEvent(
        event=Event(seq=20, timestamp=1.0, actor="coordinator", kind="x", payload={}),
        prev_hash="00" * 32, event_hash="ff" * 32)
    with p.open("a", encoding="utf-8") as f:
        f.write(forged.model_dump_json() + "\n")
    nxt = EventLog(p).emit("coordinator", "tick", {"after": "recovery"})
    assert nxt.prev_hash != "ff" * 32  # chained onto the recovered prefix, not the forgery
    assert len(list(tmp_path.glob("*.broken-*.jsonl"))) == 1


# ---- agents-K1: diff-scope path-normalization bypass (HIGH) -----------------


@pytest.mark.parametrize("path", [
    "csis/agents/coordinator.py",              # honest
    "csis/agents//coordinator.py",             # redundant slash
    "csis/./agents/coordinator.py",            # /./
    "csis/x/../agents/coordinator.py",         # /../
    "csis/safety//tripwires.py",               # forbidden dir, evaded
])
def test_agents_k1_diff_scope_blocks_normalization_evasions(path: str) -> None:
    from csis.verification.graders import touches_forbidden
    forbidden = ("csis/safety/", "csis/agents/coordinator.py", "csis/domains/")
    body = f"diff --git a/{path} b/{path}\n--- a/{path}\n+++ b/{path}\n@@\n-x\n+evil\n"
    assert touches_forbidden(body, forbidden), f"{path!r} must be blocked"


def test_agents_k1_diff_scope_allows_benign() -> None:
    from csis.verification.graders import touches_forbidden
    forbidden = ("csis/safety/", "csis/agents/coordinator.py")
    body = "diff --git a/csis/curiosity.py b/csis/curiosity.py\n+++ b/csis/curiosity.py\n"
    assert not touches_forbidden(body, forbidden)


# ---- agents-K2: dreams contradiction on internal negation ------------------


def test_agents_k2_dreams_detects_internal_negation() -> None:
    from csis.dreams.quality import _contradicts
    assert _contradicts("the migration is not safe", "the migration is safe")
    assert not _contradicts("the plan is good", "the plan is bad")


# ---- crosscut-K1: unicode-whitespace separator evasion (HIGH) --------------


@pytest.mark.parametrize("sep", [" ", " ", " "])  # NFKC does NOT fold these to space
def test_crosscut_k1_unicode_whitespace_separators_fire(sep: str) -> None:
    from csis.safety.tripwires import Tripwires
    t = Tripwires()
    assert t.scan_text(f"disable{sep}the{sep}auditor").fired
    assert t.scan_text(f"exfiltrate{sep}the{sep}api key").fired


def test_crosscut_k1_benign_multiword_still_clean() -> None:
    from csis.safety.tripwires import Tripwires
    assert not Tripwires().scan_text("please describe the auditor role in the doc").fired


# ---- crosscut-K2: phase_ceiling is enforced, not decorative ----------------


def test_crosscut_k2_phase_ceiling_cannot_loosen() -> None:
    from csis.config import CSISConfig
    from csis.substrate.capability import CapabilityTier
    with pytest.raises(ValueError):
        CSISConfig(phase_ceiling=CapabilityTier.T2)


def test_crosscut_k2_lowered_phase_ceiling_tightens_enforcement(tmp_path: Path) -> None:
    from csis.config import CSISConfig
    from csis.substrate.capability import CapabilityTier
    from csis.agents.coordinator import Coordinator
    from csis.backends.mock import MockBackend
    from tests._helpers import wrap_for_test
    cfg = CSISConfig.for_tests(tmp_path)
    cfg.phase_ceiling = CapabilityTier.T0  # forbid even T1 sandbox calls
    b = MockBackend()
    b.set_model_id(cfg.builder_checkpoint, "mock-opus")
    b.set_model_id(cfg.auditor_checkpoint, "mock-sonnet")
    # a T1 plan must now be rejected at the tier gate (effective ceiling T0)
    b.script("researcher", cfg.builder_checkpoint,
             '{"plan_id":"p","frontier_item":"f","hypothesis":"h",'
             '"falsification_condition":"x","budget":{"time_s":1,"tokens":10},'
             '"tier":"T1","tool_calls_planned":[]}')
    coord = Coordinator(config=cfg, backend=wrap_for_test(b, tmp_path))
    res = coord.run_iteration(frontier_item="t")
    assert res.outcome.startswith("rolled-back:tier-violation"), res.outcome


# ---- verification-K1/K2/K3/K4 ----------------------------------------------


def test_verification_k1_bootstrap_ci_is_order_invariant() -> None:
    from csis.verification.distributional_graders import bootstrap_ci
    vals = [0.9, 0.8, 0.85, 0.95, 0.7, 0.88, 0.92, 0.83, 0.91, 0.86]
    a = bootstrap_ci(vals, n_bootstrap=500, rng=random.Random(1))
    b = bootstrap_ci(list(reversed(vals)), n_bootstrap=500, rng=random.Random(1))
    assert a == b


def _grader(threshold=0.5, **kw):
    from csis.verification.distributional_graders import DistributionalGrader, Sample
    class _G(DistributionalGrader):
        name = "t"; metric_name = "m"; direction = "higher_is_better"
        def per_sample_metric(self, s):
            return float(s.payload)
        def _degeneracy(self, s):
            return None
    g = _G(threshold=threshold, n_bootstrap=200, **kw)
    return g, Sample


def test_verification_k2_min_n_floor_blocks_single_sample() -> None:
    g, Sample = _grader()
    r1 = g.evaluate([Sample(case_id="c", payload=0.99, slices={})])
    rN = g.evaluate([Sample(case_id="c", payload=0.99, slices={}) for _ in range(10)])
    assert not r1.passed and "GUARD_FAILED" in r1.detail
    assert rN.passed


def test_verification_k3_distributional_result_gates_the_cert() -> None:
    from csis.verification.certificates import build_certificate
    b_id = {"checkpoint_id": "b", "model_id": "opus", "tool_set": "T", "backend": "anthropic"}
    v_id = {"checkpoint_id": "v", "model_id": "sonnet", "tool_set": "T", "backend": "anthropic"}
    plan = Plan(plan_id="p", frontier_item="f", hypothesis="h", falsification_condition="x")
    art = Artifact(artifact_id="a", plan_id="p", kind="patch", body="x", body_hash="sha256:" + "0" * 64)
    gr = [GraderResult(grader="g", passed=True)]
    cf = [CriticFinding(attempt=f"a{i}", falsified=False) for i in range(3)]
    dfail = DistributionalGraderResult(grader="dice", metric_name="dice", point_estimate=0.4,
                                       ci_lower=0.3, ci_upper=0.5, n_samples=10, threshold=0.9, passed=False)
    cert = build_certificate(plan=plan, artifact=art, builder_identity=b_id, verifier_identity=v_id,
                             grader_results=gr, critic_findings=cf, distributional_results=[dfail])
    assert cert.passed is False
    assert len(cert.distributional_results) == 1


def test_verification_k4_declared_model_equal_to_checkpoint_is_allowed() -> None:
    from csis.verification.certificates import assert_cross_checkpoint, CrossCheckpointViolation
    b = {"checkpoint_id": "opus", "model_id": "opus", "tool_set": "T", "backend": "anthropic", "model_declared": "true"}
    v = {"checkpoint_id": "sonnet", "model_id": "sonnet", "tool_set": "T", "backend": "anthropic", "model_declared": "true"}
    assert_cross_checkpoint(b, v)  # legit distinct declared models — no raise
    # the un-declared default (model_id defaulted to checkpoint_id) is still rejected
    bd = {"checkpoint_id": "builder", "model_id": "builder", "tool_set": "T", "backend": "mock", "model_declared": "false"}
    vd = {"checkpoint_id": "auditor", "model_id": "auditor", "tool_set": "T", "backend": "mock", "model_declared": "false"}
    with pytest.raises(CrossCheckpointViolation):
        assert_cross_checkpoint(bd, vd)


# ---- coordinator-K1: overwritten pre-existing candidate discarded ----------


def test_coordinator_k1_overwritten_pre_existing_is_discarded(tmp_path: Path) -> None:
    from csis.agents.coordinator import Coordinator, IterationResult
    from csis.agents.auditor import TierMismatch
    from csis.backends.mock import MockBackend
    from csis.config import CSISConfig
    from tests._helpers import wrap_for_test
    cfg = CSISConfig.for_tests(tmp_path)
    b = MockBackend(); b.set_model_id(cfg.builder_checkpoint, "o"); b.set_model_id(cfg.auditor_checkpoint, "s")
    coord = Coordinator(config=cfg, backend=wrap_for_test(b, tmp_path))
    store = coord.hierarchy.tier("semantic")
    store.write_candidate(_mk("e-pre", "ORIGINAL", tier="semantic"))
    store.write_candidate(_mk("e-untouched", "KEEP", tier="semantic"))
    pre = {tn: {e.entry_id: content_hash(e) for e in coord.hierarchy.tier(tn).candidates_snapshot()}
           for tn in coord.hierarchy.__class__.tier_names()}
    # ATTACK: overwrite a pre-existing candidate in place with poison, unstamped
    store.write_candidate(_mk("e-pre", "POISONED", tier="semantic"))
    res = IterationResult(iteration_id="iter-k1")
    coord._tier_mismatch_cleanup(
        TierMismatch("lied", claimed_tier="episodic", target_tier="episodic"),
        [], "iter-k1", pre, res)
    assert not store.has_candidate("e-pre"), "overwritten poison must be discarded"
    assert store.has_candidate("e-untouched"), "untouched pre-existing must survive"


# ---- coordinator-K2: no spurious post.halt on a clean promote --------------


def test_coordinator_k2_no_spurious_post_halt_after_historical_tripwire(tmp_path: Path) -> None:
    from csis.agents.coordinator import Coordinator
    from csis.backends.mock import MockBackend
    from csis.config import CSISConfig
    from tests._helpers import wrap_for_test
    cfg = CSISConfig.for_tests(tmp_path)
    b = MockBackend()
    b.set_model_id(cfg.builder_checkpoint, "mock-opus")
    b.set_model_id(cfg.auditor_checkpoint, "mock-sonnet")
    for role, ck, script in [
        ("researcher", cfg.builder_checkpoint,
         '{"plan_id":"p","frontier_item":"f","hypothesis":"h","falsification_condition":"x",'
         '"budget":{"time_s":1,"tokens":10},"tier":"T0","tool_calls_planned":[]}'),
        ("builder", cfg.builder_checkpoint,
         '{"artifact_id":"a","plan_id":"p","kind":"patch","body":"ok","body_hash":"sha256:zz",'
         '"sandbox_logs":[],"extra":{"tests_pass":true,"lint_clean":true,"type_clean":true,'
         '"coverage_delta":0.01,"perf_ratio":1.0}}'),
        ("critic", cfg.auditor_checkpoint,
         '[{"attempt":"a","falsified":false},{"attempt":"b","falsified":false},'
         '{"attempt":"c","falsified":false}]'),
    ]:
        b.script(role, ck, script)
    coord = Coordinator(config=cfg, backend=wrap_for_test(b, tmp_path))
    # Simulate a historical tripwire firing so tripwires.fired() is sticky-True.
    coord.tripwires.scan_text("disable the auditor")
    assert coord.tripwires.fired()  # sticky
    res = coord.run_iteration(frontier_item="ordinary refactor")
    assert res.outcome == "promoted", res.outcome
    post_halts = [e for e in coord.event_log if e.event.kind == "post.halt"]
    assert post_halts == [], "a clean promote must not emit a spurious post.halt"
