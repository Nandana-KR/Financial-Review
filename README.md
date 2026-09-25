# Finz — AI-Native Financial Review

Turn raw restaurant bank transactions into an explainable financial review.

Core workflow: **ingest → categorize → review → calculate → explain → investigate.**

The guiding principle: **AI is used for reasoning and interpretation; deterministic
code is used for every financial number.** A language model never generates a total.

---

## What it does

1. **Ingest** — upload a bank transaction file (`.xlsx` or `.csv`). Columns are
   auto-detected and each row is normalized to a signed amount.
2. **Categorize** — every transaction is classified into a restaurant chart of
   accounts, with a confidence score, a source (`rule` / `ai` / `user`), and a
   P&L-vs-non-P&L distinction. Uncertain items are flagged.
3. **Review** — a queue surfaces low-confidence, inconsistent, or judgment items.
   You can reassign a category (the fix is remembered and applied to similar rows)
   or mark an item resolved.
4. **Calculate** — deterministic monthly P&L: Revenue, COGS, Gross Profit, Payroll,
   Operating Expenses, Operating Profit.
5. **Explain** — variance analysis between months flags material changes and traces
   each to the categories and transactions driving it.
6. **Investigate** — a conversational analyst answers questions using the structured
   data and links to the underlying transactions as evidence.

---

## Architecture

```
finz/
├── backend/                 FastAPI + SQLite (stdlib sqlite3)
│   ├── app/
│   │   ├── chart_of_accounts.py   Categories + P&L section mapping (financial backbone)
│   │   ├── ingest.py              Flexible xlsx/csv parser -> signed transactions
│   │   ├── categorize.py          Amount-sign-aware rules + confidence + learned corrections
│   │   ├── pnl.py                 Deterministic monthly P&L engine (no LLM math)
│   │   ├── variance.py            Material change detection + traceability
│   │   ├── ai.py                  Provider-agnostic LLM: classify + analyst (tools only)
│   │   ├── repository.py          SQLite CRUD + correction propagation
│   │   ├── db.py                  Schema + connection handling
│   │   └── main.py                HTTP API
│   ├── sample_data.py             Generates a realistic transactions.xlsx
│   └── requirements.txt
└── frontend/                React + Vite single-page app
    └── src/
        ├── api.js                 API client
        ├── App.jsx                Tabs + shell
        └── components/            Ingest, Transactions, PnL, Variance, Review, Chat
```

**Data flow:** Excel/CSV → `ingest` (structured, signed rows) → `categorize` (rules
first, AI when weak, user corrections always win) → SQLite → `pnl`/`variance`
(pure-Python math) → API → React UI and the analyst.

---

## Setup

### Prerequisites
- Python 3.11+ (developed on 3.13)
- Node.js 18+ (developed on 24)

### 1. Backend

```powershell
cd backend
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt

# (optional) create a sample dataset if you don't have a file
.\.venv\Scripts\python.exe sample_data.py

# run the API
.\.venv\Scripts\python.exe -m uvicorn app.main:app --reload --port 8000
```

On macOS/Linux use `source .venv/bin/activate` then `uvicorn app.main:app --reload`.

The API runs at `http://127.0.0.1:8000`.

### 2. Frontend

```powershell
cd frontend
npm install
npm run dev
```

Open `http://localhost:5173`. The dev server proxies `/api` to the backend, so no
extra configuration is needed. Go to the **Ingest** tab and upload
`backend/transactions.xlsx` (or your own file).

### 3. (Optional) enable an LLM

The app is fully functional **without any API key** — categorization runs on rules +
learned corrections and the analyst uses deterministic intent routing. To enable an
LLM for classifying ambiguous items and for phrasing analyst answers, set environment
variables before starting the backend:

```powershell
# OpenAI
$env:FINZ_LLM_PROVIDER = "openai"
$env:FINZ_LLM_API_KEY  = "sk-..."
$env:FINZ_LLM_MODEL    = "gpt-4o-mini"

# Anthropic
$env:FINZ_LLM_PROVIDER = "anthropic"
$env:FINZ_LLM_API_KEY  = "sk-ant-..."

# Groq (free tier, OpenAI-compatible)
$env:FINZ_LLM_PROVIDER = "groq"
$env:FINZ_LLM_API_KEY  = "gsk_..."
$env:FINZ_LLM_MODEL    = "openai/gpt-oss-20b"
```

Provider is `openai` | `anthropic` | `groq` | `none`. `pip install openai` covers
both OpenAI and Groq (Groq uses the OpenAI-compatible API). The health badge in the UI shows whether
the LLM is connected. **Even with an LLM enabled, all financial totals still come from
the deterministic engine** — see below.

---

## Key technical decisions

### Where and why AI is used
- **Categorizing ambiguous transactions.** When deterministic keyword rules are weak
  or absent, the LLM proposes a category from the chart of accounts (with a confidence
  and a short rationale). Interpreting a cryptic bank memo is a judgment task where AI
  adds value.
- **Phrasing analyst answers.** The analyst uses the LLM only to turn already-computed,
  verified figures into fluent prose.

### Where and why deterministic logic is used
- **All P&L math** (`pnl.py`) and **all variance math** (`variance.py`) are plain
  Python that sums categorized transactions. This is where correctness is
  non-negotiable, so there is no model in the loop.
- **The chart of accounts** (`chart_of_accounts.py`) fixes each category's P&L section
  and sign. The AI may suggest *which* category; it can never change what a category
  *means* financially.
- **Amount-sign disambiguation.** The categorizer uses the transaction's sign as a hard
  rule: an outflow can never be Revenue, and an inflow is never an expense. This alone
  resolves vendor-name collisions (e.g. "Toast" is both the POS software an outflow and
  the sales-payout source an inflow).

### How incorrect or unsupported financial answers are prevented
- The analyst is built on **deterministic tools** (`tool_period_pnl`,
  `tool_metric_by_month`, `tool_variance`, `tool_txns_for_category_period`,
  `tool_review_items`). Every number in an answer originates from these tools.
- When an LLM is enabled, it is given the verified figures and instructed to answer
  using only those numbers, never to recompute. When no LLM is present, answers are
  produced entirely by the deterministic router. Either way the numbers are identical
  and traceable.
- Every answer returns **evidence transaction IDs** so a claim can be traced to source
  rows. Unresolved/uncertain items are quarantined in the review queue and excluded
  from the P&L until a human acts.

### How the system output is verified
- `backend/verify.py` runs the full deterministic pipeline on a transaction file and
  asserts the accounting identities hold exactly:
  `Gross Profit == Revenue − COGS` and
  `Operating Profit == Gross Profit − Payroll − Operating Expenses`.
- Run it with: `.\.venv\Scripts\python.exe verify.py <path-to-file>` from `backend/`
  (defaults to `transactions.xlsx`). It uses an isolated temporary database.
- Because all totals come from this deterministic engine and the LLM only phrases
  answers around already-computed figures, the numbers cannot be altered by the model.

---

## API reference (summary)

| Method | Path | Purpose |
|--------|------|---------|
| GET  | `/api/health` | status + whether LLM is connected |
| GET  | `/api/categories` | chart of accounts |
| GET  | `/api/stats` | counts (transactions, periods, review) |
| POST | `/api/ingest` | upload a file (multipart) |
| GET  | `/api/transactions` | list, optional `period` / `category_key` |
| POST | `/api/transactions/{id}/category` | correct a category (saves a rule) |
| POST | `/api/transactions/{id}/resolve` | mark a review item resolved |
| GET  | `/api/review` | items needing review |
| GET  | `/api/pnl` | monthly P&L (all or one `period`) |
| GET  | `/api/variance` | compare two periods |
| GET  | `/api/variance/significant` | largest changes across the period |
| POST | `/api/chat` | ask the analyst |

---

## Notes and assumptions
- **Sign convention:** positive amount = money in (inflow), negative = money out.
- **Materiality:** a variance is "material" if it is at least $500 **and** at least 15%.
- **Non-P&L items** (transfers, owner draws, loan proceeds/repayments, capex, income
  tax) are categorized and shown but excluded from the operating P&L, with the net
  excluded amount surfaced for transparency.
- Re-ingesting a file replaces the current dataset. Learned corrections live in a
  separate table and could be persisted across ingests if desired.
