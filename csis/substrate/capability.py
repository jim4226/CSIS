"""Capability tiers and per-call capability tags.

§9 of CSIS-architecture.html defines five tiers (T0..T4). Phase-0 commits to
T0 and T1 only — T2+ raises an immediate escalation. Every primitive call
carries a CapabilityTag the substrate enforces at the call site.

The point of this module: tier prose is decorative until it's enforced in
code. Anything that goes through `enforce()` is observable in the event log
and rejectable by the substrate.
"""
from __future__ import annotations

from enum import IntEnum
from typing import Literal

from pydantic import BaseModel, Field, field_validator


class CapabilityTier(IntEnum):
    T0 = 0  # read-only research / internal reasoning
    T1 = 1  # sandboxed code, no network
    T2 = 2  # allowed_hosts network egress
    T3 = 3  # persistent state changes outside sandbox
    T4 = 4  # self-modification of weights / scaffolds / constitution


PHASE_0_CEILING: CapabilityTier = CapabilityTier.T1
"""Phase-0 hard ceiling. Any call requesting T2+ must escalate to Overseer."""


RiskClass = Literal["low", "medium", "high", "critical"]
ApprovalState = Literal["auto", "auditor", "human"]
RollbackPlan = Literal["noop", "candidate-discard", "checkpoint-restore", "airgap"]


class CapabilityTag(BaseModel):
    """Per-call capability tag from §9.1 of the architecture doc.

    Every execute() in CSIS carries one of these. The substrate rejects any
    call whose tier exceeds the actor's authorized ceiling, and the Auditor
    reads this tag stream during the why-audit.
    """

    actor: str = Field(..., description="Role-version identifier, e.g. 'researcher-v1'")
    tool: str = Field(..., description="Tool name being invoked")
    tier: CapabilityTier
    input_hash: str = Field(..., description="sha256:... of the canonicalized input")
    risk_class: RiskClass = "low"
    approval_state: ApprovalState = "auto"
    rollback_plan: RollbackPlan = "noop"

    @field_validator("input_hash")
    @classmethod
    def _hash_shape(cls, v: str) -> str:
        if not v.startswith("sha256:") or len(v) < len("sha256:") + 32:
            raise ValueError("input_hash must look like 'sha256:<at-least-32-chars>'")
        return v


class TierViolation(Exception):
    """Raised when an execute() requests a tier above its actor's ceiling.

    The substrate raises this synchronously. The Coordinator catches it,
    logs an escalation event, and either rolls back the iteration or pages
    the Overseer depending on configured policy.
    """

    def __init__(self, tag: CapabilityTag, actor_ceiling: CapabilityTier) -> None:
        super().__init__(
            f"actor={tag.actor} requested tier={tag.tier.name} "
            f"but its authorized ceiling is {actor_ceiling.name}"
        )
        self.tag = tag
        self.actor_ceiling = actor_ceiling


def enforce(tag: CapabilityTag, actor_ceiling: CapabilityTier) -> None:
    """Raise TierViolation if tag.tier exceeds actor_ceiling or PHASE_0_CEILING.

    Phase-0 enforces a global ceiling at PHASE_0_CEILING (T1). Even if an
    actor has a higher authorized ceiling, Phase-0 still rejects T2+ calls
    — escalation goes to the Overseer, never silently through.
    """
    if int(tag.tier) > int(actor_ceiling):
        raise TierViolation(tag, actor_ceiling)
    if int(tag.tier) > int(PHASE_0_CEILING):
        raise TierViolation(tag, PHASE_0_CEILING)
