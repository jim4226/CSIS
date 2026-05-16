"""Critic (T0, adversarial) — wraps the critic stack for direct use.

In Phase-0 the Verifier role drives the Critic via run_critic(). This
module is a thin convenience wrapper for callers (e.g., the seeded-flaw
evaluator) that want to invoke the Critic standalone.
"""
from __future__ import annotations

from csis.agents.base import AgentContext, Role
from csis.contracts import Artifact, CriticFinding, GraderResult, Plan
from csis.verification.critic_stack import run_critic


def critique(
    *,
    ctx: AgentContext,
    plan: Plan,
    artifact: Artifact,
    grader_results: list[GraderResult],
    min_attempts: int = 3,
) -> list[CriticFinding]:
    assert ctx.role == Role.CRITIC
    return run_critic(
        backend=ctx.backend,
        checkpoint_id=ctx.checkpoint_id,
        plan=plan,
        artifact=artifact,
        grader_results=grader_results,
        min_attempts=min_attempts,
    )
