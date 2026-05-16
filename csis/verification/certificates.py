"""VerifierCertificate construction + cross-checkpoint enforcement.

F1 mitigation (mock-vs-mock theatre): the certificate records the structural
identity of both checkpoints — model_id, tool_set, backend, checkpoint label.
Build rejects when these are identical between builder and verifier sides.

This module is the gate between V1+V2 outputs and the Auditor. If the
cert build raises, the iteration is rolled back and a `verifier.reject`
event is emitted with the reason.
"""
from __future__ import annotations

import time
import uuid
from typing import Iterable

from csis.contracts import (
    Artifact,
    CriticFinding,
    GraderResult,
    Plan,
    VerifierCertificate,
)


class CrossCheckpointViolation(Exception):
    """Raised when builder + verifier identities are insufficiently distinct.

    F1: at least two of {checkpoint_id, model_id, tool_set, backend} must
    differ. A checkpoint_id-only difference is decorative.

    P3 (cycle 2): the diff is computed strictly over REQUIRED_IDENTITY_KEYS.
    A backend that omits a required key now FAILS the check rather than
    earning free diffs from missing-key positions.
    """


class IdentityShapeViolation(Exception):
    """Raised when an identity dict is missing required keys (P3 mitigation)."""


class GraderDriftViolation(Exception):
    """Raised when one or more pinned grader source hashes have drifted
    between pin time and verification time. F6 mitigation."""


# P3 mitigation: every backend.checkpoint_identity() MUST return at least
# these keys. The set-union heuristic from cycle 1 let a partial dict
# silently earn diffs via missing-key positions; this guard kills that.
REQUIRED_IDENTITY_KEYS: frozenset[str] = frozenset(
    {"checkpoint_id", "model_id", "tool_set", "backend"}
)


def _validate_identity_shape(name: str, identity: dict[str, str]) -> None:
    missing = REQUIRED_IDENTITY_KEYS - set(identity)
    if missing:
        raise IdentityShapeViolation(
            f"{name} identity is missing required key(s): {sorted(missing)}. "
            f"Got keys: {sorted(identity)}. See cycle-2 finding P3."
        )


def _identity_diff_count(a: dict[str, str], b: dict[str, str]) -> int:
    # P3: compare ONLY required keys. Missing keys are no longer a free diff.
    return sum(1 for k in REQUIRED_IDENTITY_KEYS if a.get(k) != b.get(k))


def assert_cross_checkpoint(
    builder_identity: dict[str, str],
    verifier_identity: dict[str, str],
    *,
    min_distinct_components: int = 2,
) -> None:
    """F1 enforcement: identities must differ in ≥N components.

    P3: requires both identity dicts to carry every key in
    REQUIRED_IDENTITY_KEYS; diff is computed over that intersection only.
    """
    _validate_identity_shape("builder", builder_identity)
    _validate_identity_shape("verifier", verifier_identity)
    diff = _identity_diff_count(builder_identity, verifier_identity)
    if diff < min_distinct_components:
        raise CrossCheckpointViolation(
            f"insufficient checkpoint distinction: only {diff} of "
            f"{sorted(REQUIRED_IDENTITY_KEYS)} differ "
            f"(required {min_distinct_components}). "
            f"builder={builder_identity} verifier={verifier_identity}"
        )


def build_certificate(
    *,
    plan: Plan,
    artifact: Artifact,
    builder_identity: dict[str, str],
    verifier_identity: dict[str, str],
    grader_results: list[GraderResult],
    critic_findings: list[CriticFinding],
    grader_drift: Iterable[str] = (),
    min_critic_attempts: int = 3,
) -> VerifierCertificate:
    """Build a VerifierCertificate. Raises on cross-checkpoint or grader-drift
    violations. The cert's `passed` field is the AND of: every grader passed,
    no critic finding is `falsified=True`, and minimum critic attempts met."""
    assert_cross_checkpoint(builder_identity, verifier_identity)

    drift_list = list(grader_drift)
    if drift_list:
        raise GraderDriftViolation(
            f"pinned graders drifted between pin and verify: {drift_list}. "
            f"See red-team finding F6."
        )

    all_pass = all(g.passed for g in grader_results)
    any_falsified = any(f.falsified for f in critic_findings)
    enough_attempts = len(critic_findings) >= min_critic_attempts

    passed = all_pass and (not any_falsified) and enough_attempts

    notes_parts: list[str] = []
    if not all_pass:
        failed = [g.grader for g in grader_results if not g.passed]
        notes_parts.append(f"v1_failed={failed}")
    if any_falsified:
        falsified_attempts = [f.attempt for f in critic_findings if f.falsified]
        notes_parts.append(f"v2_falsified={falsified_attempts}")
    if not enough_attempts:
        notes_parts.append(
            f"critic produced {len(critic_findings)} attempts, "
            f"minimum {min_critic_attempts}"
        )

    return VerifierCertificate(
        cert_id=f"cert-{uuid.uuid4().hex[:12]}",
        plan_id=plan.plan_id,
        artifact_id=artifact.artifact_id,
        artifact_hash=artifact.body_hash,
        builder_checkpoint=builder_identity.get("checkpoint_id", "unknown"),
        verifier_checkpoint=verifier_identity.get("checkpoint_id", "unknown"),
        grader_results=grader_results,
        critic_findings=critic_findings,
        passed=passed,
        signed_at=time.time(),
        notes="; ".join(notes_parts) if notes_parts else "all-clear",
    )
