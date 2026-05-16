"""Librarian (T0) — proposes candidate memory entries.

The Librarian NEVER promotes. It writes to candidate stores only. The
Auditor decides what gets promoted (and even then promotion goes through
the hash-preconditioned MemoryStore.promote() — F2 atomicity).
"""
from __future__ import annotations

import time
import uuid

from csis.agents.base import AgentContext, Role
from csis.contracts import (
    Artifact,
    MemoryEntry,
    Plan,
    VerifierCertificate,
)
from csis.memory.store import MemoryHierarchy
from csis.memory.trust import TrustLevel
from csis.safety.tier_guard import TierGuard


def consolidate_to_candidates(
    *,
    ctx: AgentContext,
    hierarchy: MemoryHierarchy,
    tier_guard: TierGuard,
    plan: Plan,
    artifact: Artifact,
    cert: VerifierCertificate,
    target_tier: str = "episodic",
) -> list[MemoryEntry]:
    """Write verified gains to candidate side of the target tier.

    F5 mitigation: TierGuard rejects writes if the role's ceiling is lower
    than the consumer tier of the target store. Librarian (T0) can write
    to working/episodic/semantic/causal candidates (all T0 consumer) but
    cannot write directly into procedural (consumer T1). For procedural
    skill candidates, Librarian must escalate — handled separately.
    """
    assert ctx.role == Role.LIBRARIAN
    ok, reason = tier_guard.write_tier(ctx.role.value, target_tier)
    if not ok:
        raise PermissionError(f"librarian write blocked (F5): {reason}")

    now = time.time()
    entries = [
        MemoryEntry(
            entry_id=f"e-{uuid.uuid4().hex[:10]}",
            tier=target_tier,  # type: ignore[arg-type]
            content=(
                f"plan={plan.plan_id} artifact={artifact.artifact_id} cert={cert.cert_id} "
                f"hypothesis={plan.hypothesis!r}"
            ),
            trust=TrustLevel.CANDIDATE,
            why_tag=f"verified-by={cert.verifier_checkpoint} graders_passed={sum(1 for g in cert.grader_results if g.passed)}/{len(cert.grader_results)}",
            created_at=now,
        )
    ]
    hierarchy.tier(target_tier).write_candidates(entries)
    return entries
