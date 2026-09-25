"""
Repository: all reads/writes of transactions and corrections against SQLite.
Keeps SQL in one place so the API layer stays thin.
"""

from __future__ import annotations
from typing import Optional

from .db import get_conn
from .ingest import ParsedTxn
from .categorize import categorize, normalize_pattern
from .ai import ai_classify, llm_available


def load_corrections() -> dict[str, str]:
    with get_conn() as conn:
        rows = conn.execute("SELECT pattern, category_key FROM corrections").fetchall()
    return {r["pattern"]: r["category_key"] for r in rows}


def all_transactions() -> list[dict]:
    with get_conn() as conn:
        rows = conn.execute(
            "SELECT * FROM transactions ORDER BY txn_date, id"
        ).fetchall()
    return [dict(r) for r in rows]


def get_transaction(txn_id: int) -> Optional[dict]:
    with get_conn() as conn:
        row = conn.execute("SELECT * FROM transactions WHERE id=?", (txn_id,)).fetchone()
    return dict(row) if row else None


def insert_and_categorize(parsed: list[ParsedTxn]) -> int:
    """Insert parsed transactions using fast, deterministic categorization only.

    Ingest never calls the LLM: it must be fast and reliable for a whole file. Rules
    + learned corrections categorize most rows immediately; anything uncertain lands
    in the review queue. The AI is applied afterwards, on demand, only to the review
    items via `ai_categorize_review_items()`. This keeps ingest instant and avoids
    partial loads caused by slow/failed network calls mid-import.
    """
    corrections = load_corrections()

    with get_conn() as conn:
        for t in parsed:
            result = categorize(
                description=t.description,
                amount=t.amount,
                counterparty=t.counterparty,
                corrections=corrections,
                ai_classifier=None,  # deterministic only during bulk ingest
            )
            conn.execute(
                """
                INSERT INTO transactions
                    (txn_date, period, description, counterparty, amount, raw_amount,
                     account, raw_json, category_key, confidence, category_source,
                     ai_rationale, needs_review, review_reason)
                VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)
                """,
                (t.txn_date, t.period, t.description, t.counterparty, t.amount,
                 t.raw_amount, t.account, t.raw_json, result.category_key,
                 result.confidence, result.source, result.rationale,
                 1 if result.needs_review else 0, result.review_reason),
            )
    return len(parsed)


def update_category(txn_id: int, category_key: str, save_correction: bool = True) -> Optional[dict]:
    """Apply a user's category correction. Optionally persist it as a learned rule."""
    txn = get_transaction(txn_id)
    if txn is None:
        return None

    with get_conn() as conn:
        conn.execute(
            """
            UPDATE transactions
               SET category_key=?, category_source='user', confidence=1.0,
                   needs_review=0, resolved=1,
                   ai_rationale='Corrected by user.',
                   review_reason=NULL, updated_at=datetime('now')
             WHERE id=?
            """,
            (category_key, txn_id),
        )
        if save_correction:
            pattern = normalize_pattern(txn["description"], txn.get("counterparty"))
            if pattern:
                conn.execute(
                    """
                    INSERT INTO corrections (pattern, category_key) VALUES (?,?)
                    ON CONFLICT(pattern) DO UPDATE SET category_key=excluded.category_key
                    """,
                    (pattern, category_key),
                )
                # Apply the learned correction to other matching, non-user-edited rows.
                _apply_correction_to_matching(conn, pattern, category_key, exclude_id=txn_id)

    return get_transaction(txn_id)


def _apply_correction_to_matching(conn, pattern: str, category_key: str, exclude_id: int) -> None:
    rows = conn.execute(
        "SELECT id, description, counterparty FROM transactions "
        "WHERE category_source != 'user' AND id != ?", (exclude_id,)
    ).fetchall()
    for r in rows:
        if normalize_pattern(r["description"], r["counterparty"]) == pattern:
            conn.execute(
                "UPDATE transactions SET category_key=?, category_source='user', "
                "confidence=1.0, needs_review=0, review_reason=NULL, "
                "updated_at=datetime('now') WHERE id=?",
                (category_key, r["id"]),
            )


def resolve_review(txn_id: int) -> Optional[dict]:
    with get_conn() as conn:
        conn.execute(
            "UPDATE transactions SET needs_review=0, resolved=1, "
            "updated_at=datetime('now') WHERE id=?", (txn_id,)
        )
    return get_transaction(txn_id)


def ai_categorize_review_items(limit: int = 100) -> dict:
    """Use the AI classifier to (re)categorize items currently flagged for review.

    Runs only when an LLM is configured. This is where AI reasoning is applied to the
    genuinely ambiguous transactions, separately from the fast deterministic ingest.
    A row that the AI classifies with sufficient confidence is updated and cleared
    from the review queue; its source is marked 'ai'.
    """
    if not llm_available():
        return {"updated": 0, "llm_available": False}

    items = review_items()[:limit]
    updated = 0
    with get_conn() as conn:
        for t in items:
            try:
                res = ai_classify(t["description"], t["amount"], t.get("counterparty"))
            except Exception:
                res = None
            if not res:
                continue
            key, conf, rationale = res
            still_review = 1 if conf < 0.6 else 0
            conn.execute(
                """
                UPDATE transactions
                   SET category_key=?, confidence=?, category_source='ai',
                       ai_rationale=?, needs_review=?, review_reason=?,
                       updated_at=datetime('now')
                 WHERE id=?
                """,
                (key, round(conf, 3), rationale, still_review,
                 None if not still_review else "AI still uncertain.", t["id"]),
            )
            if not still_review:
                updated += 1
    return {"updated": updated, "llm_available": True}


def review_items() -> list[dict]:
    with get_conn() as conn:
        rows = conn.execute(
            "SELECT * FROM transactions WHERE needs_review=1 AND resolved=0 "
            "ORDER BY confidence ASC, ABS(amount) DESC"
        ).fetchall()
    return [dict(r) for r in rows]


def stats() -> dict:
    with get_conn() as conn:
        total = conn.execute("SELECT COUNT(*) c FROM transactions").fetchone()["c"]
        review = conn.execute(
            "SELECT COUNT(*) c FROM transactions WHERE needs_review=1 AND resolved=0"
        ).fetchone()["c"]
        periods = conn.execute(
            "SELECT COUNT(DISTINCT period) c FROM transactions"
        ).fetchone()["c"]
    return {"total_transactions": total, "needs_review": review, "periods": periods}
