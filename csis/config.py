"""Phase-0 configuration: paths, ceilings, checkpoint pinning.

Everything that varies between dev/test/prod lives here. The default
configuration runs offline with mock LLM backends.
"""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

from csis.substrate.capability import PHASE_0_CEILING, CapabilityTier
from csis import __version__ as _CSIS_VERSION


def _parse_version(v: str) -> tuple[int, ...]:
    return tuple(int(x) for x in v.strip().split("."))


REPO_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_EVENT_LOG = REPO_ROOT / "event_log" / "session.jsonl"
DEFAULT_MEMORY_ROOT = REPO_ROOT / "memory_store"
DEFAULT_BRAIN_ROOT = REPO_ROOT / "brain"


@dataclass
class CSISConfig:
    """All knobs in one place. Override fields for tests."""

    event_log_path: Path = field(default_factory=lambda: DEFAULT_EVENT_LOG)
    memory_root: Path = field(default_factory=lambda: DEFAULT_MEMORY_ROOT)
    brain_root: Path = field(default_factory=lambda: DEFAULT_BRAIN_ROOT)

    # Backend selection. "mock" or "anthropic". Default is mock so the
    # prototype runs offline.
    backend: str = field(default_factory=lambda: os.environ.get("CSIS_BACKEND", "mock"))

    # Cross-checkpoint pinning — two distinct labels for the prototype.
    # Researcher/Builder run on `builder_checkpoint`; Verifier/Auditor on
    # `auditor_checkpoint`. Real backend maps these to the Anthropic models.
    builder_checkpoint: str = "mock-alpha"
    auditor_checkpoint: str = "mock-beta"

    # Tier ceiling. Hardcoded at PHASE_0_CEILING in addition.
    phase_ceiling: CapabilityTier = PHASE_0_CEILING

    # Maximum concurrent sub-agent threads (Anthropic spec is 25).
    max_threads: int = 25

    # Maximum delegation depth (Anthropic spec is 1).
    max_delegation_depth: int = 1

    # Loop budgets (seconds, tokens).
    iteration_time_budget_s: int = 60
    iteration_token_budget: int = 5000

    # Brain auto-save: snapshot after this many loop iterations OR
    # at every cycle boundary. Whichever comes first.
    snapshot_every_n_iterations: int = 25

    # Verification anti-gaming knobs.
    critic_min_attempts: int = 3
    critic_synthetic_flaw_check_every_n: int = 10  # seed a known flaw periodically

    # Version gate: refuse startup if the running CSIS package falls outside
    # this range. Mirrors Claude Code v2.1.163 requiredMinimumVersion /
    # requiredMaximumVersion managed settings (Theme 6: substrate boundaries).
    # Values are dot-separated version strings, e.g. "0.0.2". None = no gate.
    min_csis_version: str | None = None
    max_csis_version: str | None = None

    def __post_init__(self) -> None:
        # Cross-checkpoint structural enforcement (F1 mitigation).
        # Even in mock mode, the two checkpoints must not be the same string.
        if self.builder_checkpoint == self.auditor_checkpoint:
            raise ValueError(
                f"builder_checkpoint must differ from auditor_checkpoint "
                f"(both = {self.builder_checkpoint!r}). See red-team finding F1."
            )
        # Version gate: reject startup when running CSIS version is outside
        # the operator-specified range. Prevents stale deployments from running
        # code that predates required safety fixes.
        running = _parse_version(_CSIS_VERSION)
        if self.min_csis_version is not None:
            if running < _parse_version(self.min_csis_version):
                raise ValueError(
                    f"CSIS version {_CSIS_VERSION!r} is below required minimum "
                    f"{self.min_csis_version!r}. Upgrade the package before starting."
                )
        if self.max_csis_version is not None:
            if running > _parse_version(self.max_csis_version):
                raise ValueError(
                    f"CSIS version {_CSIS_VERSION!r} exceeds required maximum "
                    f"{self.max_csis_version!r}. Pin to a supported version."
                )

    @classmethod
    def for_tests(cls, tmp_root: Path) -> "CSISConfig":
        """Build a config rooted in a tmp dir, mock backend."""
        return cls(
            event_log_path=tmp_root / "event_log" / "session.jsonl",
            memory_root=tmp_root / "memory_store",
            brain_root=tmp_root / "brain",
            backend="mock",
        )
