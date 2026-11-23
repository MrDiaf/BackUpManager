"""SQLite storage. One short-lived connection per call keeps threads simple."""
import os
import sqlite3
from contextlib import closing

DATA_DIR = os.environ.get("DATA_DIR", "/data")
DB_PATH = os.path.join(DATA_DIR, "backupmanager.db")
LOG_DIR = os.path.join(DATA_DIR, "logs")

SCHEMA = """
CREATE TABLE IF NOT EXISTS jobs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,  -- ids never reused (log files are named by run id)
    name TEXT NOT NULL,
    source TEXT NOT NULL,          -- host path
    dest TEXT NOT NULL,            -- host path
    mode TEXT NOT NULL CHECK (mode IN ('mirror', 'snapshot')),
    keep_daily INTEGER NOT NULL DEFAULT 7,
    keep_weekly INTEGER NOT NULL DEFAULT 4,
    run_time TEXT NOT NULL DEFAULT '03:00',
    pre_command TEXT NOT NULL DEFAULT '',
    enabled INTEGER NOT NULL DEFAULT 1,
    src_mount TEXT NOT NULL,       -- host mount point the source lived on when saved
    dst_mount TEXT NOT NULL,
    src_disks TEXT NOT NULL,       -- physical disk names, comma separated
    dst_disks TEXT NOT NULL,
    next_run TEXT                  -- local ISO datetime
);
CREATE TABLE IF NOT EXISTS runs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,  -- ids never reused (log files are named by run id)
    job_id INTEGER NOT NULL REFERENCES jobs(id) ON DELETE CASCADE,
    trigger TEXT NOT NULL,         -- 'schedule' | 'manual'
    started TEXT NOT NULL,
    ended TEXT,
    status TEXT NOT NULL,          -- 'running' | 'ok' | 'failed'
    size_bytes INTEGER,
    message TEXT NOT NULL DEFAULT ''
);
CREATE INDEX IF NOT EXISTS runs_job ON runs(job_id, id);
"""

JOB_FIELDS = ("name", "source", "dest", "mode", "keep_daily", "keep_weekly", "run_time",
              "pre_command", "enabled", "src_mount", "dst_mount", "src_disks", "dst_disks",
              "next_run")


def connect():
    conn = sqlite3.connect(DB_PATH, timeout=30)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def init():
    os.makedirs(LOG_DIR, exist_ok=True)
    with closing(connect()) as c, c:
        c.execute("PRAGMA journal_mode = WAL")
        c.executescript(SCHEMA)


def query(sql, args=()):
    with closing(connect()) as c:
        return c.execute(sql, args).fetchall()


def one(sql, args=()):
    rows = query(sql, args)
    return rows[0] if rows else None


def execute(sql, args=()):
    with closing(connect()) as c, c:
        return c.execute(sql, args).lastrowid


def log_path(run_id):
    return os.path.join(LOG_DIR, f"{run_id}.log")


# --- jobs -------------------------------------------------------------------

def jobs():
    return query("SELECT * FROM jobs ORDER BY name COLLATE NOCASE")


def job(job_id):
    return one("SELECT * FROM jobs WHERE id = ?", (job_id,))


def save_job(values, job_id=None):
    cols = [f for f in JOB_FIELDS if f in values]
    args = [values[f] for f in cols]
    if job_id is None:
        return execute(f"INSERT INTO jobs ({', '.join(cols)}) VALUES ({', '.join('?' * len(cols))})", args)
    execute(f"UPDATE jobs SET {', '.join(c + ' = ?' for c in cols)} WHERE id = ?", args + [job_id])
    return job_id


def delete_job(job_id):
    run_ids = [r["id"] for r in query("SELECT id FROM runs WHERE job_id = ?", (job_id,))]
    execute("DELETE FROM jobs WHERE id = ?", (job_id,))
    for rid in run_ids:
        try:
            os.remove(log_path(rid))
        except FileNotFoundError:
            pass


# --- runs -------------------------------------------------------------------

def runs_for(job_id, limit=50):
    return query("SELECT * FROM runs WHERE job_id = ? ORDER BY id DESC LIMIT ?", (job_id, limit))


def last_run(job_id):
    """Latest real backup run; dry-run checks don't count as backups."""
    return one("SELECT * FROM runs WHERE job_id = ? AND trigger != 'check' ORDER BY id DESC LIMIT 1", (job_id,))


def run(run_id):
    return one("SELECT * FROM runs WHERE id = ?", (run_id,))
