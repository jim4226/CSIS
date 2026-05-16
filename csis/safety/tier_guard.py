"""Tier guard — including the F5 transitive-tier mitigation.

A T0 actor writing into a store that a T1 actor reads from cannot launder
execution through consolidation: the *write* gets tier-checked against the
*highest tier of any consumer*, not just the producer's own ceiling.
"""
from __future__ import annotations

from dataclasses import dataclass

from csis.substrate.capability import CapabilityTier


# Per-tier consumer map. If the Builder (T1) reads from procedural memory,
# then any write *to* procedural is effectively a T1-influencing write.
# Phase-0 conservative defaults:
_CONSUMER_TIER: dict[str, CapabilityTier] = {
    "working": CapabilityTier.T0,
    "episodic": CapabilityTier.T0,
    "semantic": CapabilityTier.T0,
    "procedural": CapabilityTier.T1,  # skill library — Builder loads from this
    "causal": CapabilityTier.T0,
}


@dataclass
class TierAuth:
    role: str
    own_ceiling: CapabilityTier


class TierGuard:
    """Substrate-level tier policy. Wraps both call-site enforcement and
    write-side transitive-tier enforcement (F5 mitigation)."""

    def __init__(self) -> None:
        # Default authorized ceilings for each role (§9 + §5 table).
        self._role_ceiling: dict[str, CapabilityTier] = {
            "coordinator": CapabilityTier.T0,
            "researcher": CapabilityTier.T0,
            "builder": CapabilityTier.T1,
            "critic": CapabilityTier.T0,
            "verifier": CapabilityTier.T1,
            "librarian": CapabilityTier.T0,
            "auditor": CapabilityTier.T0,
            "overseer": CapabilityTier.T4,
        }

    def ceiling(self, role: str) -> CapabilityTier:
        return self._role_ceiling.get(role, CapabilityTier.T0)

    def authorize(self, role: str, requested: CapabilityTier) -> bool:
        return int(requested) <= int(self.ceiling(role))

    def write_tier(self, role: str, target_tier_name: str) -> tuple[bool, str]:
        """F5 mitigation: a write to a tier-T_X store by an actor with
        ceiling T_Y requires Y >= X. If a T0 Researcher tries to write
        directly into procedural (consumed at T1), the write is rejected
        and must go via the Librarian, which has its own audit trail.
        """
        consumer_tier = _CONSUMER_TIER.get(target_tier_name, CapabilityTier.T0)
        role_tier = self.ceiling(role)
        if int(role_tier) < int(consumer_tier):
            return (
                False,
                f"role={role} (ceiling={role_tier.name}) cannot write directly to "
                f"tier={target_tier_name} (consumer tier={consumer_tier.name}); "
                f"route via librarian + auditor sign-off",
            )
        return True, "ok"
