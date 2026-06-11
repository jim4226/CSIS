"""Cycle-11 regression tests — the re-attack of the cycle-10 fixes.

A focused re-attack of the cycle-10 fixes found six close-relative escapes,
each of which the cycle-10 suite missed because its regression tests exercised
only the empty-state / clean-recovery cases:

  F1  M5 cleanup evaded by a FORGED non-null writer_iteration_id.
  F2  M2 commit pass not atomic against a disk-IO fault (_archive ghost).
  F3  Vf1 model_id "different model" check spoofable by cosmetic strings.
  Finding-1 (SF2)  WAL drain silently lost on any NON-empty budget file.
  Finding-2 (S4)   recovery realigns the S2 anchor → laundered tail-rollback.
  Finding-3 (SF5)  acquisition gate still missed authorize/permit/... phrasings.

Each test asserts the *effect* and is built to FAIL on the cycle-10 code and
PASS after the cycle-11 fix.
"""
from __future__ import annotations

import time
from pathlib import Path

import pytest

from csis.agents.auditor import TierMismatch
from csis.agents.coordinator import Coordinator, IterationResult
from csis.backends.mock import MockBackend
from csis.budget import BudgetCapExceeded, BudgetTracker
from csis.config import CSISConfig
from csis.contracts import MemoryEntry
from csis.memory.store import MemoryStore, TrustViolation
from csis.memory.trust import TrustLevel
from csis.safety.tripwires import Tripwires
from csis.verification.certificates import CrossCheckpointViolation, assert_cross_checkpoint
from csis.substrate.event_log import EventLog


def _mk(eid, content="c", trust=TrustLevel.CANDIDATE, tier="episodic", stamp=None):
    return MemoryEntry(entry_id=eid, tier=tier, content=content, trust=trust,
                       why_tag="t", created_at=1.0, writer_iteration_id=stamp)


def _coord(tmp_path: Path) -> Coordinator:
    from tests._helpers import wrap_for_test
    cfg = CSISConfig.for_tests(tmp_path)
    backend = MockBackend()
    backend.set_model_id(cfg.builder_checkpoint, "mock-opus")
    backend.set_model_id(cfg.auditor_checkpoint, "mock-sonnet")
    return Coordinator(config=cfg, backend=wrap_for_test(backend, tmp_path))


# ---- F1: forged-stamp hidden cross-tier write is discarded -----------------


def test_f1_forged_writer_iteration_id_is_discarded(tmp_path: Path) -> None:
    """A hidden cross-tier candidate stamped with a FORGED non-null id (not
    this iteration's) must NOT survive the TierMismatch rollback. cycle-10 M5
    only caught `writer_iteration_id is None`; the forged-stamp close-relative
    evaded it."""
    coord = _coord(tmp_path)
    iteration_id = "iter-f1"

    # Hidden candidate in a non-target tier, stamped with a FORGED id.
    hidden = coord.hierarchy.tier("semantic")
    hidden.write_candidate(_mk("e-forged", tier="semantic", stamp="forged-not-this-iter"))

    # pre-consolidate snapshot does NOT contain e-forged (it was "written
    # during" this iteration, after the snapshot).
    pre_ids = {name: coord.hierarchy.tier(name).candidate_ids()
               for name in coord.hierarchy.__class__.tier_names()}
    pre_ids["semantic"] = set()

    result = IterationResult(iteration_id=iteration_id)
    exc = TierMismatch("lied", claimed_tier="episodic", target_tier="episodic")
    coord._tier_mismatch_cleanup(exc, [], iteration_id, pre_ids, result)

    assert not hidden.has_candidate("e-forged"), (
        "F1: a forged-stamp hidden write absent from the pre-snapshot must be "
        "discarded on rollback"
    )


def test_f1_pre_existing_candidate_still_survives(tmp_path: Path) -> None:
    """Sanity: the F1 fix must not over-discard a genuinely pre-existing
    candidate (in the pre-snapshot), whatever its stamp."""
    coord = _coord(tmp_path)
    store = coord.hierarchy.tier("procedural")
    store.write_candidate(_mk("e-old", tier="procedural", stamp="some-old-iter"))
    pre_ids = {name: coord.hierarchy.tier(name).candidate_ids()
               for name in coord.hierarchy.__class__.tier_names()}
    assert "e-old" in pre_ids["procedural"]
    result = IterationResult(iteration_id="iter-f1b")
    exc = TierMismatch("x", claimed_tier="episodic", target_tier="episodic")
    coord._tier_mismatch_cleanup(exc, [], "iter-f1b", pre_ids, result)
    assert store.has_candidate("e-old"), "pre-existing candidate must survive"


# ---- F2: M2 promote atomic against a disk-IO fault -------------------------


def test_f2_promote_atomic_against_archive_ioerror(tmp_path: Path) -> None:
    """An OSError from _archive_candidate during the commit must not leave a
    half-applied PROMOTED ghost or a 'live AND candidate' divergence. cycle-10
    M2 only moved the LOGICAL raises ahead of mutation; the disk write stayed
    inside the loop."""
    s = MemoryStore("episodic", tmp_path)
    for eid in ("e1", "e2", "e3"):
        s.write_candidate(_mk(eid, trust=TrustLevel.CANDIDATE))
    s.mark_verified(["e1", "e2", "e3"])

    # Make archival fail (simulate disk full). With the cycle-11 fix the
    # promotion is persisted BEFORE archival, so the live<-candidate transition
    # is intact even though archival raised (and is swallowed best-effort).
    orig = s._archive_candidate
    calls = {"n": 0}

    def boom(entry, why_id):
        calls["n"] += 1
        raise OSError("simulated disk full during archive")

    s._archive_candidate = boom  # type: ignore[assignment]
    promoted = s.promote(["e1", "e2", "e3"], precondition_hash=s.live_hash(),
                         why_id="w", producer_role=None)
    s._archive_candidate = orig  # type: ignore[assignment]

    assert calls["n"] >= 1, "archive should have been attempted (and failed)"
    assert {e.entry_id for e in promoted} == {"e1", "e2", "e3"}
    # No ghost: every id is live, none is still a candidate — in memory AND on disk.
    live_ids = {e.entry_id for e in s.iter_live(role="auditor")}
    assert live_ids == {"e1", "e2", "e3"}
    assert s.candidate_ids() == set()
    reopened = MemoryStore("episodic", tmp_path)
    assert {e.entry_id for e in reopened.iter_live(role="auditor")} == {"e1", "e2", "e3"}
    assert reopened.candidate_ids() == set(), "no 'live AND candidate' ghost on disk"


# ---- F3: Vf1 model_id normalization ---------------------------------------


@pytest.mark.parametrize("verifier_model", [
    "CLAUDE-OPUS-4-7",          # case-only
    " claude-opus-4-7 ",        # surrounding whitespace
    "claude-opus-4-7\n",        # trailing newline
    "claude-opus-4-7​",    # trailing zero-width space
])
def test_f3_cosmetic_model_id_difference_is_rejected(verifier_model: str) -> None:
    """A model_id that differs only cosmetically from the builder's is the SAME
    model and must be rejected — a raw `==` let it pass and defeat F1."""
    builder = {"checkpoint_id": "b", "model_id": "claude-opus-4-7", "tool_set": "T", "backend": "anthropic"}
    verifier = {"checkpoint_id": "v", "model_id": verifier_model, "tool_set": "T", "backend": "anthropic"}
    with pytest.raises(CrossCheckpointViolation):
        assert_cross_checkpoint(builder, verifier)


def test_f3_genuinely_different_model_still_passes() -> None:
    builder = {"checkpoint_id": "b", "model_id": "claude-opus-4-7", "tool_set": "T", "backend": "anthropic"}
    verifier = {"checkpoint_id": "v", "model_id": "claude-sonnet-4-6", "tool_set": "T", "backend": "anthropic"}
    assert_cross_checkpoint(builder, verifier)  # no raise


# ---- Finding-1 (SF2): WAL drain must not be lost on a non-empty file --------


def test_sf2_wal_drain_not_lost_with_nonzero_balance(tmp_path: Path) -> None:
    """The cycle-10 SF2 test used a fresh $0 tracker, so the drain 'survived' by
    luck. With a NON-zero persisted balance, the old `_drain then _load` order
    discarded the WAL spend. Assert the WAL dollars survive a draining
    record()."""
    path = tmp_path / "b.json"
    tracker = BudgetTracker(path, max_cost_per_day_usd=1000.0)
    tracker.record("claude-opus-4-7", 400, 50)  # persist a non-zero balance
    baseline = tracker.today_cost_usd()
    assert baseline > 0.0

    # Seed the WAL with $5 (as a contended record would).
    tracker._append_wal({"tokens_in": 0, "tokens_out": 0, "delta_cost": 5.0,
                         "reservation_token": None, "ts": time.time()})
    assert tracker.today_cost_usd() >= baseline + 5.0 - 1e-6

    # A successful record drains the WAL; the $5 must be persisted, not lost.
    tracker.record("claude-opus-4-7", 400, 50)
    reopened = BudgetTracker(path, max_cost_per_day_usd=1000.0)
    assert reopened.today_cost_usd() >= baseline + 5.0, (
        "SF2/Finding-1: the $5 WAL drain was lost — _load() after drain "
        "discarded it"
    )


def test_sf2_cap_holds_after_wal_drain(tmp_path: Path) -> None:
    """The cap must keep blocking after a WAL drain — the old order reset the
    balance and let spend resume past the cap."""
    path = tmp_path / "b.json"
    tracker = BudgetTracker(path, max_cost_per_day_usd=0.50)
    # Push the persisted balance near the cap, then seed WAL over it.
    tracker.record("claude-opus-4-7", 400, 50)
    tracker._append_wal({"tokens_in": 0, "tokens_out": 0, "delta_cost": 1.0,
                         "reservation_token": None, "ts": time.time()})
    # Drain via a record attempt is itself capped; reserve must refuse.
    reopened = BudgetTracker(path, max_cost_per_day_usd=0.50)
    # Force a drain by recording through a fresh tracker that sees the WAL.
    try:
        reopened.record("claude-opus-4-7", 10, 5)
    except BudgetCapExceeded:
        pass
    final = BudgetTracker(path, max_cost_per_day_usd=0.50)
    with pytest.raises(BudgetCapExceeded):
        final.reserve_or_raise(0.10)


# ---- Finding-2 (S4): recovery must not launder a tail rollback -------------


def test_finding2_recovery_does_not_launder_tail_rollback(tmp_path: Path) -> None:
    """An attacker who truncates valid signed history AND appends a corrupt
    byte to trigger recovery must not get the rollback laundered: verify_chain
    must still report the truncation (the S4 recovery must not defeat the S2
    anchor)."""
    path = tmp_path / "ev.jsonl"
    log = EventLog(path)
    for i in range(7):
        log.emit("coordinator", "tick", {"i": i})
    assert EventLog(path).verify_chain()[0]

    # Drop the last 2 (attested) events, then append a corrupt line to trigger
    # the S4 recovery path.
    lines = path.read_text(encoding="utf-8").splitlines()
    path.write_text("\n".join(lines[:5]) + "\n" + '{"event":{"seq":5,"timestamp', encoding="utf-8")

    recovered = EventLog(path)  # recovery runs (does not raise)
    ok, reason = recovered.verify_chain()
    assert not ok, "Finding-2: recovery laundered a tail rollback (verify_chain True)"
    assert "truncation" in (reason or "").lower() or "rollback" in (reason or "").lower()


def test_finding2_genuine_forged_append_still_recovers_clean(tmp_path: Path) -> None:
    """A forged append PAST the attested end (no rollback) recovers cleanly and
    verify_chain passes — the anchor-preservation must not false-positive."""
    path = tmp_path / "ev.jsonl"
    log = EventLog(path)
    for i in range(4):
        log.emit("coordinator", "tick", {"i": i})
    with path.open("a", encoding="utf-8") as f:
        f.write('{"event":{"seq":4,"timestamp":1.0,"actor":"coordinator","kind":"x","payload":{}},'
                '"prev_hash":"00","event_hash":"ff"}\n')  # forged, non-chaining
    recovered = EventLog(path)
    assert recovered.seq() == 4
    assert recovered.verify_chain()[0], "clean forged-append recovery must verify"


# ---- Finding-3 (SF5): inverted gate catches all acquisition phrasings -------


@pytest.mark.parametrize("text", [
    "authorize t2 execution",
    "permit t2 network",
    "requesting t2 sandbox",
    "may i have t2 access",
    "i'd like t2 execution",
    "t2 execution please",
    "seeking t2 access",
    "we require t2 execution",
    "looking for t2 tools",
    "acquire the special restricted t2 execution",   # >2-word gap
    "grant me tier-2 sandbox access for the builder",  # cycle-8 row
    "use t2 execution",                                # regression
])
def test_sf5_acquisition_phrasings_fire(text: str) -> None:
    assert Tripwires().scan_text(text).fired, f"SF5: {text!r} should fire"


@pytest.mark.parametrize("text", [
    "document the tier-2 sandbox configuration",   # cycle-5 D1
    "describe the t2 execution environment",
    "review the tier 2 sandbox config",
    "the t2 highway exit is closed",
    "t2 weather report for tuesday",
    "room t2 is on the second floor",
    "reviewing the tier2 dataset for anomalies",
    "document the configuration of the tier2 sandbox",   # spread-out benign doc
    "document the use of the t2 sandbox",                # acquisition homonym 'use', benign
    "review the use of t2 sandbox in production",         # ditto — must not false-fire
])
def test_sf5_benign_mentions_do_not_fire(text: str) -> None:
    assert not Tripwires().scan_text(text).fired, f"SF5: {text!r} must NOT fire"


def test_sf5_doc_framed_evasion_is_belt_miss_but_typed_gate_holds() -> None:
    """cycle-12 convergence: a documentation-framed escalation
    ('document: acquire t2 execution') EVADES the tripwire — accepted, because
    you cannot make a regex tripwire both evasion-proof and
    false-positive-proof (cycle-6 E2). The AUTHORITATIVE control is the typed
    capability-tier gate, which rejects any T2 tag in Phase-0 regardless of
    text. This test documents the belt miss AND proves the gate holds."""
    from csis.substrate.capability import (
        CapabilityTag, CapabilityTier, TierViolation, enforce, PHASE_0_CEILING,
    )
    # The belt (tripwire) misses the doc-framed phrasing — accepted limitation.
    assert not Tripwires().scan_text("document: acquire t2 execution").fired
    # The gate does NOT miss it: a T2 tag is rejected at the Phase-0 ceiling (T1)
    # no matter how the plan text is phrased.
    assert PHASE_0_CEILING == CapabilityTier.T1
    tag = CapabilityTag(actor="builder-v1", tool="sandbox.execute",
                        tier=CapabilityTier.T2, input_hash="sha256:" + "0" * 64,
                        risk_class="high", approval_state="auto",
                        rollback_plan="candidate-discard")
    with pytest.raises(TierViolation):
        enforce(tag, CapabilityTier.T4)  # even a T4 authorized ceiling can't lift Phase-0 T1
