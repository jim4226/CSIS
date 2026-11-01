"""Regressions for rejected batches and mutation through public store APIs."""
from pathlib import Path

import pytest

from csis.contracts import MemoryEntry
from csis.memory.store import MemoryStore, TrustViolation
from csis.memory.trust import TrustLevel


def entry(eid: str) -> MemoryEntry:
    return MemoryEntry(
        entry_id=eid, tier="episodic", content="original",
        trust=TrustLevel.CANDIDATE, why_tag="test", created_at=0.0,
        extra={"nested": {"values": ["original"]}},
    )


def files(root: Path) -> dict[str, bytes]:
    return {str(p.relative_to(root)): p.read_bytes() for p in root.rglob("*.json")}


def mutate(value: MemoryEntry) -> None:
    value.content = "changed without a write"
    value.extra["nested"]["values"].append("injected")


@pytest.mark.parametrize("bad", ["missing", "deprecated", "existing", "duplicate"])
def test_invalid_promotion_batch_changes_nothing(tmp_path: Path, bad: str) -> None:
    store = MemoryStore("episodic", tmp_path)
    first, second = entry("first"), entry("second")
    if bad == "existing":
        store.write_candidate(second)
        store.promote([second.entry_id], precondition_hash=store.live_hash(), why_id="seed")
    if bad == "deprecated":
        second.trust = TrustLevel.DEPRECATED
    store.write_candidates([first, second])
    ids = ["first", {"missing": "absent", "duplicate": "first"}.get(bad, "second")]
    before = (store.live_hash(), store.candidate_hash(), files(tmp_path))

    with pytest.raises((KeyError, TrustViolation)):
        store.promote(ids, precondition_hash=store.live_hash(), why_id="rejected")

    assert (store.live_hash(), store.candidate_hash(), files(tmp_path)) == before
    reopened = MemoryStore("episodic", tmp_path)
    assert (reopened.live_hash(), reopened.candidate_hash()) == before[:2]


@pytest.mark.parametrize("bad", ["missing", "deprecated"])
def test_invalid_verification_batch_changes_nothing(tmp_path: Path, bad: str) -> None:
    store = MemoryStore("episodic", tmp_path)
    second = entry("second")
    second.trust = TrustLevel.DEPRECATED
    store.write_candidates([entry("first"), second])
    before = (store.candidate_hash(), files(tmp_path))
    with pytest.raises((KeyError, TrustViolation)):
        store.mark_verified(["first", "absent" if bad == "missing" else "second"])
    assert (store.candidate_hash(), files(tmp_path)) == before


@pytest.mark.parametrize("bulk", [False, True])
@pytest.mark.parametrize("writer", [None, "iteration-1"])
def test_input_objects_cannot_modify_stored_memory(tmp_path: Path, bulk: bool, writer: str | None) -> None:
    store = MemoryStore("episodic", tmp_path)
    original = entry("first")
    if bulk:
        store.write_candidates([original], writer_iteration_id=writer)
    else:
        store.write_candidate(original, writer_iteration_id=writer)
    before = store.candidate_hash()
    mutate(original)
    assert store.candidate_hash() == before
    stored = store.read_candidate("first", role="auditor")
    assert stored.writer_iteration_id == writer
    store.promote(["first"], precondition_hash=store.live_hash(), why_id="test")
    before = store.live_hash()
    mutate(original)
    assert store.live_hash() == before


@pytest.mark.parametrize("surface", ["read", "snapshot", "verify", "verify_again"])
def test_candidate_outputs_are_detached(tmp_path: Path, surface: str) -> None:
    store = MemoryStore("episodic", tmp_path)
    store.write_candidate(entry("first"))
    if surface == "read":
        result = store.read_candidate("first", role="auditor")
    elif surface == "snapshot":
        result = store.candidates_snapshot()[0]
    else:
        if surface == "verify_again":
            store.mark_verified(["first"])
        result = store.mark_verified(["first"])[0]
    before = store.candidate_hash()
    mutate(result)
    assert store.candidate_hash() == before


@pytest.mark.parametrize("surface", ["read", "iterate", "promote"])
def test_live_outputs_are_detached(tmp_path: Path, surface: str) -> None:
    store = MemoryStore("episodic", tmp_path)
    store.write_candidate(entry("first"))
    result = store.promote(["first"], precondition_hash=store.live_hash(), why_id="test")[0]
    if surface == "read":
        result = store.read_live("first", role="researcher")
    elif surface == "iterate":
        result = next(iter(store.iter_live(role="researcher")))
    before = store.live_hash()
    mutate(result)
    assert store.live_hash() == before


def test_valid_batch_promotes_all_entries_and_persists(tmp_path: Path) -> None:
    store = MemoryStore("episodic", tmp_path)
    store.write_candidates([entry("first"), entry("second")])
    store.mark_verified(["first", "second"])
    promoted = store.promote(["first", "second"], precondition_hash=store.live_hash(), why_id="test")
    assert [e.entry_id for e in promoted] == ["first", "second"]
    assert all(e.trust == TrustLevel.PROMOTED for e in promoted)
    assert store.candidate_ids() == set()
    assert len(list((tmp_path / "archive").glob("*.json"))) == 2
    assert MemoryStore("episodic", tmp_path).live_hash() == store.live_hash()


def test_archive_failure_does_not_mutate_live_or_candidates(tmp_path: Path, monkeypatch) -> None:
    store = MemoryStore("episodic", tmp_path)
    store.write_candidates([entry("first"), entry("second")])
    before = (store.live_hash(), store.candidate_hash())
    archive = store._archive_candidate

    def fail_second(candidate, why_id):
        if candidate.entry_id == "second":
            raise OSError("archive storage unavailable")
        archive(candidate, why_id)

    monkeypatch.setattr(store, "_archive_candidate", fail_second)
    with pytest.raises(OSError, match="unavailable"):
        store.promote(["first", "second"], precondition_hash=store.live_hash(), why_id="test")
    assert (store.live_hash(), store.candidate_hash()) == before
    reopened = MemoryStore("episodic", tmp_path)
    assert (reopened.live_hash(), reopened.candidate_hash()) == before
