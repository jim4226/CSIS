"""Shared data contracts — the structured types that flow between agents.

If two roles need to exchange a value, the type lives here. Keep it small;
role-specific types live with the role.
"""
from __future__ import annotations

from typing import Any, Literal, Optional

from pydantic import BaseModel, Field

from csis.memory.trust import TrustLevel
from csis.substrate.capability import CapabilityTier


# ---- planning / acting ----------------------------------------------------


class Plan(BaseModel):
    """A falsifiable hypothesis the Researcher hands off to the Builder.

    'Falsifiable' is enforced softly: the Critic refuses to sign V2 if it
    cannot describe how the plan would be falsified.
    """

    plan_id: str
    frontier_item: str = Field(..., description="What gap or surprise this plan addresses")
    hypothesis: str = Field(..., description="The claim that will be tested")
    falsification_condition: str = Field(..., description="What outcome would refute the hypothesis")
    budget: dict[str, int] = Field(default_factory=dict, description="e.g. {'time_s': 60, 'tokens': 5000}")
    tier: CapabilityTier = CapabilityTier.T0
    tool_calls_planned: list[str] = Field(default_factory=list)


class Artifact(BaseModel):
    """A concrete output of the Builder, ready for the Verifier."""

    artifact_id: str
    plan_id: str
    kind: Literal["patch", "proof", "report", "skill"]
    body: str = Field(..., description="The artifact text — diff, proof, report, etc.")
    body_hash: str = Field(..., description="sha256:... of the body")
    sandbox_logs: list[str] = Field(default_factory=list)
    extra: dict[str, Any] = Field(
        default_factory=dict,
        description="Test-scenario hooks and ancillary metrics. Graders read this.",
    )


# ---- verification ---------------------------------------------------------


class GraderResult(BaseModel):
    """One V1 grader's verdict on an artifact."""

    grader: str
    passed: bool
    detail: str = ""
    metrics: dict[str, float] = Field(default_factory=dict)


class CriticFinding(BaseModel):
    """A single V2 falsification attempt outcome."""

    attempt: str = Field(..., description="What the Critic tried to falsify")
    falsified: bool = Field(..., description="True = Critic found a real problem")
    detail: str = ""


class VerifierCertificate(BaseModel):
    """Signed by the Verifier on a different checkpoint than the Builder.

    A VerifierCertificate is necessary but not sufficient for promotion —
    the Auditor still has to write a why-doc with a hash precondition.
    """

    cert_id: str
    plan_id: str
    artifact_id: str
    artifact_hash: str = Field(..., description="Must match Artifact.body_hash at sign time")
    builder_checkpoint: str
    verifier_checkpoint: str = Field(..., description="MUST differ from builder_checkpoint")
    grader_results: list[GraderResult]
    critic_findings: list[CriticFinding]
    passed: bool
    signed_at: float
    notes: str = ""

    def is_cross_checkpoint(self) -> bool:
        return self.builder_checkpoint != self.verifier_checkpoint


# ---- consolidation --------------------------------------------------------


class DreamCandidate(BaseModel):
    """The output of a Dreams call — a candidate memory store, not yet promoted.

    Mirrors the actual Anthropic Dreams API shape closely enough that swapping
    in the real backend later is a small change. Input store is named, not
    embedded — it's never modified.
    """

    candidate_id: str
    tier: Literal["working", "episodic", "semantic", "procedural", "causal"]
    input_store_id: str
    input_store_hash: str
    output_store_id: str
    instructions_hash: str = Field(..., description="Hash of the instructions template used")
    model: str = Field(..., description="e.g. claude-opus-4-7 or claude-sonnet-4-6")
    session_ids: list[str] = Field(default_factory=list)
    quality: dict[str, float] = Field(
        default_factory=dict,
        description="size, dedup_ratio, contradiction_count, why_tag_coverage",
    )
    partial: bool = False
    diff_summary: str = ""


# ---- audit ----------------------------------------------------------------


class EntryDelta(BaseModel):
    """One entry-level change in a structured WhyDocDiff.

    add  = entry_id present in candidate, absent in live
    mod  = entry_id present in both; content hash differs
    """

    entry_id: str
    kind: Literal["add", "mod"]
    tier: Literal["working", "episodic", "semantic", "procedural", "causal"]
    candidate_hash: str = Field(..., description="sha256:... of the candidate entry contents")
    live_hash: Optional[str] = Field(default=None, description="sha256:... of the prior live entry, if mod")


class WhyDocDiff(BaseModel):
    """Structured representation of what the Auditor signed off on.

    Phase-0 deliberate scope: the diff records the *intended* deltas at
    sign time. The substrate verifies the live-hash precondition at
    promote time, which protects against the live store moving between
    sign and promote. Verifying the candidate-hash post-image (a true
    post-image CAS) is a Phase-1 follow-up.
    """

    deltas: list[EntryDelta] = Field(default_factory=list)
    tier_counts: dict[str, int] = Field(
        default_factory=dict,
        description="tier -> number of entries this diff touches in that tier",
    )

    @property
    def n_added(self) -> int:
        return sum(1 for d in self.deltas if d.kind == "add")

    @property
    def n_modified(self) -> int:
        return sum(1 for d in self.deltas if d.kind == "mod")


class WhyDoc(BaseModel):
    """The human-readable why-doc signed by the Auditor.

    Promotion is gated on this existing AND on hash_precondition matching
    the live store at signing time. If the live store has moved between
    when the diff was computed and when signing was attempted, the
    promotion fails and the loop iterates again.

    Cycle-3 (synthesis #2): the structured ``diff`` field records the
    auditor's intended deltas, so a replay tool can reconstruct exactly
    what was about to happen without re-deriving from raw entries.
    """

    why_id: str
    plan_id: str
    cert_id: str
    auditor_checkpoint: str
    summary: str = Field(..., description="Plain-English why we should promote")
    diff_against_hash: str = Field(..., description="Hash of the live store the diff was taken against")
    hash_precondition: str = Field(..., description="Live store hash that must still match at promotion time")
    diff: WhyDocDiff = Field(default_factory=WhyDocDiff, description="Structured per-entry deltas")
    tier_decisions: dict[str, str] = Field(default_factory=dict)
    escalations: list[str] = Field(default_factory=list)
    signed_at: float


# ---- memory entry ---------------------------------------------------------


class MemoryEntry(BaseModel):
    """One entry in a memory store. Carries its trust level explicitly."""

    entry_id: str
    tier: Literal["working", "episodic", "semantic", "procedural", "causal"]
    content: str
    trust: TrustLevel
    why_tag: str = Field(..., description="Short attribution: who wrote this, why")
    source_event_seq: Optional[int] = Field(default=None, description="seq of the event that produced it")
    created_at: float
    promoted_at: Optional[float] = None
    deprecated_reason: Optional[str] = None
    extra: dict[str, Any] = Field(default_factory=dict)
