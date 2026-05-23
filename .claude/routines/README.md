# `.claude/routines/` — registered Claude Code routines for CSIS

This directory holds the **prompt files** for [Claude Code Routines](https://code.claude.com/docs/en/routines) that run against this repo on a schedule. The Routine itself lives on the operator's Anthropic account (visible at [claude.ai/code/routines](https://claude.ai/code/routines)); only the long-form prompt lives here, so we can version it and edit it via PRs.

## Active routines

| Routine | Schedule | Prompt | Branch prefix |
|---|---|---|---|
| **daily-improvement** | Daily, 07:00 ET (12:00 UTC) | [`daily-improvement.md`](daily-improvement.md) | `claude/daily-*` |

## How to register `daily-improvement`

### One-time setup (the operator, not the routine)

1. **Open** [claude.ai/code/routines](https://claude.ai/code/routines) → **New routine**.
2. **Name**: `CSIS daily improvement`
3. **Prompt** (paste verbatim — keep it short; the work is in the committed file):

   ```text
   Read .claude/routines/daily-improvement.md from this repository and execute
   it. The repo is CSIS, a continuous self-improving multi-agent system. Follow
   the file's six steps in order; commit a daily log under brain/routines/ and
   open draft PRs as the file specifies. End your run with a 1-3 sentence text
   summary of what shipped.
   ```

4. **Model**: Sonnet (Opus is overkill for this; Haiku is too light for the triage). The selector lives next to the prompt input.
5. **Repository**: `jim4226/CSIS`. Leave **Allow unrestricted branch pushes** *off* — the routine only needs `claude/`-prefixed branches.
6. **Environment**: pick or create one with the network access below.
7. **Trigger**: **Schedule** → **Daily** → `07:00` in your local zone (the UI converts to UTC). The minimum supported interval is 1h; daily is well above the floor. Custom cron (`0 12 * * *` UTC) is also fine via `/schedule update` if you prefer.
8. **Connectors**: only **GitHub** is needed. Remove any others that get auto-included — fewer connectors means smaller blast radius if the routine misbehaves.
9. **Save**, then click **Run now** once to validate. The first run's session shows up in the normal session list at [claude.ai/code](https://claude.ai/code).

### Required network access

The default **Trusted** environment does **not** include the Anthropic domains the routine needs to scan. Create or edit an environment with **Custom** network access and these **Allowed domains**:

```text
www.anthropic.com
anthropic.com
docs.claude.com
code.claude.com
platform.claude.com
support.claude.com
```

Check **Also include default list of common package managers** so `pip install` and friends still work during any pre-flight test runs the routine may do.

GitHub traffic flows through the GitHub MCP connector (Anthropic-bound channel), so `github.com` does **not** need to appear in Allowed domains.

### Environment variables

None are required. The routine relies only on cloned-repo state and GitHub MCP access.

## How to pause, edit, or remove

- **Pause**: open the routine in the UI → toggle off **Repeats**. The configuration is preserved; flip it back on to resume.
- **Edit prompt**: change `daily-improvement.md` here and open a PR. The next run picks up the new prompt the moment it's merged to `main`.
- **Edit schedule / model / network**: do it in the web UI. Those settings live on the routine, not in this repo.
- **Remove**: delete the routine from the UI. Past session transcripts stay in your session list. This directory can stay; an empty registered-routines table is harmless.

## What the routine produces

Each run writes one daily log to `brain/routines/YYYY-MM-DD.md`, appends to `brain/routines/index.md`, and opens between 0 and 4 draft PRs (1 log PR + up to 3 improvement PRs). See `daily-improvement.md` for the full output contract.

## Troubleshooting

| Symptom | Likely cause |
|---|---|
| Routine fails immediately with "host_not_allowed" | The environment is on **Trusted**, not **Custom** with Anthropic domains. See "Required network access" above. |
| `/schedule` is missing in the CLI | You're inside a Claude Code on the web session, or your CLI is on a Console API key. See [troubleshooting in the Routines docs](https://code.claude.com/docs/en/routines#troubleshooting). |
| Every day's run says "quiet day" even after a known Anthropic launch | Either the launch is older than the 9-day window (your routine has been idle), or the source page changed format and the index parsing failed silently. Open the most recent session transcript and search for "Sources unreachable" — most parse failures surface there. |
| PRs are opening on `main` instead of `claude/` branches | The routine's **Allow unrestricted branch pushes** got toggled on. Turn it back off. |
| Routine consumed all daily-run cap on one day | One-off / manual `Run now` clicks don't count, but recurring schedules do. If you've been triggering manually, switch to relying on the daily schedule. |
