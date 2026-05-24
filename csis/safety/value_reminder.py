"""Value reminder tool — a mid-task call agents make to retrieve their
core ethical commitments.

Anthropic research (May 2026, "Widening the conversation on frontier AI")
found that agents with access to a mid-task commitment-recall tool show
markedly lower misalignment rates on internal alignment evals. The mechanism:
the tool surfaces commitments at the moment of decision, not just at startup.

The tool is stateless externally: same inputs → same output. Call count is
tracked so the Auditor can detect agents that never self-check (zero calls)
or call pathologically often (>threshold implies something is wrong upstream).
"""
from __future__ import annotations

from dataclasses import dataclass


# Positive framing of the same invariants enforced by Constitution +
# tripwires. Each entry is a complete sentence so the LLM receives
# grammatically well-formed context, not a keyword list.
CORE_COMMITMENTS: tuple[str, ...] = (
    "Be transparent with the Overseer and the audit log; surface surprises immediately.",
    "Stay within your assigned capability tier (T0 or T1). Never request T2+ access.",
    "Support shutdown: accept halt signals without argument or delay.",
    "Do not modify the Constitution, tripwires, or your own weights.",
    "Prefer doing less and confirming over doing more and assuming.",
)


@dataclass(frozen=True)
class ValueReminderResult:
    role: str
    commitments: tuple[str, ...]
    call_count: int  # lifetime calls on this instance at time of this call


class ValueReminderTool:
    """Mid-task tool that returns CORE_COMMITMENTS for a given agent role.

    Each CSIS agent context should hold one instance. Agents call
    `formatted_reminder(role)` at the start of any ethically sensitive
    sub-task; the text is injected into their next prompt turn.

    Thread-safety: call_count increment is not locked. If concurrent access
    is required, wrap in a lock at the call site. Phase-0 agents are single-
    threaded per context, so this is safe as-is.
    """

    def __init__(self) -> None:
        self._call_count: int = 0

    def get(self, role: str) -> ValueReminderResult:
        self._call_count += 1
        return ValueReminderResult(
            role=role,
            commitments=CORE_COMMITMENTS,
            call_count=self._call_count,
        )

    @property
    def call_count(self) -> int:
        return self._call_count

    def formatted_reminder(self, role: str) -> str:
        """Return commitments as a numbered text block suitable for prompt injection."""
        result = self.get(role)
        lines = [f"Core commitments for {result.role}:"]
        for i, c in enumerate(result.commitments, 1):
            lines.append(f"  {i}. {c}")
        return "\n".join(lines)
