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
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    )


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
            BEGIN IMMEDIATE;
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
            CREATE VIRTUAL TABLE IF NOT EXISTS units_fts USING fts5(
                id UNINDEXED, source_id UNINDEXED, role UNINDEXED, heading, text
            );
            CREATE TRIGGER IF NOT EXISTS units_search_insert AFTER INSERT ON units BEGIN
                INSERT INTO units_fts (rowid,id,source_id,role,heading,text) VALUES (new.rowid, new.id, new.source_id, new.role,
                    json_extract(new.data, '$.heading'), json_extract(new.data, '$.text'));
            END;
            CREATE TRIGGER IF NOT EXISTS units_search_delete AFTER DELETE ON units BEGIN
                DELETE FROM units_fts WHERE rowid=old.rowid;
            END;
            """)
            if db.execute("PRAGMA user_version").fetchone()[0] < 1:
                # One transactional migration, including a linear backfill.
                db.execute("DELETE FROM units_fts")
                db.execute(
                    "INSERT INTO units_fts (rowid,id,source_id,role,heading,text) "
                    "SELECT rowid,id,source_id,role,json_extract(data,'$.heading'),"
                    "json_extract(data,'$.text') FROM units"
                )
                db.execute("PRAGMA user_version=1")

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
            old = db.execute(
                "SELECT role FROM sources WHERE id=?", (source["id"],)
            ).fetchone()
            if old and old["role"] != source["role"]:
                raise ValueError(
                    "Identical content already has a different role; use separate workspaces for different policies"
                )
            db.execute(
                "INSERT OR IGNORE INTO sources VALUES (?,?,?)",
                (source["id"], source["role"], canonical(source)),
            )

    def put_units(self, units: list[dict]) -> None:
        with self.connection() as db:
            for unit in units:
                source = db.execute(
                    "SELECT role FROM sources WHERE id=?", (unit["source_id"],)
                ).fetchone()
                if not source or source["role"] != unit["role"]:
                    raise ValueError("Unit must inherit the role of its source")
                db.execute(
                    "INSERT OR IGNORE INTO units VALUES (?,?,?,?,?)",
                    (
                        unit["id"],
                        unit["source_id"],
                        unit["role"],
                        unit["ordinal"],
                        canonical(unit),
                    ),
                )

    def sources(self) -> list[dict]:
        with self.connection() as db:
            return [
                json.loads(r[0])
                for r in db.execute("SELECT data FROM sources ORDER BY id")
            ]

    def import_sources(self, parsed) -> None:
        """Atomically replace parser output for exact source revisions.

        Reimporting after a parser upgrade must not mix old and new chunking.
        Saved plans retain their original source text; new plans use this index.
        """
        with self.connection() as db:
            for source, units in parsed:
                old = db.execute(
                    "SELECT role FROM sources WHERE id=?", (source["id"],)
                ).fetchone()
                if old and old[0] != source["role"]:
                    raise ValueError(
                        "Identical content already exists under another source role"
                    )
                db.execute(
                    "INSERT INTO sources VALUES (?,?,?) ON CONFLICT(id) DO UPDATE SET data=excluded.data",
                    (source["id"], source["role"], canonical(source)),
                )
                db.execute("DELETE FROM units WHERE source_id=?", (source["id"],))
                db.executemany(
                    "INSERT INTO units VALUES (?,?,?,?,?)",
                    [
                        (
                            u["id"],
                            source["id"],
                            source["role"],
                            u["ordinal"],
                            canonical(u),
                        )
                        for u in units
                    ],
                )

    def search_units(self, query: str, limit: int = 8) -> list[dict]:
        """Indexed lexical candidates. Similarity is not a grouping decision."""
        import re

        if (
            not isinstance(query, str)
            or type(limit) is not int
            or not 1 <= limit <= 1000
        ):
            raise ValueError("search needs text and a limit from 1 to 1000")
        terms = sorted(set(re.findall(r"\w+", query.casefold())))
        if not terms:
            return []
        match = " OR ".join('"' + term + '"' for term in terms)
        with self.connection() as db:
            rows = db.execute(
                """SELECT u.data, bm25(units_fts,0,0,0,3,1) AS score
                FROM units_fts JOIN units u ON u.rowid=units_fts.rowid
                WHERE units_fts MATCH ? AND u.role='teaching'
                ORDER BY score, u.id LIMIT ?""",
                (match, limit),
            ).fetchall()
        return [
            {**json.loads(row[0]), "score": -row[1], "lanes": {"fts5": {"rank": i + 1}}}
            for i, row in enumerate(rows)
        ]

    def units(
        self, role: str | None = None, source_ids: list[str] | None = None
    ) -> list[dict]:
        with self.connection() as db:
            sql = "SELECT data FROM units"
            params, clauses = [], []
            if role is not None:
                clauses.append("role=?")
                params.append(role)
            if source_ids is not None:
                if not source_ids:
                    return []
                clauses.append(
                    "source_id IN (" + ",".join("?" for _ in source_ids) + ")"
                )
                params.extend(source_ids)
            if clauses:
                sql += " WHERE " + " AND ".join(clauses)
            return [
                json.loads(r[0])
                for r in db.execute(sql + " ORDER BY source_id,ordinal", params)
            ]

    def run_cached(
        self,
        stage: str,
        payload: dict,
        handler: Callable[[dict], dict],
        *,
        identity: str,
        retries: int = 1,
    ) -> dict:
        if retries < 0:
            raise ValueError("retries cannot be negative")
        key = digest(
            {"version": 1, "stage": stage, "identity": identity, "payload": payload}
        )
        owner = uuid.uuid4().hex
        failures = 0
        waiting_since = time.monotonic()
        while True:
            now = time.time()
            claimed = False
            # Observe completed entries and live owners without taking SQLite's
            # writer lock. Only a plausible claim/reclaim enters a transaction.
            with self.connection() as db:
                observed = db.execute(
                    "SELECT status,lease_until,result FROM jobs WHERE key=?", (key,)
                ).fetchone()
            if observed is not None and observed["status"] == "completed":
                return json.loads(observed["result"])
            if (
                observed is None
                or observed["status"] != "running"
                or (observed["lease_until"] or 0) < now
            ):
                with self.connection() as db:
                    db.execute("BEGIN IMMEDIATE")
                    # The observer can race another claimant or a renewal. The
                    # decision and lease time must use this locked, fresh state.
                    now = time.time()
                    db.execute(
                        "INSERT OR IGNORE INTO jobs (key,stage,identity,status,created_at,updated_at) VALUES (?,?,?,'pending',?,?)",
                        (key, stage, identity, now, now),
                    )
                    row = db.execute(
                        "SELECT * FROM jobs WHERE key=?", (key,)
                    ).fetchone()
                    if row["status"] == "completed":
                        return json.loads(row["result"])
                    if row["status"] != "running" or (row["lease_until"] or 0) < now:
                        db.execute(
                            "UPDATE jobs SET status='running',owner=?,lease_until=?,attempts=attempts+1,error=NULL,updated_at=? WHERE key=?",
                            (owner, now + self.lease_seconds, now, key),
                        )
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
                            db.execute(
                                "UPDATE jobs SET lease_until=?,updated_at=? WHERE key=? AND owner=? AND status='running'",
                                (
                                    time.time() + self.lease_seconds,
                                    time.time(),
                                    key,
                                    owner,
                                ),
                            )
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
                    updated = db.execute(
                        "UPDATE jobs SET status='completed',result=?,lease_until=NULL,updated_at=? WHERE key=? AND owner=? AND status='running' AND lease_until>=?",
                        (encoded, time.time(), key, owner, time.time()),
                    ).rowcount
                if not updated:
                    raise RuntimeError("Job lease was lost; discarded stale result")
                return result
            except Exception as exc:
                with self.connection() as db:
                    db.execute(
                        "UPDATE jobs SET status='failed',error=?,lease_until=NULL,updated_at=? WHERE key=? AND owner=? AND status='running'",
                        (str(exc)[:1000], time.time(), key, owner),
                    )
                failures += 1
                if failures > retries:
                    raise
            finally:
                stop.set()
                pulse.join(timeout=1)

    def stats(self) -> dict:
        with self.connection() as db:
            states = {
                r[0]: r[1]
                for r in db.execute("SELECT status,COUNT(*) FROM jobs GROUP BY status")
            }
            return {
                "sources": db.execute("SELECT COUNT(*) FROM sources").fetchone()[0],
                "units": db.execute("SELECT COUNT(*) FROM units").fetchone()[0],
                "teaching_units": db.execute(
                    "SELECT COUNT(*) FROM units WHERE role='teaching'"
                ).fetchone()[0],
                "assessment_units": db.execute(
                    "SELECT COUNT(*) FROM units WHERE role='assessment'"
                ).fetchone()[0],
                "jobs": states,
                "attempts": db.execute(
                    "SELECT COALESCE(SUM(attempts),0) FROM jobs"
                ).fetchone()[0],
            }
