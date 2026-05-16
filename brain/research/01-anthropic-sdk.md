# 01 — Anthropic SDK research pass (Phase-0 CSIS prototype)

**Date:** 2026-05-16 · **Author:** SDK research engineer · **Scope:** what's shippable today vs what CSIS-architecture.html assumes

---

## 1. What's shipping now vs the CSIS doc

| CSIS doc reference | Reality (May 2026) | Notes |
|---|---|---|
| Managed Agents / Sessions | **Public beta** since April 8, 2026, header `managed-agents-2026-04-01` ([engineering post][1], [Sessions docs][2]) | All `client.beta.{agents,environments,sessions,vaults,memory_stores}.*` namespaces exist in Python SDK. SDK auto-sets the beta header. |
| Memory Stores w/ `read_only` | **Shipping.** `access: "read_only" \| "read_write"`; capped at 8 stores per session, 100 kB per memory ([Memory docs][3]) | Read-only enforced at filesystem layer of the mount, not just policy. |
| Hash preconditions (`content_sha256`) | **Shipping** on `memories.update` ([Memory docs §"Safe content edits"][3]) | Exactly the "hash-precondition on every write" the CSIS doc relies on for promotion gating. Mismatch returns 409 `memory_precondition_failed_error`. |
| Memory versions, 30-day retention | **Confirmed** ([Memory docs §Audit memory changes][3]) — versions kept ≥30 days, recent ones kept longer; redact + retrieve endpoints exist | CSIS plan to export the why-doc archive within the window is correct. |
| Dreams API, `dreaming-2026-04-21` | **Research preview, gated by access form.** ≤100 sessions per dream, ≤4,096 char `instructions`, models `claude-opus-4-7` and `claude-sonnet-4-6` ([Dreams docs][4]) | All limits in the CSIS doc check out. No mention of `claude-opus-4-7` having a `speed: "fast"` variant — only Opus 4.6 does. |
| Multi-agent: ≤25 threads, max-1 delegation | **Confirmed.** Coordinator config also caps the roster at **20 unique agents** (separate from 25 concurrent threads) ([Multi-agent docs][5]) | Shared container + per-thread isolated context is exactly as described. |
| "Candidate Memory Stores" as a first-class feature | **Does not exist as a typed primitive.** A candidate store is just a regular `memory_store` you treat as staging, plus `archive`/`delete` to dispose. | CSIS plan to layer this on top of vanilla memory stores is the right call. |
| Brain/harness/sandbox decoupling | **Architectural fact**, per Martin/Cemaj/Cohen April 2026 ([engineering post][1]) | See §5. |

---

## 2. Concrete Python SDK call signatures

All signatures below are **verified against current docs** unless marked `IDEALIZED`.

### Client init

```python
from anthropic import Anthropic
client = Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])
# SDK auto-injects: anthropic-beta: managed-agents-2026-04-01
# Dreams calls additionally get: dreaming-2026-04-21
```

### Create a session (with read-only memory store attached)

```python
session = client.beta.sessions.create(
    agent=coordinator.id,                  # or {"type":"agent","id":..,"version":N}
    environment_id=environment.id,
    vault_ids=[vault.id],                  # optional, for MCP credentials
    resources=[
        {
            "type": "memory_store",
            "memory_store_id": semantic_store.id,
            "access": "read_only",         # <- the CSIS default
            "instructions": "Semantic tier. Cite only 'verified' or 'promoted' entries.",
        },
        {
            "type": "memory_store",
            "memory_store_id": episodic_candidate_store.id,
            "access": "read_write",        # only the Librarian gets this
        },
    ],
)
```

> Memory stores can **only** be attached at session-create time. Cannot be added/removed on a running session. ([Memory docs][3])

### `getEvents` equivalent (list + stream)

The engineering post talks about `getEvents()` as the abstract interface. In the Python SDK it appears as two methods:

```python
# Polling / pagination — equivalent to a positional slice
for event in client.beta.sessions.events.list(session.id):
    handle(event)

# Streaming via SSE
with client.beta.sessions.events.stream(session.id) as stream:
    for event in stream:
        handle(event)

# For a specific sub-agent thread (multi-agent):
for event in client.beta.sessions.threads.events.list(thread.id, session_id=session.id):
    handle(event)
```

Event types include `user.message`, `user.interrupt`, `user.tool_confirmation`, `agent.message`, `agent.thinking`, `agent.tool_use`, `agent.tool_result`, `agent.mcp_tool_use`, `session.thread_created`, `session.thread_status_idle`, etc. ([Events docs][6])

> **Reconnect protocol (UNCONFIRMED but recommended by community guide):** on every reconnect, open the stream first, then call `events.list()`, then dedupe by event ID. Original cite is the AI Workflows blog; the official docs describe streaming but I did not find an explicit "always re-list after reconnect" recipe in the platform docs — needs verification.

### Schedule a Dream

```python
dream = client.beta.dreams.create(
    inputs=[
        {"type": "memory_store", "memory_store_id": episodic_live_store.id},
        {"type": "sessions",     "session_ids": [s.id for s in last_4h_sessions]},
    ],
    model="claude-opus-4-7",               # or claude-sonnet-4-6
    instructions="Episodic-tier consolidation. Dedupe by entity+timestamp. <4096 chars.",
)
# dream.id == "drm_01..."; dream.status starts as "pending"
```

### Poll / retrieve / cancel a Dream

```python
while dream.status in ("pending", "running"):
    time.sleep(10)
    dream = client.beta.dreams.retrieve(dream.id)

# When completed, pull the output candidate store ID:
output_store_id = next(o.memory_store_id for o in dream.outputs if o.type == "memory_store")

# Cancel mid-flight (only valid on pending/running):
client.beta.dreams.cancel(dream.id)

# Archive after terminal state (no unarchive):
client.beta.dreams.archive(dream.id)
```

### Memory write with hash precondition (the promotion primitive)

```python
client.beta.memory_stores.memories.update(
    memory_id=mem.id,
    memory_store_id=live_store.id,
    content=new_content,
    precondition={
        "type": "content_sha256",
        "content_sha256": expected_hash,    # what Auditor diffed against
    },
)
# 409 memory_precondition_failed_error if live store moved → CSIS aborts promotion
```

---

## 3. Pricing / rate-limit / preview-gating caveats

| Concern | What's true |
|---|---|
| **Dreams access** | Dreams is **gated by a request-access form** ([Dreams docs][4] — "Research Preview... Request access"). Phase-0 cannot assume access on day 1; provision the form submission early. |
| **Dreams billing** | Standard API token rates for the chosen model. `usage` on the resource reports exact tokens. No discount, no flat fee. |
| **Sessions rate limit** | 60 RPM for create operations (Agents, Sessions, Vaults), 600 RPM for everything else, **org-scoped** ([Managed Agents API reference][7]). |
| **Environments** | Tighter cap: 60 RPM and **max 5 concurrent** environments per org. This is the limit that bites first for a long-running CSIS instance. |
| **Concurrent threads** | 25 per session (multi-agent). Coordinator counts as one — so CSIS has 24 sub-agent slots. CSIS roster (Researcher, Builder, Critic, Verifier, Librarian, Auditor) fits comfortably, with room to fan out Researcher copies. |
| **Roster size** | `multiagent.agents` accepts at most 20 unique agents; can include `{"type":"self"}` so the coordinator can spawn copies of itself. |
| **Memory** | Per-memory size cap: 100 kB (~25k tokens). Per-session: ≤ 8 memory stores. Higher capacity by contacting support. |
| **Dream inputs** | ≤ 100 sessions, ≤ 4,096 char `instructions`. Only `claude-opus-4-7` and `claude-sonnet-4-6` are supported during preview. |
| **Beta headers** | `managed-agents-2026-04-01` always; Dreams additionally needs `dreaming-2026-04-21`. SDK sets these automatically — do not strip them. |
| **Model IDs** | Confirmed: `claude-opus-4-7`, `claude-opus-4-6` (with `speed:"fast"`). `claude-sonnet-4-6` is Dreams-only in the docs I found — UNCONFIRMED whether usable for agent execution today. |

---

## 4. Fallback design (no `ANTHROPIC_API_KEY`)

Recommendation: ship a **`MockAnthropicBackend`** that the prototype can switch into via env var. Justification: Dreams is gated by a form, the team is on Windows + offline-friendly, and Phase-0's two hardest tests (hash precondition, candidate→live rotation) are SDK-shape, not model-quality.

**Surface to mock:** the five methods CSIS actually calls. Everything else can raise `NotImplementedError`.

```python
# csis/backend.py — IDEALIZED
class Backend(Protocol):
    def sessions_create(self, *, agent, environment_id, resources=None, vault_ids=None) -> Session: ...
    def events_list(self, session_id: str) -> Iterable[Event]: ...
    def events_send(self, session_id: str, events: list) -> None: ...
    def memories_update(self, memory_store_id, memory_id, *, content, precondition) -> Memory: ...
    def dreams_create(self, *, inputs, model, instructions) -> Dream: ...
    def dreams_retrieve(self, dream_id: str) -> Dream: ...
```

**Mock behavior to get right (anything else is overfitting):**
1. `events_list` returns a deterministic in-memory append-only log keyed by `session_id`. This is what the event_log/ folder is for.
2. `memories_update` with `precondition` raises a fake `MemoryPreconditionFailedError` when the in-memory SHA doesn't match — this is the test surface for the Auditor's hash gate.
3. `dreams_create` returns a `Dream` that goes `pending → running → completed` after `time.sleep(0.1)`; outputs reference a freshly-spun-up in-memory candidate store ID. The point of mocking is to exercise the candidate-store rotation logic, not to fake good consolidation output.
4. The 25-thread / 8-memory-store / 100kB caps should be **enforced in the mock** so prototype hits the same walls as production.

**Switch:**
```python
backend = MockBackend() if os.environ.get("CSIS_MODE") == "mock" else AnthropicBackend()
```

Detect missing key → fall back to mock with a loud `WARN`. Phase-0 CI runs entirely on mock; live runs are opt-in.

---

## 5. Lance Martin et al., "Scaling Managed Agents: Decoupling the brain from the hands" (April 8, 2026)

Authors: Lance Martin, Gabe Cemaj, Michael Cohen ([Anthropic engineering][1]).

### Brain / harness / sandbox split

Three things, deliberately separated:

- **Brain (harness)** — the Claude model + control loop. **Stateless.** Cattle, not pets. Restartable.
- **Hands (sandbox)** — execution environments. Interchangeable. Provisioned *only when needed*, by the brain via a tool call.
- **Session** — durable, append-only event log living **outside** the harness.

The interface between them is intentionally tiny:

- Harness → sandbox: `execute(name, input) → string`. That's it. Any custom tool, any MCP server, any in-house tool fits this signature.
- Harness → session: `getEvents()`, which lets the brain interrogate context by *positional slices* of the event stream rather than carrying it in RAM.

Quantified payoff: **p50 TTFT dropped ~60%, p95 TTFT dropped >90%** after decoupling.

### "Many brains, many hands"

Because no hand couples to any brain, **brains can pass hands to one another**. A hand is just a tool — "a container, a phone, or a Pokémon emulator" — and the harness doesn't distinguish. This enables cross-session delegation: brain A spawns a hand, hands it to brain B, and walks away. Phase-0 CSIS uses the simpler coordinator-led model (§5 of the CSIS doc) and earns the right to migrate to this pattern in Phase 3.

### Credential isolation / vault-proxy

Credentials **never reach sandboxes where Claude-generated code runs.** Two patterns:

1. **Repository access** — tokens bundled at sandbox init; `git push/pull` works locally without exposing creds.
2. **Custom tool / MCP credentials** — stored in a Vault (`client.beta.vaults.*`) outside the sandbox; a dedicated **proxy** fetches creds and makes the external call on behalf of the harness. Code generated by Claude never touches the secret.

CSIS adopts this directly and extends the same structural discipline (an isolated different-checkpoint actor for verification/audit) to the *same-model self-confirmation* threat.

### Design principle the post leans on

> "Virtualize infrastructure into general abstractions that outlast specific implementations." OS-design framing for agent platforms.

---

## 6. OpenAI Agents SDK guardrails (the §10 mirror)

Per the OpenAI Agents Python SDK guardrails docs ([source][8]):

- Three guardrail tiers, not two:
  - **Input guardrails** — fire only at the start of a run (first agent only).
  - **Output guardrails** — fire only at the end (last agent only).
  - **Tool guardrails** — fire on **every** function-tool invocation, both pre- and post-call. This is the tier CSIS §10 mirrors, and it's the one input/output guardrails cannot reach in a multi-agent system because they only cover workflow boundaries.

- **Tripwire mechanism**: each guardrail returns a `GuardrailFunctionOutput` (or `ToolGuardrailFunctionOutput`) with a boolean tripwire. When the flag is set, the runtime immediately raises `InputGuardrailTripwireTriggered` / `OutputGuardrailTripwireTriggered` and halts the run.

- **Tool-guardrail expressiveness** is finer than the workflow-level cousins: tool input guardrails can *skip the call*, *replace the output with a message*, or *raise a tripwire*; tool output guardrails can *replace the output* or *raise a tripwire*.

- **Decorator signature** (idiomatic Python):

```python
@tool_input_guardrail
def block_secrets(data) -> ToolGuardrailFunctionOutput:
    if looks_like_secret(data.input):
        return ToolGuardrailFunctionOutput.reject_content("Blocked: secret detected")
    return ToolGuardrailFunctionOutput.allow()
```

For CSIS, the mapping is direct: every entry in the §10 table (`code_exec_sandbox`, `file_io_sandbox`, `web_search`, `http_get_whitelisted`, `schedule_dream`, `sign_why_doc`) becomes a `@tool_input_guardrail` / `@tool_output_guardrail` pair, and each guard's pre/post output is itself written to the session log as an event so the Auditor can audit guardrails independently of tool implementations.

---

## Open items / UNCONFIRMED

1. Exact reconnect protocol for the events stream (the dedup-by-event-ID recipe is in a third-party blog, not the platform docs I read).
2. Whether `claude-sonnet-4-6` is callable as an agent's `model` outside the Dreams context — Dreams docs list it; agent setup docs I sampled only showed `claude-opus-4-7` / `claude-opus-4-6`.
3. Whether memory-store `archive` reliably blocks `running` Dreams from finishing — Dreams docs say archiving an *input* store mid-run causes `input_memory_store_unavailable`, but the inverse (archiving the candidate output mid-run) is rejected with 400. Sufficient for CSIS's reversibility property as long as we never archive inputs while a Dream is running.
4. Pricing-tier specifics for Sessions/Environments beyond the base RPM caps — needs verification with sales / support before any 24/7 Phase-2 run.

---

## Sources

[1]: https://www.anthropic.com/engineering/managed-agents "Martin, Cemaj, Cohen — Scaling Managed Agents: Decoupling the brain from the hands (Anthropic Engineering, April 8 2026)"
[2]: https://platform.claude.com/docs/en/managed-agents/sessions "Anthropic — Start a session (Managed Agents docs)"
[3]: https://platform.claude.com/docs/en/managed-agents/memory "Anthropic — Using agent memory (Managed Agents docs)"
[4]: https://platform.claude.com/docs/en/managed-agents/dreams "Anthropic — Dreams (Managed Agents docs)"
[5]: https://platform.claude.com/docs/en/managed-agents/multi-agent "Anthropic — Multiagent sessions (Managed Agents docs)"
[6]: https://platform.claude.com/docs/en/managed-agents/events-and-streaming "Anthropic — Session event stream (Managed Agents docs)"
[7]: https://github.com/anthropics/skills/blob/main/skills/claude-api/shared/managed-agents-api-reference.md "anthropics/skills — Managed Agents API reference (rate limits, model IDs, beta headers)"
[8]: https://openai.github.io/openai-agents-python/guardrails/ "OpenAI Agents Python SDK — Guardrails"

- [Scaling Managed Agents: Decoupling the brain from the hands][1]
- [Sessions (Managed Agents docs)][2]
- [Memory (Managed Agents docs)][3]
- [Dreams (Managed Agents docs)][4]
- [Multi-agent sessions (Managed Agents docs)][5]
- [Events & streaming (Managed Agents docs)][6]
- [Managed Agents API reference (anthropics/skills)][7]
- [OpenAI Agents Python SDK — Guardrails][8]
