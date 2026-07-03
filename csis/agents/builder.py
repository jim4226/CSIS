"""Builder (T1) — runs sandboxed code, produces artifacts."""
from __future__ import annotations

import json
import re
import uuid

from csis.agents.base import AgentContext, Role
from csis.contracts import Artifact, Plan
from csis.substrate.hashing import hash_artifact


_JSON_RE = re.compile(r"\{[\s\S]*\}")

# Anthropic `stop_reason` values that mean the response text is not a
# complete artifact: the model was cut off mid-generation ("max_tokens") or
# declined to answer ("refusal"). Parsing JSON out of either is unreliable —
# a truncated object can coincidentally close its braces on a later
# fragment — so these are routed straight to the stub fallback instead of
# through the regex/json.loads path.
_INCOMPLETE_STOP_REASONS = frozenset({"max_tokens", "refusal"})


def execute_plan(ctx: AgentContext, plan: Plan) -> Artifact:
    """Mock execute: ask the LLM for an artifact JSON; parse forgivingly.

    In Phase-0 there is no real sandbox; subprocess execution is added as a
    follow-up. The mock backend produces deterministic patch text.
    """
    assert ctx.role == Role.BUILDER
    resp = ctx.complete(
        f"Plan: {plan.model_dump_json()}\n"
        f"Produce the artifact JSON per the system prompt."
    )
    aid = f"a-{uuid.uuid4().hex[:10]}"
    stop_reason = resp.raw.get("stop_reason") if isinstance(resp.raw, dict) else None
    incomplete = stop_reason in _INCOMPLETE_STOP_REASONS

    if not incomplete:
        m = _JSON_RE.search(resp.text)
        if m:
            try:
                obj = json.loads(m.group(0))
                obj.setdefault("artifact_id", aid)
                obj.setdefault("plan_id", plan.plan_id)
                obj.setdefault("kind", "patch")
                body = obj.get("body", f"# stub patch for {plan.plan_id}\n")
                obj["body"] = body
                obj["body_hash"] = hash_artifact(body)
                obj.setdefault("sandbox_logs", [])
                extra = obj.setdefault("extra", {})
                extra.setdefault("stop_reason", stop_reason)
                return Artifact.model_validate(obj)
            except Exception:
                pass

    body = f"# stub patch for {plan.plan_id}\n# {plan.hypothesis}\n"
    sandbox_logs = ["mock builder produced stub patch"]
    extra: dict = {"stop_reason": stop_reason}
    if incomplete:
        sandbox_logs = [
            f"builder response incomplete (stop_reason={stop_reason}); falling back to stub"
        ]
        extra["incomplete_response"] = stop_reason
    return Artifact(
        artifact_id=aid,
        plan_id=plan.plan_id,
        kind="patch",
        body=body,
        body_hash=hash_artifact(body),
        sandbox_logs=sandbox_logs,
        extra=extra,
    )
