"""
SQLite setup and data-access helpers for the contact directory kiosk.

Kept deliberately simple (raw sqlite3, no ORM) since this is a single-file
database running on a single Raspberry Pi for a single LAN deployment.
"""
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path

DB_PATH = Path(__file__).parent / "data" / "kiosk.db"

SCHEMA = """
CREATE TABLE IF NOT EXISTS contacts (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    full_name       TEXT NOT NULL,
    phone_mobile    TEXT,
    email           TEXT,
    home_address    TEXT,
    city            TEXT,
    state           TEXT,
    zip             TEXT,
    photo_path      TEXT,
    consent_given   INTEGER NOT NULL DEFAULT 0,
    status          TEXT NOT NULL DEFAULT 'pending',  -- pending / approved / rejected
    created_at      TEXT NOT NULL,
    updated_at      TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS settings (
    key   TEXT PRIMARY KEY,
    value TEXT
);

CREATE TABLE IF NOT EXISTS audit_log (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    contact_id  INTEGER,
    action      TEXT NOT NULL,
    actor       TEXT,
    timestamp   TEXT NOT NULL
);
"""

DEFAULT_SETTINGS = {
    "include_home_address_default": "0",
}


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def init_db() -> None:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    with get_conn() as conn:
        conn.executescript(SCHEMA)
        for key, value in DEFAULT_SETTINGS.items():
            conn.execute(
                "INSERT OR IGNORE INTO settings (key, value) VALUES (?, ?)",
                (key, value),
            )
        conn.commit()


@contextmanager
def get_conn():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    try:
        yield conn
    finally:
        conn.close()


def log_action(conn, contact_id, action, actor="kiosk"):
    conn.execute(
        "INSERT INTO audit_log (contact_id, action, actor, timestamp) VALUES (?, ?, ?, ?)",
        (contact_id, action, actor, now_iso()),
    )


def get_setting(conn, key, default=None):
    row = conn.execute("SELECT value FROM settings WHERE key = ?", (key,)).fetchone()
    return row["value"] if row else default


def set_setting(conn, key, value):
    conn.execute(
        "INSERT INTO settings (key, value) VALUES (?, ?) "
        "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
        (key, str(value)),
    )
