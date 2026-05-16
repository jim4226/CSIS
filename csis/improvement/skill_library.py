"""Skill library (procedural memory) accumulation path.

§3 L5 I1-I3: "skill compilation, self-distillation, DPO/RLAIF, synthetic
curricula. Phase-0 scope: I1–I3 only." Phase-0 here means: when an
iteration produces a verified-gain artifact tagged `kind="skill"`, the
Librarian routes it to the procedural store and the Coordinator promotes
under producer_role="builder" so the F5/P4 tier-consumer invariant holds.

This is the only place where "improvement" accumulates structurally —
every other tier is episodic/semantic memory that informs reasoning but
doesn't change capability. Procedural entries change what the Builder
can do next iteration.
"""
from __future__ import annotations

import time
import uuid
from dataclasses import dataclass

from csis.contracts import Artifact, MemoryEntry, Plan, VerifierCertificate
from csis.memory.store import MemoryHierarchy
from csis.memory.trust import TrustLevel
from csis.safety.tier_guard import TierGuard


def is_skill_artifact(artifact: Artifact) -> bool:
    return artifact.kind == "skill" or (
        artifact.kind == "patch"
        and isinstance(artifact.extra, dict)
        and bool(artifact.extra.get("is_skill", False))
    )


def consolidate_skill(
    *,
    hierarchy: MemoryHierarchy,
    tier_guard: TierGuard,
    plan: Plan,
    artifact: Artifact,
    cert: VerifierCertificate,
) -> list[MemoryEntry]:
    """Write a skill candidate into procedural tier.

    The Librarian role can't write directly to procedural (F5/P4 — consumer
    tier is T1). This function is called only when the artifact has been
    verified AND is shaped like a skill; the producer_role at promote() time
    is "builder", which has T1 ceiling and is authorized.
    """
    # Pre-flight: this is a Coordinator-side decision so the role we name
    # here is "builder" (the actor that produced the artifact). The
    # TierGuard check is structural; if it fails, no on-disk write.
    ok, reason = tier_guard.write_tier("builder", "procedural")
    if not ok:
        raise PermissionError(f"skill consolidation blocked: {reason}")

    entry = MemoryEntry(
        entry_id=f"skill-{uuid.uuid4().hex[:10]}",
        tier="procedural",  # type: ignore[arg-type]
        content=(
            f"plan={plan.plan_id} artifact={artifact.artifact_id} "
            f"summary={plan.hypothesis!r}\n"
            f"---\n"
            f"{artifact.body[:2000]}"  # bounded
        ),
        trust=TrustLevel.CANDIDATE,
        why_tag=(
            f"builder skill from cert={cert.cert_id} "
            f"verifier_checkpoint={cert.verifier_checkpoint} "
            f"graders={sum(1 for g in cert.grader_results if g.passed)}/{len(cert.grader_results)}"
        ),
        created_at=time.time(),
    )
    hierarchy.tier("procedural").write_candidates([entry])
    return [entry]


@dataclass
class SkillLibraryStats:
    total_promoted: int
    last_promoted_at: float | None


def stats(hierarchy: MemoryHierarchy) -> SkillLibraryStats:
    store = hierarchy.tier("procedural")
    entries = list(store.iter_live(role="auditor"))
    total = len(entries)
    last = max((e.promoted_at or 0.0 for e in entries), default=0.0) if entries else None
    return SkillLibraryStats(total_promoted=total, last_promoted_at=last)
