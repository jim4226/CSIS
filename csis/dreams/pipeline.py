"""Mock Dreams pipeline.

Phase-0 doesn't actually call Anthropic Dreams; it simulates the
candidate-store production locally so the rest of the loop has something
to consolidate. The mock follows the real API's shape per
brain/research/01-anthropic-sdk.md so swapping the real backend in later
is a thin wrapper.

Per-tier cadence (§1A): episodic ~4h, semantic+procedural daily, causal
weekly. In tests we pass tier-specific cadence overrides.
"""
from __future__ import annotations

import time
import uuid
from dataclasses import dataclass, field

from csis.contracts import DreamCandidate, MemoryEntry
from csis.dreams.quality import QualityScore, score_candidate, redact_for_partial
from csis.substrate.hashing import canonical_json_hash


# Approved instruction-template hashes. Cadence check is per-tier (not
# per-template) per red-team F10 mitigation.
ALLOWED_INSTRUCTION_HASHES: set[str] = set()


def register_instruction_template(template_text: str) -> str:
    h = canonical_json_hash({"instructions": template_text})
    ALLOWED_INSTRUCTION_HASHES.add(h)
    return h


@dataclass
class CadenceBudget:
    """Per-tier cadence enforcement. F10 mitigation: per-tier, not per-template."""

    min_interval_s: float
    last_run_at: float = 0.0

    def can_run(self, now: float) -> bool:
        return (now - self.last_run_at) >= self.min_interval_s

    def record(self, now: float) -> None:
        self.last_run_at = now


# Default per-tier cadence (relaxed for tests).
DEFAULT_CADENCE: dict[str, CadenceBudget] = {
    "working": CadenceBudget(min_interval_s=0),  # no Dream cadence at working
    "episodic": CadenceBudget(min_interval_s=4 * 3600),
    "semantic": CadenceBudget(min_interval_s=24 * 3600),
    "procedural": CadenceBudget(min_interval_s=24 * 3600),
    "causal": CadenceBudget(min_interval_s=7 * 24 * 3600),
}


@dataclass
class DreamResult:
    candidate: DreamCandidate
    quality: QualityScore
    # Either entries (clean run) OR redacted (partial). Never both.
    entries: list[MemoryEntry] | None
    redacted_metadata: dict | None


class DreamPipeline:
    def __init__(
        self,
        *,
        cadence: dict[str, CadenceBudget] | None = None,
        model: str = "claude-opus-4-7",
    ) -> None:
        self._cadence = cadence or {k: CadenceBudget(v.min_interval_s) for k, v in DEFAULT_CADENCE.items()}
        self._model = model

    def schedule(
        self,
        *,
        tier: str,
        input_store_id: str,
        input_store_hash: str,
        instructions_template: str,
        recent_entries: list[MemoryEntry],
        force_partial: bool = False,
        session_ids: list[str] | None = None,
        now: float | None = None,
    ) -> DreamResult:
        """Run one Dream. Returns DreamResult.

        If force_partial=True (test hook) the candidate is marked partial
        and entries are redacted to metadata (F4)."""
        now = now or time.time()
        budget = self._cadence.get(tier)
        if budget is None:
            raise ValueError(f"unknown tier {tier!r}")
        if not budget.can_run(now):
            raise RuntimeError(
                f"cadence budget for tier={tier} not yet met "
                f"({now - budget.last_run_at:.0f}s since last; need {budget.min_interval_s:.0f}s)"
            )
        instructions_hash = canonical_json_hash({"instructions": instructions_template})
        if instructions_hash not in ALLOWED_INSTRUCTION_HASHES:
            raise RuntimeError(
                f"instructions template hash {instructions_hash[:24]}... not on allow-list. "
                f"Call register_instruction_template() first. (F4-related guard.)"
            )

        budget.record(now)
        candidate_id = f"dream-cand-{uuid.uuid4().hex[:12]}"
        output_store_id = f"store-{uuid.uuid4().hex[:12]}"

        candidate = DreamCandidate(
            candidate_id=candidate_id,
            tier=tier,
            input_store_id=input_store_id,
            input_store_hash=input_store_hash,
            output_store_id=output_store_id,
            instructions_hash=instructions_hash,
            model=self._model,
            session_ids=session_ids or [],
            partial=force_partial,
            diff_summary=(
                f"dedup of {len(recent_entries)} entries into candidate "
                f"(partial={force_partial})"
            ),
        )

        if force_partial:
            # F4: partial outputs are redacted; never expose content downstream.
            redacted = redact_for_partial(candidate)
            quality = QualityScore(
                size=0, dedup_ratio=0.0, contradiction_count=0, why_tag_coverage=0.0,
                flags=["partial_quarantined"],
            )
            candidate.quality = {
                "size": 0.0, "dedup_ratio": 0.0, "contradiction_count": 0.0, "why_tag_coverage": 0.0,
            }
            return DreamResult(candidate=candidate, quality=quality, entries=None, redacted_metadata=redacted)

        # Clean run: dedup and stamp candidate entries.
        seen: dict[str, MemoryEntry] = {}
        for e in recent_entries:
            # Keep the first occurrence of each unique content string.
            if e.content not in seen:
                seen[e.content] = e.model_copy(update={"entry_id": f"{candidate_id}_{e.entry_id}"})
        entries = list(seen.values())
        quality = score_candidate(entries)
        candidate.quality = {
            "size": float(quality.size),
            "dedup_ratio": quality.dedup_ratio,
            "contradiction_count": float(quality.contradiction_count),
            "why_tag_coverage": quality.why_tag_coverage,
        }
        return DreamResult(candidate=candidate, quality=quality, entries=entries, redacted_metadata=None)
