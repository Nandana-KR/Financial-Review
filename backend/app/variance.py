"""
Variance analysis.

Compares two periods' P&Ls (deterministically) and identifies material changes at
both the summary-line level (Revenue, COGS, ...) and the category level. For each
material category change it also surfaces the specific transactions driving it, so a
user can trace a variance all the way down to evidence.

Materiality is defined by BOTH an absolute dollar threshold and a percentage
threshold, so we don't flag tiny lines that happen to swing a large %.
"""

from __future__ import annotations
from dataclasses import dataclass
from typing import Optional

from .pnl import compute_pnl, PnLStatement
from .chart_of_accounts import get_category

ABS_THRESHOLD = 500.0     # dollars
PCT_THRESHOLD = 0.15      # 15%


@dataclass
class CategoryVariance:
    category_key: str
    label: str
    section: str
    prior: float
    current: float
    delta: float
    pct_change: Optional[float]
    material: bool
    driving_txn_ids: list[int]


@dataclass
class LineVariance:
    line: str            # e.g. "revenue", "operating_profit"
    label: str
    prior: float
    current: float
    delta: float
    pct_change: Optional[float]
    material: bool


@dataclass
class VarianceReport:
    prior_period: str
    current_period: str
    line_variances: list[LineVariance]
    category_variances: list[CategoryVariance]

    def to_dict(self) -> dict:
        return {
            "prior_period": self.prior_period,
            "current_period": self.current_period,
            "line_variances": [vars(v) for v in self.line_variances],
            "category_variances": [vars(v) for v in self.category_variances],
        }


def _pct(prior: float, current: float) -> Optional[float]:
    if abs(prior) < 1e-9:
        return None
    return (current - prior) / abs(prior)


def _is_material(delta: float, prior: float) -> bool:
    if abs(delta) < ABS_THRESHOLD:
        return False
    pct = _pct(prior, prior + delta)
    if pct is None:
        return abs(delta) >= ABS_THRESHOLD
    return abs(pct) >= PCT_THRESHOLD


SUMMARY_LINES = [
    ("revenue", "Revenue"),
    ("cogs", "Cost of Goods Sold"),
    ("gross_profit", "Gross Profit"),
    ("payroll", "Payroll"),
    ("operating_expenses", "Operating Expenses"),
    ("operating_profit", "Operating Profit"),
]


def _category_totals(transactions: list[dict], period: str) -> dict[str, tuple[float, list[int]]]:
    """Return category_key -> (signed_total, [txn_ids]) for a period."""
    out: dict[str, tuple[float, list[int]]] = {}
    for t in transactions:
        if t.get("period") != period:
            continue
        key = t.get("category_key", "uncategorized")
        total, ids = out.get(key, (0.0, []))
        out[key] = (total + float(t["amount"]), ids + [int(t["id"])])
    return out


def compare_periods(
    transactions: list[dict],
    prior_period: str,
    current_period: str,
) -> VarianceReport:
    prior_pnl: PnLStatement = compute_pnl(transactions, prior_period)
    current_pnl: PnLStatement = compute_pnl(transactions, current_period)

    # Summary-line variances.
    line_variances: list[LineVariance] = []
    for attr, label in SUMMARY_LINES:
        p = getattr(prior_pnl, attr)
        c = getattr(current_pnl, attr)
        delta = c - p
        line_variances.append(LineVariance(
            line=attr, label=label, prior=round(p, 2), current=round(c, 2),
            delta=round(delta, 2), pct_change=_pct(p, c),
            material=_is_material(delta, p),
        ))

    # Category-level variances (as expense/revenue magnitudes for readability).
    prior_cats = _category_totals(transactions, prior_period)
    current_cats = _category_totals(transactions, current_period)
    all_keys = set(prior_cats) | set(current_cats)

    category_variances: list[CategoryVariance] = []
    for key in all_keys:
        cat = get_category(key)
        p_total, _ = prior_cats.get(key, (0.0, []))
        c_total, c_ids = current_cats.get(key, (0.0, []))

        # Present magnitudes consistent with the P&L (expenses positive).
        if cat.section.value == "Revenue":
            p_mag, c_mag = p_total, c_total
        else:
            p_mag, c_mag = -p_total, -c_total

        delta = c_mag - p_mag
        material = _is_material(delta, p_mag)

        category_variances.append(CategoryVariance(
            category_key=key,
            label=cat.label,
            section=cat.section.value,
            prior=round(p_mag, 2),
            current=round(c_mag, 2),
            delta=round(delta, 2),
            pct_change=_pct(p_mag, c_mag),
            material=material,
            # Driving transactions: the current-period transactions in this category,
            # largest first, so a user can jump straight to the evidence.
            driving_txn_ids=c_ids,
        ))

    # Order: material first, then by absolute delta.
    category_variances.sort(key=lambda v: (not v.material, -abs(v.delta)))

    return VarianceReport(
        prior_period=prior_period,
        current_period=current_period,
        line_variances=line_variances,
        category_variances=category_variances,
    )


def most_significant_changes(transactions: list[dict], periods: list[str], top_n: int = 5):
    """Across the whole review period, find the largest category movements between
    the first and last period present. Used to answer 'what changed most?'."""
    if len(periods) < 2:
        return None
    report = compare_periods(transactions, periods[0], periods[-1])
    material = [cv for cv in report.category_variances if cv.material]
    return {
        "prior_period": periods[0],
        "current_period": periods[-1],
        "changes": [vars(cv) for cv in material[:top_n]],
    }
