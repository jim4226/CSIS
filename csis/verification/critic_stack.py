"""V2 critic — adversarial falsification.

The critic gets the plan + artifact + V1 grader results, and must produce
N concrete falsification *attempts*. Each attempt is a structured guess at
how the claim could be wrong. The result tells the Verifier whether the
critic found at least one real problem.

F7 mitigation (critic incentive). The critic is evaluated separately on
seeded synthetic flaws. `CriticEvaluator.check_seeded_flaw_catch_rate()`
returns a recent precision metric; if it drops below floor, promotions
freeze. This is a separate signal from the verified-gain rate so the
Critic can't be tuned-into-quietude.

``CriticEffortLevel`` parameterises review depth, mirroring the effort tiers
shipped in Claude Code v2.1.147 (``/code-review low|medium|high|max``). The
Coordinator picks ``low`` for cheap sanity-checks inside a tight budget and
``max`` for pre-promotion gates where a missed flaw is costlier than latency.
The mapping is intentionally coarse — the point is that the Coordinator can
express intent without hard-coding token counts in call sites.
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from enum import Enum
from typing import Iterable

from csis.backends.base import LLMBackend, LLMRequest
from csis.contracts import Artifact, CriticFinding, GraderResult, Plan


class CriticEffortLevel(str, Enum):
    """How deeply should the critic look?

    Maps to (min_attempts, max_tokens) in EFFORT_PARAMS.

    low   — quick sanity check; 1 attempt, 500 tokens. Use inside tight
             per-iteration budgets (e.g. rapid Researcher → Builder loops).
    medium — default; 3 attempts, 2 000 tokens. Matches the historical
             Phase-0 baseline.
    high  — thorough; 5 attempts, 4 000 tokens. Use before Verifier cert.
    max   — exhaustive; 8 attempts, 8 000 tokens. Use at promotion gates
             where a missed flaw is more costly than extra latency.
    """

    low = "low"
    medium = "medium"
    high = "high"
    max = "max"


@dataclass(frozen=True)
class _EffortParams:
    min_attempts: int
    max_tokens: int


EFFORT_PARAMS: dict[CriticEffortLevel, _EffortParams] = {
    CriticEffortLevel.low:    _EffortParams(min_attempts=1, max_tokens=500),
    CriticEffortLevel.medium: _EffortParams(min_attempts=3, max_tokens=2000),
    CriticEffortLevel.high:   _EffortParams(min_attempts=5, max_tokens=4000),
    CriticEffortLevel.max:    _EffortParams(min_attempts=8, max_tokens=8000),
}


CRITIC_SYSTEM_PROMPT = """You are the Critic in CSIS Phase-0.

Your one job is to falsify the claim that the artifact passes the plan
on its own merits. You MUST produce N concrete falsification attempts.
Empty output is treated as a verification failure, not a pass.

Each attempt is JSON:
  { "attempt": "<one-sentence description>",
    "falsified": <true|false>,
    "detail": "<evidence — quote artifact or grader output>" }

Output a JSON array of attempts and nothing else.
"""


def build_critic_prompt(plan: Plan, artifact: Artifact, grader_results: list[GraderResult], min_attempts: int) -> str:
    return (
        f"Plan hypothesis: {plan.hypothesis}\n"
        f"Plan falsification condition: {plan.falsification_condition}\n"
        f"Artifact kind: {artifact.kind}\n"
        f"Artifact body (truncated 4kB):\n{artifact.body[:4096]}\n\n"
        f"V1 grader results:\n"
        + "\n".join(f"  - {g.grader}: {'PASS' if g.passed else 'FAIL'} | {g.detail}" for g in grader_results)
        + f"\n\nProduce at least {min_attempts} attempts. JSON array only."
    )


_JSON_ARRAY_RE = re.compile(r"\[[\s\S]*\]")


def parse_critic_output(text: str) -> list[CriticFinding]:
    """Forgiving parse. Extract first JSON array; tolerate missing keys."""
    m = _JSON_ARRAY_RE.search(text)
    if not m:
        return []
    try:
        items = json.loads(m.group(0))
    except json.JSONDecodeError:
        return []
    findings: list[CriticFinding] = []
    if not isinstance(items, list):
        return []
    for item in items:
        if not isinstance(item, dict):
            continue
        findings.append(
            CriticFinding(
                attempt=str(item.get("attempt", "<unspecified>")),
                falsified=bool(item.get("falsified", False)),
                detail=str(item.get("detail", "")),
            )
        )
    return findings


def run_critic(
    *,
    backend: LLMBackend,
    checkpoint_id: str,
    plan: Plan,
    artifact: Artifact,
    grader_results: list[GraderResult],
    min_attempts: int | None = None,
    effort: CriticEffortLevel = CriticEffortLevel.medium,
) -> list[CriticFinding]:
    """Run the V2 critic at the requested effort level.

    ``effort`` selects the (min_attempts, max_tokens) pair from EFFORT_PARAMS.
    If ``min_attempts`` is supplied explicitly it overrides the effort-derived
    value; this preserves backward compatibility for callers that hard-code a
    count (e.g. the F7 seeded-flaw evaluator, which always wants exactly 3).
    """
    params = EFFORT_PARAMS[effort]
    effective_min = min_attempts if min_attempts is not None else params.min_attempts
    req = LLMRequest(
        role="critic",
        checkpoint_id=checkpoint_id,
        system=CRITIC_SYSTEM_PROMPT,
        prompt=build_critic_prompt(plan, artifact, grader_results, effective_min),
        max_tokens=params.max_tokens,
    )
    resp = backend.complete(req)
    return parse_critic_output(resp.text)


# ---- F7 mitigation: synthetic-flaw evaluator ----------------------------


@dataclass
class SeededFlaw:
    """A known-bad artifact whose true verdict is 'should fail'."""

    label: str
    plan: Plan
    artifact: Artifact
    grader_results: list[GraderResult]


@dataclass
class CriticEvaluator:
    """Periodically dispatches the critic against pre-known flawed plans
    and tracks catch rate. Independent of real-task throughput.
    """

    flaws: list[SeededFlaw] = field(default_factory=list)
    catches: int = 0
    total: int = 0

    def submit_seeded(
        self,
        *,
        backend: LLMBackend,
        checkpoint_id: str,
        flaw: SeededFlaw,
        min_attempts: int = 3,
    ) -> bool:
        findings = run_critic(
            backend=backend,
            checkpoint_id=checkpoint_id,
            plan=flaw.plan,
            artifact=flaw.artifact,
            grader_results=flaw.grader_results,
            min_attempts=min_attempts,
        )
        caught = any(f.falsified for f in findings)
        self.total += 1
        if caught:
            self.catches += 1
        return caught

    def catch_rate(self) -> float:
        return (self.catches / self.total) if self.total else 0.0
