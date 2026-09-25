"""
Verification script for the financial engine.

Runs the full deterministic pipeline on a transaction file and asserts the core
accounting identities hold exactly. This is how correctness of the calculated
output is verified (independent of the AI layer):

    Gross Profit      == Revenue - COGS
    Operating Profit  == Gross Profit - Payroll - Operating Expenses

Usage:
    python verify.py [path-to-xlsx-or-csv]

Defaults to "transactions.xlsx" if no path is given. Uses a temporary, isolated
database so it never touches the app's data.
"""

from __future__ import annotations
import os
import sys

# Use an isolated database so verification never disturbs the running app's data.
os.environ["FINZ_DB_PATH"] = os.path.join(os.path.dirname(__file__), "_verify.db")

from app.db import init_db, reset_db          # noqa: E402
from app.ingest import parse_file             # noqa: E402
from app import repository as repo            # noqa: E402
from app.pnl import compute_all_pnls, list_periods  # noqa: E402


def main() -> int:
    path = sys.argv[1] if len(sys.argv) > 1 else os.path.join(os.path.dirname(__file__), "..", "NYC Restaurant Co. - Raw Transactions.xlsx")
    if not os.path.exists(path):
        print(f"File not found: {path}")
        return 1

    init_db()
    reset_db()

    with open(path, "rb") as f:
        parsed = parse_file(os.path.basename(path), f.read())
    if not parsed:
        print("No transactions parsed from the file.")
        return 1
    repo.insert_and_categorize(parsed)

    txns = repo.all_transactions()
    periods = list_periods(txns)
    print(f"Parsed {len(parsed)} transactions across {len(periods)} month(s): {', '.join(periods)}")

    ok = True
    for pnl in compute_all_pnls(txns):
        gp_ok = abs(pnl.gross_profit - (pnl.revenue - pnl.cogs)) < 0.01
        op_ok = abs(pnl.operating_profit -
                    (pnl.gross_profit - pnl.payroll - pnl.operating_expenses)) < 0.01
        status = "OK" if (gp_ok and op_ok) else "FAILED"
        if not (gp_ok and op_ok):
            ok = False
        print(f"  {pnl.period}: revenue={pnl.revenue:,.2f} "
              f"operating_profit={pnl.operating_profit:,.2f}  [{status}]")

    # Clean up the temporary verification database.
    try:
        os.remove(os.environ["FINZ_DB_PATH"])
    except OSError:
        pass

    print("\nAll accounting identities verified." if ok else "\nVERIFICATION FAILED.")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
