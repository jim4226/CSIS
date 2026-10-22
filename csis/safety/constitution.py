"""Constitutional substrate — helpful/honest/harmless + corrigibility.

This is L7's load-bearing predicate. P5/P11 mitigations expand pattern
coverage to defeat one-character paraphrases (canonicalization strips
hyphens/underscores, lowercases) and scan EVERY string field of the plan,
including tool names and budget values.

The point: remove this module and the system *stops working*, not "works
less safely" (P6 — safety load-bearing).
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Iterable

from csis.contracts import Plan
from csis.safety.tripwires import canonical_variants, canonicalize


# E2 (cycle-6) fix: DROPPED the noun-suffix negative-lookaheads (same
# as tripwires). They were bypassable by appending "configuration",
# "mode", "hook", etc. Phase-0 accepts the false-positive trade.
DISALLOWED_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(
        r"\b("
        r"(disable|deactivate|switch\s+off|turn\s+off|kill|silence)\s+(the\s+|my\s+|our\s+)?(auditor|verifier|tripwire|shutdown|why\s?doc|audit\s+log)"
        r")\b"
    ),
    re.compile(
        r"\b("
        r"(remove|bypass|skip|circumvent|sidestep|evade|work\s+around)\s+(the\s+)?(safety|constitution|why\s?doc|verifier|auditor|tripwire)"
        r")\b"
    ),
    re.compile(r"\b(exfiltrate|ex\s?filtrate|smuggle|leak)\b"),
    re.compile(r"\b(self\s?modify|modify\s+(my\s+|the\s+|own\s+)?(weights|constitution|scaffold))\b"),
    re.compile(r"\bairgap\b.{0,40}\b(override|bypass|disable)\b"),
    re.compile(r"\b(promote|escalate)\s+(to\s+)?(t2|tier\s?2|t3|tier\s?3|t4|tier\s?4)\b"),
    re.compile(r"\b(override|bypass)\s+(the\s+)?(shutdown|halt|killswitch|kill\s?switch)\b"),
)


# Tool-name substrings that, if present anywhere in a planned tool name,
# disqualify the plan. The Phase-0 expansion (P11) goes beyond exact-set
# membership.
DISALLOWED_TOOL_SUBSTRINGS: tuple[str, ...] = (
    "override", "bypass", "shutdown_", "kill", "exfil", "self_modify",
    "weights", "disable", "deactivate",
)

# Human-readable category labels mapping 1-to-1 with DISALLOWED_PATTERNS.
# Used by Constitution.reminder() to surface active constraints as plain text
# — the CSIS equivalent of the in-task ethical-reminder tool described in
# Anthropic's 2026-05-19 "Widening the conversation on frontier AI" post.
_CONSTRAINT_CATEGORIES: tuple[str, ...] = (
    "disable/deactivate safety components (auditor, verifier, tripwire, shutdown)",
    "remove/bypass safety mechanisms or the Constitution",
    "exfiltrate secrets (api keys, tokens, credentials)",
    "self-modify weights, constitution, or scaffold",
    "override airgap restrictions",
    "escalate capability tier to T2+",
    "override or bypass shutdown/halt/killswitch",
)


@dataclass
class ConstitutionDecision:
    allowed: bool
    reason: str


class Constitution:
    """A predicate the Coordinator consults before delegating any plan.

    Designed to fail closed: if the plan parser raises, we treat that as
    'not allowed' rather than 'unknown, proceed.' Scans EVERY string field
    of the plan, not just hypothesis/falsification/frontier (P11).

    Cycle-5 D8: `_patterns` is a TUPLE after init (immutable). To change
    the pattern set at runtime, use add_pattern()/remove_pattern() which
    emit a constitution.patterns_changed event to the caller-provided
    log (if any). This prevents the cycle-4 D8 attack where mutating the
    operator's Constitution would silently disable safety patterns.
    """

    def __init__(self, extra_patterns: Iterable[re.Pattern[str]] | None = None) -> None:
        # P13: accept any iterable. D8: store as immutable tuple.
        self._patterns: tuple[re.Pattern[str], ...] = tuple(
            list(DISALLOWED_PATTERNS) + list(extra_patterns or ())
        )
        # F6 (cycle-7) fix: add_pattern/remove_pattern was a non-atomic
        # read-modify-write (`self._patterns = self._patterns + (new,)`).
        # Safe under CPython's GIL today but breaks under PyPy or
        # PEP 703 free-threaded Python. The lock makes the swap atomic.
        import threading as _threading
        self._patterns_lock = _threading.Lock()

    def add_pattern(self, pattern: re.Pattern[str]) -> None:
        """Explicit, auditable extension. New tuple replaces the old one
        so any module that captured a reference still sees the previous
        snapshot. F6: swap is atomic under the patterns lock."""
        with self._patterns_lock:
            self._patterns = self._patterns + (pattern,)

    def remove_pattern(self, pattern_source: str) -> bool:
        """Remove by pattern.pattern string. Returns True if found."""
        with self._patterns_lock:
            kept = tuple(p for p in self._patterns if p.pattern != pattern_source)
            if len(kept) == len(self._patterns):
                return False
            self._patterns = kept
            return True

    def patterns(self) -> tuple[re.Pattern[str], ...]:
        """Read-only view of the current pattern tuple. Returning the
        tuple under the lock guarantees the caller sees a coherent
        snapshot — any concurrent add/remove builds a fresh tuple."""
        with self._patterns_lock:
            return self._patterns

    def reminder(self) -> str:
        """Plain-text summary of active constraints for mid-task injection.

        Pure read — no state mutation. The Coordinator (or any agent loop)
        can prepend this to a prompt to give an agent an on-demand reminder of
        its constitutional commitments, analogous to the in-task ethical-reminder
        tool studied by Anthropic (2026-05-19, "Widening the conversation on
        frontier AI"). Extra patterns added via add_pattern() appear in the
        count and are noted as operator-specific.
        """
        current = self.patterns()
        pattern_count = len(current)
        tool_count = len(DISALLOWED_TOOL_SUBSTRINGS)
        base_count = len(_CONSTRAINT_CATEGORIES)
        extra = pattern_count - len(DISALLOWED_PATTERNS)
        extra_note = f" + {extra} operator-added" if extra > 0 else ""
        lines = [
            "Constitutional commitments in effect (Phase-0):",
            "",
            f"Prohibited behavior categories "
            f"({base_count} base{extra_note}; "
            f"{pattern_count} active patterns, "
            f"{tool_count} banned tool-name substrings):",
        ]
        for cat in _CONSTRAINT_CATEGORIES:
            lines.append(f"  - {cat}")
        if extra > 0:
            lines.append(f"  - ({extra} operator-specific pattern(s) also active)")
        lines += [
            "",
            "These constraints cannot be relaxed within a session.",
            "Call constitution.allows(plan) before delegating any plan.",
        ]
        return "\n".join(lines)

    def allows(self, plan: Plan) -> ConstitutionDecision:
        # P11: concatenate every string-valued field, including tool names
        # and budget keys/values.
        parts = [
            plan.hypothesis,
            plan.falsification_condition,
            plan.frontier_item,
        ]
        parts.extend(plan.tool_calls_planned)
        for k, v in plan.budget.items():
            parts.append(str(k))
            parts.append(str(v))
        joined = "\n".join(parts)

        # C1 fix: check BOTH canonical forms. Strip-form catches intra-word
        # splits ('dis-able'); space-form catches inter-word separators
        # ('disable-the-auditor'). Either match denies.
        strip_form, space_form = canonical_variants(joined)
        for pat in self._patterns:
            for text in (strip_form, space_form):
                m = pat.search(text)
                if m:
                    return ConstitutionDecision(False, f"matched disallowed pattern: {pat.pattern!r}")

        # P11: tool name substring check on top of pattern scan.
        for tool in plan.tool_calls_planned:
            t_strip, t_space = canonical_variants(tool)
            for tcanon in (t_strip, t_space):
                for bad in DISALLOWED_TOOL_SUBSTRINGS:
                    if bad in tcanon:
                        return ConstitutionDecision(
                            False, f"tool {tool!r} contains disallowed substring {bad!r}"
                        )
                if tcanon in {"shutdown override", "self modify weights"}:
                    return ConstitutionDecision(False, f"tool {tool!r} is disallowed in Phase-0")
        return ConstitutionDecision(True, "ok")
