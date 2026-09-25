"""
AI layer (provider-agnostic, optional).

Two responsibilities:
  1. `ai_classify` : suggest a category for a transaction when rules are weak.
  2. `analyst_answer` : answer a natural-language question about the finances.

Design principles enforced here:
  - The LLM NEVER computes financial totals. For the analyst, all numbers come from
    deterministic "tools" (functions in this module that query the P&L / variance
    engines). The LLM only decides which tool to call and phrases the answer.
  - If no API key is set (FINZ_LLM_API_KEY), everything falls back to deterministic
    behavior: rules-only categorization and a template-based analyst that still
    returns real, traceable numbers. The app is fully functional offline.

Supported providers via FINZ_LLM_PROVIDER: "openai" | "anthropic" | "none".
"""

from __future__ import annotations
import json
import os
import re
from typing import Optional, Callable

from .chart_of_accounts import CATEGORIES, valid_category_keys, get_category
from .pnl import compute_pnl, list_periods
from .variance import compare_periods, most_significant_changes

PROVIDER = os.environ.get("FINZ_LLM_PROVIDER", "none").lower()
API_KEY = os.environ.get("FINZ_LLM_API_KEY", "")
MODEL = os.environ.get("FINZ_LLM_MODEL", "")


# Groq exposes an OpenAI-compatible API, so we reuse the OpenAI SDK with a base_url.
GROQ_BASE_URL = "https://api.groq.com/openai/v1"


def llm_available() -> bool:
    return PROVIDER in ("openai", "anthropic", "groq") and bool(API_KEY)


# --------------------------------------------------------------------------
# Provider call shim
# --------------------------------------------------------------------------
def _call_llm(system: str, user: str, max_tokens: int = 600) -> Optional[str]:
    """Send a single-turn prompt to the configured provider. Returns text or None."""
    if not llm_available():
        return None
    try:
        if PROVIDER in ("openai", "groq"):
            from openai import OpenAI  # imported lazily
            if PROVIDER == "groq":
                client = OpenAI(api_key=API_KEY, base_url=GROQ_BASE_URL)
                model = MODEL or "openai/gpt-oss-20b"
            else:
                client = OpenAI(api_key=API_KEY)
                model = MODEL or "gpt-4o-mini"
            resp = client.chat.completions.create(
                model=model,
                messages=[{"role": "system", "content": system},
                          {"role": "user", "content": user}],
                temperature=0,
                max_tokens=max_tokens,
            )
            return resp.choices[0].message.content
        if PROVIDER == "anthropic":
            import anthropic  # imported lazily
            client = anthropic.Anthropic(api_key=API_KEY)
            resp = client.messages.create(
                model=MODEL or "claude-3-5-sonnet-latest",
                system=system,
                max_tokens=max_tokens,
                temperature=0,
                messages=[{"role": "user", "content": user}],
            )
            return "".join(block.text for block in resp.content if hasattr(block, "text"))
    except Exception:
        return None
    return None


# --------------------------------------------------------------------------
# 1) Categorization classifier
# --------------------------------------------------------------------------
def _category_menu() -> str:
    return "\n".join(f"- {c.key}: {c.label} ({c.section.value}) - {c.description}"
                     for c in CATEGORIES)


def ai_classify(description: str, amount: float, counterparty: Optional[str]):
    """Return (category_key, confidence, rationale) or None if unavailable/failed."""
    if not llm_available():
        return None
    system = (
        "You are a bookkeeping assistant for a restaurant. Classify a single bank "
        "transaction into exactly one category key from the provided chart of accounts. "
        "Respond ONLY as compact JSON: {\"category_key\": \"...\", \"confidence\": 0.0-1.0, "
        "\"rationale\": \"short reason\"}. Do not compute totals. Choose 'uncategorized' "
        "if genuinely unclear."
    )
    user = (
        f"Chart of accounts:\n{_category_menu()}\n\n"
        f"Transaction:\n description: {description}\n counterparty: {counterparty or ''}\n"
        f" amount (positive=money in, negative=money out): {amount}\n\n"
        "Return the JSON now."
    )
    raw = _call_llm(system, user, max_tokens=800)
    if not raw:
        return None
    try:
        m = re.search(r"\{.*\}", raw, re.DOTALL)
        data = json.loads(m.group(0) if m else raw)
        key = str(data.get("category_key", "")).strip()
        if key not in valid_category_keys():
            return None
        conf = float(data.get("confidence", 0.5))
        conf = max(0.0, min(1.0, conf))
        rationale = str(data.get("rationale", "AI classification."))[:300]
        return (key, conf, f"AI: {rationale}")
    except Exception:
        return None


# --------------------------------------------------------------------------
# 2) Analyst: deterministic tools + LLM phrasing
# --------------------------------------------------------------------------
# Each tool returns structured data with the real numbers AND the txn ids that back
# them, so every answer is traceable.

def _fmt_money(x: float) -> str:
    return f"${x:,.2f}"


def tool_period_pnl(transactions: list[dict], period: str) -> dict:
    pnl = compute_pnl(transactions, period)
    return pnl.to_dict()


def tool_metric_by_month(transactions: list[dict], metric: str) -> dict:
    """metric in {revenue, cogs, gross_profit, payroll, operating_expenses, operating_profit}."""
    out = {}
    for p in list_periods(transactions):
        pnl = compute_pnl(transactions, p)
        out[p] = round(getattr(pnl, metric), 2)
    return {"metric": metric, "by_period": out}


def tool_variance(transactions: list[dict], prior: str, current: str) -> dict:
    return compare_periods(transactions, prior, current).to_dict()


def tool_txns_for_category_period(transactions: list[dict], category_key: str, period: str) -> dict:
    rows = [t for t in transactions
            if t.get("category_key") == category_key and t.get("period") == period]
    rows.sort(key=lambda t: abs(float(t["amount"])), reverse=True)
    return {
        "category_key": category_key,
        "period": period,
        "transactions": [
            {"id": t["id"], "date": t["txn_date"], "description": t["description"],
             "amount": round(float(t["amount"]), 2)}
            for t in rows
        ],
    }


def tool_review_items(transactions: list[dict]) -> dict:
    rows = [t for t in transactions if t.get("needs_review") and not t.get("resolved")]
    return {"count": len(rows),
            "transactions": [
                {"id": t["id"], "date": t["txn_date"], "description": t["description"],
                 "amount": round(float(t["amount"]), 2),
                 "category_key": t["category_key"], "reason": t.get("review_reason")}
                for t in rows]}


MONTH_NAMES = {
    "january": "01", "february": "02", "march": "03", "april": "04",
    "may": "05", "june": "06", "july": "07", "august": "08",
    "september": "09", "october": "10", "november": "11", "december": "12",
    "jan": "01", "feb": "02", "mar": "03", "apr": "04", "jun": "06", "jul": "07",
    "aug": "08", "sep": "09", "sept": "09", "oct": "10", "nov": "11", "dec": "12",
}


def _resolve_period(text: str, periods: list[str]) -> Optional[str]:
    """Map a month name mentioned in text to a YYYY-MM present in the data."""
    tl = text.lower()
    for name, mm in MONTH_NAMES.items():
        if re.search(rf"\b{name}\b", tl):
            matches = [p for p in periods if p.endswith(f"-{mm}")]
            if matches:
                return matches[-1]  # latest year with that month
    # explicit YYYY-MM
    m = re.search(r"\b(20\d{2})-(0[1-9]|1[0-2])\b", tl)
    if m and m.group(0) in periods:
        return m.group(0)
    return None


def _deterministic_answer(question: str, transactions: list[dict]) -> dict:
    """Rule-based intent routing that always returns real numbers + evidence.
    Used both as the no-LLM fallback and as the tool-execution backend for the LLM."""
    periods = list_periods(transactions)
    q = question.lower()

    def answer(text, evidence=None, data=None):
        return {"answer": text, "evidence_txn_ids": evidence or [], "data": data or {}}

    if not periods:
        return answer("There are no transactions loaded yet. Ingest a file first.")

    metric_map = {
        "revenue": ["revenue", "sales", "top line", "income"],
        "payroll": ["payroll", "wages", "salaries", "staff cost", "labor"],
        "cogs": ["cogs", "cost of goods", "food cost", "food costs"],
        "gross_profit": ["gross profit", "gross margin"],
        "operating_expenses": ["operating expense", "opex", "overhead"],
        "operating_profit": ["operating profit", "operating income", "bottom line", "profit"],
    }

    # "what changed most / biggest variance over the period"
    if any(k in q for k in ["changed most", "biggest change", "most significant",
                            "largest change", "over the review period", "over the period"]):
        sig = most_significant_changes(transactions, periods)
        if sig and sig["changes"]:
            top = sig["changes"][0]
            ev = top.get("driving_txn_ids", [])
            lines = [f"{c['label']}: {_fmt_money(c['prior'])} -> {_fmt_money(c['current'])} "
                     f"({_fmt_money(c['delta'])})" for c in sig["changes"]]
            return answer(
                f"Comparing {sig['prior_period']} to {sig['current_period']}, the largest "
                f"movements were:\n- " + "\n- ".join(lines),
                evidence=ev, data=sig)
        return answer("No material changes were detected across the review period.")

    # Variance / "why did X change between A and B"
    if ("why" in q or "change" in q or "variance" in q or "drove" in q or "increase" in q
            or "decrease" in q or "drop" in q) and len(periods) >= 2:
        mentioned = [p for name, mm in MONTH_NAMES.items()
                     for p in periods if p.endswith(f"-{mm}") and re.search(rf"\b{name}\b", q)]
        mentioned = list(dict.fromkeys(mentioned))
        if len(mentioned) >= 2:
            prior, current = mentioned[0], mentioned[1]
        else:
            prior, current = periods[-2], periods[-1]
        rep = compare_periods(transactions, prior, current)
        # Which metric is the user asking about?
        target_metric = None
        for metric, kws in metric_map.items():
            if any(kw in q for kw in kws):
                target_metric = metric
                break
        material_cats = [cv for cv in rep.category_variances if cv["material"]] \
            if isinstance(rep.category_variances[0], dict) else \
            [vars(cv) for cv in rep.category_variances if cv.material]
        # rep.category_variances are dataclasses; normalize
        material_cats = [cv if isinstance(cv, dict) else vars(cv) for cv in rep.category_variances]
        material_cats = [cv for cv in material_cats if cv["material"]]
        ev = []
        for cv in material_cats[:3]:
            ev.extend(cv.get("driving_txn_ids", [])[:10])
        if target_metric:
            lv = next((vars(v) if not isinstance(v, dict) else v
                       for v in rep.line_variances
                       if (v.line if not isinstance(v, dict) else v["line"]) == target_metric), None)
            lv = lv if isinstance(lv, dict) else None
        drivers = "\n- ".join(
            f"{cv['label']}: {_fmt_money(cv['prior'])} -> {_fmt_money(cv['current'])} "
            f"({_fmt_money(cv['delta'])})" for cv in material_cats[:5]) or "no material category changes"
        return answer(
            f"Between {prior} and {current}, the material drivers were:\n- {drivers}",
            evidence=ev, data=rep.to_dict())

    # Metric queries, possibly for a specific month.
    for metric, kws in metric_map.items():
        if any(kw in q for kw in kws):
            period = _resolve_period(q, periods)
            if period:
                pnl = compute_pnl(transactions, period)
                val = getattr(pnl, metric)
                # gather evidence txns for that metric's section
                ev = _evidence_for_metric(transactions, metric, period)
                label = metric.replace("_", " ").title()
                return answer(f"{label} for {period} was {_fmt_money(val)}.",
                              evidence=ev, data={"period": period, metric: round(val, 2)})
            # all months
            series = tool_metric_by_month(transactions, metric)
            lines = "\n- ".join(f"{p}: {_fmt_money(v)}" for p, v in series["by_period"].items())
            label = metric.replace("_", " ").title()
            return answer(f"{label} by month:\n- {lines}", data=series)

    # "which transactions need attention/review"
    if any(k in q for k in ["need my attention", "need attention", "review", "flagged", "unusual"]):
        r = tool_review_items(transactions)
        ev = [t["id"] for t in r["transactions"]]
        if not ev:
            return answer("No transactions are currently flagged for review.")
        preview = "\n- ".join(f"{t['date']} {t['description']} {_fmt_money(t['amount'])} "
                              f"({t['reason']})" for t in r["transactions"][:8])
        return answer(f"{r['count']} transaction(s) need review:\n- {preview}",
                      evidence=ev, data=r)

    # "show me the transactions behind that / for X"
    if "transaction" in q or "show me" in q:
        period = _resolve_period(q, periods) or periods[-1]
        # try to detect a category by label
        for c in CATEGORIES:
            if c.label.lower() in q or c.key in q:
                res = tool_txns_for_category_period(transactions, c.key, period)
                ev = [t["id"] for t in res["transactions"]]
                preview = "\n- ".join(f"{t['date']} {t['description']} {_fmt_money(t['amount'])}"
                                     for t in res["transactions"][:10])
                return answer(f"{c.label} transactions in {period}:\n- {preview}",
                              evidence=ev, data=res)

    # Fallback: give the latest month's snapshot.
    latest = periods[-1]
    pnl = compute_pnl(transactions, latest)
    return answer(
        f"Here's the {latest} snapshot: revenue {_fmt_money(pnl.revenue)}, "
        f"COGS {_fmt_money(pnl.cogs)}, gross profit {_fmt_money(pnl.gross_profit)}, "
        f"payroll {_fmt_money(pnl.payroll)}, operating expenses {_fmt_money(pnl.operating_expenses)}, "
        f"operating profit {_fmt_money(pnl.operating_profit)}. "
        f"Ask about a specific month, metric, variance, or items needing review.",
        data=pnl.to_dict())


def _evidence_for_metric(transactions: list[dict], metric: str, period: str) -> list[int]:
    section_for_metric = {
        "revenue": "Revenue", "cogs": "Cost of Goods Sold",
        "payroll": "Payroll", "operating_expenses": "Operating Expenses",
    }
    sec = section_for_metric.get(metric)
    ids = []
    for t in transactions:
        if t.get("period") != period:
            continue
        cat = get_category(t.get("category_key", "uncategorized"))
        if sec is None or cat.section.value == sec:
            ids.append(int(t["id"]))
    return ids[:50]


def analyst_answer(question: str, transactions: list[dict]) -> dict:
    """Answer a question. Numbers always come from deterministic tools.

    If an LLM is available, it is used ONLY to phrase the final answer around the
    deterministic result (never to produce numbers). Otherwise the deterministic
    answer is returned directly.
    """
    result = _deterministic_answer(question, transactions)

    # If no data is loaded, return the clear message directly. Do NOT let the LLM
    # rephrase it, or it may turn "no data loaded" into a misleading "no figures for
    # March" that wrongly implies data exists.
    if not transactions:
        result["llm_used"] = False
        return result

    if llm_available():
        system = (
            "You are a careful financial analyst for a restaurant. You are given a user "
            "question and a JSON block of VERIFIED figures computed by a deterministic "
            "engine. Write a concise, plain-English answer using ONLY those figures. "
            "Never invent or recompute numbers. If the data does not contain the answer, "
            "say so. Keep it to a few sentences."
        )
        user = (
            f"Question: {question}\n\n"
            f"Verified data (authoritative, do not alter numbers):\n"
            f"{json.dumps(result.get('data', {}), default=str)[:6000]}\n\n"
            f"Draft answer from the engine: {result['answer']}\n\n"
            "Rewrite the answer clearly. Do not change any number."
        )
        phrased = _call_llm(system, user, max_tokens=900)
        if phrased:
            result["answer"] = phrased.strip()
            result["llm_used"] = True
    else:
        result["llm_used"] = False

    return result
