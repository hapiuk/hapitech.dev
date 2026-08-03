# journal_db.py
import os
import sqlite3
from pathlib import Path

# 🔎 CTRL+F: DB_PATH + init_db
BASE_DIR = Path(__file__).resolve().parent
DB_PATH = os.environ.get("HAPITECH_DB_PATH") or str(BASE_DIR / "hapitech.sqlite3")


def get_db():
	conn = sqlite3.connect(DB_PATH)
	conn.row_factory = sqlite3.Row
	# Better durability + concurrency for SQLite on VPS
	conn.execute("PRAGMA journal_mode=WAL;")
	conn.execute("PRAGMA foreign_keys=ON;")
	return conn


def init_db():
	conn = get_db()
	cur = conn.cursor()

	# 🔎 CTRL+F: CREATE TABLE journal_entries
	cur.execute("""
	CREATE TABLE IF NOT EXISTS journal_entries (
                id TEXT PRIMARY KEY,
                entity_kind TEXT NOT NULL,       -- planet | moon | satellite | station | general
                entity_name TEXT NOT NULL,       -- e.g. Mars, Europa, General
                entity_parent TEXT,              -- optional (e.g. Jupiter for Europa)
                title TEXT NOT NULL,
                body TEXT NOT NULL,
                tags_json TEXT NOT NULL DEFAULT '[]',
                created_at TEXT NOT NULL,        -- ISO string
                updated_at TEXT,                 -- ISO string
                snapshot_json TEXT,              -- JSON blob (camera/time/selection)
                images_json TEXT                 -- JSON array of URLs
        );
        """)



	# 🔎 CTRL+F: CREATE TABLE goals
	cur.execute("""
	CREATE TABLE IF NOT EXISTS goals (
		id TEXT PRIMARY KEY,
		title TEXT NOT NULL,
		description TEXT NOT NULL,
		status TEXT NOT NULL DEFAULT 'todo', -- todo | doing | done
		entity_kind TEXT,                   -- nullable (global goal if null)
		entity_name TEXT,                   -- nullable
		created_at TEXT NOT NULL,
		due_at TEXT                          -- nullable ISO
	);
	""")

	# Helpful indexes
	cur.execute("CREATE INDEX IF NOT EXISTS idx_journal_created ON journal_entries(created_at DESC);")
	cur.execute("CREATE INDEX IF NOT EXISTS idx_journal_entity ON journal_entries(entity_kind, entity_name, created_at DESC);")
	cur.execute("CREATE INDEX IF NOT EXISTS idx_goals_status ON goals(status, created_at DESC);")

	conn.commit()
	conn.close()
