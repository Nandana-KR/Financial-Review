"""
Chart of Accounts for a restaurant business.

This is the deterministic financial backbone of the application. It defines:
  - Every category a transaction can be assigned to.
  - Which P&L section each category rolls up into (or that it is NOT a P&L item).
  - The sign convention (whether the category represents inflow or outflow).

Nothing here depends on an LLM. The AI layer may *suggest* a category, but the
category's financial meaning (which P&L line it hits, its sign) is fixed here.
"""

from __future__ import annotations
from dataclasses import dataclass
from enum import Enum


class PnLSection(str, Enum):
    """Sections of the Profit & Loss statement, in presentation order."""
    REVENUE = "Revenue"
    COGS = "Cost of Goods Sold"
    PAYROLL = "Payroll"
    OPERATING_EXPENSES = "Operating Expenses"
    # Items that must NOT appear in the P&L (balance sheet / financing / transfers).
    NON_PNL = "Non-P&L"


@dataclass(frozen=True)
class Category:
    key: str                 # stable machine key, e.g. "food_supplies"
    label: str               # human label, e.g. "Food Supplies"
    section: PnLSection      # which P&L section it belongs to
    is_pnl: bool             # convenience flag; False for balance-sheet/transfer items
    description: str         # guidance used by the categorizer + shown to users


# The canonical category list. Keys are stable identifiers used throughout the app.
CATEGORIES: list[Category] = [
    # ---- Revenue ----
    Category("sales_revenue", "Sales Revenue", PnLSection.REVENUE, True,
             "Income from food, beverage and dine-in/takeout sales, POS deposits, delivery platform payouts."),
    Category("other_income", "Other Income", PnLSection.REVENUE, True,
             "Non-core income such as refunds received, rebates, or miscellaneous receipts."),

    # ---- Cost of Goods Sold ----
    Category("food_supplies", "Food Supplies", PnLSection.COGS, True,
             "Ingredients and food inventory from suppliers, produce, meat, dairy, dry goods."),
    Category("beverage_supplies", "Beverage Supplies", PnLSection.COGS, True,
             "Alcohol, soft drinks, coffee, and other beverage inventory purchased for resale."),
    Category("kitchen_supplies", "Kitchen & Packaging Supplies", PnLSection.COGS, True,
             "Consumable packaging, takeout containers, napkins directly tied to serving food."),

    # ---- Payroll ----
    Category("payroll_wages", "Payroll & Wages", PnLSection.PAYROLL, True,
             "Employee wages, salaries, tips paid out, payroll processor runs (Gusto, ADP)."),
    Category("payroll_taxes", "Payroll Taxes & Benefits", PnLSection.PAYROLL, True,
             "Employer payroll taxes, health benefits, workers comp tied to staffing."),

    # ---- Operating Expenses ----
    Category("rent", "Rent & Occupancy", PnLSection.OPERATING_EXPENSES, True,
             "Base rent, lease payments for the premises."),
    Category("utilities", "Utilities", PnLSection.OPERATING_EXPENSES, True,
             "Electricity, gas, water, internet, phone."),
    Category("marketing", "Marketing & Advertising", PnLSection.OPERATING_EXPENSES, True,
             "Ads, social media, promotions, listing/marketing fees."),
    Category("repairs_maintenance", "Repairs & Maintenance", PnLSection.OPERATING_EXPENSES, True,
             "Equipment repair, cleaning services, general upkeep."),
    Category("insurance", "Insurance", PnLSection.OPERATING_EXPENSES, True,
             "Business, liability, property insurance premiums."),
    Category("software_subscriptions", "Software & Subscriptions", PnLSection.OPERATING_EXPENSES, True,
             "POS software, accounting tools, SaaS subscriptions."),
    Category("bank_fees", "Bank & Card Processing Fees", PnLSection.OPERATING_EXPENSES, True,
             "Merchant processing fees, bank service charges, card fees."),
    Category("professional_services", "Professional Services", PnLSection.OPERATING_EXPENSES, True,
             "Accounting, legal, consulting fees."),
    Category("office_admin", "Office & Administrative", PnLSection.OPERATING_EXPENSES, True,
             "Office supplies, small admin costs, licenses and permits."),
    Category("other_operating", "Other Operating Expense", PnLSection.OPERATING_EXPENSES, True,
             "Operating expense that does not fit a more specific category."),

    # ---- Non-P&L (must be excluded from the P&L) ----
    Category("owner_draw", "Owner Draw / Contribution", PnLSection.NON_PNL, False,
             "Owner taking money out or putting capital in. Equity movement, not an expense or income."),
    Category("loan_proceeds", "Loan Proceeds", PnLSection.NON_PNL, False,
             "Cash received from a loan. Financing inflow, not revenue."),
    Category("loan_repayment", "Loan Repayment", PnLSection.NON_PNL, False,
             "Principal repayment on a loan. Financing outflow, not an expense (interest is an expense)."),
    Category("transfer", "Internal Transfer", PnLSection.NON_PNL, False,
             "Movement between the company's own accounts. Nets to zero, not a P&L item."),
    Category("tax_payment", "Income Tax Payment", PnLSection.NON_PNL, False,
             "Corporate/income tax remittance. Below operating profit; excluded from operating P&L."),
    Category("capital_expenditure", "Capital Expenditure", PnLSection.NON_PNL, False,
             "Purchase of long-lived equipment/assets. Capitalized, not an operating expense."),

    # ---- Fallback ----
    Category("uncategorized", "Uncategorized", PnLSection.NON_PNL, False,
             "Could not be confidently categorized. Excluded from P&L until reviewed."),
]

# Fast lookup by key.
CATEGORY_BY_KEY: dict[str, Category] = {c.key: c for c in CATEGORIES}

# P&L presentation order for sections.
PNL_SECTION_ORDER: list[PnLSection] = [
    PnLSection.REVENUE,
    PnLSection.COGS,
    PnLSection.PAYROLL,
    PnLSection.OPERATING_EXPENSES,
]


def get_category(key: str) -> Category:
    """Return a Category by key, falling back to 'uncategorized' if unknown."""
    return CATEGORY_BY_KEY.get(key, CATEGORY_BY_KEY["uncategorized"])


def valid_category_keys() -> set[str]:
    return set(CATEGORY_BY_KEY.keys())
