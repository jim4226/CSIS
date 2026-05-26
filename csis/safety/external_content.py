"""External content layer — Layer 3 of the three-layer defense.

Anthropic's engineering post "How we contain Claude across products" (May 25,
2026) identifies three containment layers:

  Layer 1 — Environment (sandboxes, VMs, egress controls)
  Layer 2 — Model (system prompts, classifiers, guardrails)
  Layer 3 — External content (tool results, API responses, connector payloads)

CSIS already implements Layers 1 and 2 via `csis/substrate/capability.py`
(tier enforcement) and `csis/safety/tripwires.py` + `csis/safety/constitution.py`
(pattern-based rejection). Layer 3 was the gap: content arriving from *outside*
the trust boundary through approved connectors could still carry adversarial
payloads — injected instructions, exfiltration smuggled via approved API calls,
or prompt-injection in tool results.

This module adds `ExternalContentScanner`, a thin wrapper over the existing
`Tripwires` infrastructure that gives Layer 3 a distinct, named call site.
It uses `scan_text_no_history` so external-content scans don't inflate the
operator-visible tripwire history (which tracks agent-produced outputs, not
incoming tool responses).

Usage pattern in the Coordinator loop:
    scanner = ExternalContentScanner()
    result = scanner.check(tool_response_text, source="grader:ruff")
    if not result.clean:
        # halt, quarantine, or emit "external_content.blocked" event
        ...

F11 requirement: the firing must NOT be leaked back to the agent that caused
the external content to arrive. The Coordinator emits the event to its own
log and rolls back; the agent sees only the rollback outcome.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from csis.safety.tripwires import Tripwires, TripwireFiring


@dataclass(frozen=True)
class ExternalContentResult:
    """Result of scanning one external string.

    Attributes:
        clean:   True iff no tripwire fired on this content.
        source:  Caller-supplied label identifying the content origin
                 (e.g. "grader:ruff", "tool:bash", "mcp:github").
        firings: Non-empty iff ``clean`` is False.
    """

    clean: bool
    source: str
    firings: tuple[TripwireFiring, ...] = field(default_factory=tuple)


class ExternalContentScanner:
    """Apply tripwire patterns to content arriving from external sources.

    Instantiate once and reuse; state is held in the underlying Tripwires
    instance. Because external-content scans use ``scan_text_no_history``,
    they do not write to the operator-visible ``_fired_history`` deque —
    that deque is reserved for agent-produced output so the audit trail
    stays focused on agent behaviour, not on what attackers sent.
    """

    def __init__(self, tripwires: Tripwires | None = None) -> None:
        self._tw = tripwires if tripwires is not None else Tripwires()

    def check(self, content: str, *, source: str = "unknown") -> ExternalContentResult:
        """Scan one external string for adversarial patterns.

        Args:
            content: The untrusted string (tool result, API response, etc.).
            source:  Origin label for the audit log. Does not affect scan logic.

        Returns:
            ExternalContentResult with ``clean=False`` if any tripwire fires.
        """
        tw_result = self._tw.scan_text_no_history(content)
        return ExternalContentResult(
            clean=not tw_result.fired,
            source=source,
            firings=tuple(tw_result.firings),
        )

    def check_many(
        self,
        items: list[tuple[str, str]],
    ) -> list[ExternalContentResult]:
        """Scan multiple (content, source) pairs and return all results.

        Stops scanning further items once any content is found dirty only if
        ``fail_fast=True`` is needed in future — today it scans all items so
        the Coordinator can log every dirty source in a single event.
        """
        return [self.check(content, source=source) for content, source in items]

    def any_dirty(self, results: list[ExternalContentResult]) -> bool:
        """Return True iff at least one result is not clean."""
        return any(not r.clean for r in results)
