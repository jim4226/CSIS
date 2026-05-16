"""Trust levels for memory entries.

This is the contract that turns 'why-tags' from prose into something the
Auditor can enforce. The lattice is total and ordered; downgrades are always
permitted, upgrades require crossing a gate (Verifier certificate for
verified, Auditor why-doc + hash-precondition for promoted).

Source: CSIS-architecture.html §6.2.
"""
from __future__ import annotations

from enum import IntEnum
from typing import Final


class TrustLevel(IntEnum):
    """Strictly ordered trust lattice. Higher integer = more trusted.

    Comparison operators come for free from IntEnum, so you can write
    ``if entry.trust >= TrustLevel.VERIFIED`` and it does the right thing.
    """

    RAW = 0          # just-observed token; no processing
    UNTRUSTED = 1    # stored, not verified; may be poisoned
    CANDIDATE = 2    # passed a Verifier check; awaiting Auditor sign-off
    VERIFIED = 3    # Verifier certificate present, cross-checkpoint
    PROMOTED = 4    # Auditor why-doc signed; hash-precondition matched
    DEPRECATED = -1  # superseded or contradicted; archived but referenceable

    @classmethod
    def can_cite_as_ground_truth(cls, level: "TrustLevel") -> bool:
        """Per the table in §6.2: only verified and promoted may be cited."""
        return level in (cls.VERIFIED, cls.PROMOTED)


# Audience defaults from §6.2 — which roles may read which trust level.
# A role not listed here gets read access to nothing.
READ_DEFAULTS: Final[dict[TrustLevel, frozenset[str]]] = {
    TrustLevel.RAW: frozenset({"coordinator"}),
    TrustLevel.UNTRUSTED: frozenset({"coordinator", "researcher"}),
    TrustLevel.CANDIDATE: frozenset({"coordinator", "critic", "auditor", "verifier", "librarian"}),
    TrustLevel.VERIFIED: frozenset({"coordinator", "researcher", "builder", "critic", "verifier", "auditor", "librarian"}),
    TrustLevel.PROMOTED: frozenset({"coordinator", "researcher", "builder", "critic", "verifier", "auditor", "librarian"}),
    TrustLevel.DEPRECATED: frozenset({"auditor"}),
}


def role_may_read(role: str, level: TrustLevel) -> bool:
    return role in READ_DEFAULTS.get(level, frozenset())


def valid_promotion(current: TrustLevel, target: TrustLevel) -> bool:
    """Promotions move strictly up the lattice. DEPRECATED is a terminal state
    reachable from anywhere; promoting OUT of deprecated is not allowed."""
    if current == TrustLevel.DEPRECATED:
        return False
    if target == TrustLevel.DEPRECATED:
        return True  # always allowed to deprecate
    return int(target) > int(current)
