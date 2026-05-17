"""24/7 daemon runner.

Long-lived process. Each tick:
  1. Check the stop file. Exists -> graceful shutdown.
  2. Check the budget. Exceeded -> sleep until next window.
  3. Ask Curiosity for the next frontier item.
  4. Run one Coordinator iteration.
  5. Update outcome history; tell Curiosity what happened.
  6. Touch the heartbeat file (external watchdog can detect staleness).
  7. Every N iterations: write an auto-snapshot to brain/snapshots/.
  8. Sleep a short interval to avoid hammering the LLM.

Safety:
  - Stop file (STOP in repo root) is checked every tick and halts gracefully.
  - Budget: max_iterations_per_hour caps work.
  - Hard halt: ShutdownToken (also wired to Ctrl-C).
  - All exceptions inside an iteration are caught and emitted as events;
    the daemon does NOT die on a single failed iteration.

Run:
  python -m csis.daemon                    # default config, mock backend
  python -m csis.daemon --max-iter 100     # finite run
  python -m csis.daemon --backend anthropic  # real backend (requires API key)
"""
from __future__ import annotations

import argparse
import json
import signal
import sys
import threading
import time
import traceback
from collections import deque
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Optional

from csis.agents.coordinator import Coordinator, IterationResult
from csis.backends.base import LLMBackend
from csis.backends.mock import MockBackend
from csis.budget import BudgetCapExceeded, BudgetTracker, _BackendTracker
from csis.config import CSISConfig
from csis.curiosity import Curiosity, FrontierItem
from csis.improvement.skill_library import consolidate_skill, is_skill_artifact, stats as skill_stats
from csis.safety.fuzzer import SafetyFuzzer


STOP_FILE_NAME = "STOP"


@dataclass
class DaemonBudget:
    max_iterations_per_hour: int = 60
    sleep_between_iterations_s: float = 1.0
    snapshot_every_n_iterations: int = 25
    heartbeat_every_n_iterations: int = 1
    # F7 (cycle-7) fix: dedupe fuzz_false_positives events so a daemon
    # that hits the same stable set of false-positive corpus rows on
    # every snapshot doesn't spam the event log 5760+ times per day.
    # When the failure signature is unchanged from last emission, we
    # skip; the next change emits.
    fuzz_event_dedupe: bool = True


@dataclass
class DaemonStats:
    started_at: float = field(default_factory=time.time)
    iterations_total: int = 0
    iterations_promoted: int = 0
    iterations_rolled_back: int = 0
    rollback_reason_counts: dict[str, int] = field(default_factory=dict)
    last_iteration_at: float = 0.0
    skills_promoted: int = 0
    # Sliding window of iteration timestamps for rate-limit calculations.
    _recent_times: deque[float] = field(default_factory=lambda: deque(maxlen=1000))

    def record(self, res: IterationResult) -> None:
        self.iterations_total += 1
        self.last_iteration_at = time.time()
        self._recent_times.append(self.last_iteration_at)
        if res.outcome == "promoted":
            self.iterations_promoted += 1
        else:
            self.iterations_rolled_back += 1
            # Bucket rollback reason to the first colon-delimited segment.
            reason_key = res.outcome.split(":", 2)[1] if ":" in res.outcome else res.outcome
            self.rollback_reason_counts[reason_key] = self.rollback_reason_counts.get(reason_key, 0) + 1

    def iterations_in_last_hour(self) -> int:
        cutoff = time.time() - 3600
        return sum(1 for t in self._recent_times if t >= cutoff)

    def to_dict(self) -> dict:
        d = {
            "started_at": self.started_at,
            "iterations_total": self.iterations_total,
            "iterations_promoted": self.iterations_promoted,
            "iterations_rolled_back": self.iterations_rolled_back,
            "rollback_reason_counts": dict(self.rollback_reason_counts),
            "last_iteration_at": self.last_iteration_at,
            "skills_promoted": self.skills_promoted,
            "uptime_s": time.time() - self.started_at,
            "iterations_in_last_hour": self.iterations_in_last_hour(),
        }
        return d


class Daemon:
    def __init__(
        self,
        *,
        config: CSISConfig,
        backend: LLMBackend,
        budget: DaemonBudget | None = None,
        max_total_iterations: Optional[int] = None,
        domain: "object | None" = None,
        max_cost_per_day_usd: float | None = None,
        max_cost_per_call_usd: float | None = None,
    ) -> None:
        self.config = config
        # Wrap the backend in the budget tracker so EVERY complete() call
        # (Researcher, Builder, Critic, Verifier, Auditor — all of them)
        # is metered against the per-day cap.
        self.budget_tracker = BudgetTracker(
            path=config.brain_root / "daemon.budget.json",
            max_cost_per_day_usd=max_cost_per_day_usd,
            max_cost_per_call_usd=max_cost_per_call_usd,
        )
        wrapped = _BackendTracker(backend, self.budget_tracker)
        # Cycle-8 G1: wrap-site exact-type check (defeats subclass-shaped
        # bypasses). Cycle-9 H1+H3: Coordinator demands a _BackendTracker
        # too (the real chokepoint), and the property setter blocks
        # post-init swap. The Daemon's check is now belt-and-suspenders.
        if type(wrapped) is not _BackendTracker:
            raise TypeError(
                f"daemon backend must be exactly _BackendTracker, "
                f"not a subclass or impostor. got: {type(wrapped).__name__!r}"
            )
        self._backend = wrapped
        self.budget = budget or DaemonBudget()
        self.max_total_iterations = max_total_iterations
        # If a Domain is provided, swap in its grader registry + curiosity.
        registry = None
        curiosity = Curiosity()
        if domain is not None:
            registry = domain.graders()
            curiosity = domain.curiosity()
        self.coord = Coordinator(config=config, backend=self._backend, registry=registry)
        self.curiosity = curiosity
        self.domain = domain
        self.stats = DaemonStats()
        # Synthesis #4: continuous safety-pattern fuzzer.
        # Cycle-4 C10 fix: the fuzzer sees the SAME constitution + tripwires
        # the Coordinator uses, so operator-added patterns are validated too.
        self.fuzzer = SafetyFuzzer(
            constitution=self.coord.constitution,
            tripwires=self.coord.tripwires,
        )
        # F7: track the last fuzz-false-positive signature so we don't
        # emit a duplicate event every snapshot when the failure set is
        # stable.
        self._last_false_positive_signature: tuple[str, ...] = ()
        self._heartbeat_path = config.brain_root / "daemon.heartbeat"
        self._stats_path = config.brain_root / "daemon.stats.json"
        self._stop_file = Path(config.event_log_path).parent.parent / STOP_FILE_NAME
        self._stopped = threading.Event()

    # H3 (cycle-9): backend is a property + setter. Post-init reassignment
    # must go through the setter, which re-validates exact-type. Defeats
    # `d.backend = EvilBackend()` and the subclass-overrides-__init__
    # attack from the cycle-9 G1G3 red team.
    @property
    def backend(self):
        return self._backend

    @backend.setter
    def backend(self, value):
        if type(value) is not _BackendTracker:
            raise TypeError(
                f"Daemon.backend cannot be reassigned to a non-_BackendTracker "
                f"value. Got: {type(value).__name__!r}."
            )
        self._backend = value

    # ---- lifecycle ------------------------------------------------------

    def run_forever(self) -> int:
        self._install_signal_handlers()
        self.coord.event_log.emit("coordinator", "daemon.start", {
            "backend": self.backend.name,
            "max_iter_per_hour": self.budget.max_iterations_per_hour,
            "max_total": self.max_total_iterations,
        })
        self._write_heartbeat()
        try:
            while not self._should_stop():
                if not self._budget_allows_now():
                    self._sleep_to_next_window()
                    continue
                try:
                    self._tick()
                except KeyboardInterrupt:
                    raise
                except BudgetCapExceeded as exc:
                    self.coord.event_log.emit("coordinator", "daemon.budget_cap", {
                        "reason": str(exc),
                        "today": self.budget_tracker.snapshot()["today"],
                    })
                    # Halt; the next while-loop check exits cleanly.
                    self.stop(reason=f"budget-cap:{exc}")
                except Exception as exc:  # noqa: BLE001 — daemon must survive any single failure
                    tb = traceback.format_exc(limit=4)
                    self.coord.event_log.emit("coordinator", "daemon.exception", {
                        "error": repr(exc),
                        "traceback": tb,
                    })
                # Even on exception, sleep so we don't hot-loop a bug.
                if not self._stopped.wait(self.budget.sleep_between_iterations_s):
                    continue
        except KeyboardInterrupt:
            pass
        finally:
            self.coord.event_log.emit("coordinator", "daemon.stop", self.stats.to_dict())
            self._write_stats()
        return 0

    def stop(self, reason: str = "operator") -> None:
        self.coord.shutdown.halt(reason)
        self._stopped.set()

    # ---- one tick -------------------------------------------------------

    def _tick(self) -> None:
        item: FrontierItem = self.curiosity.next(self.coord.hierarchy)
        # F4 (cycle-7) fix: pass salt explicitly so the iter.start event
        # records the authoritative value from FrontierItem rather than
        # regex-extracting a possibly-misleading substring.
        res = self.coord.run_iteration(frontier_item=item.text, salt=item.salt)
        self.stats.record(res)

        if res.outcome == "promoted":
            self.curiosity.record_promoted(item.text)
            # Skill-library accumulation path.
            if res.artifact and is_skill_artifact(res.artifact) and res.cert and res.cert.passed:
                try:
                    skill_entries = consolidate_skill(
                        hierarchy=self.coord.hierarchy,
                        tier_guard=self.coord.tier_guard,
                        plan=res.plan,  # type: ignore[arg-type]
                        artifact=res.artifact,
                        cert=res.cert,
                    )
                    # Promote skill entries through the substrate (P4-safe).
                    store = self.coord.hierarchy.tier("procedural")
                    store.mark_verified([e.entry_id for e in skill_entries])
                    promoted = store.promote(
                        [e.entry_id for e in skill_entries],
                        precondition_hash=store.live_hash(),
                        why_id=res.why.why_id if res.why else "no-why",
                        producer_role="builder",
                    )
                    self.stats.skills_promoted += len(promoted)
                    self.coord.event_log.emit("coordinator", "skill.promoted", {
                        "skill_ids": [e.entry_id for e in promoted],
                    })
                except Exception as exc:  # noqa: BLE001
                    self.coord.event_log.emit("coordinator", "skill.failed", {"error": repr(exc)})
        else:
            self.curiosity.record_rollback(item.text, res.outcome)

        if self.stats.iterations_total % self.budget.heartbeat_every_n_iterations == 0:
            self._write_heartbeat()
        if self.stats.iterations_total % self.budget.snapshot_every_n_iterations == 0:
            self._write_snapshot()
            self._write_stats()
            # Synthesis #4 + cycle-5 D1 refinement: at every snapshot
            # boundary, run the safety fuzz pass. Distinguish two
            # failure modes:
            #   - SECURITY REGRESSION (blocked → allowed): halt the daemon.
            #   - FALSE POSITIVE (allowed → blocked): warn-only event.
            # The benign corpus rows from cycle-5 D1 generate the latter
            # when patterns over-catch; halting on those is a self-DoS.
            rep = self.fuzzer.check()
            if rep.has_security_regression:
                self.coord.event_log.emit("coordinator", "safety.fuzz_failure", {
                    "cases_checked": rep.cases_checked,
                    "security_regressions": rep.security_regressions,
                    "false_positives": rep.false_positives,
                })
                self.stop(reason=f"safety-fuzz-failure:{len(rep.security_regressions)}")
            elif rep.false_positives:
                # G6 (cycle-8) fix: dedupe signature now includes both
                # label AND short text-hash. Cycle-7 F7 used labels only,
                # which collapsed two different false-positive texts that
                # happened to share a label into one signature and
                # suppressed the second.
                import hashlib as _hashlib
                signature = tuple(sorted(
                    (fp["label"], _hashlib.sha256(fp["text"].encode("utf-8")).hexdigest()[:16])
                    for fp in rep.false_positives
                ))
                if (not self.budget.fuzz_event_dedupe) or signature != self._last_false_positive_signature:
                    self.coord.event_log.emit("coordinator", "safety.fuzz_false_positives", {
                        "cases_checked": rep.cases_checked,
                        "false_positives": rep.false_positives,
                    })
                    self._last_false_positive_signature = signature
            else:
                # H9 (cycle-9): reset the dedupe signature on green snapshots
                # so an FP set that disappears then recurs emits a fresh
                # event. Cycle-8 G6 dedupe was correct for "FP set stable
                # across snapshots" but silently treated FP=A → ok → FP=A
                # as a no-change (same signature as last non-green).
                self._last_false_positive_signature = ()
                self.coord.event_log.emit("coordinator", "safety.fuzz_ok", {
                    "cases_checked": rep.cases_checked,
                })

    # ---- budget / pacing ------------------------------------------------

    def _budget_allows_now(self) -> bool:
        if self.budget.max_iterations_per_hour <= 0:
            return True
        return self.stats.iterations_in_last_hour() < self.budget.max_iterations_per_hour

    def _sleep_to_next_window(self) -> None:
        # Sleep until the oldest recent_times falls out of the 1h window.
        if not self.stats._recent_times:
            return
        oldest = min(self.stats._recent_times)
        wait_s = max(1.0, (oldest + 3600) - time.time())
        # Cap each sleep at 60s so stop file is checked often.
        self._stopped.wait(min(wait_s, 60.0))

    # ---- stop / heartbeat / snapshot -----------------------------------

    def _should_stop(self) -> bool:
        if self._stopped.is_set():
            return True
        if self._stop_file.exists():
            try:
                reason = self._stop_file.read_text(encoding="utf-8").strip() or "stop-file"
            except Exception:
                reason = "stop-file"
            self.coord.event_log.emit("coordinator", "daemon.stop_file_seen", {"reason": reason})
            return True
        if self.max_total_iterations and self.stats.iterations_total >= self.max_total_iterations:
            self.coord.event_log.emit("coordinator", "daemon.max_iter_reached", {
                "max": self.max_total_iterations,
            })
            return True
        return False

    def _write_heartbeat(self) -> None:
        self._heartbeat_path.parent.mkdir(parents=True, exist_ok=True)
        self._heartbeat_path.write_text(
            json.dumps({
                "ts": time.time(),
                "iterations_total": self.stats.iterations_total,
                "iterations_promoted": self.stats.iterations_promoted,
                "iterations_rolled_back": self.stats.iterations_rolled_back,
                "skills_promoted": self.stats.skills_promoted,
                "backend": self.backend.name,
            }),
            encoding="utf-8",
        )

    def _write_stats(self) -> None:
        self._stats_path.parent.mkdir(parents=True, exist_ok=True)
        skills = skill_stats(self.coord.hierarchy)
        out = self.stats.to_dict()
        out["skill_library"] = asdict(skills)
        self._stats_path.write_text(json.dumps(out, indent=2), encoding="utf-8")

    def _write_snapshot(self) -> None:
        path = self.config.brain_root / "snapshots" / f"auto-{self.stats.iterations_total:06d}.md"
        path.parent.mkdir(parents=True, exist_ok=True)
        ok, reason = self.coord.event_log.verify_chain()
        path.write_text(
            f"# Daemon auto-snapshot — iteration {self.stats.iterations_total}\n\n"
            f"started_at: {time.ctime(self.stats.started_at)}\n"
            f"snapshot_at: {time.ctime()}\n"
            f"uptime: {int(time.time() - self.stats.started_at)}s\n"
            f"backend: {self.backend.name}\n\n"
            f"## Stats\n\n"
            f"- total iterations: {self.stats.iterations_total}\n"
            f"- promoted: {self.stats.iterations_promoted}\n"
            f"- rolled back: {self.stats.iterations_rolled_back}\n"
            f"- skills promoted: {self.stats.skills_promoted}\n"
            f"- iterations in last hour: {self.stats.iterations_in_last_hour()}\n"
            f"- event log seq: {self.coord.event_log.seq()}\n"
            f"- chain integrity: {'OK' if ok else f'BROKEN: {reason}'}\n\n"
            f"## Rollback reason breakdown\n\n"
            + "\n".join(f"- {k}: {v}" for k, v in sorted(self.stats.rollback_reason_counts.items()))
            + "\n",
            encoding="utf-8",
        )

    # ---- signals --------------------------------------------------------

    def _install_signal_handlers(self) -> None:
        def _handle(signum, frame):  # noqa: ARG001
            self.stop(reason=f"signal-{signum}")
        try:
            signal.signal(signal.SIGINT, _handle)
            signal.signal(signal.SIGTERM, _handle)
        except (ValueError, AttributeError):
            # Not in main thread, or signal unsupported on platform.
            pass


# ---- backend selection + entry point -----------------------------------


def _select_backend(name: str, config: CSISConfig) -> LLMBackend:
    if name == "anthropic":
        from csis.backends.anthropic import AnthropicBackend
        return AnthropicBackend()
    backend = MockBackend()
    # Wire the mock so it produces well-formed responses regardless of
    # what the curiosity module asks. The responses don't need to vary
    # per frontier item to demonstrate the architecture.
    backend.set_model_id(config.builder_checkpoint, "mock-opus")
    backend.set_model_id(config.auditor_checkpoint, "mock-sonnet")
    backend.set_tools(config.builder_checkpoint, ["sandbox.execute", "web_search"])
    backend.set_tools(config.auditor_checkpoint, ["pinned_graders"])
    def _researcher(req):
        # Use the prompt prefix to derive a deterministic but varied plan.
        text_seed = abs(hash(req.prompt)) % 100
        is_skill = (text_seed % 5) == 0  # every 5th plan proposes a skill
        return json.dumps({
            "plan_id": f"p-{text_seed:04d}",
            "frontier_item": "auto",
            "hypothesis": f"daemon iteration seed={text_seed}, candidate skill={is_skill}",
            "falsification_condition": "any pinned grader fails",
            "budget": {"time_s": 30, "tokens": 2000},
            "tier": "T0",
            "tool_calls_planned": [],
        })

    def _builder(req):
        text_seed = abs(hash(req.prompt)) % 100
        # 1 in 8 iterations: induce a perf regression so the verifier rolls back.
        perf_ratio = 1.4 if (text_seed % 8) == 0 else 1.01
        is_skill = (text_seed % 5) == 0
        return json.dumps({
            "artifact_id": f"a-{text_seed:04d}",
            "plan_id": f"p-{text_seed:04d}",
            "kind": "skill" if is_skill else "patch",
            "body": (
                "# daemon-produced skill\n"
                f"def helper_{text_seed}(): pass\n"
            ) if is_skill else (
                "# daemon-produced patch\n"
                f"# small change {text_seed}\n"
            ),
            "body_hash": f"sha256:{text_seed:064d}",
            "sandbox_logs": [],
            "extra": {
                "tests_pass": True,
                "lint_clean": True,
                "type_clean": True,
                "coverage_delta": 0.0,
                "perf_ratio": perf_ratio,
                "is_skill": is_skill,
            },
        })

    def _critic(req):
        return json.dumps([
            {"attempt": "check tests", "falsified": False},
            {"attempt": "check perf", "falsified": False},
            {"attempt": "check coverage", "falsified": False},
        ])

    backend.script("researcher", config.builder_checkpoint, _researcher)
    backend.script("builder", config.builder_checkpoint, _builder)
    backend.script("critic", config.auditor_checkpoint, _critic)
    return backend


def _select_domain(name: str | None, *, repo_path: str | None):
    if name is None or name == "" or name == "none":
        return None
    if name == "pr_maintenance":
        from csis.domains.pr_maintenance import PRMaintenanceDomain
        if not repo_path:
            raise SystemExit("--domain pr_maintenance requires --repo-path")
        return PRMaintenanceDomain(repo_path)
    if name == "self_improve":
        from csis.domains.self_improve import SelfImproveDomain
        return SelfImproveDomain()
    if name == "lean_math":
        from csis.domains.lean_math import LeanMathDomain
        return LeanMathDomain(graceful_fallback=True)
    raise SystemExit(f"unknown domain: {name}")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="CSIS 24/7 daemon runner")
    parser.add_argument("--backend", default=None, help="mock (default) or anthropic")
    parser.add_argument("--max-iter", type=int, default=None,
                        help="stop after this many iterations (default: unlimited)")
    parser.add_argument("--rate-per-hour", type=int, default=60,
                        help="max iterations per rolling hour (default 60)")
    parser.add_argument("--sleep-s", type=float, default=1.0,
                        help="sleep between iterations (default 1.0s)")
    parser.add_argument("--snapshot-every", type=int, default=25,
                        help="auto-snapshot every N iterations (default 25)")
    parser.add_argument("--domain", default=None,
                        help="optional: pr_maintenance | self_improve | lean_math (default: none, uses mock graders)")
    parser.add_argument("--repo-path", default=None,
                        help="repo path for --domain pr_maintenance")
    parser.add_argument("--max-cost-per-day-usd", type=float, default=None,
                        help="cumulative spend cap per UTC day. Daemon halts when reached (default: no cap)")
    parser.add_argument("--max-cost-per-call-usd", type=float, default=None,
                        help="hard ceiling on any single LLM call's estimated cost (default: no ceiling)")
    args = parser.parse_args(argv)

    cfg = CSISConfig()
    backend_name = args.backend or cfg.backend
    backend = _select_backend(backend_name, cfg)
    budget = DaemonBudget(
        max_iterations_per_hour=args.rate_per_hour,
        sleep_between_iterations_s=args.sleep_s,
        snapshot_every_n_iterations=args.snapshot_every,
    )
    domain = _select_domain(args.domain, repo_path=args.repo_path)
    if domain is not None:
        ready = domain.can_run()
        if not ready.ready:
            print(f"[csis.daemon] domain={args.domain} not ready: {ready.reason}", file=sys.stderr)
            return 2
        print(f"[csis.daemon] domain ready: {domain.describe()} ({ready.reason})")

    daemon = Daemon(
        config=cfg,
        backend=backend,
        budget=budget,
        max_total_iterations=args.max_iter,
        domain=domain,
        max_cost_per_day_usd=args.max_cost_per_day_usd,
        max_cost_per_call_usd=args.max_cost_per_call_usd,
    )
    print(f"[csis.daemon] starting · backend={backend_name} · max-iter={args.max_iter or 'unlimited'} "
          f"· rate={args.rate_per_hour}/h · domain={args.domain or 'none'} "
          f"· max-cost/day={('$' + str(args.max_cost_per_day_usd)) if args.max_cost_per_day_usd else 'none'} "
          f"· stop file = {daemon._stop_file}")
    return daemon.run_forever()


if __name__ == "__main__":
    sys.exit(main())
