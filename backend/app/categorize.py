"""
Categorization engine.

Strategy (in priority order):
  1. Learned user corrections  -> highest trust (source="user", confidence 1.0)
  2. Deterministic keyword rules -> high trust when a strong match (source="rule")
  3. AI classifier (optional)    -> used when rules are weak/ambiguous (source="ai")
  4. Fallback "uncategorized"    -> flagged for review

IMPORTANT: The categorizer only decides *which category* a transaction belongs to.
It never computes financial totals. Category -> P&L mapping and all arithmetic are
handled deterministically in chart_of_accounts.py and pnl.py.

The AI classifier is optional and provider-agnostic. If no API key is configured,
the engine runs fully on rules + learned corrections, so the app works offline.
"""

from __future__ import annotations
import re
from dataclasses import dataclass
from typing import Optional

from .chart_of_accounts import get_category, valid_category_keys


@dataclass
class CategorizationResult:
    category_key: str
    confidence: float          # 0..1
    source: str                # 'rule' | 'ai' | 'user' | 'none'
    rationale: str
    needs_review: bool
    review_reason: Optional[str]


# Keyword rules: (category_key, list_of_regex_keywords, base_confidence).
# Ordered by specificity; earlier strong matches win.
RULES: list[tuple[str, list[str], float]] = [
    ("payroll_wages", [r"\bpayroll\b", r"\bgusto\b", r"\badp\b", r"\bwages?\b",
                        r"\bsalary\b", r"\bsalaries\b", r"paychex", r"\btips? payout\b"], 0.95),
    ("payroll_taxes", [r"payroll tax", r"\beftps\b", r"irs.*payroll", r"\b941\b",
                       r"health (insurance|benefit)", r"workers? comp"], 0.9),
    ("rent", [r"\brent\b", r"\blease\b", r"landlord", r"property mgmt", r"realty"], 0.92),
    ("utilities", [r"\bcon ?ed\b", r"national grid", r"\butility\b", r"\butilities\b",
                   r"electric", r"\bgas co\b", r"water", r"verizon", r"comcast",
                   r"\bat&t\b", r"spectrum", r"internet", r"\bphone\b"], 0.88),
    ("food_supplies", [r"sysco", r"us ?foods", r"restaurant depot", r"produce",
                       r"\bmeat\b", r"seafood", r"\bfarms?\b", r"food (supply|service|dist)",
                       r"grocery", r"wholesale food", r"baldor", r"\bdairy\b"], 0.9),
    ("beverage_supplies", [r"beverage", r"\bwine\b", r"\bliquor\b", r"brewery",
                           r"distribut.*bev", r"coffee", r"\bbeer\b", r"soda", r"\bcoke\b",
                           r"pepsi", r"\bbar supply\b"], 0.88),
    ("kitchen_supplies", [r"packaging", r"containers?", r"napkins?", r"to.?go",
                          r"webstaurant", r"paper (goods|supply)", r"disposables?"], 0.82),
    ("marketing", [r"\bads?\b", r"advertis", r"marketing", r"\byelp\b", r"google ads",
                   r"facebook", r"\bmeta\b", r"instagram", r"promo", r"grubhub mktg",
                   r"mailchimp"], 0.85),
    ("bank_fees", [r"bank fee", r"service charge", r"\bnsf\b", r"overdraft",
                   r"card fee", r"processing fee", r"merchant fee", r"\bstripe fee\b",
                   r"square fee", r"interchange"], 0.9),
    ("software_subscriptions", [r"\btoast\b", r"\bsquare\b", r"\bclover\b", r"quickbooks",
                                r"\bintuit\b", r"subscription", r"\bsaas\b", r"software",
                                r"\bopentable\b", r"\bresy\b", r"microsoft", r"\bgoogle\b",
                                r"adobe", r"dropbox"], 0.8),
    ("insurance", [r"insurance", r"\bhartford\b", r"geico", r"\bstate farm\b",
                   r"liberty mutual", r"premium"], 0.9),
    ("repairs_maintenance", [r"repair", r"maintenance", r"plumb", r"\bhvac\b",
                             r"cleaning", r"\bpest\b", r"exterminat", r"equipment service"], 0.85),
    ("professional_services", [r"accounting", r"\bcpa\b", r"\blegal\b", r"attorney",
                               r"\blaw\b", r"consult", r"bookkeep", r"payroll service"], 0.82),
    ("office_admin", [r"office", r"staples", r"license", r"permit", r"\bdmv\b",
                      r"filing fee", r"supplies"], 0.7),

    # Revenue
    ("sales_revenue", [r"\bpos\b", r"card settlement", r"\bdeposit\b.*sales",
                       r"\btoast\b.*payout", r"\bsquare\b.*payout", r"grubhub", r"doordash",
                       r"uber ?eats", r"seamless", r"daily sales", r"batch deposit",
                       r"merchant deposit", r"stripe payout"], 0.8),

    # Non-P&L
    ("owner_draw", [r"owner draw", r"owner('s)? draw", r"distribution", r"capital contribution",
                    r"member draw", r"shareholder"], 0.9),
    ("loan_proceeds", [r"loan (proceeds|advance|disburs)", r"\bsba\b.*loan", r"line of credit draw"], 0.88),
    ("loan_repayment", [r"loan (payment|repay)", r"\bemi\b", r"principal payment",
                        r"note payment", r"\bsba\b.*payment"], 0.85),
    ("transfer", [r"transfer", r"\bxfer\b", r"\bzelle\b", r"internal", r"to savings",
                  r"from savings", r"book transfer"], 0.7),
    ("tax_payment", [r"income tax", r"corporate tax", r"\bfranchise tax\b",
                     r"tax payment", r"nys tax", r"sales tax remit"], 0.8),
    ("capital_expenditure", [r"equipment purchase", r"\boven\b", r"\bfreezer\b",
                             r"\brefrigerator\b", r"furniture", r"build ?out",
                             r"renovation", r"\bcapex\b"], 0.7),
]

# Amount-based hints used only to break ties / sanity check, never to invent totals.
CONFIDENCE_REVIEW_THRESHOLD = 0.6


def normalize_pattern(description: str, counterparty: Optional[str] = None) -> str:
    """Create a stable key for matching learned corrections.

    Strips digits and punctuation so 'SYSCO #12345 03/04' and 'SYSCO #98765 03/19'
    map to the same learned pattern.
    """
    base = f"{counterparty or ''} {description}".lower()
    base = re.sub(r"\d+", " ", base)
    base = re.sub(r"[^a-z ]+", " ", base)
    base = re.sub(r"\s+", " ", base).strip()
    return base[:120]


def _apply_rules(text: str, amount: float) -> Optional[tuple[str, float, str]]:
    """Return (category_key, confidence, matched_keyword) for the best rule match.

    The transaction's sign is a strong deterministic signal that disambiguates
    vendors whose name means different things depending on direction. For example
    "TOAST" is the POS software (an outflow) but "TOAST POS Payout" is a sales
    deposit (an inflow). We therefore:
      - suppress Revenue-section rules for outflows (money out is never revenue),
      - suppress expense-section rules for meaningful inflows (money in is not an
        expense), and
      - for a clear inflow, prefer the sales_revenue rule when it matches.
    """
    is_inflow = amount > 0
    is_outflow = amount < 0

    best: Optional[tuple[str, float, str]] = None
    for cat_key, patterns, base_conf in RULES:
        cat = get_category(cat_key)
        section = cat.section.value

        # Directional suppression.
        if is_outflow and section == "Revenue":
            continue  # an outflow can't be revenue
        if is_inflow and cat.is_pnl and section != "Revenue":
            # money in should not map to an expense category
            continue

        for pat in patterns:
            if re.search(pat, text):
                cleaned = pat.replace(r"\b", "").replace(".*", " ").strip()
                conf = base_conf
                # For a clear inflow, boost revenue so it wins any remaining ties.
                if is_inflow and section == "Revenue":
                    conf = max(conf, 0.9)
                candidate = (cat_key, conf, cleaned)
                if best is None or candidate[1] > best[1]:
                    best = candidate
                break
    return best


def categorize(
    description: str,
    amount: float,
    counterparty: Optional[str],
    corrections: dict[str, str],
    ai_classifier=None,
) -> CategorizationResult:
    """Categorize one transaction.

    `corrections` maps normalized-pattern -> category_key (learned from users).
    `ai_classifier` is an optional callable(description, amount, counterparty) ->
        (category_key, confidence, rationale) or None.
    """
    text = f"{counterparty or ''} {description}".lower()
    pattern = normalize_pattern(description, counterparty)

    # 1) Learned user correction wins outright.
    if pattern in corrections:
        cat = corrections[pattern]
        if cat in valid_category_keys():
            return CategorizationResult(
                category_key=cat, confidence=1.0, source="user",
                rationale="Matched a saved user correction for this description pattern.",
                needs_review=False, review_reason=None,
            )

    # 2) Deterministic rules (amount-sign aware).
    rule = _apply_rules(text, amount)

    # An inflow that matched no revenue rule is income we couldn't attribute to a
    # specific source. Treat as other_income with modest confidence rather than
    # forcing it into an expense bucket.
    if rule is None and amount > 0:
        rule = ("other_income", 0.55, "unmatched inflow -> other income")

    # 3) Optional AI classifier when rules are weak or absent.
    ai_result = None
    if (rule is None or rule[1] < 0.85) and ai_classifier is not None:
        try:
            ai_result = ai_classifier(description, amount, counterparty)
        except Exception:
            ai_result = None

    # Decide between rule and AI.
    chosen_key: str
    confidence: float
    source: str
    rationale: str

    if rule is not None and (ai_result is None or rule[1] >= ai_result[1]):
        chosen_key, confidence, matched = rule
        source = "rule"
        rationale = f"Keyword rule matched '{matched}'."
    elif ai_result is not None:
        chosen_key, confidence, rationale = ai_result
        source = "ai"
        if chosen_key not in valid_category_keys():
            chosen_key, confidence = "uncategorized", 0.0
    else:
        chosen_key, confidence, source, rationale = (
            "uncategorized", 0.0, "none",
            "No rule matched and no AI classifier available.",
        )

    # Sign sanity: a category in Revenue with a strong outflow (or vice versa) is suspicious.
    cat_obj = get_category(chosen_key)
    needs_review = False
    review_reason: Optional[str] = None

    if confidence < CONFIDENCE_REVIEW_THRESHOLD:
        needs_review = True
        review_reason = "Low categorization confidence."

    if cat_obj.section.value == "Revenue" and amount < 0 and confidence >= CONFIDENCE_REVIEW_THRESHOLD:
        needs_review = True
        review_reason = "Classified as Revenue but the amount is an outflow (negative)."
    if cat_obj.is_pnl and cat_obj.section.value != "Revenue" and amount > 0 and abs(amount) > 1:
        # An expense category showing money IN is worth a human glance.
        if chosen_key not in ("other_income",):
            needs_review = True
            review_reason = review_reason or "Expense category but the amount is an inflow (positive)."

    if chosen_key == "uncategorized":
        needs_review = True
        review_reason = review_reason or "Could not confidently categorize."

    return CategorizationResult(
        category_key=chosen_key,
        confidence=round(confidence, 3),
        source=source,
        rationale=rationale,
        needs_review=needs_review,
        review_reason=review_reason,
    )
