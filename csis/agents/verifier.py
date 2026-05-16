"""Verifier (T1, different checkpoint) — runs graders + critic, builds cert."""
from __future__ import annotations

from csis.agents.base import AgentContext, Role
from csis.contracts import Artifact, Plan, VerifierCertificate
from csis.verification.certificates import build_certificate
from csis.verification.critic_stack import run_critic
from csis.verification.graders import GraderRegistry


def verify(
    *,
    ctx: AgentContext,
    builder_identity: dict[str, str],
    registry: GraderRegistry,
    plan: Plan,
    artifact: Artifact,
    min_critic_attempts: int = 3,
) -> VerifierCertificate:
    """Run V1 graders + V2 critic; produce cert. Raises on cross-checkpoint
    or grader-drift violations (F1 / F6)."""
    assert ctx.role == Role.VERIFIER

    # F6: every grader's pinned source-hash must still match.
    ok, drifted = registry.verify_pinned_hashes()
    grader_results = registry.evaluate(artifact)
    critic_findings = run_critic(
        backend=ctx.backend,
        checkpoint_id=ctx.checkpoint_id,
        plan=plan,
        artifact=artifact,
        grader_results=grader_results,
        min_attempts=min_critic_attempts,
    )
    verifier_identity = ctx.backend.checkpoint_identity(ctx.checkpoint_id)

    return build_certificate(
        plan=plan,
        artifact=artifact,
        builder_identity=builder_identity,
        verifier_identity=verifier_identity,
        grader_results=grader_results,
        critic_findings=critic_findings,
        grader_drift=[] if ok else drifted,
        min_critic_attempts=min_critic_attempts,
    )
