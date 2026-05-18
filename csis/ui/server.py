"""HTTP server for the CSIS live dashboard.

Single-process, stdlib-only (http.server). Reads from on-disk artifacts
the daemon/burst/loop write — no coupling, no shared state. Default
host is 127.0.0.1 so the dashboard is not exposed beyond localhost
unless the operator explicitly opts in.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
from collections import Counter, defaultdict
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

STATIC_DIR = Path(__file__).resolve().parent / "static"


class State:
    """Holds the resolved CSIS state-root path. Set once at startup."""

    root: Path = Path(".")


# ---------------------------------------------------------------------- helpers


def _safe_read_json(path: Path) -> dict | list | None:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError, OSError):
        return None


def _tail_jsonl(path: Path, limit: int) -> list[dict]:
    """Read the last `limit` lines of a JSON-lines file. Returns
    chronological order (oldest first)."""
    if not path.exists():
        return []
    try:
        # For small-to-medium files this is fast enough; for huge files
        # we'd want to seek-from-end, but the daemon already keeps these
        # bounded.
        lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
    except OSError:
        return []
    out: list[dict] = []
    for line in lines[-limit:]:
        line = line.strip()
        if not line:
            continue
        try:
            out.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    return out


def _discover_call_logs() -> list[Path]:
    """Return all `brain/*.calls.jsonl` sidecars present."""
    brain = State.root / "brain"
    if not brain.exists():
        return []
    return sorted(brain.glob("*.calls.jsonl"))


def _discover_budgets() -> list[Path]:
    brain = State.root / "brain"
    if not brain.exists():
        return []
    # Exclude .lock / .wal siblings — only the data files.
    out: list[Path] = []
    for p in sorted(brain.glob("*.budget.json")):
        if p.suffix == ".json":
            out.append(p)
    return out


# ---------------------------------------------------------------------- endpoints


def endpoint_status() -> dict:
    """Aggregate "is the daemon alive?" view."""
    brain = State.root / "brain"
    heartbeat = brain / "daemon.heartbeat"
    stats_path = brain / "daemon.stats.json"
    stats = _safe_read_json(stats_path) or {}

    hb_age_s: float | None = None
    daemon_alive = False
    if heartbeat.exists():
        try:
            mtime = heartbeat.stat().st_mtime
            hb_age_s = round(time.time() - mtime, 2)
            # Consider alive if heartbeat is fresh in the last 5 minutes.
            daemon_alive = hb_age_s < 300
        except OSError:
            pass

    return {
        "now": time.time(),
        "csis_root": str(State.root.resolve()),
        "daemon": {
            "alive": daemon_alive,
            "heartbeat_age_s": hb_age_s,
            "started_at": stats.get("started_at"),
            "iterations_total": stats.get("iterations_total", 0),
            "iterations_promoted": stats.get("iterations_promoted", 0),
            "iterations_rolled_back": stats.get("iterations_rolled_back", 0),
            "rollback_reason_counts": stats.get("rollback_reason_counts", {}),
            "skills_promoted": stats.get("skills_promoted", 0),
            "last_iteration_at": stats.get("last_iteration_at"),
        },
    }


def endpoint_cost() -> dict:
    """Aggregate cost across every BudgetTracker file under brain/."""
    out_per_tracker: list[dict] = []
    total_today_usd = 0.0
    total_today_calls = 0
    pending_total = 0.0
    for budget_path in _discover_budgets():
        data = _safe_read_json(budget_path)
        if not isinstance(data, dict):
            continue
        days = data.get("days", []) or []
        today = days[0] if days else None
        today_cost = (today or {}).get("cost_usd", 0.0)
        today_calls = (today or {}).get("calls", 0)
        pending = sum(
            float(p.get("amount_usd", 0))
            for p in data.get("pending", []) or []
        )
        out_per_tracker.append({
            "path": str(budget_path.relative_to(State.root)).replace("\\", "/"),
            "today_cost_usd": today_cost,
            "today_calls": today_calls,
            "today_tokens_in": (today or {}).get("tokens_in", 0),
            "today_tokens_out": (today or {}).get("tokens_out", 0),
            "pending_reservations_usd": round(pending, 4),
            "history_days": len(days),
        })
        total_today_usd += today_cost
        total_today_calls += today_calls
        pending_total += pending

    # Per-call sidecar aggregation for the last hour (burn rate, p50/p95 latency).
    calls_last_hour: list[dict] = []
    cutoff = time.time() - 3600
    for log_path in _discover_call_logs():
        for rec in _tail_jsonl(log_path, 5000):
            if rec.get("ts", 0) >= cutoff:
                calls_last_hour.append(rec)
    calls_last_hour.sort(key=lambda r: r.get("ts", 0))

    by_model: dict[str, dict] = defaultdict(lambda: {"calls": 0, "cost_usd": 0.0, "tokens_out": 0})
    latencies: list[int] = []
    burn_per_min: dict[int, float] = defaultdict(float)
    for r in calls_last_hour:
        model = r.get("model_id", "unknown")
        by_model[model]["calls"] += 1
        by_model[model]["cost_usd"] += float(r.get("cost_usd", 0.0))
        by_model[model]["tokens_out"] += int(r.get("tokens_out", 0) or 0)
        lat = r.get("latency_ms") or r.get("elapsed_ms")
        if isinstance(lat, (int, float)):
            latencies.append(int(lat))
        ts = r.get("ts", 0)
        minute = int(ts // 60) if ts else 0
        burn_per_min[minute] += float(r.get("cost_usd", 0.0))

    latencies.sort()

    def pct(p: int) -> int | None:
        if not latencies:
            return None
        i = max(0, min(len(latencies) - 1, int(round((p / 100) * (len(latencies) - 1)))))
        return latencies[i]

    return {
        "trackers": out_per_tracker,
        "total_today_usd": round(total_today_usd, 4),
        "total_today_calls": total_today_calls,
        "pending_reservations_usd": round(pending_total, 4),
        "last_hour": {
            "calls": len(calls_last_hour),
            "cost_usd": round(sum(r.get("cost_usd", 0.0) for r in calls_last_hour), 4),
            "burn_rate_usd_per_min": round(
                sum(r.get("cost_usd", 0.0) for r in calls_last_hour) / 60.0, 6
            ),
            "by_model": [
                {"model": m, **{k: round(v, 4) if isinstance(v, float) else v for k, v in d.items()}}
                for m, d in by_model.items()
            ],
            "latency_ms": {
                "p50": pct(50),
                "p95": pct(95),
                "p99": pct(99),
                "count": len(latencies),
            },
        },
    }


def endpoint_events(limit: int) -> dict:
    """Recent rows from the event log."""
    cfg_path = State.root / "event_log" / "session.jsonl"
    rows = _tail_jsonl(cfg_path, limit)
    # Each row is a signed event: {"seq", "event", "prev_hash", "hash", ...}
    return {
        "events": rows[::-1],  # newest first for display
        "count": len(rows),
        "source": str(cfg_path.relative_to(State.root)).replace("\\", "/")
                  if cfg_path.exists() else None,
    }


def endpoint_calls(limit: int) -> dict:
    """Recent per-call rows across all .calls.jsonl sidecars."""
    rows: list[dict] = []
    for log_path in _discover_call_logs():
        for rec in _tail_jsonl(log_path, limit * 2):
            rec["_sidecar"] = log_path.stem.replace(".calls", "")
            rows.append(rec)
    rows.sort(key=lambda r: r.get("ts", 0), reverse=True)
    return {
        "calls": rows[:limit],
        "total_sidecars": len(_discover_call_logs()),
    }


def endpoint_memory() -> dict:
    """Per-tier candidate + live counts."""
    memory_root = State.root / "memory_store"
    tiers = ("working", "episodic", "semantic", "procedural", "causal")
    out = {}
    for tier in tiers:
        cand = _safe_read_json(memory_root / f"{tier}.candidate.json") or {}
        live = _safe_read_json(memory_root / f"{tier}.live.json") or {}
        out[tier] = {
            "candidate_count": len(cand) if isinstance(cand, dict) else 0,
            "live_count": len(live) if isinstance(live, dict) else 0,
        }
    out["_root"] = str(memory_root.relative_to(State.root)).replace("\\", "/") \
        if memory_root.exists() else None
    return out


def endpoint_tripwires(limit: int) -> dict:
    """Mine the event log for tripwire firings."""
    cfg_path = State.root / "event_log" / "session.jsonl"
    rows = _tail_jsonl(cfg_path, 2000)
    firings: list[dict] = []
    for sig in rows:
        ev = sig.get("event") or {}
        if ev.get("kind") == "tripwire.fired":
            firings.append({
                "ts": sig.get("ts"),
                "seq": sig.get("seq"),
                "payload": ev.get("payload", {}),
            })
    return {
        "firings": firings[-limit:][::-1],
        "total_in_window": len(firings),
        "window_size": len(rows),
    }


def endpoint_summary() -> dict:
    """One-call bundle for the dashboard's first paint — avoids 5
    sequential requests on page load."""
    return {
        "status": endpoint_status(),
        "cost": endpoint_cost(),
        "memory": endpoint_memory(),
        "tripwires": endpoint_tripwires(10),
        "events": endpoint_events(20),
        "calls": endpoint_calls(30),
    }


# ---------------------------------------------------------------------- routing


ROUTES = {
    "/api/status": lambda q: endpoint_status(),
    "/api/cost": lambda q: endpoint_cost(),
    "/api/memory": lambda q: endpoint_memory(),
    "/api/summary": lambda q: endpoint_summary(),
    "/api/events": lambda q: endpoint_events(int(q.get("limit", ["50"])[0])),
    "/api/calls": lambda q: endpoint_calls(int(q.get("limit", ["50"])[0])),
    "/api/tripwires": lambda q: endpoint_tripwires(int(q.get("limit", ["20"])[0])),
}


class Handler(BaseHTTPRequestHandler):
    """Read-only dashboard handler."""

    server_version = "csis-ui/0.1"

    def log_message(self, format, *args):
        # Quieter than the default per-request access log. Skip favicon
        # noise. `args` may contain non-string items (e.g., HTTPStatus
        # enum on error paths) so coerce defensively.
        first = str(args[0]) if args else ""
        if "favicon" in first:
            return
        try:
            line = format % args
        except Exception:
            line = " ".join(str(a) for a in args)
        sys.stderr.write(f"[ui] {self.address_string()} - {line}\n")

    def _send_json(self, data: dict | list, status: int = 200) -> None:
        body = json.dumps(data, default=str).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        # Allow the dashboard at any port to fetch from this server when
        # they're co-resident. Cross-origin is fine because we're read-only
        # and bind to 127.0.0.1 by default.
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(body)

    def _send_file(self, path: Path, content_type: str) -> None:
        try:
            body = path.read_bytes()
        except OSError:
            self.send_error(404, "Not Found")
            return
        self.send_response(200)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        parsed = urlparse(self.path)
        path = parsed.path
        query = parse_qs(parsed.query)

        if path == "/" or path == "/index.html":
            self._send_file(STATIC_DIR / "dashboard.html", "text/html; charset=utf-8")
            return
        if path == "/favicon.ico":
            self.send_response(204)
            self.end_headers()
            return

        if path in ROUTES:
            try:
                self._send_json(ROUTES[path](query))
            except Exception as exc:  # noqa: BLE001
                self._send_json({"error": str(exc), "type": type(exc).__name__}, status=500)
            return

        # Static asset
        if path.startswith("/static/"):
            asset = STATIC_DIR / path[len("/static/"):]
            # Prevent path traversal
            try:
                asset.resolve().relative_to(STATIC_DIR.resolve())
            except ValueError:
                self.send_error(403, "Forbidden")
                return
            if asset.suffix == ".html":
                ct = "text/html; charset=utf-8"
            elif asset.suffix == ".css":
                ct = "text/css; charset=utf-8"
            elif asset.suffix == ".js":
                ct = "application/javascript; charset=utf-8"
            elif asset.suffix == ".svg":
                ct = "image/svg+xml"
            else:
                ct = "application/octet-stream"
            self._send_file(asset, ct)
            return

        self.send_error(404, "Not Found")


# ---------------------------------------------------------------------- entry


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="CSIS live dashboard — single-page UI for the daemon/burst/loop."
    )
    parser.add_argument("--port", type=int, default=8765,
                        help="port to bind (default 8765)")
    parser.add_argument("--host", default="127.0.0.1",
                        help="host to bind (default 127.0.0.1; set 0.0.0.0 to expose beyond localhost)")
    parser.add_argument("--root", default=".",
                        help="path to the CSIS state root (default: current working directory). "
                             "The server reads brain/, event_log/, memory_store/ underneath this.")
    parser.add_argument("--no-open", action="store_true",
                        help="do not open the dashboard in a browser on start")
    args = parser.parse_args(argv)

    State.root = Path(args.root).resolve()
    if not State.root.exists():
        print(f"[ui] root path does not exist: {State.root}", file=sys.stderr)
        return 2

    server = ThreadingHTTPServer((args.host, args.port), Handler)
    url = f"http://{args.host}:{args.port}/"
    print(f"[ui] CSIS dashboard serving at {url}")
    print(f"[ui] state root: {State.root}")
    print(f"[ui]   event log: {(State.root / 'event_log').exists() and 'present' or 'missing (no events yet)'}")
    print(f"[ui]   memory store: {(State.root / 'memory_store').exists() and 'present' or 'missing'}")
    print(f"[ui]   budgets found: {len(_discover_budgets())}")
    print(f"[ui]   call logs found: {len(_discover_call_logs())}")
    print(f"[ui] Ctrl-C to stop")

    if not args.no_open:
        try:
            import webbrowser
            webbrowser.open(url)
        except Exception:
            pass

    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\n[ui] shutting down")
        server.shutdown()
    return 0
