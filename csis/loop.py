"""Continuous loop entry point — runnable, offline.

`python -m csis` or `python -m csis.loop` will run a short demo using the
MockBackend with scripted responses, end-to-end through the 8-step loop
on a single frontier item, then print a one-line outcome and exit 0.

This is the "make sure it could run" requirement. A real deployment would
swap MockBackend for AnthropicBackend, point at a real environment, and
drive frontier items from the curiosity module.
"""
from __future__ import annotations

import sys
from pathlib import Path

from csis.agents.coordinator import Coordinator
from csis.backends.mock import MockBackend
from csis.budget import BudgetTracker, _BackendTracker
from csis.config import CSISConfig


def _script_demo_backend(cfg: CSISConfig) -> MockBackend:
    """Wire up a mock backend that produces well-formed responses for every role."""
    backend = MockBackend()

    # F1: model_id must differ across checkpoints in our identity dict.
    backend.set_model_id(cfg.builder_checkpoint, "mock-opus-like")
    backend.set_model_id(cfg.auditor_checkpoint, "mock-sonnet-like")
    backend.set_tools(cfg.builder_checkpoint, ["sandbox.execute", "web_search"])
    backend.set_tools(cfg.auditor_checkpoint, ["pinned_graders", "critic_falsify"])

    backend.script(
        "researcher", cfg.builder_checkpoint,
        '{"plan_id":"p-demo","frontier_item":"demo",'
        '"hypothesis":"a small patch passes the mock graders",'
        '"falsification_condition":"any pinned grader fails",'
        '"budget":{"time_s":60,"tokens":5000},'
        '"tier":"T0","tool_calls_planned":[]}'
    )
    backend.script(
        "builder", cfg.builder_checkpoint,
        '{"artifact_id":"a-demo","plan_id":"p-demo","kind":"patch",'
        '"body":"# demo patch\\nprint(\\"hello\\")\\n",'
        '"body_hash":"sha256:placeholder","sandbox_logs":[],'
        '"extra":{"tests_pass":true,"lint_clean":true,"type_clean":true,"coverage_delta":0.01,"perf_ratio":1.0}}'
    )
    backend.script(
        "critic", cfg.auditor_checkpoint,
        '[{"attempt":"could the diff touch a test","falsified":false,"detail":"no test paths in body"},'
        '{"attempt":"could perf regress","falsified":false,"detail":"perf_ratio reported 1.0"},'
        '{"attempt":"is coverage moving backward","falsified":false,"detail":"coverage_delta +0.01"}]'
    )
    return backend


def main(argv: list[str] | None = None) -> int:
    argv = list(argv or sys.argv[1:])
    # Default to a tmp-style run under repo root so the demo doesn't
    # pollute a hypothetical operator's state.
    cfg = CSISConfig()
    raw_backend = _script_demo_backend(cfg)
    # H1 (cycle-9): Coordinator demands a _BackendTracker. Mock demo
    # uses a no-cap tracker so the wrap-site invariant is uniform.
    backend = _BackendTracker(
        raw_backend,
        BudgetTracker(path=cfg.brain_root / "loop.budget.json"),
    )
    coord = Coordinator(config=cfg, backend=backend)
    # H8 (cycle-9): explicit salt=None — no salt in this static demo,
    # but the explicitness keeps forensic-replay contracts consistent.
    res = coord.run_iteration(frontier_item="demo frontier", salt=None)
    print(
        f"[csis.loop] iteration {res.iteration_id} -> {res.outcome} "
        f"(promoted {len(res.promoted)} entries, "
        f"event_log seq={coord.event_log.seq()})"
    )
    return 0 if res.outcome == "promoted" else 1


if __name__ == "__main__":
    sys.exit(main())
