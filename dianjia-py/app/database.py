from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Iterable

SCHEMA = """
CREATE TABLE IF NOT EXISTS memories (
 id TEXT PRIMARY KEY, title TEXT NOT NULL, category TEXT NOT NULL,
 subcategory TEXT, tags TEXT, summary TEXT, path TEXT NOT NULL,
 score INTEGER, memory_level TEXT, status TEXT DEFAULT 'active',
 created_at TEXT NOT NULL, updated_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS memory_sources (
 id INTEGER PRIMARY KEY AUTOINCREMENT, memory_id TEXT NOT NULL,
 source_date TEXT, source_type TEXT, source_path TEXT, created_at TEXT,
 FOREIGN KEY(memory_id) REFERENCES memories(id)
);
CREATE TABLE IF NOT EXISTS memory_relations (
 id INTEGER PRIMARY KEY AUTOINCREMENT, source_memory_id TEXT NOT NULL,
 target_memory_id TEXT NOT NULL, relation_type TEXT NOT NULL, created_at TEXT,
 UNIQUE(source_memory_id, target_memory_id, relation_type)
);
CREATE TABLE IF NOT EXISTS memory_actions (
 id INTEGER PRIMARY KEY AUTOINCREMENT, memory_id TEXT, action TEXT,
 reason TEXT, payload TEXT, created_at TEXT
);
CREATE TABLE IF NOT EXISTS sources (
 id TEXT PRIMARY KEY, source_type TEXT, content_hash TEXT UNIQUE, path TEXT,
 source_date TEXT, created_at TEXT, processed_at TEXT,
 pipeline_status TEXT DEFAULT 'pending', last_candidate_hash TEXT
);
"""


def connect(path: Path) -> sqlite3.Connection:
    path.parent.mkdir(parents=True, exist_ok=True)
    # The local web server handles requests in worker threads. SQLite's
    # connection is shared by the service, so allow cross-thread use here.
    conn = sqlite3.connect(path, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.executescript(SCHEMA)
    migrations = {
        "sources": [
            ("title", "TEXT"),
            ("metadata", "TEXT"),
            ("processed_at", "TEXT"),
            ("pipeline_status", "TEXT DEFAULT 'pending'"),
            ("last_candidate_hash", "TEXT"),
        ],
    }
    for table, columns in migrations.items():
        existing = {row[1] for row in conn.execute(f"PRAGMA table_info({table})")}
        for name, kind in columns:
            if name not in existing:
                conn.execute(f"ALTER TABLE {table} ADD COLUMN {name} {kind}")
    # Backfill the idempotency marker for Sources that were already linked to
    # a long-term memory before pipeline_status was introduced. Sources with
    # no historical memory relation remain pending and will be processed once.
    conn.execute("""UPDATE sources
        SET processed_at = COALESCE(processed_at, created_at),
            pipeline_status = 'processed'
        WHERE processed_at IS NULL
          AND EXISTS (
              SELECT 1 FROM memory_sources ms
              WHERE ms.source_path = sources.path
          )""")
    conn.commit()
    return conn


def execute(conn: sqlite3.Connection, sql: str, params: Iterable = ()):
    cur = conn.execute(sql, tuple(params))
    conn.commit()
    return cur
