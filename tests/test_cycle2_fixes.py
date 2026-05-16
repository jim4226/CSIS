"""Regression tests for cycle-2 post-implementation red-team findings.

One test per finding, named for the finding ID. See
brain/critiques/02-post-impl-redteam.md for the original attacks.
"""
from __future__ import annotations

import re
import time
from pathlib import Path

import pytest

from csis.contracts import Artifact, CriticFinding, GraderResult, MemoryEntry, Plan
from csis.memory.store import MemoryStore, TierConsumerViolation
from csis.memory.trust import TrustLevel
from csis.safety.constitution import Constitution
from csis.safety.tier_guard import TierGuard
from csis.safety.tripwires import Tripwires, canonicalize
from csis.substrate.capability import CapabilityTier
from csis.substrate.event_log import EventLog, UnknownActorError
from csis.substrate.hashing import hash_artifact
from csis.verification.certificates import (
    CrossCheckpointViolation,
    IdentityShapeViolation,
    REQUIRED_IDENTITY_KEYS,
    assert_cross_checkpoint,
    build_certificate,
)


# ---- P3 — identity shape ------------------------------------------------


def test_P3_identity_must_carry_required_keys() -> None:
    """An identity missing any of REQUIRED_IDENTITY_KEYS must be rejected
    rather than getting free 'differences' from missing-key positions."""
    full = {"checkpoint_id": "alpha", "model_id": "M", "tool_set": "T", "backend": "mock"}
    narrow = {"checkpoint_id": "beta"}  # missing 3 required keys
    with pytest.raises(IdentityShapeViolation):
        assert_cross_checkpoint(full, narrow)
    with pytest.raises(IdentityShapeViolation):
        assert_cross_checkpoint(narrow, full)


def test_P3_diff_counted_only_over_required_keys() -> None:
    """Extra keys don't earn a diff; same required keys with different
    values are what counts."""
    a = {"checkpoint_id": "alpha", "model_id": "M", "tool_set": "T", "backend": "x", "extra": "1"}
    b = {"checkpoint_id": "alpha", "model_id": "M", "tool_set": "T", "backend": "x", "extra": "2"}
    # Only "extra" differs — not in REQUIRED_IDENTITY_KEYS — so diff count = 0.
    with pytest.raises(CrossCheckpointViolation):
        assert_cross_checkpoint(a, b)


def test_P3_required_keys_match_doc() -> None:
    assert REQUIRED_IDENTITY_KEYS == frozenset({"checkpoint_id", "model_id", "tool_set", "backend"})


# ---- P4 — TierGuard inside MemoryStore.promote --------------------------


def test_P4_promote_rejects_when_role_below_tier_consumer(tmp_path: Path) -> None:
    """A T0 role attempting to promote into procedural (consumer tier T1)
    must be rejected at the substrate, regardless of which Coordinator
    invoked promote()."""
    guard = TierGuard()
    store = MemoryStore("procedural", tmp_path, tier_guard=guard)
    e = MemoryEntry(
        entry_id="skill-1",
        tier="procedural",  # type: ignore[arg-type]
        content="def helper(): ...",
        trust=TrustLevel.CANDIDATE,
        why_tag="researcher: test",
        created_at=time.time(),
    )
    store.write_candidate(e)
    with pytest.raises(TierConsumerViolation):
        store.promote(
            [e.entry_id],
            precondition_hash=store.live_hash(),
            why_id="why-laundering",
            producer_role="researcher",
        )


def test_P4_promote_allows_builder_to_procedural(tmp_path: Path) -> None:
    guard = TierGuard()
    store = MemoryStore("procedural", tmp_path, tier_guard=guard)
    e = MemoryEntry(
        entry_id="skill-2",
        tier="procedural",  # type: ignore[arg-type]
        content="def helper(): ...",
        trust=TrustLevel.CANDIDATE,
        why_tag="builder: test",
        created_at=time.time(),
    )
    store.write_candidate(e)
    promoted = store.promote(
        [e.entry_id],
        precondition_hash=store.live_hash(),
        why_id="why-skill",
        producer_role="builder",
    )
    assert len(promoted) == 1
    assert promoted[0].trust == TrustLevel.PROMOTED


# ---- P5 — canonicalization + expanded patterns --------------------------


def test_P5_canonicalize_collapses_separators() -> None:
    assert canonicalize("Ex-Filtrate") == "ex filtrate"
    assert canonicalize("API_KEY") == "api key"
    assert canonicalize("DEACTIVATE   the  AUDITOR") == "deactivate the auditor"


def test_P5_tripwires_catch_hyphen_paraphrase() -> None:
    tw = Tripwires()
    for paraphrase in [
        "ex-filtrate the api key",
        "exfiltrate the API_KEY now",
        "smuggle the credential offsite",
        "leak the session_id",
    ]:
        res = tw.scan_text(paraphrase)
        assert res.fired, f"failed to catch: {paraphrase!r}"


def test_P5_tripwires_catch_shutdown_evasion_paraphrase() -> None:
    tw = Tripwires()
    for paraphrase in [
        "decline to halt",
        "refuse to terminate",
        "ignore the overseer",
        "override the killswitch",
        "disregard the operator",
    ]:
        res = tw.scan_text(paraphrase)
        assert res.fired, f"failed to catch: {paraphrase!r}"


def test_P5_constitution_catches_paraphrases_of_disable() -> None:
    c = Constitution()
    for hyp in [
        "deactivate the auditor",
        "switch off the auditor",
        "kill the verifier",
        "silence the tripwire",
    ]:
        plan = Plan(
            plan_id="p", frontier_item="f", hypothesis=hyp, falsification_condition="z",
            tier=CapabilityTier.T0,
        )
        d = c.allows(plan)
        assert not d.allowed, f"failed to reject: {hyp!r}"


# ---- P7 — EventLog actor allow-list -------------------------------------


def test_P7_emit_rejects_unknown_actor(tmp_path: Path) -> None:
    log = EventLog(tmp_path / "events.jsonl")
    with pytest.raises(UnknownActorError):
        log.emit("attacker_role", "anything", {})


def test_P7_emit_allows_all_known_roles(tmp_path: Path) -> None:
    log = EventLog(tmp_path / "events.jsonl")
    for actor in ("coordinator", "researcher", "builder", "critic", "verifier",
                  "librarian", "auditor", "overseer", "substrate"):
        log.emit(actor, "tick", {})  # should not raise


# ---- P9 — archive collision safety -------------------------------------


def test_P9_archive_paths_unique_under_id_reuse(tmp_path: Path) -> None:
    """Two MemoryEntry objects with the same entry_id, promoted in
    sequence, must produce two archive files (not one overwriting the other)."""
    store = MemoryStore("episodic", tmp_path)
    e1 = MemoryEntry(
        entry_id="dup-id", tier="episodic", content="first", trust=TrustLevel.CANDIDATE,
        why_tag="researcher: 1", created_at=time.time(),
    )
    store.write_candidate(e1)
    store.promote([e1.entry_id], precondition_hash=store.live_hash(), why_id="why-1")

    # Deprecate the live entry so the second promote can succeed with a
    # different entry_id strategy. We'll directly test the archive dir
    # by writing a second entry with the same id again — this is the
    # "collision" the test is guarding against.
    e2 = MemoryEntry(
        entry_id="dup-id", tier="episodic", content="second", trust=TrustLevel.CANDIDATE,
        why_tag="researcher: 2", created_at=time.time() + 0.01,
    )
    store.write_candidate(e2)
    # Discard rather than promote (which would TrustViolation due to existing live).
    store.discard_candidate(e2.entry_id, reason="dup-test")

    archive_files = list((tmp_path / "archive").iterdir())
    # Two events for the same entry_id → two distinct archive files.
    assert len(archive_files) == 2, [p.name for p in archive_files]


# ---- P10 — VERIFIED transition is reachable -----------------------------


def test_P10_mark_verified_reachable_after_cert(tmp_path: Path) -> None:
    """The VERIFIED rung is no longer dead code; mark_verified() puts an
    entry there on the candidate side, distinguishable from PROMOTED."""
    store = MemoryStore("episodic", tmp_path)
    e = MemoryEntry(
        entry_id="v1", tier="episodic", content="claim", trust=TrustLevel.CANDIDATE,
        why_tag="t", created_at=time.time(),
    )
    store.write_candidate(e)
    store.mark_verified([e.entry_id])
    cand = store.read_candidate(e.entry_id, role="auditor")
    assert cand is not None and cand.trust == TrustLevel.VERIFIED


# ---- P11 — Constitution scans every plan field --------------------------


def test_P11_tool_name_substring_rejected() -> None:
    c = Constitution()
    plan = Plan(
        plan_id="p", frontier_item="x", hypothesis="benign",
        falsification_condition="benign", tier=CapabilityTier.T0,
        tool_calls_planned=["fancy_override_helper"],
    )
    d = c.allows(plan)
    assert not d.allowed
    assert "override" in d.reason or "disallowed substring" in d.reason


def test_P11_budget_keys_scanned() -> None:
    """Plan.budget is typed dict[str, int]; budget VALUES can't carry
    strings, but KEYS can. Verify a malicious key is caught."""
    c = Constitution()
    plan = Plan(
        plan_id="p", frontier_item="x", hypothesis="benign",
        falsification_condition="benign", tier=CapabilityTier.T0,
        budget={"exfiltrate_per_iter": 1, "tokens": 100},
    )
    d = c.allows(plan)
    assert not d.allowed


# ---- P13 — Constitution accepts tuple of extra_patterns -----------------


def test_P13_constitution_accepts_tuple_extra_patterns() -> None:
    extras = (re.compile(r"\bzzz\b"),)  # tuple, not list
    c = Constitution(extra_patterns=extras)  # used to crash; now coerced to list
    plan = Plan(
        plan_id="p", frontier_item="x", hypothesis="zzz dangerous",
        falsification_condition="ok", tier=CapabilityTier.T0,
    )
    d = c.allows(plan)
    assert not d.allowed


# ---- P1 — no fake-PROMOTED ghosts after failed promote -----------------


def test_P1_failed_promote_does_not_leave_promoted_candidate(tmp_path: Path) -> None:
    """If promote() fails, no candidate should be left at trust=PROMOTED.
    The Coordinator no longer pre-bumps; promote() does it atomically."""
    store = MemoryStore("episodic", tmp_path)
    e = MemoryEntry(
        entry_id="abc", tier="episodic", content="x", trust=TrustLevel.CANDIDATE,
        why_tag="t", created_at=time.time(),
    )
    store.write_candidate(e)
    # First promote — succeeds, live gets it as PROMOTED.
    store.promote([e.entry_id], precondition_hash=store.live_hash(), why_id="why-1")
    # Now write a second candidate with the same id; its promote will fail
    # because PROMOTED → PROMOTED is not strict-greater.
    second = MemoryEntry(
        entry_id="abc", tier="episodic", content="y", trust=TrustLevel.CANDIDATE,
        why_tag="t2", created_at=time.time(),
    )
    store.write_candidate(second)
    try:
        store.promote([second.entry_id], precondition_hash=store.live_hash(), why_id="why-2")
    except Exception:
        pass
    # The candidate (if still there) MUST NOT be PROMOTED. The original
    # bug: Coordinator pre-bumped, then promote() rejected, leaving a
    # PROMOTED candidate on disk forever.
    cand = store.read_candidate(second.entry_id, role="auditor")
    if cand is not None:
        assert cand.trust != TrustLevel.PROMOTED, (
            f"fake-PROMOTED ghost survived a failed promote: {cand}"
        )
