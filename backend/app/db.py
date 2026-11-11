"""SQLite document store.

Each aggregate (benchmark, task, agent, run) is stored as a JSON document that is
*exactly* the shape the frontend expects, next to a few indexed columns. This keeps the
API contract in one place (the document) and makes a later move to PostgreSQL trivial.
Hidden test suites live in their own column and are never part of a task document.
"""
from __future__ import annotations

import json
import sqlite3
import threading
from typing import Any, Iterable

SCHEMA = """
CREATE TABLE IF NOT EXISTS benchmarks (id TEXT PRIMARY KEY, position INTEGER, doc TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS tasks (
    id TEXT PRIMARY KEY, benchmark_id TEXT NOT NULL, position INTEGER, doc TEXT NOT NULL,
    hidden_tests TEXT
);
CREATE INDEX IF NOT EXISTS idx_tasks_bench ON tasks(benchmark_id, position);
CREATE TABLE IF NOT EXISTS agents (id TEXT PRIMARY KEY, position INTEGER, doc TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS runs (
    seq INTEGER PRIMARY KEY AUTOINCREMENT, id TEXT UNIQUE, benchmark_id TEXT, status TEXT,
    started_at TEXT, mode TEXT, doc TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS events (
    id INTEGER PRIMARY KEY AUTOINCREMENT, run_id TEXT NOT NULL, doc TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_events_run ON events(run_id, id);
CREATE TABLE IF NOT EXISTS model_calls (
    id TEXT PRIMARY KEY,
    run_id TEXT NOT NULL,
    agent_id TEXT,
    task_id TEXT,
    seq INTEGER,
    doc TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_model_calls_run ON model_calls(run_id, seq);
CREATE INDEX IF NOT EXISTS idx_model_calls_agent ON model_calls(run_id, agent_id);
CREATE INDEX IF NOT EXISTS idx_model_calls_task ON model_calls(run_id, task_id);
"""

RUN_ID_OFFSET = 2500


class Store:
    def __init__(self, path: str):
        self._lock = threading.RLock()
        self._conn = sqlite3.connect(path, check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        with self._lock:
            self._conn.execute("PRAGMA journal_mode=WAL")
            self._conn.executescript(SCHEMA)
            self._conn.commit()

    # -- helpers -----------------------------------------------------------
    def _q(self, sql: str, params: Iterable[Any] = ()) -> list[sqlite3.Row]:
        with self._lock:
            return self._conn.execute(sql, tuple(params)).fetchall()

    def _x(self, sql: str, params: Iterable[Any] = ()) -> sqlite3.Cursor:
        with self._lock:
            cur = self._conn.execute(sql, tuple(params))
            self._conn.commit()
            return cur

    # -- benchmarks --------------------------------------------------------
    def count_benchmarks(self) -> int:
        return self._q("SELECT COUNT(*) c FROM benchmarks")[0]["c"]

    def put_benchmark(self, doc: dict, position: int) -> None:
        self._x("INSERT OR REPLACE INTO benchmarks(id, position, doc) VALUES (?,?,?)",
                (doc["id"], position, json.dumps(doc)))

    def list_benchmarks(self) -> list[dict]:
        return [json.loads(r["doc"]) for r in self._q("SELECT doc FROM benchmarks ORDER BY position")]

    def get_benchmark(self, bid: str) -> dict | None:
        r = self._q("SELECT doc FROM benchmarks WHERE id=?", (bid,))
        return json.loads(r[0]["doc"]) if r else None

    # -- tasks -------------------------------------------------------------
    def put_task(self, doc: dict, position: int, hidden_tests: str | None) -> None:
        self._x("INSERT OR REPLACE INTO tasks(id, benchmark_id, position, doc, hidden_tests) VALUES (?,?,?,?,?)",
                (doc["id"], doc["benchmark_id"], position, json.dumps(doc), hidden_tests))

    def get_task(self, task_id: str) -> dict | None:
        r = self._q("SELECT doc FROM tasks WHERE id=?", (task_id,))
        return json.loads(r[0]["doc"]) if r else None

    def count_tasks(self, benchmark_id: str | None = None) -> int:
        if benchmark_id:
            return self._q("SELECT COUNT(*) c FROM tasks WHERE benchmark_id=?", (benchmark_id,))[0]["c"]
        return self._q("SELECT COUNT(*) c FROM tasks")[0]["c"]

    def list_tasks(
        self,
        benchmark_id: str | None = None,
        *,
        search: str | None = None,
        difficulty: str | None = None,
        category: str | None = None,
        limit: int | None = None,
        offset: int = 0,
    ) -> list[dict]:
        """List tasks with optional filters. Filtering on JSON fields is done in Python
        for SQLite portability; result is ordered by benchmark_id, position."""
        if benchmark_id:
            rows = self._q(
                "SELECT doc FROM tasks WHERE benchmark_id=? ORDER BY position",
                (benchmark_id,),
            )
        else:
            rows = self._q("SELECT doc FROM tasks ORDER BY benchmark_id, position")
        out = [json.loads(r["doc"]) for r in rows]
        if search:
            q = search.strip().lower()
            if q:
                out = [
                    t for t in out
                    if q in (t.get("title") or "").lower()
                    or q in (t.get("id") or "").lower()
                    or q in (t.get("category") or "").lower()
                    or any(q in str(tag).lower() for tag in (t.get("tags") or []))
                ]
        if difficulty:
            d = difficulty.strip().lower()
            out = [t for t in out if (t.get("difficulty") or "").lower() == d]
        if category:
            c = category.strip().lower()
            out = [t for t in out if (t.get("category") or "").lower() == c]
        if offset:
            out = out[offset:]
        if limit is not None:
            out = out[:limit]
        return out

    def tasks_with_hidden(self, benchmark_id: str) -> list[tuple[dict, str | None]]:
        rows = self._q("SELECT doc, hidden_tests FROM tasks WHERE benchmark_id=? ORDER BY position", (benchmark_id,))
        return [(json.loads(r["doc"]), r["hidden_tests"]) for r in rows]

    def has_hidden_tests(self, task_id: str) -> bool:
        r = self._q("SELECT hidden_tests FROM tasks WHERE id=?", (task_id,))
        if not r:
            return False
        ht = r[0]["hidden_tests"]
        return bool(ht and str(ht).strip())

    # -- agents ------------------------------------------------------------
    def list_agents(self) -> list[dict]:
        return [json.loads(r["doc"]) for r in self._q("SELECT doc FROM agents ORDER BY position, id")]

    def get_agent(self, aid: str) -> dict | None:
        r = self._q("SELECT doc FROM agents WHERE id=?", (aid,))
        return json.loads(r[0]["doc"]) if r else None

    def put_agent(self, doc: dict) -> None:
        pos = self._q("SELECT COALESCE(MAX(position), -1) + 1 p FROM agents")[0]["p"]
        existing = self._q("SELECT position FROM agents WHERE id=?", (doc["id"],))
        if existing:
            pos = existing[0]["position"]
        self._x("INSERT OR REPLACE INTO agents(id, position, doc) VALUES (?,?,?)", (doc["id"], pos, json.dumps(doc)))

    # -- runs --------------------------------------------------------------
    def insert_run(self, doc: dict, mode: str) -> dict:
        """Insert a run, allocating its public id (run-<n>) from the autoincrement sequence."""
        with self._lock:
            cur = self._conn.execute(
                "INSERT INTO runs(id, benchmark_id, status, started_at, mode, doc) VALUES (?,?,?,?,?,?)",
                (f"tmp-{id(doc)}", doc["benchmark_id"], doc["status"], doc["started_at"], mode, "{}"),
            )
            run_id = f"run-{RUN_ID_OFFSET + cur.lastrowid}"
            doc = {**doc, "id": run_id}
            if not doc.get("name"):
                doc["name"] = f"{doc['benchmark_name']} · {run_id}"
            self._conn.execute("UPDATE runs SET id=?, doc=? WHERE seq=?", (run_id, json.dumps(doc), cur.lastrowid))
            self._conn.commit()
        return doc

    def update_run(self, doc: dict) -> None:
        self._x("UPDATE runs SET status=?, doc=? WHERE id=?", (doc["status"], json.dumps(doc), doc["id"]))

    def get_run(self, rid: str) -> dict | None:
        r = self._q("SELECT doc FROM runs WHERE id=?", (rid,))
        return json.loads(r[0]["doc"]) if r else None

    def get_run_mode(self, rid: str) -> str:
        r = self._q("SELECT mode FROM runs WHERE id=?", (rid,))
        return r[0]["mode"] if r else "simulated"

    def list_runs(self, benchmark_id: str | None = None, status: str | None = None,
                  limit: int = 200, offset: int = 0) -> list[dict]:
        sql, params = "SELECT doc, mode FROM runs WHERE 1=1", []
        if benchmark_id:
            sql += " AND benchmark_id=?"; params.append(benchmark_id)
        if status:
            sql += " AND status=?"; params.append(status)
        sql += " ORDER BY seq DESC LIMIT ? OFFSET ?"; params += [limit, offset]
        out = []
        for r in self._q(sql, params):
            d = json.loads(r["doc"]); d["execution_mode"] = r["mode"]; out.append(d)
        return out

    def fail_interrupted_runs(self) -> int:
        n = 0
        for r in self._q("SELECT doc FROM runs WHERE status IN ('queued','running')"):
            d = json.loads(r["doc"])
            d["status"] = "failed"
            d["notes"] = (d.get("notes", "") + " [interrupted by server restart]").strip()
            self.update_run(d); n += 1
        return n

    # -- events ------------------------------------------------------------
    def add_event(self, run_id: str, doc: dict) -> int:
        """Persist a structured event. Returns the SQLite event id.

        Expected fields (all optional except type/message or type):
          type, message, agent_id, task_id, status, duration_ms,
          gateway_request_id, metadata
        """
        payload = dict(doc)
        payload.setdefault("run_id", run_id)
        if "ts" not in payload:
            from datetime import datetime, timezone
            payload["ts"] = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        cur = self._x("INSERT INTO events(run_id, doc) VALUES (?,?)", (run_id, json.dumps(payload)))
        eid = int(cur.lastrowid)
        # Store event_id back into doc for readers that only see the JSON blob
        payload["event_id"] = eid
        self._x("UPDATE events SET doc=? WHERE id=?", (json.dumps(payload), eid))
        return eid

    def events_after(self, run_id: str, after_id: int = 0) -> list[tuple[int, dict]]:
        rows = self._q("SELECT id, doc FROM events WHERE run_id=? AND id>? ORDER BY id", (run_id, after_id))
        out = []
        for r in rows:
            d = json.loads(r["doc"])
            d.setdefault("event_id", r["id"])
            out.append((r["id"], d))
        return out

    def list_events(self, run_id: str) -> list[dict]:
        """All events for a run in chronological order (by id)."""
        return [ev for _, ev in self.events_after(run_id, 0)]

    # -- model call traces -------------------------------------------------
    def add_model_call(self, doc: dict) -> str:
        """Persist a model-call trace document. Returns call id."""
        call_id = doc.get("id") or f"mc_{id(doc)}"
        run_id = doc.get("run_id") or ""
        with self._lock:
            row = self._conn.execute(
                "SELECT COALESCE(MAX(seq), 0) + 1 AS n FROM model_calls WHERE run_id=?",
                (run_id,),
            ).fetchone()
            seq = int(row["n"])
            doc = dict(doc)
            doc["id"] = call_id
            doc["seq"] = seq
            self._conn.execute(
                "INSERT INTO model_calls(id, run_id, agent_id, task_id, seq, doc) VALUES (?,?,?,?,?,?)",
                (call_id, run_id, doc.get("agent_id"), doc.get("task_id"), seq, json.dumps(doc)),
            )
            self._conn.commit()
        return call_id

    def list_model_calls(
        self,
        run_id: str,
        *,
        agent_id: str | None = None,
        errors_only: bool = False,
        offset: int = 0,
        limit: int = 200,
    ) -> list[dict]:
        sql = "SELECT doc FROM model_calls WHERE run_id=?"
        params: list = [run_id]
        if agent_id:
            sql += " AND agent_id=?"
            params.append(agent_id)
        sql += " ORDER BY seq ASC LIMIT ? OFFSET ?"
        params.extend([limit, offset])
        rows = self._q(sql, params)
        out = []
        for r in rows:
            d = json.loads(r["doc"])
            if errors_only and d.get("success", True):
                continue
            out.append(d)
        return out

    def get_model_call(self, call_id: str) -> dict | None:
        rows = self._q("SELECT doc FROM model_calls WHERE id=?", (call_id,))
        return json.loads(rows[0]["doc"]) if rows else None

    def list_model_calls_for_runs(self, run_ids: list[str], limit: int = 5000) -> list[dict]:
        """Model-call documents for many runs, chronological within each run."""
        if not run_ids:
            return []
        out: list[dict] = []
        for i in range(0, len(run_ids), 200):
            chunk = run_ids[i:i + 200]
            marks = ",".join("?" * len(chunk))
            rows = self._q(
                f"SELECT doc FROM model_calls WHERE run_id IN ({marks}) ORDER BY run_id, seq",
                tuple(chunk),
            )
            for r in rows:
                out.append(json.loads(r["doc"]))
                if len(out) >= limit:
                    return out
        return out

    def model_call_summary(self, run_id: str) -> dict:
        rows = self._q("SELECT doc FROM model_calls WHERE run_id=? ORDER BY seq", (run_id,))
        calls = [json.loads(r["doc"]) for r in rows]
        by_agent: dict = {}
        total_in = total_out = total_cached = 0
        saw_in = saw_out = saw_cached = False
        cost_sum = 0.0
        cost_known = False
        success = fail = 0
        latencies = []
        for c in calls:
            if c.get("success"):
                success += 1
            else:
                fail += 1
            if c.get("tokens_input") is not None:
                total_in += int(c["tokens_input"])
                saw_in = True
            if c.get("tokens_output") is not None:
                total_out += int(c["tokens_output"])
                saw_out = True
            if c.get("tokens_cached") is not None:
                total_cached += int(c["tokens_cached"])
                saw_cached = True
            if c.get("cost_usd") is not None and c.get("cost_source") == "gateway":
                cost_sum += float(c["cost_usd"])
                cost_known = True
            if c.get("latency_ms") is not None:
                latencies.append(float(c["latency_ms"]))
            aid = c.get("agent_id") or "unknown"
            slot = by_agent.setdefault(aid, {
                "agent_id": aid, "calls": 0, "success": 0, "failed": 0,
                "tokens_input": None, "tokens_output": None, "cost_usd": None, "cost_source": None,
            })
            slot["calls"] += 1
            slot["success" if c.get("success") else "failed"] += 1
            if c.get("tokens_input") is not None:
                slot["tokens_input"] = (slot["tokens_input"] or 0) + int(c["tokens_input"])
            if c.get("tokens_output") is not None:
                slot["tokens_output"] = (slot["tokens_output"] or 0) + int(c["tokens_output"])
            if c.get("cost_usd") is not None and c.get("cost_source") == "gateway":
                slot["cost_usd"] = (slot["cost_usd"] or 0) + float(c["cost_usd"])
                slot["cost_source"] = "gateway"
        return {
            "run_id": run_id,
            "total_calls": len(calls),
            "successful_calls": success,
            "failed_calls": fail,
            "tokens_input": total_in if saw_in else None,
            "tokens_output": total_out if saw_out else None,
            "tokens_cached": total_cached if saw_cached else None,
            "total_tokens": (total_in + total_out) if saw_in and saw_out else None,
            "cost_usd": cost_sum if cost_known else None,
            "cost_source": "gateway" if cost_known else None,
            "latency_ms_avg": (sum(latencies) / len(latencies)) if latencies else None,
            "latency_ms_p95": sorted(latencies)[int(len(latencies) * 0.95)] if len(latencies) >= 2 else (latencies[0] if latencies else None),
            "by_agent": list(by_agent.values()),
        }
