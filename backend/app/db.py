"""
SQLite persistence layer.

Kept intentionally simple and dependency-free (standard library `sqlite3`) so the
data model is transparent and easy to inspect. Each transaction row stores both the
raw parsed fields and the categorization state (including whether a human corrected it).
"""

from __future__ import annotations
import sqlite3
import os
from contextlib import contextmanager
from typing import Iterator

DB_PATH = os.environ.get(
    "FINZ_DB_PATH",
    os.path.join(os.path.dirname(os.path.dirname(__file__)), "finz.db"),
)


def _connect() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


@contextmanager
def get_conn() -> Iterator[sqlite3.Connection]:
    conn = _connect()
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


SCHEMA = """
CREATE TABLE IF NOT EXISTS transactions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    txn_date TEXT NOT NULL,              -- ISO date YYYY-MM-DD
    period TEXT NOT NULL,                -- YYYY-MM, derived from txn_date
    description TEXT NOT NULL,
    counterparty TEXT,                   -- merchant / payer if separable
    amount REAL NOT NULL,                -- signed: positive = inflow, negative = outflow
    raw_amount REAL NOT NULL,            -- amount exactly as parsed (pre-normalization)
    account TEXT,                        -- source account label if present
    raw_json TEXT,                       -- original row as JSON for full traceability

    category_key TEXT NOT NULL DEFAULT 'uncategorized',
    confidence REAL NOT NULL DEFAULT 0.0,-- 0..1 categorizer confidence
    category_source TEXT NOT NULL DEFAULT 'none', -- 'rule' | 'ai' | 'user' | 'none'
    ai_rationale TEXT,                   -- short explanation from the categorizer

    needs_review INTEGER NOT NULL DEFAULT 0,  -- 1 if flagged for human review
    review_reason TEXT,                       -- why it was flagged
    resolved INTEGER NOT NULL DEFAULT 0,      -- 1 if a human has resolved the review

    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE INDEX IF NOT EXISTS idx_txn_period ON transactions(period);
CREATE INDEX IF NOT EXISTS idx_txn_category ON transactions(category_key);
CREATE INDEX IF NOT EXISTS idx_txn_review ON transactions(needs_review);

-- Learned corrections: when a user fixes a category for a description pattern,
-- we remember it so future ingests of similar descriptions apply the correction.
CREATE TABLE IF NOT EXISTS corrections (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    pattern TEXT NOT NULL UNIQUE,        -- normalized description key
    category_key TEXT NOT NULL,
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS meta (
    key TEXT PRIMARY KEY,
    value TEXT
);
"""


def init_db() -> None:
    with get_conn() as conn:
        conn.executescript(SCHEMA)


def reset_db() -> None:
    """Clear all data. Ensures the schema exists first so this is safe even if the
    database file was just created or removed."""
    with get_conn() as conn:
        conn.executescript(SCHEMA)
        conn.executescript(
            "DELETE FROM transactions; DELETE FROM corrections; DELETE FROM meta;"
        )
