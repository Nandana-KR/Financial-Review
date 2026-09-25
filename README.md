# Financial Review App

A simple tool that takes your restaurant bank statements and turns them into easy-to-understand financial reports. Upload your transactions, and the app automatically categorizes them, calculates your profits/losses, and even answers questions about your finances.

---

## What It Does

1. **Upload** — Drop your Excel file with bank transactions
2. **Auto-Categorize** — Every transaction is sorted into the right category (food, payroll, rent, etc.)
3. **Review** — Check and fix any transactions that need attention
4. **Profit Report** — See your monthly Revenue, Costs, and Profit
5. **Compare** — See what changed between months
6. **Ask Questions** — Chat with an AI analyst about your finances

---

## Quick Start

### 1. Start the Backend

```powershell
cd backend
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe -m uvicorn app.main:app --reload --port 8000
```

### 2. Start the Frontend

```powershell
cd frontend
npm install
npm run dev
```

### 3. Use the App

Open your browser to **http://localhost:5173**

1. Go to the **Ingest** tab
2. Upload your bank statement (Excel `.xlsx` or CSV)
3. Browse the different tabs to see your data

---

## Your Data

Upload your own Excel file (`.xlsx` or `.csv`) with columns like:
- Date
- Description
- Amount

The app automatically detects the columns.

---

## Want AI Features?

The app works fully without any AI API key. But if you want the AI analyst to answer questions in natural language:

```powershell
# Groq (free)
$env:FINZ_LLM_PROVIDER = "groq"
$env:FINZ_LLM_API_KEY  = "your-groq-key"

# or OpenAI
$env:FINZ_LLM_PROVIDER = "openai"
$env:FINZ_LLM_API_KEY  = "your-openai-key"
```

Then restart the backend.

---

## Questions the AI Analyst Can Answer

- "What was our revenue in March?"
- "How much did we spend on payroll each month?"
- "Why did profit change between February and March?"
- "Which transactions need my attention?"

Every answer links back to the actual transactions.

---

## How It Works

- **Rules-based categorization** — Common vendors (Sysco, Gusto, Con Edison) are automatically recognized
- **AI for tricky cases** — When unsure, AI suggests a category
- **Deterministic math** — All profit numbers are calculated by code, not AI — so they're always accurate
- **SQLite database** — All data stored locally in a simple file

---

## Files

- `backend/` — The API server (Python)
- `frontend/` — The web interface (React)
- `backend/transactions.xlsx` — Sample data file
- `backend/verify.py` — Script to verify calculations are correct

---

## Verify the Math

Run this to confirm all profit calculations are correct:

```powershell
cd backend
.\.venv\Scripts\python.exe verify.py
```

This checks that Gross Profit = Revenue - Costs, and Operating Profit = Gross Profit - Expenses.

---

## Need Help?

The app has 6 main sections:

| Tab | What You'll See |
|-----|-----------------|
| **Ingest** | Upload your bank statement |
| **Transactions** | List of all transactions with categories |
| **P&L** | Monthly profit and loss report |
| **Variances** | What changed between months |
| **Review Queue** | Items that need your attention |
| **AI Analyst** | Chat to ask questions about your finances |

---

**Tech Stack:** Python (FastAPI), SQLite, React, Vite

**Note:** All financial numbers come from deterministic code. AI is only used for categorizing tricky transactions and phrasing answers — never for calculating totals.