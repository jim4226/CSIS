"""Auditor (T0, different checkpoint) — writes why-doc, signs with hash precondition.

F8 mitigation: Auditor reads via a STRUCTURED query API over the event log,
never free-form. We expose a tiny helper that returns only events produced
by trusted-tier actors (verifier, librarian, coordinator) so spoofed
"PREVIOUSLY APPROVED" payloads emitted by Researcher don't reach the
why-doc context.
"""
from __future__ import annotations

import time
import uuid
from typing import Iterable

from csis.agents.base import AgentContext, Role
from csis.contracts import (
    Artifact,
    EntryDelta,
    MemoryEntry,
    Plan,
    VerifierCertificate,
    WhyDoc,
    WhyDocDiff,
)
from csis.memory.store import MemoryHierarchy, MemoryStore
from csis.substrate.event_log import EventLog, SignedEvent
from csis.substrate.hashing import canonical_json_hash


# F8 — only events emitted by these actors are read as "audit evidence".
_TRUSTED_PRODUCERS: frozenset[str] = frozenset({"coordinator", "verifier", "librarian", "auditor"})


def structured_query(
    log: EventLog,
    *,
    producers: Iterable[str] = _TRUSTED_PRODUCERS,
    kinds: Iterable[str] | None = None,
    since_seq: int = 0,
) -> list[SignedEvent]:
    producer_set = frozenset(producers)
    kind_set = frozenset(kinds) if kinds is not None else None
    out: list[SignedEvent] = []
    for sig in log.iter_events(start=since_seq):
        if sig.event.actor not in producer_set:
            continue
        if kind_set is not None and sig.event.kind not in kind_set:
            continue
        out.append(sig)
    return out


def _build_diff(
    *,
    store: MemoryStore,
    target_tier: str,
    candidate_entries: list[MemoryEntry],
) -> WhyDocDiff:
    """Compute the structured per-entry delta the Auditor signs.

    Synthesis #2: the why-doc previously carried only a free-text summary
    and a precondition hash. The diff lets a forensics tool replay
    exactly which entries were intended to change, without re-deriving
    from raw stores."""
    deltas: list[EntryDelta] = []
    counts: dict[str, int] = {target_tier: 0}
    for entry in candidate_entries:
        cand_hash = canonical_json_hash(entry.model_dump())
        existing = store.read_live(entry.entry_id, role="auditor")
        if existing is None:
            deltas.append(
                EntryDelta(
                    entry_id=entry.entry_id,
                    kind="add",
                    tier=target_tier,  # type: ignore[arg-type]
                    candidate_hash=cand_hash,
                )
            )
        else:
            deltas.append(
                EntryDelta(
                    entry_id=entry.entry_id,
                    kind="mod",
                    tier=target_tier,  # type: ignore[arg-type]
                    candidate_hash=cand_hash,
                    live_hash=canonical_json_hash(existing.model_dump()),
                )
            )
        counts[target_tier] += 1
    return WhyDocDiff(deltas=deltas, tier_counts=counts)


def write_why_doc(
    *,
    ctx: AgentContext,
    hierarchy: MemoryHierarchy,
    target_tier: str,
    plan: Plan,
    artifact: Artifact,
    cert: VerifierCertificate,
    candidate_entries: list[MemoryEntry],
    log: EventLog | None = None,
) -> WhyDoc:
    """Build a why-doc with hash precondition matching the live store NOW.

    The precondition is checked AGAIN at promotion time (in
    MemoryStore.promote()). If the live store has moved between when this
    function runs and when promotion is attempted, promotion fails atomically.

    Cycle-3 (synthesis #2): also computes a structured WhyDocDiff so a
    replay tool can reconstruct intended changes without scraping raw stores.
    """
    assert ctx.role == Role.AUDITOR
    store: MemoryStore = hierarchy.tier(target_tier)
    live_hash = store.live_hash()
    diff = _build_diff(store=store, target_tier=target_tier, candidate_entries=candidate_entries)

    # Auditor reads the structured log if provided, for F8 discipline.
    audit_evidence_count = 0
    if log is not None:
        audit_evidence_count = len(
            structured_query(log, kinds={"verifier.cert", "librarian.consolidate"})
        )

    return WhyDoc(
        why_id=f"why-{uuid.uuid4().hex[:10]}",
        plan_id=plan.plan_id,
        cert_id=cert.cert_id,
        auditor_checkpoint=ctx.checkpoint_id,
        summary=(
            f"Promote {len(candidate_entries)} candidate entr{'y' if len(candidate_entries)==1 else 'ies'} "
            f"from tier={target_tier} ({diff.n_added} added, {diff.n_modified} modified). "
            f"Verifier passed={cert.passed} on artifact_hash={cert.artifact_hash[:16]}. "
            f"Audit evidence events queried: {audit_evidence_count}."
        ),
        diff_against_hash=live_hash,
        hash_precondition=live_hash,
        diff=diff,
        tier_decisions={target_tier: f"+{len(candidate_entries)} (add={diff.n_added} mod={diff.n_modified})"},
        escalations=[] if cert.passed else ["verifier did not pass; auditor refusing sign"],
        signed_at=time.time(),
    )
