"""On-demand finite real-backend run.

Use when you want to spend a fixed amount of LLM budget on a short
burst of real iterations, then exit. Pairs naturally with a mock daemon
running 24/7 in the background: the mock keeps the architecture warm,
this burst does real work when you want it.

Examples:
    # 10 real iterations against the CSIS codebase itself.
    python scripts/burst.py --iters 10 --domain self_improve

    # 5 real iterations against a target git repo.
    python scripts/burst.py --iters 5 --domain pr_maintenance --repo-path C:/path/to/repo

    # 3 real iterations on Lean (graceful fallback if Lean not installed).
    python scripts/burst.py --iters 3 --domain lean_math

    # 1 real iteration with no domain (mock-grader sanity check).
    python scripts/burst.py --iters 1

Safety:
  - Defaults to backend=anthropic. Pass --backend mock to test plumbing.
  - --max-cost-usd $X estimates spend post-hoc from token counts; if
    exceeded mid-burst, the next iteration is skipped and the burst
    exits cleanly. Estimate is rough (Phase-0 doesn't read pricing live).
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parent.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from csis.agents.coordinator import Coordinator  # noqa: E402
from csis.budget import BudgetTracker, _BackendTracker  # noqa: E402
from csis.config import CSISConfig  # noqa: E402
from csis.curiosity import Curiosity  # noqa: E402
from csis.daemon import _select_backend, _select_domain  # noqa: E402


# Very rough USD-per-1k-tokens defaults (Phase-0; refresh from billing).
_PRICE_PER_1K = {
    "claude-opus-4-7": {"in": 0.015, "out": 0.075},
    "claude-sonnet-4-6": {"in": 0.003, "out": 0.015},
    "mock-opus-like": {"in": 0.0, "out": 0.0},
    "mock-sonnet-like": {"in": 0.0, "out": 0.0},
    "mock-opus": {"in": 0.0, "out": 0.0},
    "mock-sonnet": {"in": 0.0, "out": 0.0},
}


def _estimate_cost(backend, calls) -> float:
    """Rough cost estimate. Phase-0: assume ~1 token / 4 chars for input,
    and a flat 800-token output assumption per call (mid-range for our
    short structured prompts). Real billing will differ."""
    total = 0.0
    for call in calls:
        ident = backend.checkpoint_identity(call.checkpoint_id)
        model_id = ident.get("model_id", call.checkpoint_id)
        prices = _PRICE_PER_1K.get(model_id, {"in": 0.015, "out": 0.075})
        tokens_in = len(call.prompt) / 4.0
        tokens_out = 800.0
        total += (tokens_in / 1000.0) * prices["in"]
        total += (tokens_out / 1000.0) * prices["out"]
    return total


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--iters", type=int, required=True, help="number of iterations to run")
    parser.add_argument("--backend", default="anthropic", help="anthropic (default) or mock")
    parser.add_argument("--domain", default=None, help="pr_maintenance | self_improve | lean_math (default: none)")
    parser.add_argument("--repo-path", default=None, help="for --domain pr_maintenance")
    parser.add_argument("--max-cost-usd", type=float, default=5.0,
                        help="hard ceiling on rough cost estimate (default $5)")
    parser.add_argument("--sleep-s", type=float, default=2.0,
                        help="sleep between iterations (default 2.0s)")
    parser.add_argument("--ledger-out", default=None,
                        help="path to a markdown file capturing a publication-ready "
                             "summary of this burst (per-iteration outcome, cost, "
                             "cert pass/fail, why-doc IDs). Suitable for committing "
                             "to brain/snapshots/.")
    args = parser.parse_args(argv)

    cfg = CSISConfig()
    raw_backend = _select_backend(args.backend, cfg)
    # H1 (cycle-9): Coordinator demands a _BackendTracker. Wrap with a
    # per-burst BudgetTracker so even mock runs go through the metering
    # path — and so `--backend anthropic` (the default) can't bypass the
    # day cap by skipping the wrap site as cycle-8 G1 allowed.
    burst_tracker = BudgetTracker(
        path=cfg.brain_root / "burst.budget.json",
        max_cost_per_day_usd=args.max_cost_usd,
    )
    backend = _BackendTracker(raw_backend, burst_tracker)
    domain = _select_domain(args.domain, repo_path=args.repo_path)

    registry = domain.graders() if domain else None
    curiosity = domain.curiosity() if domain else Curiosity()
    coord = Coordinator(config=cfg, backend=backend, registry=registry)

    print(f"[burst] backend={args.backend} domain={args.domain or 'none'} iters={args.iters} "
          f"max-cost=${args.max_cost_usd}")
    if domain is not None:
        ready = domain.can_run()
        print(f"[burst] domain ready: {ready.ready} | {ready.reason}")
        if not ready.ready:
            return 2

    started = time.time()
    started_iso = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
    promoted = 0
    rolled_back = 0
    ledger_rows: list[dict] = []
    for i in range(args.iters):
        # H1 (cycle-9): cost ceiling check now reads from the authoritative
        # BudgetTracker rather than `backend.calls()`. The previous version
        # used `hasattr(backend, 'calls')` which was False on the wrapped
        # _BackendTracker AND on AnthropicBackend, silently skipping the
        # ceiling entirely on real runs (the cycle-8 G1 escape).
        cost_so_far = burst_tracker.today_cost_usd()
        if cost_so_far >= args.max_cost_usd:
            print(f"[burst] cost ceiling reached: ${cost_so_far:.4f} >= ${args.max_cost_usd}; stopping early")
            break

        item = curiosity.next(coord.hierarchy)
        print(f"[burst] iter {i+1}/{args.iters} · frontier='{item.text[:60]}...'")
        cost_before = burst_tracker.today_cost_usd()
        # G5 (cycle-8) fix: pass salt explicitly so iter.start records
        # the authoritative salt for forensic replay; cycle-7 F4
        # established the parameter but burst.py hadn't been updated.
        res = coord.run_iteration(frontier_item=item.text, salt=item.salt)
        cost_after = burst_tracker.today_cost_usd()
        if res.outcome == "promoted":
            promoted += 1
            curiosity.record_promoted(item.text)
            print(f"  -> PROMOTED ({len(res.promoted)} entries)")
        else:
            rolled_back += 1
            curiosity.record_rollback(item.text, res.outcome)
            print(f"  -> {res.outcome}")
        # Ledger row capture (independent of stdout so it survives terminal scroll).
        ledger_rows.append({
            "iteration_id": res.iteration_id,
            "frontier": item.text[:120],
            "salt": item.salt,
            "source": getattr(item, "source", "unknown"),
            "outcome": res.outcome,
            "promoted_count": len(res.promoted),
            "cert_passed": (res.cert.passed if res.cert else None),
            "grader_results": (
                [{"grader": g.grader, "passed": g.passed, "detail": g.detail[:80]}
                 for g in res.cert.grader_results]
                if res.cert else []
            ),
            "critic_attempts": (
                len(res.cert.critic_findings) if res.cert else 0
            ),
            "why_id": (res.why.why_id if res.why else None),
            "cost_usd": round(cost_after - cost_before, 6),
        })
        if args.sleep_s > 0:
            time.sleep(args.sleep_s)

    elapsed = time.time() - started
    cost = burst_tracker.today_cost_usd()
    print()
    print(f"[burst] DONE in {elapsed:.1f}s · promoted={promoted} rolled_back={rolled_back} "
          f"· billed_cost=${cost:.4f}")

    if args.ledger_out:
        _write_ledger(
            path=Path(args.ledger_out),
            args=args,
            started_iso=started_iso,
            elapsed_s=elapsed,
            promoted=promoted,
            rolled_back=rolled_back,
            cost=cost,
            rows=ledger_rows,
            cfg=cfg,
        )
        print(f"[burst] ledger written: {args.ledger_out}")
    return 0


def _write_ledger(*, path: Path, args, started_iso: str, elapsed_s: float,
                  promoted: int, rolled_back: int, cost: float,
                  rows: list[dict], cfg: CSISConfig) -> None:
    """Render a publication-ready markdown ledger for this burst run."""
    path.parent.mkdir(parents=True, exist_ok=True)
    lines: list[str] = []
    lines.append(f"# Real-backend burst · {started_iso}")
    lines.append("")
    lines.append(f"- **backend:** `{args.backend}`")
    lines.append(f"- **domain:** `{args.domain or 'none (mock graders)'}`")
    lines.append(f"- **iterations requested:** {args.iters}")
    lines.append(f"- **iterations completed:** {len(rows)}")
    lines.append(f"- **promoted:** {promoted}")
    lines.append(f"- **rolled back:** {rolled_back}")
    lines.append(f"- **elapsed:** {elapsed_s:.1f}s")
    lines.append(f"- **billed cost (USD):** ${cost:.4f}")
    lines.append(f"- **per-iteration cost average:** ${(cost / max(1, len(rows))):.4f}")
    lines.append(f"- **cost ceiling:** ${args.max_cost_usd}")
    lines.append("")
    lines.append("## Per-iteration ledger")
    lines.append("")
    lines.append("| # | outcome | cost | cert | graders pass | critic | frontier (truncated) | why-doc |")
    lines.append("|---:|---|---:|---|---|---:|---|---|")
    for i, row in enumerate(rows, 1):
        outcome = row["outcome"]
        cert_passed = row.get("cert_passed")
        cert_str = ("✓" if cert_passed is True else ("✗" if cert_passed is False else "—"))
        graders = row.get("grader_results", [])
        if graders:
            passed_n = sum(1 for g in graders if g["passed"])
            graders_str = f"{passed_n}/{len(graders)}"
        else:
            graders_str = "—"
        why = row.get("why_id") or "—"
        frontier_short = row["frontier"].replace("|", "\\|")
        lines.append(
            f"| {i} | `{outcome}` | ${row['cost_usd']:.4f} | {cert_str} "
            f"| {graders_str} | {row['critic_attempts']} "
            f"| {frontier_short} | `{why}` |"
        )
    lines.append("")
    # Per-iteration rollback reasons (if any).
    rollbacks = [(i, r["outcome"]) for i, r in enumerate(rows, 1)
                 if r["outcome"].startswith("rolled-back")]
    if rollbacks:
        lines.append("## Rollback reasons")
        lines.append("")
        for i, reason in rollbacks:
            lines.append(f"- **iter {i}:** `{reason}`")
        lines.append("")
    # Final per-iteration grader failure surface (interesting for readers).
    failing = []
    for i, r in enumerate(rows, 1):
        if not r["grader_results"]: continue
        bad = [g["grader"] for g in r["grader_results"] if not g["passed"]]
        if bad:
            failing.append((i, bad))
    if failing:
        lines.append("## Grader failures by iteration")
        lines.append("")
        for i, bad in failing:
            lines.append(f"- **iter {i}:** `{', '.join(bad)}`")
        lines.append("")
    # Event-log + memory pointers so readers can drill in.
    # Render as repo-relative paths so the ledger doesn't leak the absolute
    # OS-local path the operator's box happens to live at.
    def _rel(p: Path) -> str:
        try:
            return str(p.relative_to(_REPO_ROOT)).replace("\\", "/")
        except ValueError:
            return p.name  # outside repo root — at least don't print the full path
    lines.append("## Audit pointers")
    lines.append("")
    lines.append(f"- event log: `{_rel(cfg.event_log_path)}`")
    lines.append(f"- memory store root: `{_rel(cfg.memory_root)}`")
    lines.append(f"- budget tracker: `{_rel(cfg.brain_root / 'burst.budget.json')}`")
    lines.append("")
    lines.append("Every row in the ledger has a corresponding `iter.start` / `iter.promoted` / `iter.rolled_back` event in the chained event log. Replay any iteration with the iteration_id from the corresponding event entries; the WhyDoc carries the hash precondition that gated promotion.")
    lines.append("")
    lines.append("---")
    lines.append("")
    lines.append("Generated by `scripts/burst.py --ledger-out`. Commit this file under `brain/snapshots/` to keep the public cycle trail honest.")

    path.write_text("\n".join(lines), encoding="utf-8")


if __name__ == "__main__":
    sys.exit(main())
