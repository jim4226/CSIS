"""CSIS Phase-0 prototype.

A coordinator-led continuous self-improving system, implementing the v0.2
Phase-0 contract from CSIS-architecture.html.

Public API surface:
    from csis.loop import run_iteration, run_continuous
    from csis.runtime.coordinator import Coordinator
    from csis.memory.trust import TrustLevel
    from csis.substrate.capability import CapabilityTier
"""

__version__ = "0.0.1"
