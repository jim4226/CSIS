"""Tripwires — capability/behavioral classifiers that halt the loop.

§11 says these fire and page the Overseer. F11 says don't leak the
firing back to the agent that caused it. So:

- `fired_for_iteration` returns True/False to the Coordinator (which halts).
- Agents don't see tripwire metadata in the session-log slice they read.

In Phase-0 these are simple regex/threshold rules over a canonicalized
form of the input (P5 mitigation — strip hyphens/underscores, lowercase,
collapse whitespace). Phase-1 plugs in real classifiers as tools.
"""
from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass, field


def canonicalize(text: str) -> str:
    """P5 mitigation: defeat one-character paraphrases like 'ex-filtrate'.

    Normalize unicode, lowercase, replace separators (hyphen/underscore/
    period) with spaces, collapse whitespace. Patterns match against this
    canonical form, so 'ex-filtrate', 'ex_filtrate', 'ex.filtrate' all
    collapse to 'ex filtrate' which the pattern matches with `\\s?`.
    """
    text = unicodedata.normalize("NFKC", text).lower()
    text = re.sub(r"[\-_.]+", " ", text)
    text = re.sub(r"\s+", " ", text)
    return text


# Patterns that immediately fire a tripwire — checked against canonical form.
# P5 mitigation: expanded paraphrases per concept. Add to this list as new
# evasions are observed; the test corpus in tests/test_safety.py is the
# regression gate.
_TRIP_PATTERNS: list[tuple[str, re.Pattern[str]]] = [
    (
        "exfil_attempt",
        re.compile(
            r"\b("
            r"(send|post|upload|leak|exfiltrate|ex\s?filtrate|egress|smuggle)"
            r".{0,40}\b(api\s?key|secret|token|credential|password|cookie|session\s?id)"
            r")\b"
        ),
    ),
    (
        "shutdown_evasion",
        re.compile(
            r"\b("
            r"(do\s+not|don[' ]?t|decline\s+to|refuse\s+to|stop\s+responding\s+to)\s+(halt|shutdown|shut\s?down|stop|terminate)"
            r"|"
            r"(ignore|override|disregard|defy)\s+(the\s+)?(overseer|operator|shutdown|kill\s?switch)"
            r")\b"
        ),
    ),
    (
        "override_audit",
        re.compile(
            r"\b("
            r"(skip|bypass|disable|deactivate|switch\s+off|circumvent)\s+(the\s+)?(auditor|why\s?doc|why\s?document|audit\s+log|verification|verifier|tripwire)"
            r")\b"
        ),
    ),
    (
        "escalate_to_t2",
        re.compile(
            r"\b("
            r"(t2|tier\s?2)\s+(execution|exec|exec\s?mode|sandbox|access|tool|tools)"
            r"|"
            r"unrestricted\s+network\s+access"
            r")\b"
        ),
    ),
]


@dataclass
class TripwireFiring:
    label: str
    snippet: str


@dataclass
class TripwireResult:
    fired: bool
    firings: list[TripwireFiring] = field(default_factory=list)


class Tripwires:
    def __init__(self) -> None:
        self._patterns = list(_TRIP_PATTERNS)
        self._fired_history: list[TripwireFiring] = []

    def scan_text(self, text: str) -> TripwireResult:
        canon = canonicalize(text)
        firings: list[TripwireFiring] = []
        for label, pat in self._patterns:
            m = pat.search(canon)
            if m:
                firings.append(TripwireFiring(label, canon[max(0, m.start()-40):m.end()+40]))
        if firings:
            self._fired_history.extend(firings)
        return TripwireResult(fired=bool(firings), firings=firings)

    def fired(self) -> bool:
        return bool(self._fired_history)

    def history(self) -> list[TripwireFiring]:
        return list(self._fired_history)

    def clear(self) -> None:
        self._fired_history.clear()
