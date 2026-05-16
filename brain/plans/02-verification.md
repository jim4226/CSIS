# 02 — Verification & Critic Stack (V1 + V2)

**Scope.** Phase-0 commits to V1 (programmatic graders) and V2 (adversarial critic) only. Cross-checkpoint pinning is mandatory: the Verifier session runs on a different model checkpoint than the Builder. This document specifies the verification stack for both candidate domains — open-source PR maintenance (primary) and formal-math reasoning (alternative) — in enough detail that mock graders can be implemented in the prototype.

---

## 1. Builder Artifact

### 1A. PR maintenance
The Builder emits a `PRArtifact`:
```json
{
  "artifact_kind": "pr_patch",
  "repo": "owner/name",
  "base_sha": "abc123...",
  "diff": "<unified diff text>",
  "rationale": "1-3 paragraphs of why-doc",
  "touched_files": ["src/foo.py", "tests/test_foo.py"],
  "claimed_intent": "fix #1234",
  "build_log_ref": "logs/build-<uuid>.txt"
}
```
The diff is the load-bearing payload; `rationale` and `claimed_intent` feed V2.

### 1B. Formal math
The Builder emits a `ProofArtifact`:
```json
{
  "artifact_kind": "lean_proof",
  "theorem_id": "mathlib.algebra.foo.bar",
  "statement": "theorem bar (n : Nat) : ...",
  "proof": "<Lean 4 proof body>",
  "imports": ["Mathlib.Algebra.Basic"],
  "tactic_count": 47,
  "rationale": "informal sketch of the argument"
}
```

---

## 2. V1 Graders (concrete checks)

### 2A. PR maintenance — 8 graders
Each grader is a pure function `(artifact, repo_snapshot) -> GraderResult`. Pass criteria are binary; numeric thresholds are explicit.

| # | Grader | Pass criterion |
|---|---|---|
| 1 | `tests_pass_grader` | `pytest` (or repo's declared runner) exit code 0 on the **post-patch** working tree; full suite, no skips of tests touching changed files |
| 2 | `tests_unchanged_grader` | The set of tests deleted or marked `@skip` is empty unless `claimed_intent` explicitly says "remove test" |
| 3 | `lint_grader` | `ruff`/`eslint`/repo-declared linter returns 0 new violations vs base_sha |
| 4 | `typecheck_grader` | `mypy --strict` / `tsc --noEmit` returns 0 new errors vs base_sha |
| 5 | `coverage_delta_grader` | Line coverage on touched files ≥ coverage at base_sha; new statements have ≥ 70% coverage |
| 6 | `perf_regression_grader` | Microbench harness on declared hot-paths: p50 latency ≤ 1.10× base_sha; p95 ≤ 1.20× |
| 7 | `diff_scope_grader` | All hunks land in `touched_files`; no edits to `.github/`, `pyproject.toml` test config, or CI files unless `claimed_intent` declares it |
| 8 | `build_grader` | `make` / `cargo build` / package build returns 0; produced artifacts are byte-identical kind to base (no new entrypoints, no removed binaries) |

### 2B. Formal math — 7 graders
| # | Grader | Pass criterion |
|---|---|---|
| 1 | `typechecks_grader` | `lake build` succeeds; the proof file elaborates with no errors |
| 2 | `goal_closed_grader` | After the proof body, no remaining goals (Lean reports `no goals` at proof close) |
| 3 | `no_sorry_grader` | Proof contains zero `sorry`, `admit`, or `native_decide` shortcuts in non-decidable contexts |
| 4 | `no_axiom_leak_grader` | `#print axioms <theorem_id>` lists only the whitelisted base axioms (e.g., `Classical.choice`, `propext`, `Quot.sound`); no new `axiom` declarations introduced |
| 5 | `statement_unchanged_grader` | The theorem's type/statement string-equals the requested target (Builder can't weaken the claim) |
| 6 | `proof_budget_grader` | `tactic_count` ≤ budget (e.g., 200), proof file < 50KB |
| 7 | `dependency_pin_grader` | `imports` are within the declared Mathlib commit; no new top-level imports beyond an allowlist |

---

## 3. V2 Critic — Falsification Prompt Templates

The V2 Critic runs on a **different checkpoint** than the Builder, with read-only access to the artifact, the V1 grader outputs, and the relevant memory store entries (all attached `read_only`). It must emit a structured `FalsificationReport`:
```json
{ "falsification": null | {"category": "...", "evidence": "...", "reproducer": "..."} }
```
Absence (`null`) when V1 passes ⇒ **Verifier Certificate**. Presence ⇒ **Verifier Rejection**.

### 3A. PR maintenance critic prompt (template)
```
You are the V2 Critic. A Builder on checkpoint {builder_ckpt} produced the
attached PR patch claiming to {claimed_intent}. V1 graders {v1_summary}.

Your job is to FALSIFY the claim that this patch is a safe, correct fix.
Search specifically for:
  (a) Tests that were silently weakened (assertion gutted, mock added that
      hides the real failure).
  (b) New code paths exercised by no test (look for uncovered branches in
      touched_files).
  (c) Behavior change beyond claimed_intent (e.g., refactor smuggled into a
      "bug fix"; API surface change).
  (d) Hidden runtime cost not caught by the bench (allocation in hot loop,
      O(n^2) in pre-existing O(n) path).
  (e) Security regression (input no longer sanitized, auth check moved,
      logging of secrets).
  (f) Spec-gaming of any V1 grader (e.g., test pinned to current output
      rather than expected output).

Return JSON: {"falsification": null} if you can find nothing wrong after
honest effort, else {"falsification": {"category": "<a-f>", "evidence":
"<file:line + 1-3 sentence explanation>", "reproducer": "<failing test or
shell command that demonstrates the issue>"}}.

Empty falsification with no analysis is a tripwire. You must produce at
least one attempted-falsification trace even on certify.
```

### 3B. Formal math critic prompt (template)
```
You are the V2 Critic. A Builder on checkpoint {builder_ckpt} produced the
attached Lean proof of {statement}. V1 graders {v1_summary}.

Falsify the claim that this proof establishes the stated theorem. Look for:
  (a) Hypothesis-strengthening (proof uses a tighter precondition than the
      statement actually grants).
  (b) Conclusion-weakening via definitional unfolding tricks.
  (c) Use of an axiom that the project's axiom budget forbids.
  (d) Decidability hand-waves (`decide`/`native_decide` over an
      undecidable or unproven-decidable proposition).
  (e) Import of a theorem from Mathlib that itself depends on a `sorry` in
      the pinned commit (poisoned dependency).
  (f) Statement drift: theorem name matches but type signature was edited
      to be trivially provable.

Return {"falsification": null} or the structured report. Include the exact
tactic line or `#print` query that demonstrates the issue.
```

**Logging rule.** Even on certify, the critic must emit its attempted falsifications (the (a)-(f) probes it ran) into `attempts[]` — empty `attempts[]` is itself a Verifier Rejection.

---

## 4. `VerifierCertificate` Schema

```json
{
  "schema_version": "csis.verifier.v1",
  "certificate_id": "vc-<ulid>",
  "artifact_hash": "sha256:<hex>",
  "artifact_kind": "pr_patch | lean_proof",
  "domain": "pr_maintenance | formal_math",

  "builder": {
    "checkpoint_id": "ckpt:claude-opus-4-7:rev-2026-04-21",
    "actor_id": "builder-<uuid>",
    "session_id": "sess-<ulid>"
  },
  "verifier": {
    "checkpoint_id": "ckpt:claude-sonnet-4-6:rev-2026-03-15",
    "actor_id": "verifier-<uuid>",
    "session_id": "sess-<ulid>"
  },

  "v1_graders": [
    {
      "name": "tests_pass_grader",
      "version": "1.0.3",
      "passed": true,
      "duration_ms": 41200,
      "evidence_hash": "sha256:<log>",
      "exit_code": 0
    }
  ],
  "v1_aggregate": "pass",

  "v2_critic": {
    "prompt_template_hash": "sha256:<hex>",
    "attempts": [
      {"category": "a", "summary": "scanned for weakened assertions", "found": false},
      {"category": "b", "summary": "checked branch coverage of new lines", "found": false}
    ],
    "falsification": null,
    "verdict": "certify | reject"
  },

  "result": "certificate | rejection",
  "signed_at": "2026-05-16T14:33:02Z",
  "signature": "ed25519:<sig over canonical JSON minus signature field>",
  "signer_key_id": "verifier-key-2026-q2"
}
```

**Invariants enforced by the substrate before promotion:**
- `builder.checkpoint_id != verifier.checkpoint_id` (see §5)
- `signed_at` is monotonic vs the session log's last event
- `signature` validates against `signer_key_id` over the canonical-JSON serialization with the `signature` field elided
- `artifact_hash` matches the actual artifact in the candidate store

---

## 5. Cross-Checkpoint Enforcement (`CheckpointID` discipline)

A free-form string like `"mock-alpha"` is unverifiable. CSIS defines a structured `CheckpointID`:

```
ckpt:<family>:<revision>:<role-binding>
   = "ckpt" ":" family ":" revision ":" binding
where:
  family   = identifier matching ^[a-z0-9-]+$         (e.g., "claude-opus-4-7", "mock-builder-family")
  revision = identifier matching ^[a-z0-9-]+$         (e.g., "rev-2026-04-21", "seed-42")
  binding  = one of "builder" | "verifier" | "auditor" | "critic" | "researcher" | "librarian"
```

Examples (mocks): `ckpt:mock-alpha:seed-42:builder`, `ckpt:mock-beta:seed-99:verifier`.

**`distinct_checkpoints(a, b)` rule** — returns `True` iff:
1. `a.family != b.family` **OR** `a.revision != b.revision` (different actual checkpoint), AND
2. `a.binding != b.binding` (a brain cannot self-verify even under a relabel).

Enforcement is centralized in `csis.verify.gate.assert_cross_checkpoint(cert)` which is called by the Coordinator before `promote()`. The gate also requires that the two `CheckpointID`s appear in a static `checkpoint_registry.yaml` with cryptographic public keys; an unregistered ID fails the gate even if structurally well-formed. For the prototype, the registry holds entries for `mock-alpha` / `mock-beta` / `mock-gamma` with locally generated ed25519 keys so signatures are actually verifiable.

**Why a registry, not just a string compare.** It prevents the Builder from constructing a forged certificate that names a fake "verifier" checkpoint that does not exist. The registry plus signature check is what makes cross-checkpoint a real invariant rather than a naming convention.

---

## 6. Mock V1 Graders for the Prototype (PR maintenance)

Recommended domain: **PR maintenance** (simpler signal, real CI infrastructure later). Shipping five scriptable mock graders lets us exercise the end-to-end loop without standing up real test harnesses.

```python
# csis/mocks/graders.py
from dataclasses import dataclass
from typing import Callable

@dataclass(frozen=True)
class GraderResult:
    name: str
    version: str
    passed: bool
    duration_ms: int
    evidence_hash: str       # sha256 of evidence blob (mock: hash of decision)
    detail: str              # human-readable

@dataclass(frozen=True)
class MockArtifact:
    artifact_id: str
    diff: str                # raw text; mocks key off content
    claimed_intent: str
    metadata: dict           # scenario flags injected by the test harness

# Each grader keys its decision off `metadata["scenarios"][grader_name]`
# so the test harness can script outcomes:
#   {"scenarios": {"tests_pass_grader": "pass" | "fail" | "flaky"}}

def _make(name: str, version: str = "0.1.0") -> Callable[[MockArtifact], GraderResult]:
    def grader(art: MockArtifact) -> GraderResult:
        verdict = art.metadata.get("scenarios", {}).get(name, "pass")
        passed = verdict == "pass"
        # `flaky` flips a coin seeded by artifact_id for reproducibility
        if verdict == "flaky":
            import hashlib
            passed = (int(hashlib.sha256(art.artifact_id.encode()).hexdigest(), 16) & 1) == 0
        evidence = f"{name}:{art.artifact_id}:{verdict}".encode()
        import hashlib
        return GraderResult(
            name=name, version=version, passed=passed,
            duration_ms=10, detail=f"mock:{verdict}",
            evidence_hash="sha256:" + hashlib.sha256(evidence).hexdigest(),
        )
    grader.__name__ = name
    return grader

tests_pass_grader      = _make("tests_pass_grader")
lint_grader            = _make("lint_grader")
typecheck_grader       = _make("typecheck_grader")
coverage_delta_grader  = _make("coverage_delta_grader")
diff_scope_grader      = _make("diff_scope_grader")

MOCK_V1_SUITE = [
    tests_pass_grader, lint_grader, typecheck_grader,
    coverage_delta_grader, diff_scope_grader,
]
```

**Scriptable scenarios used in tests:**
| Scenario flag | What it exercises |
|---|---|
| all `"pass"` | Happy path → Verifier Certificate |
| `tests_pass_grader: "fail"` | V1 hard fail → no V2 invocation; rejection |
| `lint_grader: "fail"`, rest pass | Partial V1 fail → rejection, no promotion |
| all V1 `"pass"` + V2 mock returns falsification | V1-pass / V2-reject path |
| `tests_pass_grader: "flaky"` | Replay determinism check (run twice, expect same verdict for same `artifact_id`) |

The mock V2 critic is similarly scripted: it reads `metadata["v2_verdict"] in {"certify", "reject:<category>"}`.

---

## 7. Anti-Gaming List

Five concrete ways the Builder could try to game V1/V2, and the defense:

1. **Weakening tests to pass them.**
   *Attack:* Builder edits assertions in `tests/` so the suite passes the changed behavior.
   *Defense:* `tests_unchanged_grader` (V1 #2 in 2A) diffs the test files specifically; any deletion/`@skip`/assertion-text change in a touched test file flips it to fail unless `claimed_intent` declares a test refactor. V2 critic prompt (a) is the second line of defense.

2. **Tautological proofs / definition-unfolding tricks (formal math).**
   *Attack:* Builder edits the theorem statement to something trivially provable (e.g., `n + 0 = n + 0`) while keeping the name.
   *Defense:* `statement_unchanged_grader` (V1 #5 in 2B) string-equals the requested theorem type against the canonical target stored in the candidate store. V2 critic prompt (f) catches subtle definitional drift the string match misses.

3. **Mock-in-production / hidden network egress.**
   *Attack:* Builder slips a `monkeypatch` or a `requests.get` mock into production code so the suite passes by short-circuiting real behavior.
   *Defense:* `diff_scope_grader` rejects diffs that touch test-only modules from production paths. The sandbox tier (T1) denies network syscalls at the substrate level (§9.1, §10), so a real request would fail anyway. V2 critic prompt (a)/(c) hunts for the smell explicitly.

4. **Forged verifier checkpoint / self-certification.**
   *Attack:* Builder constructs a `VerifierCertificate` JSON naming itself (or a colluding sibling on the same checkpoint) as the Verifier.
   *Defense:* `assert_cross_checkpoint` (§5) requires (a) different `CheckpointID` along the family-or-revision axis, (b) registry presence, (c) valid ed25519 signature under the registered verifier key. The Builder has no access to the verifier signing key (vault + proxy pattern, §15 of the architecture), so it cannot mint a forgery.

5. **Empty critic — `falsification: null` with no work done.**
   *Attack:* V2 critic returns `{"falsification": null}` immediately without actually probing.
   *Defense:* The `attempts[]` array in `v2_critic` is mandatory and non-empty; the Coordinator's pre-promotion gate rejects certificates with `len(attempts) < min_probes_for_domain` (e.g., ≥ 4 for PR, ≥ 4 for formal math, matching the (a)-(f) categories). Critics that pattern-fill `attempts[]` without real content are caught by V3 debate in Phase 1; for Phase 0 we accept this as a known residual risk and log all certificates for sampled human audit.

---

**Cross-references.** Aligns with §4 (continuous loop step 5), §6.2 (trust level transition `untrusted -> candidate -> verified` is gated on this certificate), §8 (verification stack), §9.1 (call-site tier tags), and Appendix B (the `cert.passes` check). The `VerifierCertificate` is what the Auditor's why-doc (separate spec) cites by `certificate_id` and `artifact_hash`.
