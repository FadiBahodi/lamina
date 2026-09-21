"""Local durable jobs. Transactions own claims; models never own job identity."""
from __future__ import annotations

import hashlib
import json
import sqlite3
import threading
import time
import uuid
from contextlib import contextmanager
from pathlib import Path
from typing import Callable


def canonical(value: object) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False)


def digest(value: object) -> str:
    return hashlib.sha256(canonical(value).encode()).hexdigest()


class Workspace:
    """One SQLite workspace, with short-lived connections safe across threads.

    SQLite WAL supports concurrent workers on one local filesystem, not a
    distributed queue. A renewable lease recovers abandoned jobs; a fencing
    token prevents an expired owner from committing over its replacement.
    """

    def __init__(self, root: Path, *, lease_seconds: float = 60):
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)
        self.path = self.root / "workspace.sqlite3"
        self.lease_seconds = lease_seconds
        if lease_seconds <= 0:
            raise ValueError("lease_seconds must be positive")
        with self.connection() as db:
            db.execute("PRAGMA journal_mode=WAL")
            db.executescript("""
            CREATE TABLE IF NOT EXISTS sources (
                id TEXT PRIMARY KEY, role TEXT NOT NULL, data TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS units (
                id TEXT PRIMARY KEY, source_id TEXT NOT NULL REFERENCES sources(id),
                role TEXT NOT NULL, ordinal INTEGER NOT NULL, data TEXT NOT NULL
            );
            CREATE INDEX IF NOT EXISTS units_source ON units(source_id, ordinal);
            CREATE TABLE IF NOT EXISTS jobs (
                key TEXT PRIMARY KEY, stage TEXT NOT NULL, identity TEXT NOT NULL,
                status TEXT NOT NULL, owner TEXT, lease_until REAL,
                attempts INTEGER NOT NULL DEFAULT 0, result TEXT, error TEXT,
                created_at REAL NOT NULL, updated_at REAL NOT NULL
            );
            CREATE INDEX IF NOT EXISTS jobs_status ON jobs(status);
            """)

    @contextmanager
    def connection(self):
        db = sqlite3.connect(self.path, timeout=30)
        db.row_factory = sqlite3.Row
        db.execute("PRAGMA foreign_keys=ON")
        try:
            with db:
                yield db
        finally:
            db.close()

    def put_source(self, source: dict) -> None:
        if source.get("role") not in {"teaching", "assessment"}:
            raise ValueError("Source role must be teaching or assessment")
        with self.connection() as db:
            old = db.execute("SELECT role FROM sources WHERE id=?", (source["id"],)).fetchone()
            if old and old["role"] != source["role"]:
                raise ValueError("Identical content already has a different role; use separate workspaces for different policies")
            db.execute("INSERT OR IGNORE INTO sources VALUES (?,?,?)", (source["id"], source["role"], canonical(source)))

    def put_units(self, units: list[dict]) -> None:
        with self.connection() as db:
            for unit in units:
                source = db.execute("SELECT role FROM sources WHERE id=?", (unit["source_id"],)).fetchone()
                if not source or source["role"] != unit["role"]:
                    raise ValueError("Unit must inherit the role of its source")
                db.execute("INSERT OR IGNORE INTO units VALUES (?,?,?,?,?)", (
                    unit["id"], unit["source_id"], unit["role"], unit["ordinal"], canonical(unit)))

    def sources(self) -> list[dict]:
        with self.connection() as db:
            return [json.loads(r[0]) for r in db.execute("SELECT data FROM sources ORDER BY id")]

    def units(self, role: str | None = None) -> list[dict]:
        with self.connection() as db:
            sql = "SELECT data FROM units"
            params = ()
            if role is not None:
                sql += " WHERE role=?"
                params = (role,)
            return [json.loads(r[0]) for r in db.execute(sql + " ORDER BY source_id,ordinal", params)]

    def run_cached(self, stage: str, payload: dict, handler: Callable[[dict], dict], *,
                   identity: str, retries: int = 1) -> dict:
        if retries < 0:
            raise ValueError("retries cannot be negative")
        key = digest({"version": 1, "stage": stage, "identity": identity, "payload": payload})
        owner = uuid.uuid4().hex
        failures = 0
        waiting_since = time.monotonic()
        while True:
            now = time.time()
            claimed = False
            with self.connection() as db:
                db.execute("BEGIN IMMEDIATE")
                db.execute("INSERT OR IGNORE INTO jobs (key,stage,identity,status,created_at,updated_at) VALUES (?,?,?,'pending',?,?)",
                           (key, stage, identity, now, now))
                row = db.execute("SELECT * FROM jobs WHERE key=?", (key,)).fetchone()
                if row["status"] == "completed":
                    return json.loads(row["result"])
                if row["status"] != "running" or (row["lease_until"] or 0) < now:
                    db.execute("UPDATE jobs SET status='running',owner=?,lease_until=?,attempts=attempts+1,error=NULL,updated_at=? WHERE key=?",
                               (owner, now + self.lease_seconds, now, key))
                    claimed = True
            if not claimed:
                if time.monotonic() - waiting_since > 600:
                    raise TimeoutError(f"Timed out waiting for shared {stage} job")
                time.sleep(0.05)
                continue
            stop = threading.Event()

            def heartbeat():
                while not stop.wait(max(0.02, self.lease_seconds / 3)):
                    try:
                        with self.connection() as db:
                            db.execute("UPDATE jobs SET lease_until=?,updated_at=? WHERE key=? AND owner=? AND status='running'",
                                       (time.time() + self.lease_seconds, time.time(), key, owner))
                    except sqlite3.Error:
                        # A failed renewal never grants an expired owner commit rights.
                        pass

            pulse = threading.Thread(target=heartbeat, daemon=True)
            pulse.start()
            try:
                result = handler(payload)
                if not isinstance(result, dict):
                    raise ValueError("Job handlers must return JSON objects")
                encoded = canonical(result)
                with self.connection() as db:
                    updated = db.execute("UPDATE jobs SET status='completed',result=?,lease_until=NULL,updated_at=? WHERE key=? AND owner=? AND status='running' AND lease_until>=?",
                                         (encoded, time.time(), key, owner, time.time())).rowcount
                if not updated:
                    raise RuntimeError("Job lease was lost; discarded stale result")
                return result
            except Exception as exc:
                with self.connection() as db:
                    db.execute("UPDATE jobs SET status='failed',error=?,lease_until=NULL,updated_at=? WHERE key=? AND owner=? AND status='running'",
                               (str(exc)[:1000], time.time(), key, owner))
                failures += 1
                if failures > retries:
                    raise
            finally:
                stop.set()
                pulse.join(timeout=1)

    def stats(self) -> dict:
        with self.connection() as db:
            states = {r[0]: r[1] for r in db.execute("SELECT status,COUNT(*) FROM jobs GROUP BY status")}
            return {"sources": db.execute("SELECT COUNT(*) FROM sources").fetchone()[0],
                    "units": db.execute("SELECT COUNT(*) FROM units").fetchone()[0],
                    "teaching_units": db.execute("SELECT COUNT(*) FROM units WHERE role='teaching'").fetchone()[0],
                    "assessment_units": db.execute("SELECT COUNT(*) FROM units WHERE role='assessment'").fetchone()[0],
                    "jobs": states,
                    "attempts": db.execute("SELECT COALESCE(SUM(attempts),0) FROM jobs").fetchone()[0]}
