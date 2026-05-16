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
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parent.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from csis.agents.coordinator import Coordinator  # noqa: E402
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
    args = parser.parse_args(argv)

    cfg = CSISConfig()
    backend = _select_backend(args.backend, cfg)
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
    promoted = 0
    rolled_back = 0
    for i in range(args.iters):
        # Cost check before each iteration (skip if over).
        if hasattr(backend, "calls"):
            cost_so_far = _estimate_cost(backend, backend.calls())
            if cost_so_far >= args.max_cost_usd:
                print(f"[burst] cost ceiling reached: ${cost_so_far:.4f} >= ${args.max_cost_usd}; stopping early")
                break

        item = curiosity.next(coord.hierarchy)
        print(f"[burst] iter {i+1}/{args.iters} · frontier='{item.text[:60]}...'")
        res = coord.run_iteration(frontier_item=item.text)
        if res.outcome == "promoted":
            promoted += 1
            curiosity.record_promoted(item.text)
            print(f"  -> PROMOTED ({len(res.promoted)} entries)")
        else:
            rolled_back += 1
            curiosity.record_rollback(item.text, res.outcome)
            print(f"  -> {res.outcome}")
        if args.sleep_s > 0:
            time.sleep(args.sleep_s)

    elapsed = time.time() - started
    cost = _estimate_cost(backend, backend.calls()) if hasattr(backend, "calls") else 0.0
    print()
    print(f"[burst] DONE in {elapsed:.1f}s · promoted={promoted} rolled_back={rolled_back} "
          f"· est_cost=${cost:.4f}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
