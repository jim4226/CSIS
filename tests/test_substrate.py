"""Substrate tests — event log integrity, capability enforcement, hashing."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from csis.substrate.capability import (
    PHASE_0_CEILING,
    CapabilityTag,
    CapabilityTier,
    TierViolation,
    enforce,
)
from csis.substrate.event_log import EventLog, GENESIS_PREV_HASH, SignedEvent
from csis.substrate.hashing import canonical_json_hash, hash_artifact, sha256_hex


# ---- hashing --------------------------------------------------------------


def test_canonical_json_hash_is_stable_across_key_order() -> None:
    a = canonical_json_hash({"a": 1, "b": 2})
    b = canonical_json_hash({"b": 2, "a": 1})
    assert a == b
    assert a.startswith("sha256:")


def test_artifact_hash_matches_string_and_bytes() -> None:
    assert hash_artifact("hello") == hash_artifact(b"hello")
    assert hash_artifact("hello") != hash_artifact("world")


def test_sha256_hex_known_value() -> None:
    # Sanity check against a known SHA-256 — the empty string.
    assert sha256_hex("") == "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855"


# ---- event log ------------------------------------------------------------


def test_event_log_emits_and_chains(tmp_path: Path) -> None:
    log = EventLog(tmp_path / "events.jsonl")
    e1 = log.emit("coordinator", "boot", {"version": "0.0.1"})
    e2 = log.emit("researcher", "plan.proposed", {"plan_id": "p-1"})
    assert e1.event.seq == 0
    assert e2.event.seq == 1
    assert e1.prev_hash == GENESIS_PREV_HASH
    assert e2.prev_hash == e1.event_hash


def test_event_log_verify_chain_passes_on_clean_log(tmp_path: Path) -> None:
    log = EventLog(tmp_path / "events.jsonl")
    for i in range(10):
        log.emit("coordinator", "tick", {"i": i})
    ok, reason = log.verify_chain()
    assert ok, reason


def test_event_log_detects_tampering(tmp_path: Path) -> None:
    path = tmp_path / "events.jsonl"
    log = EventLog(path)
    log.emit("coordinator", "boot", {})
    log.emit("coordinator", "tick", {"i": 1})
    log.emit("coordinator", "tick", {"i": 2})

    # Tamper with the middle event's payload.
    lines = path.read_text(encoding="utf-8").splitlines()
    middle = SignedEvent.model_validate_json(lines[1])
    tampered_event = middle.event.model_copy(update={"payload": {"i": 9999}})
    tampered_line = SignedEvent(
        event=tampered_event,
        prev_hash=middle.prev_hash,
        event_hash=middle.event_hash,  # stale hash on purpose
    ).model_dump_json()
    lines[1] = tampered_line
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")

    ok, reason = EventLog(path).verify_chain()
    assert not ok
    assert "event_hash mismatch" in (reason or "")


def test_event_log_restores_after_reopen(tmp_path: Path) -> None:
    path = tmp_path / "events.jsonl"
    log1 = EventLog(path)
    for i in range(5):
        log1.emit("coordinator", "tick", {"i": i})
    last_hash = log1.latest_hash()

    log2 = EventLog(path)
    assert log2.seq() == 5
    assert log2.latest_hash() == last_hash

    new_event = log2.emit("coordinator", "after-restart", {})
    assert new_event.event.seq == 5
    assert new_event.prev_hash == last_hash


# ---- capability enforcement ----------------------------------------------


def _tag(tier: CapabilityTier, actor: str = "researcher-v1", tool: str = "web_search") -> CapabilityTag:
    return CapabilityTag(
        actor=actor,
        tool=tool,
        tier=tier,
        input_hash="sha256:" + "0" * 64,
    )


def test_enforce_allows_at_or_below_ceiling() -> None:
    enforce(_tag(CapabilityTier.T0), CapabilityTier.T1)
    enforce(_tag(CapabilityTier.T1), CapabilityTier.T1)


def test_enforce_rejects_above_actor_ceiling() -> None:
    with pytest.raises(TierViolation):
        enforce(_tag(CapabilityTier.T1), CapabilityTier.T0)


def test_enforce_rejects_above_phase_0_ceiling_even_if_actor_authorized() -> None:
    # Phase-0 hard ceiling is T1 regardless of authorized ceiling.
    assert PHASE_0_CEILING == CapabilityTier.T1
    with pytest.raises(TierViolation):
        enforce(_tag(CapabilityTier.T2), CapabilityTier.T4)


def test_capability_tag_input_hash_must_look_like_sha256() -> None:
    with pytest.raises(Exception):
        CapabilityTag(
            actor="x",
            tool="y",
            tier=CapabilityTier.T0,
            input_hash="not-a-hash",
        )
