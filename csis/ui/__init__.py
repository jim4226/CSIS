"""csis.ui — live dashboard for the running CSIS daemon / burst / loop.

Run with:

    python -m csis.ui [--port 8765] [--host 127.0.0.1] [--root .]

Reads from on-disk artifacts (event log, budget tracker, .calls.jsonl
sidecars, memory store JSONs, daemon.heartbeat + daemon.stats.json).
Read-only by default. Serves a single-page dashboard at /.
"""
