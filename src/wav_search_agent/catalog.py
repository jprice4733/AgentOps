"""SQLite catalog: ingestion job state plus persisted transcript segments.

S3 stays the source of truth for audio and transcripts; the catalog can be
rebuilt from it. It lets the worker and the web app avoid listing and fetching
every object from S3 at startup.
"""
import re
import sqlite3
import threading
import time
from contextlib import contextmanager
from pathlib import Path

SCHEMA = """
CREATE TABLE IF NOT EXISTS calls (
    uri TEXT PRIMARY KEY,
    key TEXT NOT NULL,
    fingerprint TEXT NOT NULL,
    etag TEXT,
    size INTEGER NOT NULL,
    last_modified TEXT,
    status TEXT NOT NULL,
    attempts INTEGER NOT NULL DEFAULT 0,
    next_attempt_at REAL NOT NULL DEFAULT 0,
    lease_expires REAL,
    last_error TEXT,
    duration REAL,
    segment_count INTEGER NOT NULL DEFAULT 0,
    first_seen REAL NOT NULL,
    indexed_at REAL
);
CREATE INDEX IF NOT EXISTS calls_status ON calls(status, next_attempt_at);
CREATE TABLE IF NOT EXISTS segments (
    id INTEGER PRIMARY KEY,
    call_uri TEXT NOT NULL,
    idx INTEGER NOT NULL,
    start_time REAL NOT NULL,
    end_time REAL NOT NULL,
    text TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS segments_call ON segments(call_uri);
CREATE VIRTUAL TABLE IF NOT EXISTS segments_fts USING fts5(
    text, content='segments', content_rowid='id', tokenize='porter unicode61');
CREATE TRIGGER IF NOT EXISTS segments_ai AFTER INSERT ON segments BEGIN
    INSERT INTO segments_fts(rowid, text) VALUES (new.id, new.text);
END;
CREATE TRIGGER IF NOT EXISTS segments_ad AFTER DELETE ON segments BEGIN
    INSERT INTO segments_fts(segments_fts, rowid, text) VALUES ('delete', old.id, old.text);
END;
"""

CLAIM_COLUMNS = "uri, key, fingerprint, etag, size, last_modified, attempts"


class Catalog:
    def __init__(self, path):
        if str(path) != ":memory:":
            Path(path).parent.mkdir(parents=True, exist_ok=True)
        self._db = sqlite3.connect(str(path), check_same_thread=False, isolation_level=None)
        self._db.row_factory = sqlite3.Row
        self._lock = threading.RLock()
        self._db.execute("PRAGMA journal_mode=WAL")
        self._db.execute("PRAGMA busy_timeout=30000")
        self._db.executescript(SCHEMA)

    def close(self):
        with self._lock:
            self._db.close()

    @contextmanager
    def _tx(self):
        with self._lock:
            self._db.execute("BEGIN IMMEDIATE")
            try:
                yield self._db
            except BaseException:
                self._db.execute("ROLLBACK")
                raise
            self._db.execute("COMMIT")

    def register(self, items, now=None):
        """Record scanned recordings; new or replaced ones become pending.

        Each item needs uri, key, fingerprint, etag, size and last_modified.
        """
        now = time.time() if now is None else now
        counts = {"new": 0, "changed": 0, "unchanged": 0}
        with self._tx() as db:
            known = {row["uri"]: (row["fingerprint"], row["status"])
                     for row in db.execute("SELECT uri, fingerprint, status FROM calls")}
            for item in items:
                current = known.get(item["uri"])
                if current is None:
                    db.execute(
                        "INSERT INTO calls (uri, key, fingerprint, etag, size, last_modified, status, first_seen)"
                        " VALUES (?, ?, ?, ?, ?, ?, 'pending', ?)",
                        (item["uri"], item["key"], item["fingerprint"], item["etag"],
                         item["size"], item["last_modified"], now))
                    counts["new"] += 1
                elif current[0] != item["fingerprint"] or current[1] == "removed":
                    db.execute(
                        "UPDATE calls SET key=?, fingerprint=?, etag=?, size=?, last_modified=?,"
                        " status='pending', attempts=0, next_attempt_at=0, lease_expires=NULL,"
                        " last_error=NULL WHERE uri=?",
                        (item["key"], item["fingerprint"], item["etag"], item["size"],
                         item["last_modified"], item["uri"]))
                    counts["changed"] += 1
                else:
                    counts["unchanged"] += 1
        return counts

    def mark_removed(self, seen_uris):
        """Drop recordings no longer in S3. Returns their URIs so vectors can be deleted.

        An empty scan never removes anything, so a wrong prefix or a listing
        failure cannot wipe the index.
        """
        if not seen_uris:
            return []
        with self._tx() as db:
            gone = [row["uri"] for row in db.execute("SELECT uri FROM calls WHERE status != 'removed'")
                    if row["uri"] not in seen_uris]
            for uri in gone:
                db.execute("UPDATE calls SET status='removed', lease_expires=NULL WHERE uri=?", (uri,))
                db.execute("DELETE FROM segments WHERE call_uri=?", (uri,))
        return gone

    def claim(self, limit, lease_seconds, max_attempts, now=None):
        """Lease up to `limit` due jobs. Each claim counts as an attempt."""
        now = time.time() if now is None else now
        with self._tx() as db:
            # A job whose lease keeps expiring (crash, OOM) must not loop forever.
            db.execute(
                "UPDATE calls SET status='failed', lease_expires=NULL,"
                " last_error='Worker lease expired after too many attempts'"
                " WHERE status='processing' AND lease_expires < ? AND attempts >= ?",
                (now, max_attempts))
            rows = db.execute(
                f"SELECT {CLAIM_COLUMNS} FROM calls"
                " WHERE (status='pending' AND next_attempt_at <= ?)"
                " OR (status='processing' AND lease_expires < ?)"
                " ORDER BY first_seen, uri LIMIT ?", (now, now, limit)).fetchall()
            for row in rows:
                db.execute("UPDATE calls SET status='processing', attempts=attempts+1,"
                           " lease_expires=? WHERE uri=?", (now + lease_seconds, row["uri"]))
        return [dict(row, attempts=row["attempts"] + 1) for row in rows]

    def complete(self, uri, fingerprint, segments, duration, now=None):
        """Store the call's segments. Returns False if the recording changed meanwhile."""
        now = time.time() if now is None else now
        with self._tx() as db:
            row = db.execute("SELECT fingerprint FROM calls WHERE uri=?", (uri,)).fetchone()
            if row is None or row["fingerprint"] != fingerprint:
                return False
            db.execute("DELETE FROM segments WHERE call_uri=?", (uri,))
            db.executemany(
                "INSERT INTO segments (call_uri, idx, start_time, end_time, text) VALUES (?, ?, ?, ?, ?)",
                [(uri, s["idx"], s["start_time"], s["end_time"], s["text"]) for s in segments])
            db.execute(
                "UPDATE calls SET status='done', lease_expires=NULL, last_error=NULL, duration=?,"
                " segment_count=?, indexed_at=? WHERE uri=?", (duration, len(segments), now, uri))
        return True

    def fail(self, uri, fingerprint, error, max_attempts, permanent=False, now=None):
        """Schedule a retry with exponential backoff, or give up. Returns the new status."""
        now = time.time() if now is None else now
        with self._tx() as db:
            row = db.execute("SELECT fingerprint, attempts FROM calls WHERE uri=?", (uri,)).fetchone()
            if row is None or row["fingerprint"] != fingerprint:
                return "stale"
            if permanent or row["attempts"] >= max_attempts:
                status, delay = "failed", 0
            else:
                status, delay = "pending", min(60 * 2 ** (row["attempts"] - 1), 3600)
            db.execute("UPDATE calls SET status=?, next_attempt_at=?, lease_expires=NULL,"
                       " last_error=? WHERE uri=?", (status, now + delay, str(error)[:1000], uri))
        return status

    def requeue_failed(self):
        with self._tx() as db:
            return db.execute("UPDATE calls SET status='pending', attempts=0, next_attempt_at=0,"
                              " last_error=NULL WHERE status='failed'").rowcount

    def stats(self):
        with self._lock:
            counts = {row["status"]: row["n"] for row in self._db.execute(
                "SELECT status, COUNT(*) AS n FROM calls GROUP BY status")}
            segments = self._db.execute("SELECT COUNT(*) FROM segments").fetchone()[0]
        return {"calls": counts, "segments": segments}

    def failures(self, limit=20):
        with self._lock:
            return [dict(row) for row in self._db.execute(
                "SELECT uri, attempts, last_error FROM calls WHERE status='failed' LIMIT ?", (limit,))]

    def search_text(self, query, limit=50, phrase=False):
        """Full-text (stemmed) search over indexed segments, best match first.

        All terms must appear; with phrase=True they must appear adjacent and in order.
        Stemming makes this a candidate filter, so callers needing exact wording re-check it.
        """
        terms = [term.replace('"', "") for term in re.findall(r"\w+", query)]
        if not terms:
            return []
        match = '"' + " ".join(terms) + '"' if phrase else " ".join(f'"{term}"' for term in terms)
        with self._lock:
            rows = self._db.execute(
                "SELECT s.call_uri AS file_path, s.start_time, s.end_time, s.text"
                " FROM segments_fts JOIN segments s ON s.id = segments_fts.rowid"
                " JOIN calls c ON c.uri = s.call_uri AND c.status = 'done'"
                " WHERE segments_fts MATCH ? ORDER BY rank LIMIT ?", (match, limit)).fetchall()
        return [dict(row) for row in rows]

    def list_calls(self, limit=25, offset=0, contains=None):
        """Page through recordings that are still in S3, oldest first."""
        where, params = "status != 'removed'", []
        if contains:
            where += " AND uri LIKE ? ESCAPE '\\'"
            params.append("%" + _like_escape(contains) + "%")
        with self._lock:
            total = self._db.execute(f"SELECT COUNT(*) FROM calls WHERE {where}", params).fetchone()[0]
            rows = self._db.execute(
                f"SELECT uri, status, last_modified FROM calls WHERE {where}"
                " ORDER BY last_modified, uri LIMIT ? OFFSET ?", (*params, limit, offset)).fetchall()
        return {"total": total, "offset": offset,
                "calls": [{"file_path": row["uri"], "transcribed": row["status"] == "done",
                           "recorded_at": row["last_modified"]} for row in rows]}

    def find_calls(self, name):
        """Recordings whose URI equals `name` or whose filename equals it."""
        with self._lock:
            rows = self._db.execute(
                "SELECT uri FROM calls WHERE status != 'removed' AND (uri = ? OR uri LIKE ? ESCAPE '\\')"
                " LIMIT 2", (name, "%/" + _like_escape(name))).fetchall()
        return [row["uri"] for row in rows]

    def call_segments(self, uri):
        """Transcript segments for a call, or None if it is not transcribed."""
        with self._lock:
            call = self._db.execute("SELECT status FROM calls WHERE uri=?", (uri,)).fetchone()
            if call is None or call["status"] != "done":
                return None
            rows = self._db.execute(
                "SELECT idx, start_time, end_time, text FROM segments WHERE call_uri=? ORDER BY idx",
                (uri,)).fetchall()
        return [dict(row) for row in rows]

    def coverage(self, sample=20):
        """How many recordings are searchable, with a sample of those that are not."""
        with self._lock:
            recordings, done = self._db.execute(
                "SELECT COUNT(*), COALESCE(SUM(status='done'), 0) FROM calls WHERE status != 'removed'"
            ).fetchone()
            missing = [row["uri"] for row in self._db.execute(
                "SELECT uri FROM calls WHERE status NOT IN ('done', 'removed') ORDER BY uri LIMIT ?",
                (sample,))]
        return {"recordings": recordings, "transcribed": done,
                "missing_count": recordings - done, "missing_transcripts": missing}


def _like_escape(value):
    return value.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
