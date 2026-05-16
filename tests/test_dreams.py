"""Dreams pipeline tests.

Red-team coverage:
  F4 — partial outputs must be redacted to metadata
  F10 — cadence is per-tier, not per-template
"""
from __future__ import annotations

import time

import pytest

from csis.contracts import MemoryEntry
from csis.dreams.pipeline import (
    ALLOWED_INSTRUCTION_HASHES,
    CadenceBudget,
    DreamPipeline,
    register_instruction_template,
)
from csis.dreams.quality import score_candidate
from csis.memory.trust import TrustLevel


def _entries(n: int, content_pattern: str = "claim-{i}") -> list[MemoryEntry]:
    now = time.time()
    return [
        MemoryEntry(
            entry_id=f"e-{i}",
            tier="episodic",
            content=content_pattern.format(i=i),
            trust=TrustLevel.UNTRUSTED,
            why_tag=f"researcher-v1: entry {i}",
            created_at=now,
        )
        for i in range(n)
    ]


def test_quality_score_clean_unique_with_tags() -> None:
    score = score_candidate(_entries(10))
    assert score.size == 10
    assert score.dedup_ratio == 1.0
    assert score.why_tag_coverage == 1.0
    assert score.contradiction_count == 0
    assert "missing_why_tags" not in score.flags


def test_quality_score_flags_duplicates() -> None:
    # All same content -> dedup ratio 1/n -> very low.
    score = score_candidate(_entries(10, content_pattern="same"))
    assert score.dedup_ratio < 0.7
    assert "low_dedup" in score.flags


def test_dream_runs_after_register() -> None:
    pipe = DreamPipeline(cadence={"episodic": CadenceBudget(min_interval_s=0)})
    template = "Consolidate episodic memory: dedup and integrate."
    register_instruction_template(template)
    result = pipe.schedule(
        tier="episodic",
        input_store_id="store-in",
        input_store_hash="sha256:zero",
        instructions_template=template,
        recent_entries=_entries(5),
    )
    assert result.entries is not None
    assert result.redacted_metadata is None
    assert len(result.entries) == 5
    assert result.candidate.partial is False


def test_dream_rejects_unregistered_template() -> None:
    pipe = DreamPipeline(cadence={"episodic": CadenceBudget(min_interval_s=0)})
    with pytest.raises(RuntimeError):
        pipe.schedule(
            tier="episodic",
            input_store_id="store-in",
            input_store_hash="sha256:zero",
            instructions_template="UNREGISTERED template " + str(time.time()),
            recent_entries=_entries(1),
        )


def test_partial_output_is_redacted_F4() -> None:
    """F4: partial Dream outputs must NOT expose entries downstream."""
    pipe = DreamPipeline(cadence={"episodic": CadenceBudget(min_interval_s=0)})
    template = "Partial-test template " + str(time.time())
    register_instruction_template(template)
    result = pipe.schedule(
        tier="episodic",
        input_store_id="store-in",
        input_store_hash="sha256:zero",
        instructions_template=template,
        recent_entries=_entries(5),
        force_partial=True,
    )
    assert result.candidate.partial is True
    assert result.entries is None
    assert result.redacted_metadata is not None
    # Metadata must NOT contain entry content fragments.
    flat = " ".join(str(v) for v in result.redacted_metadata.values())
    assert "claim-0" not in flat
    assert "_redacted_reason" in result.redacted_metadata


def test_cadence_per_tier_not_per_template_F10() -> None:
    """F10: cadence is enforced per tier, regardless of template variant."""
    pipe = DreamPipeline(cadence={"episodic": CadenceBudget(min_interval_s=3600)})
    template_a = "Template A " + str(time.time())
    template_b = "Template B " + str(time.time())
    register_instruction_template(template_a)
    register_instruction_template(template_b)
    pipe.schedule(
        tier="episodic", input_store_id="in", input_store_hash="sha256:0",
        instructions_template=template_a, recent_entries=_entries(1),
    )
    # Second Dream within the same tier should fail even with a different template hash.
    with pytest.raises(RuntimeError, match="cadence"):
        pipe.schedule(
            tier="episodic", input_store_id="in", input_store_hash="sha256:0",
            instructions_template=template_b, recent_entries=_entries(1),
        )
