# Contributing to CSIS

CSIS is a Phase-0 prototype with strong test discipline and a public critique-fix trail. Contributions are welcome on the same terms the project holds itself to.

## Local setup

```bash
git clone https://github.com/jim4226/CSIS
cd CSIS
pip install pydantic pytest

python -m pytest tests/ -v          # confirm 213 tests pass before changing anything
python -m csis.loop                  # one full iteration end-to-end (mock backend)
```

## How the project actually works

Cycle-driven, not feature-driven. Each cycle:

1. Parallel red-team agents attack the prior cycle's fixes
2. Findings get triaged into `brain/critiques/NN-cycleN-redteam.md` with reproducible `file:line` evidence
3. Fixes land in code with regression tests
4. A snapshot lands in `brain/snapshots/`
5. Cumulative state lands in `brain/BRAIN.html`

If your contribution doesn't fit the cycle model (most don't — they're features, not security findings), no problem. Just follow the conventions below.

## Conventions

- **Type checking**: Pydantic v2 throughout. Add `pydantic.BaseModel` subclasses for any new contract.
- **Tests**: every behavior-changing PR ships with at least one regression test. The cycle history is the proof this is load-bearing — cycle 6 E1 was caused by a fix that landed without a test asserting the *effect*.
- **Imports**: keep `csis.*` imports relative; tests use `from tests._helpers import wrap_for_test` for the cycle-9 H1 `_BackendTracker` requirement.
- **No `--no-verify`**: pre-commit hooks (if you add them) must not be bypassed. The cycle log is the only authority on what's allowed to be deferred.
- **Commit messages**: imperative mood, first line ≤72 chars, body explains *why* (cycle log is the *what*).

## Good first issues

These are tagged `good-first-issue` in the [issue tracker](https://github.com/jim4226/CSIS/issues?q=is%3Aissue+is%3Aopen+label%3A%22good+first+issue%22):

- **Add a local-backend adapter** (`csis/backends/vllm.py` or `csis/backends/llamacpp.py`) — same interface as `csis/backends/anthropic.py` so the system can run on a self-hosted LLM.
- **Add a new tripwire pattern** with regression test — see `csis/safety/tripwires.py:_TRIP_PATTERNS` and the cycle-history pattern in `tests/test_cycle9_fixes.py`.
- **Add a new domain adapter** (`csis/domains/<name>.py`) — must implement `graders()`, `curiosity()`, `can_run()`. The three existing ones (`pr_maintenance`, `self_improve`, `lean_math`) are the reference.
- **Add a new V1 grader** (`csis/verification/graders.py`) — pinned source-hash, deterministic, returns `GraderResult`.
- **Convert a stale `auto-NNNN.md` snapshot to insight** — pick one auto-snapshot from `brain/snapshots/`, identify what it tells us about the system's behavior over time, and write that up in a short markdown file under `brain/observations/`.

## PR process

1. Open an issue first describing what you want to change (small PRs OK without). Discussion lives there.
2. Branch off `main`; never force-push to `main`.
3. PR must include: a regression test, a passing full suite (`python -m pytest tests/ --tb=short`), and a 1-2 line summary in the PR body.
4. Squash on merge.

## What's out of scope (for now)

- Vendor lock-in beyond Anthropic + mock (we accept local-LLM adapters; we don't accept replacing the `_BackendTracker` contract that gates metering)
- Drive-by removals of test coverage
- Changes that bypass safety properties documented in the README without an explicit cycle-style critique + fix loop

## What if you found a security issue?

If it's reproducible against the current `main`, open an issue with the `security` label. If it's load-bearing (could leak secrets, escalate capability past Phase-0 T1, or defeat memory promotion atomicity), email a vague description first to coordinate disclosure — actual reproducer can come after. The cycle log shows the system's prior failure modes; novel ones are worth being careful about.

## License

MIT. Contributions are accepted under the same license.
