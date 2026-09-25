"""
Generate a realistic sample restaurant transaction workbook (transactions.xlsx).

Creates 3 months (Jan-Mar 2025) with:
  - Daily-ish sales deposits (POS payouts, delivery platforms)
  - Recurring costs (rent, payroll, utilities, insurance, software)
  - Food & beverage supplier purchases (with a deliberate March food-cost spike)
  - Some non-P&L items (owner draw, loan repayment, transfer, capex)
  - A few ambiguous descriptions that should land in the review queue

Run:  python sample_data.py
Then ingest transactions.xlsx via the app.
"""

from __future__ import annotations
import random
from datetime import date, timedelta
from openpyxl import Workbook

random.seed(42)

OUT = "transactions.xlsx"

rows: list[tuple] = []


def add(d: date, description: str, amount: float, counterparty: str = ""):
    # Debit/Credit layout: positive amount -> credit (money in), negative -> debit.
    debit = -amount if amount < 0 else ""
    credit = amount if amount > 0 else ""
    rows.append((d.isoformat(), description, counterparty, credit, debit, "Operating Checking"))


def month_days(year: int, month: int):
    d = date(year, month, 1)
    while d.month == month:
        yield d
        d += timedelta(days=1)


# Sales level per month; March gets a revenue bump too.
sales_base = {1: 2200, 2: 2100, 3: 2600}
food_multiplier = {1: 1.0, 2: 1.0, 3: 1.35}  # March food cost spike

for month in (1, 2, 3):
    for d in month_days(2025, month):
        # Daily POS sales deposit (skip some days for realism)
        if d.weekday() != 0:  # closed Mondays
            base = sales_base[month]
            amt = round(random.uniform(base * 0.7, base * 1.4), 2)
            add(d, "TOAST POS Payout - daily sales", amt, "Toast")
            if d.weekday() >= 4:  # busier Fri/Sat/Sun delivery
                add(d, "DoorDash Payout", round(random.uniform(200, 600), 2), "DoorDash")
                add(d, "Grubhub Deposit", round(random.uniform(150, 500), 2), "Grubhub")

    # Food suppliers (twice a week)
    for wk_day in (1, 4):
        for d in [x for x in month_days(2025, month) if x.weekday() == wk_day]:
            add(d, f"SYSCO invoice #{random.randint(10000,99999)}",
                -round(random.uniform(1800, 3200) * food_multiplier[month], 2), "Sysco")
            add(d, f"Baldor Produce delivery",
                -round(random.uniform(400, 900) * food_multiplier[month], 2), "Baldor")

    # Beverage (weekly)
    for d in [x for x in month_days(2025, month) if x.weekday() == 2][:4]:
        add(d, "Empire Wine & Liquor Distributors",
            -round(random.uniform(600, 1200), 2), "Empire Distributors")

    # Payroll (bi-weekly via Gusto)
    for day in (5, 20):
        add(date(2025, month, day), "GUSTO payroll run", -round(random.uniform(9000, 11000), 2), "Gusto")
    add(date(2025, month, 20), "EFTPS payroll tax 941", -round(random.uniform(2200, 2800), 2), "IRS")

    # Fixed operating costs
    add(date(2025, month, 1), "Rent - 123 Bleecker St LLC", -6500.00, "Bleecker Realty")
    add(date(2025, month, 8), "Con Edison electric", -round(random.uniform(900, 1400), 2), "ConEd")
    add(date(2025, month, 10), "National Grid gas", -round(random.uniform(300, 700), 2), "National Grid")
    add(date(2025, month, 12), "Verizon internet & phone", -189.99, "Verizon")
    add(date(2025, month, 15), "The Hartford insurance premium", -720.00, "The Hartford")
    add(date(2025, month, 3), "Toast software subscription", -165.00, "Toast")
    add(date(2025, month, 3), "QuickBooks Online", -80.00, "Intuit")
    add(date(2025, month, 18), "Card processing fees - Stripe", -round(random.uniform(400, 700), 2), "Stripe")
    add(date(2025, month, 22), "Yelp Ads", -350.00, "Yelp")

    # Repairs (occasional; March HVAC repair adds an OpEx bump)
    if month == 3:
        add(date(2025, 3, 14), "ACME HVAC emergency repair", -2400.00, "ACME HVAC")

    # Non-P&L items
    add(date(2025, month, 28), "Owner draw", -3000.00, "Owner")
    add(date(2025, month, 2), "SBA loan payment", -1250.00, "SBA")
    add(date(2025, month, 25), "Transfer to savings", -2000.00, "Internal")

    # Ambiguous items -> should be flagged for review
    add(date(2025, month, 16), f"AMEX payment misc {random.randint(100,999)}",
        -round(random.uniform(500, 1500), 2), "")
    add(date(2025, month, 17), "Square Cash withdrawal", -round(random.uniform(200, 800), 2), "")

# One capex in Feb
add(date(2025, 2, 11), "Equipment purchase - new freezer", -4200.00, "Restaurant Equipment Co")

# Write workbook
wb = Workbook()
ws = wb.active
ws.title = "Transactions"
ws.append(["Date", "Description", "Counterparty", "Credit", "Debit", "Account"])
for r in sorted(rows, key=lambda x: x[0]):
    ws.append(list(r))
wb.save(OUT)
print(f"Wrote {OUT} with {len(rows)} transactions across Jan-Mar 2025.")
