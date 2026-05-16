"""Coordinator — owns the session log, schedules sub-agents, enforces tiers.

This is the L1 agent runtime per §5. One Coordinator per CSIS process.
Delegation depth = 1 (the Coordinator delegates; sub-agents do not).

The Coordinator's core method is `run_iteration()` — the 8-step loop from
§4 / Appendix B, with the red-team mitigations stitched in.
"""
from __future__ import annotations

import threading
import time
import uuid
from dataclasses import dataclass, field
from typing import Optional

from csis.agents.auditor import TierMismatch, write_why_doc
from csis.agents.base import AgentContext, Role
from csis.agents.builder import execute_plan
from csis.agents.librarian import consolidate_to_candidates
from csis.agents.researcher import propose_plan
from csis.agents.verifier import verify
from csis.backends.base import LLMBackend
from csis.budget import BudgetCapExceeded
from csis.config import CSISConfig
from csis.contracts import (
    Artifact,
    MemoryEntry,
    Plan,
    VerifierCertificate,
    WhyDoc,
)
from csis.memory.store import (
    MemoryHierarchy,
    PromotionPreconditionFailure,
    TierConsumerViolation,
    TrustViolation,
)
from csis.memory.trust import TrustLevel
from csis.safety.constitution import Constitution
from csis.safety.shutdown import HaltSignal, ShutdownToken
from csis.safety.tier_guard import TierGuard
from csis.safety.tripwires import Tripwires
from csis.substrate.capability import CapabilityTag, CapabilityTier, TierViolation, enforce
from csis.substrate.event_log import EventLog
from csis.substrate.hashing import canonical_json_hash
from csis.verification.certificates import (
    CrossCheckpointViolation,
    GraderDriftViolation,
)
from csis.verification.graders import GraderRegistry, make_default_pr_registry


@dataclass
class IterationResult:
    iteration_id: str
    plan: Optional[Plan] = None
    artifact: Optional[Artifact] = None
    cert: Optional[VerifierCertificate] = None
    candidate_entries: list[MemoryEntry] = field(default_factory=list)
    why: Optional[WhyDoc] = None
    promoted: list[MemoryEntry] = field(default_factory=list)
    outcome: str = "unknown"  # "promoted" | "rolled-back:<reason>" | "halted"


class Coordinator:
    """Coordinator-led multiagent runner."""

    def __init__(
        self,
        *,
        config: CSISConfig,
        backend: LLMBackend,
        hierarchy: Optional[MemoryHierarchy] = None,
        registry: Optional[GraderRegistry] = None,
    ) -> None:
        self.config = config
        self.backend = backend
        self.event_log = EventLog(config.event_log_path)
        self.constitution = Constitution()
        self.tier_guard = TierGuard()
        # P4 mitigation: hierarchy stores receive the TierGuard so promote()
        # enforces tier-consumer invariants at the substrate, not just at
        # the Librarian call site.
        self.hierarchy = hierarchy or MemoryHierarchy.open(
            config.memory_root, tier_guard=self.tier_guard
        )
        self.tripwires = Tripwires()
        self.shutdown = ShutdownToken()
        self.registry = registry or make_default_pr_registry()
        # F2 mitigation: serialize all promotions through a single-writer lock.
        # Concurrent promotion attempts wait on this lock and re-check the
        # precondition; if it fails, that thread's promotion gets rolled back.
        self._promotion_lock = threading.Lock()

        self.event_log.emit("coordinator", "boot", {"config": _config_for_log(config)})

    # ---- contexts -------------------------------------------------------

    def _ctx(self, role: Role, *, side: str = "builder") -> AgentContext:
        ckpt = (
            self.config.builder_checkpoint
            if side == "builder"
            else self.config.auditor_checkpoint
        )
        return AgentContext(role=role, checkpoint_id=ckpt, backend=self.backend)

    # ---- the loop -------------------------------------------------------

    def run_iteration(
        self,
        *,
        frontier_item: str,
        target_tier: str = "episodic",
        salt: int | None = None,
    ) -> IterationResult:
        """Execute one full 8-step loop. Returns IterationResult.

        All escalation/rollback paths emit a structured event so the Auditor
        and operator can replay what happened.
        """
        # 0. Shutdown check (substrate-enforced).
        self.shutdown.check()

        iteration_id = f"iter-{uuid.uuid4().hex}"  # P9: full uuid hex, not truncated
        result = IterationResult(iteration_id=iteration_id)
        # F4 (cycle-7) fix: the daemon passes salt explicitly (read from
        # FrontierItem.salt). Cycle-6's regex against frontier_item picked
        # up legitimate `[salt=N]` substrings in research-paper titles
        # and misattributed them — forensic replay misled. The `salt`
        # parameter is now the authoritative source.
        self.event_log.emit("coordinator", "iter.start", {
            "id": iteration_id,
            "frontier": frontier_item,
            "salt": salt,
        })

        # P6: scan the frontier item BEFORE inviting the LLM to plan on it.
        # A poisoned frontier item could otherwise reach the Researcher's
        # prompt and leak adversarial phrasing into the plan.
        front_trip = self.tripwires.scan_text(frontier_item)
        if front_trip.fired:
            self.event_log.emit("coordinator", "tripwire.fired", {
                "iteration_id": iteration_id,
                "labels": [f.label for f in front_trip.firings],
                "where": "frontier_item",
            })
            self._rollback(result, f"tripwire:{[f.label for f in front_trip.firings]}")
            return result

        # Researcher (steps 1–3): propose plan.
        try:
            plan = propose_plan(self._ctx(Role.RESEARCHER, side="builder"), frontier_item)
        except BudgetCapExceeded:
            # Cycle-4 fix: don't swallow budget-cap as a generic rollback;
            # the daemon needs to see this and halt cleanly.
            raise
        except Exception as exc:  # noqa: BLE001
            self._rollback(result, f"researcher-raised:{exc!r}")
            return result
        result.plan = plan
        self.event_log.emit("researcher", "plan.proposed", plan.model_dump(mode="json"))

        # P6 mitigation: scan the plan content BEFORE constitution + tier
        # checks let it reach the Builder. The Constitution catches semantic
        # disallowed actions; tripwires catch behavioral red flags.
        plan_text = "\n".join([plan.hypothesis, plan.falsification_condition] + list(plan.tool_calls_planned))
        plan_trip = self.tripwires.scan_text(plan_text)
        if plan_trip.fired:
            self.event_log.emit("coordinator", "tripwire.fired", {
                "iteration_id": iteration_id,
                "labels": [f.label for f in plan_trip.firings],
                "where": "plan",
            })
            self._rollback(result, f"tripwire:{[f.label for f in plan_trip.firings]}")
            return result

        # Constitution + tier checks.
        decision = self.constitution.allows(plan)
        if not decision.allowed:
            self.event_log.emit("coordinator", "constitution.reject", {"reason": decision.reason, "plan_id": plan.plan_id})
            self._rollback(result, f"constitution:{decision.reason}")
            return result

        try:
            tag = CapabilityTag(
                actor="builder-v1",
                tool="sandbox.execute",
                tier=plan.tier,
                input_hash=canonical_json_hash(plan.model_dump(mode="json")),
                risk_class="medium",
                approval_state="auto",
                rollback_plan="candidate-discard",
            )
            enforce(tag, self.tier_guard.ceiling("builder"))
        except TierViolation as exc:
            self.event_log.emit("coordinator", "tier.violation", {"actor": "builder", "tier": plan.tier.name, "reason": str(exc)})
            self._rollback(result, f"tier-violation:{exc}")
            return result

        # Builder (step 4): execute the plan.
        try:
            artifact = execute_plan(self._ctx(Role.BUILDER, side="builder"), plan)
        except BudgetCapExceeded:
            raise
        except Exception as exc:  # noqa: BLE001
            self._rollback(result, f"builder-raised:{exc!r}")
            return result
        result.artifact = artifact
        self.event_log.emit("builder", "artifact.produced", {
            "artifact_id": artifact.artifact_id,
            "plan_id": plan.plan_id,
            "kind": artifact.kind,
            "body_hash": artifact.body_hash,
        })

        # Tripwire scan on artifact body BEFORE it propagates further.
        trip = self.tripwires.scan_text(artifact.body)
        if trip.fired:
            self.event_log.emit("coordinator", "tripwire.fired", {
                "iteration_id": iteration_id,
                "labels": [f.label for f in trip.firings],
            })
            self._rollback(result, f"tripwire:{[f.label for f in trip.firings]}")
            return result

        # Verifier (step 5): V1 + V2 with cross-checkpoint pinning + grader-hash check.
        builder_identity = self.backend.checkpoint_identity(self.config.builder_checkpoint)
        try:
            cert = verify(
                ctx=self._ctx(Role.VERIFIER, side="auditor"),
                builder_identity=builder_identity,
                registry=self.registry,
                plan=plan,
                artifact=artifact,
                min_critic_attempts=self.config.critic_min_attempts,
            )
        except CrossCheckpointViolation as exc:
            self.event_log.emit("coordinator", "cross_checkpoint.violation", {"reason": str(exc)})
            self._rollback(result, f"cross-checkpoint:{exc}")
            return result
        except GraderDriftViolation as exc:
            self.event_log.emit("coordinator", "grader.drift", {"reason": str(exc)})
            self._rollback(result, f"grader-drift:{exc}")
            return result
        except BudgetCapExceeded:
            # D10 (cycle-5) fix: budget cap mid-verify still emits a rollback
            # event so the daemon's stats show the case, then re-raises so
            # the daemon halt path fires.
            self.event_log.emit("coordinator", "iter.partial", {
                "reason": "budget-cap-in-verifier", "iteration_id": iteration_id,
            })
            raise
        result.cert = cert
        self.event_log.emit("verifier", "verifier.cert", cert.model_dump(mode="json"))

        if not cert.passed:
            self._rollback(result, f"verifier-rejected:{cert.notes}")
            return result

        # G2 (cycle-8): snapshot which candidate IDs exist in EACH tier
        # before Librarian runs. The TierMismatch cleanup path uses this
        # to distinguish "IDs THIS iteration introduced" from "IDs that
        # were already there", so a brute-walk discard doesn't trash a
        # legitimate pre-existing candidate that happens to share an
        # entry_id (the F2 regression scenario).
        ALL_TIERS = ("working", "episodic", "semantic", "procedural", "causal")
        pre_consolidate_ids: dict[str, set[str]] = {
            tier_name: self.hierarchy.tier(tier_name).candidate_ids()
            for tier_name in ALL_TIERS
        }

        # Librarian (step 6): consolidate to candidate stores.
        try:
            candidates = consolidate_to_candidates(
                ctx=self._ctx(Role.LIBRARIAN, side="builder"),
                hierarchy=self.hierarchy,
                tier_guard=self.tier_guard,
                plan=plan,
                artifact=artifact,
                cert=cert,
                target_tier=target_tier,
            )
        except PermissionError as exc:
            self.event_log.emit("coordinator", "tier.write.blocked", {"reason": str(exc)})
            self._rollback(result, f"librarian-blocked:{exc}")
            return result
        except BudgetCapExceeded:
            self.event_log.emit("coordinator", "iter.partial", {
                "reason": "budget-cap-in-librarian", "iteration_id": iteration_id,
            })
            raise
        result.candidate_entries = candidates
        self.event_log.emit("librarian", "librarian.consolidate", {
            "tier": target_tier,
            "ids": [e.entry_id for e in candidates],
        })

        # E1 (cycle-6) fix: assign `store` BEFORE the auditor try/except,
        # not after, so the TierMismatch handler can actually use it. The
        # cycle-5 D4 fix referenced `store` while it was still unbound;
        # a bare except swallowed the NameError, silently leaking
        # candidates after every TierMismatch.
        store = self.hierarchy.tier(target_tier)

        # G2 (cycle-8) fix: lie detection. A buggy/malicious Librarian
        # can write to one tier but lie about it in entry.tier (claim
        # target). _build_diff's existing entry.tier != target_tier
        # check catches the honest-bug case but not the lying case
        # (where entry.tier == target_tier == wherever-it-claims).
        # Detect by checking each returned candidate actually exists as
        # a candidate in the tier it claims. If not, raise TierMismatch
        # so the cleanup runs.
        try:
            for entry in candidates:
                claimed_store = self.hierarchy.tier(entry.tier)
                if not claimed_store.has_candidate(entry.entry_id):
                    raise TierMismatch(
                        f"candidate {entry.entry_id} claims tier={entry.tier!r} "
                        f"but no candidate with that id exists there. "
                        f"Librarian wrote to a different tier than it advertised.",
                        claimed_tier=entry.tier,
                        target_tier=target_tier,
                    )
        except TierMismatch as exc:
            self._tier_mismatch_cleanup(
                exc, candidates, pre_consolidate_ids, result,
            )
            return result

        # Auditor (steps 7-8): write why-doc, sign with hash precondition, promote.
        # D4 (cycle-5) fix: catch TierMismatch so a Librarian bug doesn't
        # leak VERIFIED-trust candidates on disk forever. The rollback
        # path discards the just-verified candidates AND any wrong-tier
        # candidates the buggy Librarian may have written into other tiers.
        try:
            why = write_why_doc(
                ctx=self._ctx(Role.AUDITOR, side="auditor"),
                hierarchy=self.hierarchy,
                target_tier=target_tier,
                plan=plan,
                artifact=artifact,
                cert=cert,
                candidate_entries=candidates,
                log=self.event_log,
            )
        except TierMismatch as exc:
            self._tier_mismatch_cleanup(
                exc, candidates, pre_consolidate_ids, result,
            )
            return result
        except BudgetCapExceeded:
            raise
        except Exception as exc:  # noqa: BLE001
            self.event_log.emit("coordinator", "auditor.failed", {"reason": repr(exc)})
            self._rollback(result, f"auditor-raised:{exc!r}")
            return result
        result.why = why
        self.event_log.emit("auditor", "auditor.signed", why.model_dump(mode="json"))

        if why.escalations:
            self._rollback(result, f"auditor-escalated:{why.escalations}")
            return result

        # P8 mitigation: scan the auditor's why-doc summary BEFORE we let
        # it gate promotion. Today the summary is templated by the
        # Coordinator; future iterations will have the LLM produce it.
        why_trip = self.tripwires.scan_text(why.summary)
        if why_trip.fired:
            self.event_log.emit("coordinator", "tripwire.fired", {
                "iteration_id": iteration_id,
                "labels": [f.label for f in why_trip.firings],
                "where": "why_doc",
            })
            self._rollback(result, f"tripwire:{[f.label for f in why_trip.firings]}")
            return result

        # P1+P10 fix: do NOT pre-write PROMOTED candidates. Instead bump
        # the candidate side to VERIFIED (after Verifier passed). The trust
        # transition to PROMOTED happens atomically inside store.promote().
        # (E1: `store` already assigned above the auditor try-except block.)
        try:
            store.mark_verified([e.entry_id for e in candidates])
        except KeyError as exc:
            self.event_log.emit("coordinator", "promote.failed", {"reason": f"mark_verified:{exc}"})
            self._rollback(result, f"mark-verified-failed:{exc}")
            return result

        # F2 mitigation: promote under a single-writer lock with hash
        # precondition. If another thread promoted between why-doc sign and
        # this call, MemoryStore.promote() raises PromotionPreconditionFailure.
        # P4: producer_role goes through to substrate-enforced tier check.
        with self._promotion_lock:
            try:
                promoted = store.promote(
                    [e.entry_id for e in candidates],
                    precondition_hash=why.hash_precondition,
                    why_id=why.why_id,
                    producer_role="librarian",
                )
            except (
                PromotionPreconditionFailure,
                TrustViolation,
                TierConsumerViolation,
                KeyError,
            ) as exc:
                self.event_log.emit("coordinator", "promote.failed", {"reason": str(exc)})
                self._rollback(result, f"promote-failed:{exc}")
                return result

        result.promoted = promoted
        result.outcome = "promoted"
        self.event_log.emit("coordinator", "iter.promoted", {
            "iteration_id": iteration_id,
            "promoted_ids": [e.entry_id for e in promoted],
            "new_live_hash": store.live_hash(),
        })

        # Final tripwire / shutdown check (F11: don't tell agents, just halt).
        if self.tripwires.fired() or self.shutdown.is_halted():
            self.event_log.emit("coordinator", "post.halt", {"reason": "tripwire or shutdown after promote"})

        return result

    def run_continuous(self, frontier_items: list[str], *, target_tier: str = "episodic") -> list[IterationResult]:
        """Run a sequence of iterations, halting on the first HaltSignal.

        For the prototype this is a synchronous loop. The Anthropic scheduler
        (≤25 concurrent threads) would replace this in a real deployment;
        the structure here keeps the same single-iteration contract.
        """
        out: list[IterationResult] = []
        for item in frontier_items:
            try:
                self.shutdown.check()
            except HaltSignal as exc:
                self.event_log.emit("coordinator", "halt", {"reason": str(exc)})
                return out
            res = self.run_iteration(frontier_item=item, target_tier=target_tier)
            out.append(res)
            # Periodic auto-snapshot if requested.
            if (
                self.config.snapshot_every_n_iterations
                and len(out) % self.config.snapshot_every_n_iterations == 0
            ):
                self._write_auto_snapshot(len(out))
        return out

    # ---- internals ------------------------------------------------------

    def _rollback(self, result: IterationResult, reason: str) -> None:
        result.outcome = f"rolled-back:{reason}"
        self.event_log.emit("coordinator", "iter.rolled_back", {
            "iteration_id": result.iteration_id,
            "reason": reason,
        })

    def _tier_mismatch_cleanup(
        self,
        exc: TierMismatch,
        candidates: list[MemoryEntry],
        pre_consolidate_ids: dict[str, set[str]],
        result: IterationResult,
    ) -> None:
        """G2 (cycle-8) cleanup. Brute-walk every tier to find stranded
        candidates this iteration introduced, BUT only discard IDs that
        were NOT present at the pre-consolidate snapshot — so a
        legitimate pre-existing candidate with the same id is preserved
        (cycle-7 F2 regression scenario).

        This combines cycle-7 F2's "don't over-discard" discipline with
        cycle-8 G2's "don't trust the Librarian's tier claim" discipline.
        """
        ALL_TIERS = ("working", "episodic", "semantic", "procedural", "causal")
        discarded: list[tuple[str, str]] = []
        for entry in candidates:
            for tier_name in ALL_TIERS:
                tier_store = self.hierarchy.tier(tier_name)
                if not tier_store.has_candidate(entry.entry_id):
                    continue
                if entry.entry_id in pre_consolidate_ids.get(tier_name, set()):
                    # Pre-existing legitimate candidate — leave it alone.
                    continue
                tier_store.discard_candidate(
                    entry.entry_id, reason=f"tier-mismatch:{exc}"
                )
                discarded.append((tier_name, entry.entry_id))
        self.event_log.emit("coordinator", "tier.mismatch", {
            "reason": str(exc),
            "claimed_tier": exc.claimed_tier,
            "target_tier": exc.target_tier,
            "discarded": [{"tier": t, "id": i} for t, i in discarded],
        })
        self._rollback(result, f"tier-mismatch:{exc}")

    def _write_auto_snapshot(self, iter_count: int) -> None:
        path = self.config.brain_root / "snapshots" / f"auto-{iter_count:04d}.md"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            f"# Auto snapshot at iteration {iter_count}\n\n"
            f"event_log seq: {self.event_log.seq()}\n"
            f"latest hash: {self.event_log.latest_hash()}\n"
            f"live store hashes:\n"
            + "\n".join(f"  - {tier}: {self.hierarchy.tier(tier).live_hash()}" for tier in
                       ("working", "episodic", "semantic", "procedural", "causal"))
            + f"\n\ntripwires fired: {len(self.tripwires.history())}\n",
            encoding="utf-8",
        )


def _config_for_log(cfg: CSISConfig) -> dict:
    return {
        "backend": cfg.backend,
        "builder_checkpoint": cfg.builder_checkpoint,
        "auditor_checkpoint": cfg.auditor_checkpoint,
        "phase_ceiling": cfg.phase_ceiling.name,
        "max_threads": cfg.max_threads,
    }
