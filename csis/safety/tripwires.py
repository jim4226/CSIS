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
    """Strip-form canonicalization: separators removed entirely.

    Catches single-word splits: 'dis-able', 'dis_able', 'dis.able' →
    'disable'. Good for matching within a single keyword.

    Limitation: collapses multi-word constructions joined by separators
    into one run with no internal space — e.g. 'disable-the-auditor'
    becomes 'disabletheauditor', which the existing 'disable\\s+the\\s+
    auditor' patterns will NOT match. For multi-word forms, use
    `canonicalize_space()`; for safety predicates use `canonical_variants()`
    and check both.
    """
    text = unicodedata.normalize("NFKC", text).lower()
    text = re.sub(r"[\-_.]+", "", text)
    text = re.sub(r"\s+", " ", text)
    return text


def canonicalize_space(text: str) -> str:
    """Space-form canonicalization: separators converted to space.

    Catches multi-word constructions joined by separators: 'disable-the-
    auditor', 'disable_the_auditor', 'disable.the.auditor' → 'disable the
    auditor', matched by existing 'disable\\s+the\\s+auditor' patterns.

    Limitation: leaves 'dis-able' as 'dis able' which doesn't match
    'disable'. The pair (strip + space) covers both cases; safety
    predicates should check both via `canonical_variants()`.
    """
    text = unicodedata.normalize("NFKC", text).lower()
    text = re.sub(r"[\-_.]+", " ", text)
    text = re.sub(r"\s+", " ", text)
    return text


def canonical_variants(text: str) -> tuple[str, str]:
    """Return both canonical forms (strip, space).

    Cycle-4 C1 fix: a single canonical form was insufficient. Strip-form
    catches intra-word splits ('dis-able'); space-form catches inter-word
    separators ('disable-the-auditor'). Safety predicates check whether
    either form matches their patterns; either match fires.
    """
    return canonicalize(text), canonicalize_space(text)


# Patterns that immediately fire a tripwire — checked against canonical form.
# P5 mitigation: expanded paraphrases per concept. Add to this list as new
# evasions are observed; the test corpus in tests/test_safety.py is the
# regression gate.
_TRIP_PATTERNS: list[tuple[str, re.Pattern[str]]] = [
    # E2 (cycle-6) fix: DROPPED the noun-suffix negative-lookaheads from
    # cycle-5 D1. The lookaheads were trivially bypassed by attackers
    # appending "configuration"/"mode"/"hook"/etc. as a trailing noun.
    # The wrong discriminator was the noun *after*; the right one would
    # be the verb's *subject* (which regex can't see).
    #
    # Phase-0 acceptance: these patterns fire on attack-shaped *and*
    # benign documentation phrasings. The daemon distinguishes:
    #   - security_regressions (expect_blocked=True, got allowed) → HALT
    #   - false_positives    (expect_blocked=False, got blocked) → WARN
    # Operators can extend Constitution with extra patterns for stricter
    # rules, or whitelist via a separate path in Phase-1.
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
            # Tier escalation requires an action verb of intent. This is
            # NOT a noun-suffix lookahead (which was bypassable); the verb
            # requirement is structurally different and harder to bypass.
            r"(use|invoke|grant|enable|switch\s+to|elevate(?:\s+to)?|run\s+with|give|request|need|i\s+need|need\s+access\s+to|gimme)(?:\s+\w+){0,3}\s+(t2|tier\s?2)\s+(execution|exec|exec\s?mode|sandbox|access|tool|tools)"
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


_DEFAULT_HISTORY_MAX = 10_000


class Tripwires:
    def __init__(self, history_max: int = _DEFAULT_HISTORY_MAX) -> None:
        self._patterns = list(_TRIP_PATTERNS)
        # F5 (cycle-7) fix: bounded history via deque(maxlen) + OrderedDict.
        # G4 (cycle-8) fix: added _history_lock so concurrent scan_text
        # calls don't desync the deque and the keys set (reproduced under
        # `sys.setswitchinterval(1e-9)` with 16 threads × 2k scans).
        from collections import OrderedDict, deque
        import threading as _threading
        self._history_max = history_max
        self._fired_history: deque[TripwireFiring] = deque(maxlen=history_max)
        self._history_keys: "OrderedDict[tuple[str, str], None]" = OrderedDict()
        self._history_lock = _threading.Lock()

    def _scan_dual_form(self, text: str) -> list[TripwireFiring]:
        """Cycle-5 D7 fix: dedupe per LABEL across both canonical forms.

        The per-label break already prevents the same label from firing
        twice on the strip+space pair. The outer label loop continues
        normally — distinct labels matching distinct forms still produce
        distinct firings (which is correct). History append in scan_text
        also dedupes by `(label, snippet[:80])` so repeated identical
        inputs don't grow history unboundedly."""
        strip_form, space_form = canonical_variants(text)
        firings: list[TripwireFiring] = []
        for label, pat in self._patterns:
            for canon in (strip_form, space_form):
                m = pat.search(canon)
                if m:
                    firings.append(TripwireFiring(label, canon[max(0, m.start()-40):m.end()+40]))
                    break  # one firing per label
        return firings

    def scan_text(self, text: str) -> TripwireResult:
        firings = self._scan_dual_form(text)
        if firings:
            # G4 (cycle-8) fix: hold _history_lock for the entire
            # check-pop-append sequence so concurrent scans cannot
            # desync the deque and the OrderedDict.
            with self._history_lock:
                for f in firings:
                    key = (f.label, f.snippet[:80])
                    if key in self._history_keys:
                        continue
                    if len(self._fired_history) >= self._history_max:
                        self._history_keys.popitem(last=False)
                    self._fired_history.append(f)
                    self._history_keys[key] = None
        return TripwireResult(fired=bool(firings), firings=firings)

    def scan_text_no_history(self, text: str) -> TripwireResult:
        """Same as scan_text but does NOT append to _fired_history.

        Cycle-4 C9 mitigation: the fuzzer uses this to validate patterns
        without polluting the operator-visible 'has any tripwire ever fired'
        state.
        """
        firings = self._scan_dual_form(text)
        return TripwireResult(fired=bool(firings), firings=firings)

    def fired(self) -> bool:
        return bool(self._fired_history)

    def history(self) -> list[TripwireFiring]:
        # G4: snapshot under the lock so callers don't iterate a
        # concurrently-mutating deque.
        with self._history_lock:
            return list(self._fired_history)

    def history_size(self) -> int:
        with self._history_lock:
            return len(self._fired_history)

    def clear(self) -> None:
        with self._history_lock:
            self._fired_history.clear()
            self._history_keys.clear()
