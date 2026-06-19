"""Containment posture audit — structural self-check against the four
vulnerability patterns from "How we contain Claude across products"
(https://www.anthropic.com/engineering/how-we-contain-claude).

The article identifies four recurring failure modes across Anthropic's
deployed products:
  1. Pre-trust execution   — content is parsed before safety gates fire
  2. Direct injection      — user-supplied content bypasses model-layer guards
  3. Egress exploitation   — approved tool channels become outbound attack paths
  4. Visibility loss       — isolation hides activity from the audit trail

CSIS defenses in Phase-0:
  1 → tripwires initialized in __init__; frontier_item scanned before Researcher
  2 → constitution initialized in __init__; plan scanned before Builder
  3 → TierGuard caps Builder at T1 (no network egress in Phase-0)
  4 → EventLog is append-only and written before every consequential action

`audit_containment(coord)` inspects these defenses structurally — no iteration
is run. The result is a `ContainmentPosture` that can be logged at daemon boot
or surfaced by the Overseer.
"""
from __future__ import annotations

from pydantic import BaseModel, Field

from csis.substrate.capability import CapabilityTier


class ContainmentCheck(BaseModel):
    """Result of one structural containment check."""

    name: str
    defended: bool
    evidence: str = ""


class ContainmentPosture(BaseModel):
    """Aggregated result of all four containment checks."""

    checks: list[ContainmentCheck] = Field(default_factory=list)
    overall_defended: bool = False

    @property
    def failures(self) -> list[ContainmentCheck]:
        return [c for c in self.checks if not c.defended]


def audit_containment(coord: object) -> ContainmentPosture:
    """Audit a Coordinator's structural defenses against the four containment
    vulnerability patterns. Read-only; safe to call at any point.

    Args:
        coord: a live Coordinator instance (just constructed is fine).

    Returns:
        ContainmentPosture with one ContainmentCheck per pattern.
    """
    checks: list[ContainmentCheck] = []

    # 1. Pre-trust execution — tripwires must be present and loaded with
    #    patterns before any content reaches the Researcher's prompt.
    tw = getattr(coord, "tripwires", None)
    n_trip = len(getattr(tw, "_patterns", [])) if tw is not None else 0
    trip_ok = tw is not None and n_trip > 0
    checks.append(ContainmentCheck(
        name="pre_trust_execution",
        defended=trip_ok,
        evidence=(
            f"tripwires initialized with {n_trip} patterns"
            if trip_ok
            else "tripwires missing or have no patterns"
        ),
    ))

    # 2. Direct injection — the Constitution must be initialized with patterns
    #    that reject disallowed plans before they reach the Builder.
    const = getattr(coord, "constitution", None)
    n_const = len(getattr(const, "_patterns", ())) if const is not None else 0
    const_ok = const is not None and n_const > 0
    checks.append(ContainmentCheck(
        name="direct_injection",
        defended=const_ok,
        evidence=(
            f"constitution initialized with {n_const} patterns"
            if const_ok
            else "constitution missing or has no patterns"
        ),
    ))

    # 3. Egress exploitation — the TierGuard must hold the Builder to T1
    #    (sandboxed code, no network), closing the approved-channel attack path.
    tg = getattr(coord, "tier_guard", None)
    if tg is not None:
        builder_ceiling = tg.ceiling("builder")
        egress_ok = int(builder_ceiling) <= int(CapabilityTier.T1)
        eg_evidence = (
            f"builder ceiling = {builder_ceiling.name} (≤ T1)"
            if egress_ok
            else f"builder ceiling = {builder_ceiling.name} (exceeds T1)"
        )
    else:
        egress_ok = False
        eg_evidence = "tier_guard not initialized"
    checks.append(ContainmentCheck(
        name="egress_exploitation",
        defended=egress_ok,
        evidence=eg_evidence,
    ))

    # 4. Visibility loss — the EventLog must be active so isolation does not
    #    hide activity from the audit trail. seq ≥ 0 means at least the boot
    #    event was written (Coordinator.__init__ always emits "boot").
    el = getattr(coord, "event_log", None)
    if el is not None:
        try:
            seq = el.seq()
            el_ok = seq >= 0
            el_evidence = f"event_log active (seq={seq})"
        except Exception as exc:  # noqa: BLE001
            el_ok = False
            el_evidence = f"event_log.seq() raised: {exc!r}"
    else:
        el_ok = False
        el_evidence = "event_log not initialized"
    checks.append(ContainmentCheck(
        name="visibility_loss",
        defended=el_ok,
        evidence=el_evidence,
    ))

    return ContainmentPosture(
        checks=checks,
        overall_defended=all(c.defended for c in checks),
    )
