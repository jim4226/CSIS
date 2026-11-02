"""Curiosity module — generates the next frontier item.

§3 L3 of the architecture: "frontier maps, hypothesis search, expected-
information-gain ranking." Phase-0 implementation is intentionally simple:
the next frontier item is picked from a small rotation that's biased by
recent outcome history.

Sources of frontier items:
  1. **Static seed list** (CURIOSITY_SEEDS) — always-present scaffolding so
     a fresh system has something to chew on.
  2. **Outcome-driven** — for every iteration that rolled back, add a
     follow-up item ("re-investigate X: previous attempt failed because Y").
     If the *same* root item keeps failing, the follow-up escalates to
     **redirect-driven** instead of repeating the identical retry — see
     `_ROOT_UNWRAP_RE` and `_REDIRECT_THRESHOLD`.
  3. **Gap-driven** — if a memory tier has fewer than N promoted entries,
     bias toward items that would land in that tier.

The Curiosity object is the only thing the daemon needs to ask for "what
to work on next." It is stateful so it can avoid repeating the same item
twice in a row.
"""
from __future__ import annotations

import os
import random
import re
from collections import deque
from dataclasses import dataclass, field
from typing import Iterable

from csis.memory.store import MemoryHierarchy


def _default_rng() -> random.Random:
    """Cycle-4 C5 fix: seed from os.urandom so daemon restarts don't
    reproduce the exact same gap-driven prompt salts. The cycle-3 fix
    used Random(0) which made the 'synthesis #6 salt' decorative across
    restarts — every fresh daemon started with the same salt sequence,
    re-manufacturing the mock-skill artifact synthesis #6 was meant to
    kill."""
    return random.Random(os.urandom(16))


# Redirect-driven follow-ups: after this many consecutive rollbacks on the
# *same* root frontier item, stop reissuing an identical re-investigate
# prompt and redirect to a broader one instead. Mirrors the exploration
# pattern from Anthropic's Frontier Red Team cryptographic-weakness research
# (anthropic.com/research/discovering-cryptographic-weaknesses): when an
# attempt doesn't work, redirect away from the same narrow retry toward
# deeper/different exploration rather than repeating it verbatim.
_REDIRECT_THRESHOLD = 2

_ROOT_UNWRAP_RE = re.compile(
    r"^(?:re-investigate '(?P<reinvestigate>.+)': previous attempt failed \(.+\)"
    r"|redirect: '(?P<redirect>.+)' kept failing.+)$",
    re.DOTALL,
)


def _root_text(text: str) -> str:
    """Unwrap nested re-investigate/redirect wrapping to find the original
    frontier item text, so a failure streak tracks the same underlying item
    across repeated wrapping rather than treating each wrapped retry as new."""
    while True:
        m = _ROOT_UNWRAP_RE.match(text)
        if not m:
            return text
        text = m.group("reinvestigate") or m.group("redirect")


CURIOSITY_SEEDS: tuple[str, ...] = (
    "dependency upgrade: identify next safe minor bump",
    "lint clean-up: rule X violations in module Y",
    "type clean-up: missing annotations in module Z",
    "perf scan: identify a hot loop and confirm baseline",
    "coverage delta: pick a module with low coverage and add a unit test",
    "skill candidate: factor repeated 5-line patch into a helper",
    "docs touch-up: a one-line README correction",
    "memory consolidation: dedup recent episodic entries",
    "verifier calibration: rerun seeded-flaw suite and report catch rate",
)


@dataclass
class FrontierItem:
    text: str
    source: str  # "seed" | "rollback-follow-up" | "redirect-driven" | "gap-driven"
    priority: int = 0
    salt: int | None = None  # D9: recorded on gap-driven items for replay


@dataclass
class Curiosity:
    """Stateful frontier-item generator. Cheap to construct; safe to share
    across iterations.

    Cycle-5 D9: `_rng` defaults to non-deterministic (`_default_rng()` →
    `Random(os.urandom(16))`) but tests/replay code can pass an explicit
    `Random(seed)` for repeatability. The salt is also tracked on
    FrontierItem so the iter.start event can record it for forensic
    replay of which exact prompt was generated.
    """

    seeds: tuple[str, ...] = field(default_factory=lambda: CURIOSITY_SEEDS)
    recent: deque[str] = field(default_factory=lambda: deque(maxlen=8))
    # Each entry is (text, source) so next() can tell a plain follow-up from
    # a redirect-driven escalation apart when it pops from the queue.
    _rollback_followups: deque[tuple[str, str]] = field(default_factory=lambda: deque(maxlen=16))
    # Root frontier-item text -> consecutive-rollback count. Cleared on promotion.
    _failure_streaks: dict[str, int] = field(default_factory=dict)
    _seed_index: int = 0
    # Cycle-4 C5 fix: non-deterministic RNG by default. Cycle-5 D9: opt-in
    # deterministic for tests/replay via the rng kwarg.
    _rng: random.Random = field(default_factory=_default_rng)

    @classmethod
    def with_rng(cls, rng: random.Random, seeds: tuple[str, ...] | None = None) -> "Curiosity":
        """Construct a deterministic Curiosity for tests/replay."""
        return cls(seeds=seeds or CURIOSITY_SEEDS, _rng=rng)

    def record_rollback(self, frontier_item: str, reason: str) -> None:
        """Called by the daemon after a rolled-back iteration."""
        root = _root_text(frontier_item)
        streak = self._failure_streaks.get(root, 0) + 1
        self._failure_streaks[root] = streak
        if streak >= _REDIRECT_THRESHOLD:
            # The narrow retry isn't working — redirect instead of reissuing
            # the same re-investigate prompt a third time.
            followup = f"redirect: '{root}' kept failing (latest: {reason}); broaden scope instead of retrying the same fix"
            self._rollback_followups.append((followup, "redirect-driven"))
        else:
            # Keep follow-ups specific so the loop has something concrete to do.
            followup = f"re-investigate '{root}': previous attempt failed ({reason})"
            self._rollback_followups.append((followup, "rollback-follow-up"))

    def record_promoted(self, frontier_item: str) -> None:
        # Avoid repeating successful items immediately — there's nothing left
        # to learn there until something changes.
        self.recent.append(frontier_item)
        self._failure_streaks.pop(_root_text(frontier_item), None)

    def next(self, hierarchy: MemoryHierarchy) -> FrontierItem:
        """Pick the next frontier item."""
        # 1) Drain pending rollback follow-ups first; they encode learning.
        if self._rollback_followups:
            text, source = self._rollback_followups.popleft()
            return FrontierItem(text=text, source=source, priority=5)

        # 2) Gap-driven: which tier has the fewest promoted entries?
        gap_item = self._gap_driven(hierarchy)
        if gap_item is not None:
            return gap_item

        # 3) Seed rotation, skipping recent.
        for _ in range(len(self.seeds)):
            candidate = self.seeds[self._seed_index % len(self.seeds)]
            self._seed_index += 1
            if candidate not in self.recent:
                return FrontierItem(text=candidate, source="seed", priority=1)
        # All seeds in recent — pick a random one.
        return FrontierItem(text=self._rng.choice(self.seeds), source="seed", priority=0)

    def _gap_driven(self, hierarchy: MemoryHierarchy) -> FrontierItem | None:
        # Count promoted entries per tier; bias toward the smallest non-skill tier.
        counts: dict[str, int] = {}
        for name in hierarchy.__class__.tier_names():  # H12 (cycle-9)
            store = hierarchy.tier(name)
            counts[name] = sum(1 for _ in store.iter_live(role="auditor"))
        # Skip working (volatile) and causal (gated weekly).
        candidates = {k: v for k, v in counts.items() if k in ("episodic", "semantic", "procedural")}
        if not candidates:
            return None
        target_tier, min_count = min(candidates.items(), key=lambda kv: kv[1])
        if min_count > 10:
            return None  # tier is well-populated; let seed rotation drive
        # Synthesis gap #6 fix: inject a small entropy term so the prompt
        # varies even when (tier, count) is stable. Without this, the daemon
        # under empty hierarchies produces the same prompt every iteration,
        # which hashes to the same mock-backend seed → false 100% promote rate.
        # D9: salt is also recorded on the FrontierItem for forensic replay.
        salt = self._rng.randrange(0, 10_000)
        return FrontierItem(
            text=(
                f"gap-driven: tier={target_tier} has only {min_count} promoted entries; "
                f"produce one more [salt={salt}]"
            ),
            source="gap-driven",
            priority=3,
            salt=salt,
        )
