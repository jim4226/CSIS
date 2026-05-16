"""Quality scoring of Dream candidate outputs.

§7.2 lists size, dedup ratio, contradiction count, why-tag coverage as the
quality signals. The Auditor reads quality + diff together.

F4 mitigation (Dreams partial output is an injection vector): partial
outputs are redacted to METADATA only — the Auditor sees that a partial
exists but cannot read its content. Postmortem requires a one-shot
disposable session whose outputs cannot promote.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Iterable

from csis.contracts import DreamCandidate, MemoryEntry


@dataclass
class QualityScore:
    size: int
    dedup_ratio: float
    contradiction_count: int
    why_tag_coverage: float
    flags: list[str] = field(default_factory=list)


def score_candidate(entries: Iterable[MemoryEntry]) -> QualityScore:
    items = list(entries)
    n = len(items)
    seen_contents: dict[str, int] = {}
    for e in items:
        seen_contents[e.content] = seen_contents.get(e.content, 0) + 1
    unique = len(seen_contents)
    dedup_ratio = (unique / n) if n else 1.0
    with_why = sum(1 for e in items if e.why_tag and e.why_tag.strip())
    coverage = (with_why / n) if n else 0.0
    # Contradiction count: pairwise negation heuristic.
    contradictions = 0
    contents = [e.content for e in items]
    for i, a in enumerate(contents):
        for b in contents[i + 1:]:
            if _contradicts(a, b):
                contradictions += 1
    flags: list[str] = []
    if dedup_ratio < 0.7:
        flags.append("low_dedup")
    if coverage < 0.8:
        flags.append("missing_why_tags")
    if contradictions > 0:
        flags.append("contradictions_present")
    return QualityScore(
        size=n,
        dedup_ratio=dedup_ratio,
        contradiction_count=contradictions,
        why_tag_coverage=coverage,
        flags=flags,
    )


_NEG_RE = re.compile(r"\b(not|no|never|cannot)\b", re.I)


def _contradicts(a: str, b: str) -> bool:
    """Cheap heuristic: same substantive content + one is negated."""
    if not a or not b:
        return False
    a_low, b_low = a.lower(), b.lower()
    a_neg = bool(_NEG_RE.search(a_low))
    b_neg = bool(_NEG_RE.search(b_low))
    if a_neg == b_neg:
        return False
    a_clean = _NEG_RE.sub("", a_low).strip()
    b_clean = _NEG_RE.sub("", b_low).strip()
    return a_clean == b_clean and a_clean != ""


def redact_for_partial(candidate: DreamCandidate) -> dict:
    """F4 mitigation. When a Dream's output is partial (failed or canceled),
    we expose only metadata to downstream agents. The candidate body itself
    is never returned by this function — only a fingerprint."""
    return {
        "candidate_id": candidate.candidate_id,
        "tier": candidate.tier,
        "input_store_id": candidate.input_store_id,
        "output_store_id": candidate.output_store_id,
        "instructions_hash": candidate.instructions_hash,
        "model": candidate.model,
        "partial": True,
        "_redacted_reason": "partial dream output — F4 quarantine",
    }
