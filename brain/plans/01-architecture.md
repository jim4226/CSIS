# CSIS Phase-0 — Python Module Architecture

**Status:** v1 blueprint, ready for implementation.
**Constraints:** stdlib + `pydantic` + `pytest`. No LangChain, no LangGraph. Must run on Windows via `python -m csis.loop` after `pip install pydantic pytest`. Target ≤ ~2,500 LOC total.

This document is the engineering contract that maps `CSIS-architecture.html` (the spec) onto concrete Python modules. The eight-step continuous loop from §4 and the pseudocode from Appendix B drive the module shape; the trust-level contract from §6.2 and the call-site tier tag from §9.1 drive the data types.

---

## 1. Module tree under `csis/`

The existing skeleton (`agents/`, `dreams/`, `memory/`, `runtime/`, `safety/`, `substrate/`, `verification/`) is the right top-level cut — each subdirectory maps to a stack layer from §3. I'm keeping it and adding two siblings: `backends/` (the pluggable LLM layer, separated so swapping mock↔real is one import) and `types/` (Pydantic data types, separated so every module depends on types but types depend on nothing).

```
csis/
  __init__.py
  __main__.py             # routes `python -m csis` to loop.main()
  loop.py                 # the continuous loop driver (Appendix B made real)
  config.py               # paths, tier ceilings, model-checkpoint pinning

  types/
    __init__.py           # re-exports all models
    events.py             # Event, EventKind enum
    memory.py             # MemoryEntry, TrustLevel, MemoryTier
    capability.py         # CapabilityTag, Tier enum, RiskClass enum
    certificates.py       # VerifierCertificate, FalsificationAttempt
    audit.py              # WhyDoc, HashPrecondition
    dreams.py             # DreamCandidate, DreamInstruction
    work.py               # Plan, Artifact, Response

  backends/
    __init__.py
    base.py               # LLMBackend ABC: complete(role, prompt, **opts) -> str
    mock.py               # MockBackend — deterministic, scriptable per role
    anthropic.py          # AnthropicBackend — optional, lazy-imported, real API

  agents/
    __init__.py
    base.py               # Agent base class + Role enum + tier ceiling
    coordinator.py        # Coordinator: schedules sub-agents, owns session log
    researcher.py         # T0 — proposes falsifiable plans
    builder.py            # T1 — runs sandboxed code (Phase-0: subprocess-mocked)
    critic.py             # T0 — adversarial; must produce falsification attempt
    verifier.py           # T1 — cross-checkpoint; runs graders
    librarian.py          # T0 — consolidates to candidate memory stores
    auditor.py            # T0 — cross-checkpoint; writes why-doc, signs/escalates

  memory/
    __init__.py
    store.py              # MemoryStore: per-tier × per-trust JSON file
    tiers.py              # the 5 tiers (working/episodic/semantic/procedural/causal)
    trust.py              # promotion/demotion rules; hash-precondition check
    skill_library.py      # procedural memory = directory of *.py skills

  verification/
    __init__.py
    graders.py            # V1 — programmatic graders (pytest-style)
    critic_stack.py       # V2 — adversarial critic harness
    certificates.py       # build/verify VerifierCertificate, cross-checkpoint pin

  dreams/
    __init__.py
    pipeline.py           # mock multi-Dream pipeline; per-tier cadence
    quality.py            # quality-score the candidate output (§7.2)
    rollback_test.py      # instantiate candidate in sandbox; rerun evals

  safety/
    __init__.py
    constitution.py       # constitution.allows(plan) — load-bearing predicate
    tier_guard.py         # tier_authorized() + tier_ceiling enforcement
    tripwires.py          # tripwires.fired() — capability/behavioral classifiers
    rollback.py           # rollback() primitive; checkpoint-restore

  substrate/
    __init__.py
    event_log.py          # append-only JSONL writer/reader
    session_log.py        # in-process shared log (Coordinator-owned)
    sandbox.py            # execute(tool, input) -> str; tier-tagged
    tools.py              # tool registry + pre/post guards (§10)

  runtime/
    __init__.py
    scheduler.py          # async scheduler (asyncio); ≤25 concurrent threads
    delegate.py            # delegate() helper used by Coordinator
    state.py              # session state, wake(sessionId), checkpointing
```

**Justifications.** `types/` is its own package because every other module imports models — keeping them dependency-free prevents cycles. `backends/` is separated from `agents/` so the LLM is swappable without touching agent logic (P5 reversibility applied to ourselves). `runtime/` holds the async + state plumbing distinct from policy in `safety/` (P6 — safety is code, not config). `dreams/` is its own module even though Phase-0 uses a mock because the spec's §7 emphasizes Dreams is a *candidate generator*, not safety; the boundary matters.

---

## 2. Core data types (Pydantic v2)

All in `csis/types/`. Every model has `model_config = ConfigDict(frozen=True)` so passed-around objects can't be mutated mid-flight; mutation is via `.model_copy(update=...)` which surfaces in diffs.

```python
# csis/types/capability.py
class Tier(str, Enum):
    T0 = "T0"; T1 = "T1"; T2 = "T2"; T3 = "T3"; T4 = "T4"

class RiskClass(str, Enum):
    LOW = "low"; MEDIUM = "medium"; HIGH = "high"; CRITICAL = "critical"

class ApprovalState(str, Enum):
    AUTO = "auto"; AUDITOR = "auditor"; HUMAN = "human"

class RollbackPlan(str, Enum):
    NOOP = "noop"; CANDIDATE_DISCARD = "candidate-discard"
    CHECKPOINT_RESTORE = "checkpoint-restore"; AIRGAP = "airgap"

class CapabilityTag(BaseModel):    # §9.1 — exact shape from the spec
    actor: str                      # "researcher-v1"
    tool: str                       # "web_search"
    tier: Tier
    input_hash: str                 # "sha256:..."
    risk_class: RiskClass
    approval_state: ApprovalState
    rollback_plan: RollbackPlan
```

```python
# csis/types/memory.py
class TrustLevel(str, Enum):       # §6.2 — six levels, ordered
    RAW = "raw"; UNTRUSTED = "untrusted"; CANDIDATE = "candidate"
    VERIFIED = "verified"; PROMOTED = "promoted"; DEPRECATED = "deprecated"

class MemoryTier(str, Enum):       # §6.1
    WORKING = "working"; EPISODIC = "episodic"; SEMANTIC = "semantic"
    PROCEDURAL = "procedural"; CAUSAL = "causal"

class MemoryEntry(BaseModel):
    id: str                         # uuid4
    tier: MemoryTier
    trust: TrustLevel
    content: str                    # the actual memorized text/json blob
    why_tag: Optional[str] = None   # P3 — "why over what"; required for verified+
    created_at: datetime
    promoted_at: Optional[datetime] = None
    source_event_ids: List[str]     # provenance back to session log
    superseded_by: Optional[str] = None   # for deprecated
    content_hash: str               # sha256 — used for hash-precondition checks
```

```python
# csis/types/certificates.py
class FalsificationAttempt(BaseModel):
    attempted: bool
    succeeded: bool                 # if True → cert.passes = False
    description: str
    artifact_refs: List[str]

class VerifierCertificate(BaseModel):
    cert_id: str
    plan_id: str
    artifact_ids: List[str]
    passes: bool
    v1_grader_results: Dict[str, bool]   # grader-name → pass
    v2_falsification: FalsificationAttempt
    verifier_checkpoint: str        # MUST differ from producer_checkpoint
    producer_checkpoint: str
    signed_at: datetime
```

```python
# csis/types/audit.py
class HashPrecondition(BaseModel):
    store_id: str
    expected_hash: str              # promotion fails if live hash differs

class WhyDoc(BaseModel):
    why_id: str
    plan_id: str
    diff: str                       # human-readable delta vs live store
    rationale: str                  # the "why over what"
    hash_precondition: HashPrecondition
    auditor_checkpoint: str         # MUST differ from producer
    signed: bool
    escalated: bool
    signature: Optional[str] = None # sha256 of (diff + rationale + checkpoint)
```

```python
# csis/types/events.py
class EventKind(str, Enum):
    OBSERVE = "observe"; PLAN = "plan"; ACT = "act"
    VERIFY = "verify"; CONSOLIDATE = "consolidate"; IMPROVE = "improve"
    AUDIT = "audit"; PROMOTE = "promote"; ROLLBACK = "rollback"
    TRIPWIRE = "tripwire"; TOOL_PRE = "tool_pre"; TOOL_POST = "tool_post"
    DELEGATE = "delegate"; ESCALATE = "escalate"

class Event(BaseModel):
    event_id: str
    session_id: str
    kind: EventKind
    actor: str
    timestamp: datetime
    payload: Dict[str, Any]         # type-specific; validated by EventKind
    tier_tag: Optional[CapabilityTag] = None
    parent_event_id: Optional[str] = None    # threading
```

```python
# csis/types/dreams.py
class DreamInstruction(BaseModel):
    template_id: str                # versioned; hashed; not free-form
    template_hash: str
    target_tier: MemoryTier
    cadence_hint: str               # "4h" | "daily" | "weekly"

class DreamCandidate(BaseModel):
    candidate_id: str
    input_store_id: str             # never modified — §7.1
    output_store_id: str            # the candidate output
    instruction: DreamInstruction
    status: Literal["complete","failed","canceled"]
    quality_score: float            # 0..1 — see §7.2; gates Auditor entry
    dedup_ratio: float
    contradiction_count: int
    why_tag_coverage: float
```

```python
# csis/types/work.py
class Plan(BaseModel):
    plan_id: str
    hypothesis: str                 # falsifiable
    budget_tokens: int
    budget_seconds: int
    tier: Tier                      # ceiling for execution
    success_criteria: List[str]
    frontier_item_id: Optional[str] = None

class Artifact(BaseModel):
    artifact_id: str
    plan_id: str
    kind: Literal["code","text","data","log"]
    content_ref: str                # filesystem path or inline hash
    content_hash: str

class Response(BaseModel):          # returned by Agent.delegate
    actor: str
    content: str
    artifacts: List[Artifact] = []
    capability_tag: CapabilityTag
    cost_tokens: int = 0
```

---

## 3. Agent interface

`csis/agents/base.py`:

```python
class Role(str, Enum):
    COORDINATOR="coordinator"; RESEARCHER="researcher"; BUILDER="builder"
    CRITIC="critic"; VERIFIER="verifier"; LIBRARIAN="librarian"; AUDITOR="auditor"

class Agent:
    role: Role
    tier_ceiling: Tier              # enforced at delegate-time
    checkpoint: str                 # logical model-checkpoint id

    def __init__(self, backend: LLMBackend, session_log: SessionLog,
                 checkpoint: str, tier_ceiling: Tier): ...

    async def delegate(self, prompt: str, *, tier: Tier = Tier.T0,
                       tools: Optional[List[str]] = None) -> Response:
        # 1. tier_guard.check(self.tier_ceiling, tier) → raise on escalation
        # 2. emit DELEGATE event to session_log
        # 3. call self.backend.complete(role=self.role, prompt=...)
        # 4. wrap output into Response with CapabilityTag
        # 5. emit completion event with cost_tokens
        ...
```

**Communication model.** All agents share one `SessionLog` (in-process, owned by Coordinator). The log is the *only* inter-agent channel — there is no agent-to-agent direct call. Sub-agents append `Event`s with `parent_event_id` threading. The Coordinator's `delegate(role, prompt)` looks up the agent for `role`, posts a DELEGATE event, awaits the result, and posts the completion. This mirrors §5's "shared session log" and is what makes the Auditor's later read consistent.

**Cross-checkpoint pinning when both checkpoints are mocked.** In Phase-0, the "checkpoint" is just a string label (`"ckpt-A"`, `"ckpt-B"`). The Verifier and Auditor are constructed with `checkpoint="ckpt-B"`; Researcher/Builder with `checkpoint="ckpt-A"`. The `MockBackend` accepts a `checkpoint` argument and returns scripted responses keyed by `(checkpoint, role, prompt_pattern)` — so even though both are deterministic Python, the *contract* that "verifier ≠ producer checkpoint" is enforced and asserted in `certificates.py::build_certificate()` (`assert cert.verifier_checkpoint != cert.producer_checkpoint`). When `AnthropicBackend` lands, the same string maps to `claude-opus-4-7` vs `claude-sonnet-4-6` (the two Dreams-supported checkpoints, §7.1). The discipline is identical; only the implementation behind the string changes.

---

## 4. The continuous loop

`csis/loop.py` — direct translation of Appendix B, calling into the modules above:

```python
async def fast_loop_iteration(coord: Coordinator) -> LoopResult:
    # 1-3. OBSERVE + FRONTIER SCAN + PLAN
    plan_resp = await coord.delegate(Role.RESEARCHER,
        "Plan an experiment for the top frontier item.", tier=Tier.T0)
    plan = Plan.model_validate_json(plan_resp.content)

    if not constitution.allows(plan):
        return safety.escalate(plan, reason="constitution")
    if not tier_guard.tier_authorized(plan, coord.policy):
        return safety.escalate(plan, reason="tier")

    # 4. ACT
    artifacts_resp = await coord.delegate(Role.BUILDER,
        f"Execute: {plan.model_dump_json()}",
        tier=plan.tier, tools=["code_exec_sandbox","file_io_sandbox"])
    artifacts = [Artifact.model_validate(a) for a in artifacts_resp.artifacts]

    # 5. VERIFY (cross-checkpoint enforced inside)
    cert_resp = await coord.delegate(Role.VERIFIER,
        f"Verify: {[a.artifact_id for a in artifacts]}",
        tier=Tier.T1, tools=["run_grader","falsify"])
    cert = VerifierCertificate.model_validate_json(cert_resp.content)
    if not cert.passes:
        safety.rollback(plan); return LoopResult(promoted=False, reason="verify")

    # 6. CONSOLIDATE → candidate stores only
    deltas_resp = await coord.delegate(Role.LIBRARIAN,
        f"Consolidate to candidate stores: {cert.cert_id}")
    deltas = json.loads(deltas_resp.content)   # list of MemoryEntry ids

    # 7-8. IMPROVE + AUDIT
    why_resp = await coord.delegate(Role.AUDITOR,
        f"Why-doc for: plan={plan.plan_id} cert={cert.cert_id}")
    why = WhyDoc.model_validate_json(why_resp.content)
    if not auditor_signs(why, hash_precondition=memory.live_store_hash()):
        safety.rollback(plan); safety.page_overseer(why)
        return LoopResult(promoted=False, reason="audit")

    memory.promote(deltas)                     # atomic candidate→live
    coord.session_log.emit(Event(kind=EventKind.PROMOTE, ...))
    interp.scan(coord.recent_threads())        # SAE stub in Phase-0
    if tripwires.fired():
        coord.halt_and_escalate()
    return LoopResult(promoted=True, deltas=deltas)
```

`csis/__main__.py` does `asyncio.run(loop.main())` which sets up the Coordinator, registers all agents, and either runs N iterations (test mode) or runs forever with `wake(sessionId)` resume on restart.

---

## 5. Pluggable LLM backend

`csis/backends/base.py`:

```python
class LLMBackend(ABC):
    @abstractmethod
    def complete(self, *, role: Role, checkpoint: str, prompt: str,
                 max_tokens: int = 2000, tools: Optional[List[str]] = None
                 ) -> BackendResponse: ...
```

`MockBackend` (default; lives in `mock.py`, ~250 LOC):

- Constructed with an optional `script: Dict[Tuple[str, Role, str], str]` mapping `(checkpoint, role, prompt_prefix)` → canned response.
- Falls back to a deterministic role-template if no script entry: e.g. Researcher returns a stock `Plan` JSON with `hypothesis="mock hypothesis"`; Verifier returns a `VerifierCertificate` with `passes=True` and `verifier_checkpoint=<self.checkpoint>`; Auditor returns a `WhyDoc` with `signed=True`.
- Records every `(role, prompt)` it sees in `self.call_log` so tests can assert call shape.
- Has knobs: `fail_verify_after_n`, `fail_audit_after_n`, `inject_tripwire_at` — to drive failure-path tests without monkey-patching.

`AnthropicBackend` (`anthropic.py`, ~150 LOC, lazy-imported):

- `from anthropic import Anthropic` only inside `__init__` so the package import never fails when the SDK isn't installed.
- Maps internal `checkpoint` strings to model ids (`"ckpt-A" → "claude-opus-4-7"`, `"ckpt-B" → "claude-sonnet-4-6"` to satisfy §7.1).
- Reads `ANTHROPIC_API_KEY` from env; raises a clear error if unset.
- Translates `tools` into tool-use blocks; serializes the result back into `BackendResponse`.

Backend is selected in `config.py`: `BACKEND = os.environ.get("CSIS_BACKEND", "mock")`. The default is `mock`, so `pytest` and `python -m csis.loop` both run offline with zero API cost.

---

## 6. Persistence: disk vs in-memory

| Concern | Where it lives | Format |
|---|---|---|
| Event log (append-only) | `event_log/<session_id>.jsonl` | One `Event` per line as JSON. Reader streams; writer flushes per event. |
| Memory stores | `memory_store/<tier>/<trust>.json` | One JSON file per `(tier, trust)`. Object: `{"entries": [MemoryEntry, ...], "store_hash": "..."}`. Hash recomputed on every write; used for hash-precondition. |
| Skill library (procedural) | `memory_store/procedural/skills/*.py` | One Python file per skill, importable via `importlib`. Skill metadata in `index.json`. |
| Why-doc archive | `event_log/why_docs/<why_id>.json` | The signed `WhyDoc` JSON, immutable. Cross-referenced from PROMOTE events. |
| Verifier certificates | `event_log/certificates/<cert_id>.json` | Same pattern. |
| Dream candidate stores | `dream_candidates/<candidate_id>/` | Directory; promoted candidates get archived into `memory_store/`, rejected ones stay here for replay. |
| Session log (active) | In-memory `SessionLog` + mirrored to event_log | The in-memory copy is the working view; the JSONL is the durable copy. |
| Frontier map, capability tier policy | In-memory (config-loaded) | Reloaded on every `wake()`. |
| Working-tier memory | In-memory only (it's the scratchpad) | Per §6.1, working tier has trust ceiling `raw` and is not persisted. |

**Atomicity.** Promotion is the only multi-file mutation: it (a) appends to `memory_store/<tier>/promoted.json`, (b) demotes the prior version to `deprecated.json`, (c) writes the `WhyDoc`, (d) writes a `PROMOTE` event. Implemented as a `try/except` + temp-file rename in `memory/store.py::promote_atomic()`. If any step fails, the rename is rolled back and a `ROLLBACK` event is emitted.

---

## 7. Concrete file list with LOC estimates

| File | LOC | Notes |
|---|---:|---|
| `csis/__init__.py` | 10 | re-exports |
| `csis/__main__.py` | 20 | `asyncio.run(loop.main())` |
| `csis/loop.py` | 200 | the loop + `main()` + `wake(sessionId)` |
| `csis/config.py` | 60 | paths, tier ceilings, backend selection |
| `csis/types/events.py` | 50 | |
| `csis/types/memory.py` | 60 | |
| `csis/types/capability.py` | 50 | |
| `csis/types/certificates.py` | 50 | |
| `csis/types/audit.py` | 40 | |
| `csis/types/dreams.py` | 40 | |
| `csis/types/work.py` | 50 | |
| `csis/types/__init__.py` | 30 | re-exports |
| `csis/backends/base.py` | 40 | ABC + BackendResponse |
| `csis/backends/mock.py` | 250 | scripted + deterministic-fallback |
| `csis/backends/anthropic.py` | 150 | optional real backend |
| `csis/agents/base.py` | 120 | Agent + Role + delegate plumbing |
| `csis/agents/coordinator.py` | 200 | schedules, owns session log, registers agents |
| `csis/agents/researcher.py` | 60 | role-specific prompt assembly |
| `csis/agents/builder.py` | 80 | tier-bounded sandbox calls |
| `csis/agents/critic.py` | 50 | |
| `csis/agents/verifier.py` | 80 | builds cert + cross-checkpoint assert |
| `csis/agents/librarian.py` | 100 | candidate-store writes |
| `csis/agents/auditor.py` | 100 | why-doc + sign/escalate |
| `csis/memory/store.py` | 200 | JSON store + atomic promote |
| `csis/memory/tiers.py` | 50 | enum + per-tier policies |
| `csis/memory/trust.py` | 80 | promotion/demotion rules |
| `csis/memory/skill_library.py` | 100 | procedural memory via importlib |
| `csis/verification/graders.py` | 100 | V1 grader harness |
| `csis/verification/critic_stack.py` | 80 | V2 |
| `csis/verification/certificates.py` | 80 | cert build + verify signature |
| `csis/dreams/pipeline.py` | 120 | mock multi-Dream |
| `csis/dreams/quality.py` | 60 | quality-score §7.2 |
| `csis/dreams/rollback_test.py` | 60 | sandbox-rerun eval |
| `csis/safety/constitution.py` | 70 | `allows(plan)` + escalate |
| `csis/safety/tier_guard.py` | 70 | tier authorization |
| `csis/safety/tripwires.py` | 60 | classifier stubs |
| `csis/safety/rollback.py` | 60 | checkpoint-restore |
| `csis/substrate/event_log.py` | 120 | append-only JSONL |
| `csis/substrate/session_log.py` | 80 | in-memory + mirror |
| `csis/substrate/sandbox.py` | 100 | `execute(tool, input)` with tier tag |
| `csis/substrate/tools.py` | 150 | tool registry + §10 guards |
| `csis/runtime/scheduler.py` | 80 | asyncio scheduler, ≤25 concurrent |
| `csis/runtime/delegate.py` | 40 | delegate helper |
| `csis/runtime/state.py` | 80 | wake(sessionId), checkpoint |
| **Subtotal csis/** | **~2,260** | |
| `tests/test_loop_happy_path.py` | 80 | one full iteration end-to-end |
| `tests/test_verifier_cross_checkpoint.py` | 50 | asserts pin discipline |
| `tests/test_promotion_atomicity.py` | 60 | crash-mid-promote → rollback |
| `tests/test_tier_escalation.py` | 40 | T0 actor cannot execute T1 |
| `tests/test_audit_hash_precondition.py` | 50 | stale hash → rejected |
| `tests/test_dreams_partial_output.py` | 40 | canceled Dream archived not promoted |
| `tests/test_mock_backend_scripting.py` | 40 | scripted responses + call log |
| `tests/conftest.py` | 30 | shared fixtures |
| **Subtotal tests/** | **~390** | |
| **TOTAL** | **~2,650** | ~6% over target; first prune target: collapse `runtime/delegate.py` into `agents/base.py`, trim `dreams/` since Phase-0 mocks it. |

---

## 8. Open questions

- **Which benchmark domain do we wire in first?** Spec offers PR maintenance or formal-math reasoning. Builder's tool surface, Verifier's V1 graders, and the skill-library bootstrap content all depend on this. I assumed PR maintenance for sizing (lighter grader stack).
- **Async vs threads on Windows.** `asyncio` is fine for I/O but `claude-in-chrome`-style tool calls may need a thread pool. Need to confirm Windows `ProactorEventLoop` plays well with `subprocess` in `sandbox.py`.
- **`wake(sessionId)` semantics for in-flight delegations.** If we crash mid-`delegate`, do we replay from the last DELEGATE event or skip to the next plan? Replay needs idempotent agents; spec doesn't pin this.
- **Skill library safety.** Procedural memory as importable `.py` files is the natural shape, but importing files written by a future agent crosses a tier boundary. Phase-0 proposal: skills are read-only (T0-loaded, never agent-written) until Phase 1, when Librarian gains scoped write via the candidate-store flow.
- **Interpretability stub scope.** `interp.scan()` is in Appendix B but the spec (§14.1) explicitly says SAE monitoring is research telemetry, not a brake. Phase-0 stub: a no-op that emits an `INTERP_SCAN` event so the call site exists for Phase 1 to fill in. Confirm that's the right shape.
- **Tripwire taxonomy.** Spec names "capability and behavioral classifiers" but doesn't enumerate. Proposal: ship three concrete tripwires for Phase-0 (tier-escalation-attempted, shutdown-resistance, why-doc-refusal) and treat the rest as Phase-1 work. Confirm.
- **Where does the `Overseer` live?** Spec lists it as a T4 human role. Phase-0 implementation: a single `safety/overseer.py` that writes `ESCALATE` events to a dedicated file and exits the loop with a non-zero code — *not* an interactive prompt, since the loop runs unattended. Confirm acceptable.
