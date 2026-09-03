from __future__ import annotations
from contextlib import contextmanager
import hashlib
import json
import sqlite3
import threading
from pathlib import Path

class DurableStore:
    """WAL-backed reference store for resumable jobs, idempotency, and outbox."""
    def __init__(self, path: str | Path) -> None:
        self.path = str(path)
        Path(self.path).parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.RLock()
        with self._connect() as db:
            db.executescript("""
            PRAGMA journal_mode=WAL;
            CREATE TABLE IF NOT EXISTS jobs(
                job_id TEXT PRIMARY KEY,
                tenant_id TEXT NOT NULL,
                principal_id TEXT NOT NULL,
                state TEXT NOT NULL,
                version INTEGER NOT NULL,
                payload TEXT NOT NULL,
                checksum TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS idempotency(
                key TEXT PRIMARY KEY,
                request_hash TEXT NOT NULL,
                status_code INTEGER NOT NULL,
                body TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS outbox(
                event_id TEXT PRIMARY KEY,
                tenant_id TEXT NOT NULL,
                event_type TEXT NOT NULL,
                payload TEXT NOT NULL,
                delivered INTEGER NOT NULL DEFAULT 0
            );
            """)

    @contextmanager
    def _connect(self):
        conn = sqlite3.connect(self.path, timeout=15, check_same_thread=False)
        try:
            with conn:
                yield conn
        finally:
            conn.close()

    @staticmethod
    def checksum(job_id: str, state: str, version: int, payload: dict) -> str:
        raw = json.dumps({"job_id": job_id, "state": state, "version": version, "payload": payload},
                         sort_keys=True, separators=(",", ":")).encode()
        return hashlib.sha256(raw).hexdigest()

    def save_job(self, job_id, tenant_id, principal_id, state, version, payload, updated_at) -> bool:
        digest = self.checksum(job_id, state, version, payload)
        with self._lock, self._connect() as db:
            cur = db.execute("""
            INSERT INTO jobs(job_id,tenant_id,principal_id,state,version,payload,checksum,updated_at)
            VALUES(?,?,?,?,?,?,?,?)
            ON CONFLICT(job_id) DO UPDATE SET
              state=excluded.state, version=excluded.version,
              payload=excluded.payload, checksum=excluded.checksum,
              updated_at=excluded.updated_at
            WHERE jobs.version = excluded.version - 1
            """, (job_id, tenant_id, principal_id, state, version, json.dumps(payload), digest, updated_at))
            return cur.rowcount == 1

    def get_job(self, job_id):
        with self._lock, self._connect() as db:
            row = db.execute("SELECT * FROM jobs WHERE job_id=?", (job_id,)).fetchone()
            if not row:
                return None
            payload = json.loads(row[5])
            expected = self.checksum(row[0], row[3], row[4], payload)
            if expected != row[6]:
                raise ValueError("job checksum mismatch")
            return {
                "job_id": row[0], "tenant_id": row[1], "principal_id": row[2],
                "state": row[3], "version": row[4], "payload": payload, "updated_at": row[7]
            }

    def put_idempotency(self, key, request_hash, status_code, body) -> bool:
        with self._lock, self._connect() as db:
            cur = db.execute("INSERT OR IGNORE INTO idempotency VALUES(?,?,?,?)",
                             (key, request_hash, status_code, json.dumps(body)))
            return cur.rowcount == 1

    def get_idempotency(self, key):
        with self._lock, self._connect() as db:
            row = db.execute("SELECT * FROM idempotency WHERE key=?", (key,)).fetchone()
            return None if not row else {"key": row[0], "request_hash": row[1], "status_code": row[2], "body": json.loads(row[3])}

    def append_outbox(self, event_id, tenant_id, event_type, payload) -> bool:
        with self._lock, self._connect() as db:
            cur = db.execute("INSERT OR IGNORE INTO outbox VALUES(?,?,?,?,0)",
                             (event_id, tenant_id, event_type, json.dumps(payload)))
            return cur.rowcount == 1

    def pending_outbox(self, limit=100):
        if not 1 <= limit <= 1000:
            raise ValueError("invalid outbox limit")
        with self._lock, self._connect() as db:
            rows = db.execute("SELECT event_id,tenant_id,event_type,payload FROM outbox WHERE delivered=0 ORDER BY rowid LIMIT ?",
                              (limit,)).fetchall()
            return [{"event_id": r[0], "tenant_id": r[1], "event_type": r[2], "payload": json.loads(r[3])} for r in rows]

    def mark_outbox_delivered(self, event_id) -> bool:
        with self._lock, self._connect() as db:
            cur = db.execute("UPDATE outbox SET delivered=1 WHERE event_id=? AND delivered=0", (event_id,))
            return cur.rowcount == 1
