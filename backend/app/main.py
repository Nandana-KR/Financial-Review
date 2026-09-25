"""
FastAPI application: wires ingest, categorization, P&L, variance, review and the
AI analyst into a small HTTP API consumed by the React frontend.
"""

from __future__ import annotations
from typing import Optional

from fastapi import FastAPI, UploadFile, File, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from .db import init_db, reset_db
from .ingest import parse_file
from . import repository as repo
from .chart_of_accounts import CATEGORIES
from .pnl import compute_pnl, compute_all_pnls, compute_pnl_range, list_periods
from .variance import compare_periods, most_significant_changes
from .ai import analyst_answer, llm_available

app = FastAPI(title="Finz - AI-Native Financial Review", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.on_event("startup")
def _startup():
    init_db()


# ---------------------------- Models ----------------------------
class CorrectionRequest(BaseModel):
    category_key: str
    save_correction: bool = True


class ChatRequest(BaseModel):
    question: str


# ---------------------------- Meta ----------------------------
@app.get("/api/health")
def health():
    return {"status": "ok", "llm_available": llm_available()}


@app.get("/api/categories")
def categories():
    return [
        {"key": c.key, "label": c.label, "section": c.section.value, "is_pnl": c.is_pnl,
         "description": c.description}
        for c in CATEGORIES
    ]


@app.get("/api/stats")
def get_stats():
    return {**repo.stats(), "llm_available": llm_available()}


# ---------------------------- Ingest ----------------------------
@app.post("/api/ingest")
async def ingest(file: UploadFile = File(...), replace: bool = True):
    content = await file.read()
    parsed = parse_file(file.filename, content)
    if not parsed:
        raise HTTPException(status_code=400,
                            detail="No transactions could be parsed from the file.")
    if replace:
        reset_db()
    count = repo.insert_and_categorize(parsed)
    return {"ingested": count, "periods": list_periods(repo.all_transactions())}


@app.post("/api/reset")
def reset():
    """Clear all loaded transactions and corrections. Returns to an empty state."""
    reset_db()
    return {"status": "cleared"}


# ---------------------------- Transactions ----------------------------
@app.get("/api/transactions")
def get_transactions(period: Optional[str] = None, category_key: Optional[str] = None):
    txns = repo.all_transactions()
    if period:
        txns = [t for t in txns if t["period"] == period]
    if category_key:
        txns = [t for t in txns if t["category_key"] == category_key]
    return txns


@app.post("/api/transactions/{txn_id}/category")
def correct_category(txn_id: int, body: CorrectionRequest):
    valid = {c.key for c in CATEGORIES}
    if body.category_key not in valid:
        raise HTTPException(status_code=400, detail="Unknown category_key.")
    updated = repo.update_category(txn_id, body.category_key, body.save_correction)
    if updated is None:
        raise HTTPException(status_code=404, detail="Transaction not found.")
    return updated


@app.post("/api/transactions/{txn_id}/resolve")
def resolve(txn_id: int):
    updated = repo.resolve_review(txn_id)
    if updated is None:
        raise HTTPException(status_code=404, detail="Transaction not found.")
    return updated


# ---------------------------- Review queue ----------------------------
@app.get("/api/review")
def review():
    return repo.review_items()


@app.post("/api/review/ai-categorize")
def ai_categorize_review():
    """Apply the AI classifier to the items currently flagged for review."""
    return repo.ai_categorize_review_items()


# ---------------------------- P&L ----------------------------
@app.get("/api/pnl")
def pnl(period: Optional[str] = None, start: Optional[str] = None, end: Optional[str] = None):
    txns = repo.all_transactions()
    # Date-range P&L (from the date pickers).
    if start or end:
        return compute_pnl_range(txns, start, end).to_dict()
    if period:
        return compute_pnl(txns, period).to_dict()
    return [p.to_dict() for p in compute_all_pnls(txns)]


@app.get("/api/periods")
def periods():
    return list_periods(repo.all_transactions())


# ---------------------------- Variance ----------------------------
@app.get("/api/variance")
def variance(prior: Optional[str] = None, current: Optional[str] = None):
    txns = repo.all_transactions()
    ps = list_periods(txns)
    if len(ps) < 2:
        raise HTTPException(status_code=400, detail="Need at least two periods.")
    if prior is None or current is None:
        prior, current = ps[-2], ps[-1]
    return compare_periods(txns, prior, current).to_dict()


@app.get("/api/variance/significant")
def significant():
    txns = repo.all_transactions()
    ps = list_periods(txns)
    result = most_significant_changes(txns, ps)
    if result is None:
        raise HTTPException(status_code=400, detail="Need at least two periods.")
    return result


# ---------------------------- Analyst ----------------------------
@app.post("/api/chat")
def chat(body: ChatRequest):
    if not body.question.strip():
        raise HTTPException(status_code=400, detail="Empty question.")
    return analyst_answer(body.question, repo.all_transactions())
