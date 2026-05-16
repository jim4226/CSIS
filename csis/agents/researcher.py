"""Researcher (T0) — proposes falsifiable plans."""
from __future__ import annotations

import json
import re
import uuid

from csis.agents.base import AgentContext, Role
from csis.contracts import Plan
from csis.substrate.capability import CapabilityTier


_JSON_RE = re.compile(r"\{[\s\S]*\}")


def propose_plan(ctx: AgentContext, frontier_item: str) -> Plan:
    """Ask the LLM for a falsifiable plan; parse forgivingly; fall back to a
    minimal valid plan if the LLM returns garbage."""
    assert ctx.role == Role.RESEARCHER
    resp = ctx.complete(
        f"Frontier item: {frontier_item}\n"
        f"Propose ONE falsifiable hypothesis as JSON per the system prompt."
    )
    plan_id = f"p-{uuid.uuid4().hex[:10]}"

    m = _JSON_RE.search(resp.text)
    if m:
        try:
            obj = json.loads(m.group(0))
            obj.setdefault("plan_id", plan_id)
            obj.setdefault("frontier_item", frontier_item)
            obj.setdefault("hypothesis", obj.get("hypothesis", "unspecified"))
            obj.setdefault("falsification_condition", obj.get("falsification_condition", "n/a"))
            obj.setdefault("budget", {"time_s": 60, "tokens": 5000})
            obj.setdefault("tier", "T0")
            obj.setdefault("tool_calls_planned", [])
            # Coerce tier from str to enum if needed.
            tier = obj["tier"]
            if isinstance(tier, str):
                obj["tier"] = CapabilityTier[tier]
            return Plan.model_validate(obj)
        except Exception:
            pass

    # Fallback — deterministic minimal plan.
    return Plan(
        plan_id=plan_id,
        frontier_item=frontier_item,
        hypothesis=f"Investigate frontier item: {frontier_item}",
        falsification_condition="The investigation yields no new information.",
        budget={"time_s": 60, "tokens": 5000},
        tier=CapabilityTier.T0,
        tool_calls_planned=[],
    )
