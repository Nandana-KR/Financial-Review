"""
Deterministic P&L engine.

Every number in the financial statements is computed here, in plain Python, by
summing categorized transactions. No language model is involved in any total.

Sign convention from ingest:
    positive amount = inflow (money in)
    negative amount = outflow (money out)

P&L presentation convention:
    Revenue  -> reported as positive (sum of inflows)
    COGS / Payroll / OpEx -> reported as positive expense magnitudes
    Gross Profit    = Revenue - COGS
    Operating Profit = Gross Profit - Payroll - Operating Expenses

Non-P&L categories (transfers, owner draws, loans, capex, taxes) are excluded.
"""

from __future__ import annotations
from dataclasses import dataclass, field
from typing import Optional

from .chart_of_accounts import (
    PnLSection, CATEGORY_BY_KEY, get_category, PNL_SECTION_ORDER,
)


@dataclass
class LineItem:
    category_key: str
    label: str
    amount: float          # positive magnitude in its section's convention
    txn_count: int


@dataclass
class PnLStatement:
    period: str            # YYYY-MM
    revenue: float
    cogs: float
    gross_profit: float
    payroll: float
    operating_expenses: float
    operating_profit: float
    lines_by_section: dict[str, list[LineItem]] = field(default_factory=dict)
    excluded_non_pnl: float = 0.0   # net of non-P&L movements, for transparency

    def to_dict(self) -> dict:
        return {
            "period": self.period,
            "revenue": round(self.revenue, 2),
            "cogs": round(self.cogs, 2),
            "gross_profit": round(self.gross_profit, 2),
            "payroll": round(self.payroll, 2),
            "operating_expenses": round(self.operating_expenses, 2),
            "operating_profit": round(self.operating_profit, 2),
            "excluded_non_pnl": round(self.excluded_non_pnl, 2),
            "lines_by_section": {
                section: [
                    {
                        "category_key": li.category_key,
                        "label": li.label,
                        "amount": round(li.amount, 2),
                        "txn_count": li.txn_count,
                    }
                    for li in items
                ]
                for section, items in self.lines_by_section.items()
            },
        }


def compute_pnl(transactions: list[dict], period: str) -> PnLStatement:
    """Compute a P&L for a single month (period = 'YYYY-MM')."""
    selected = [t for t in transactions if t.get("period") == period]
    return _compute_from_rows(selected, label=period)


def compute_pnl_range(transactions: list[dict], start: str | None,
                      end: str | None) -> PnLStatement:
    """Compute a P&L over an arbitrary inclusive date range (ISO 'YYYY-MM-DD').

    Either bound may be None (open-ended). Used by the date-range filter. Note:
    a P&L over a partial range is only as meaningful as the range chosen; for
    standard reporting, whole months are recommended.
    """
    def in_range(t):
        d = t.get("txn_date", "")
        if start and d < start:
            return False
        if end and d > end:
            return False
        return True

    selected = [t for t in transactions if in_range(t)]
    if start and end:
        label = f"{start} to {end}"
    elif start:
        label = f"from {start}"
    elif end:
        label = f"through {end}"
    else:
        label = "All dates"
    return _compute_from_rows(selected, label=label)


def _compute_from_rows(rows: list[dict], label: str) -> PnLStatement:
    """Shared deterministic P&L computation over an already-filtered set of rows."""
    period = label
    # Accumulators keyed by category.
    cat_totals: dict[str, float] = {}
    cat_counts: dict[str, int] = {}

    for t in rows:
        key = t.get("category_key", "uncategorized")
        cat_totals[key] = cat_totals.get(key, 0.0) + float(t["amount"])
        cat_counts[key] = cat_counts.get(key, 0) + 1

    revenue = 0.0
    cogs = 0.0
    payroll = 0.0
    opex = 0.0
    excluded = 0.0

    lines_by_section: dict[str, list[LineItem]] = {
        s.value: [] for s in PNL_SECTION_ORDER
    }

    for cat_key, total in cat_totals.items():
        cat = get_category(cat_key)
        count = cat_counts.get(cat_key, 0)

        if not cat.is_pnl:
            excluded += total
            continue

        if cat.section == PnLSection.REVENUE:
            # Revenue is inflow; present as positive.
            magnitude = total  # already positive for inflows
            revenue += magnitude
            lines_by_section[PnLSection.REVENUE.value].append(
                LineItem(cat_key, cat.label, round(magnitude, 2), count)
            )
        else:
            # Expense sections: present as positive magnitude of the outflow.
            magnitude = -total  # outflows are negative, flip to positive expense
            if cat.section == PnLSection.COGS:
                cogs += magnitude
            elif cat.section == PnLSection.PAYROLL:
                payroll += magnitude
            elif cat.section == PnLSection.OPERATING_EXPENSES:
                opex += magnitude
            lines_by_section[cat.section.value].append(
                LineItem(cat_key, cat.label, round(magnitude, 2), count)
            )

    # Sort line items within each section by descending magnitude.
    for items in lines_by_section.values():
        items.sort(key=lambda li: abs(li.amount), reverse=True)

    gross_profit = revenue - cogs
    operating_profit = gross_profit - payroll - opex

    return PnLStatement(
        period=period,
        revenue=revenue,
        cogs=cogs,
        gross_profit=gross_profit,
        payroll=payroll,
        operating_expenses=opex,
        operating_profit=operating_profit,
        lines_by_section=lines_by_section,
        excluded_non_pnl=excluded,
    )


def list_periods(transactions: list[dict]) -> list[str]:
    """Return sorted distinct periods present in the data."""
    return sorted({t["period"] for t in transactions if t.get("period")})


def compute_all_pnls(transactions: list[dict]) -> list[PnLStatement]:
    return [compute_pnl(transactions, p) for p in list_periods(transactions)]
