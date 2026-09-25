import React, { useEffect, useState, useCallback } from "react";
import { api } from "./api.js";
import Ingest from "./components/Ingest.jsx";
import Transactions from "./components/Transactions.jsx";
import PnL from "./components/PnL.jsx";
import Variance from "./components/Variance.jsx";
import Review from "./components/Review.jsx";
import Chat from "./components/Chat.jsx";

const TABS = [
  { key: "ingest", label: "Ingest" },
  { key: "transactions", label: "Transactions" },
  { key: "pnl", label: "Profit & Loss" },
  { key: "variance", label: "Variances" },
  { key: "review", label: "Review Queue" },
  { key: "chat", label: "AI Analyst" },
];

export default function App() {
  const [tab, setTab] = useState("ingest");
  const [stats, setStats] = useState(null);
  const [categories, setCategories] = useState([]);
  const [periods, setPeriods] = useState([]);
  const [focusTxnId, setFocusTxnId] = useState(null);

  const refresh = useCallback(async () => {
    try {
      const [s, c, p] = await Promise.all([
        api.stats(), api.categories(), api.periods(),
      ]);
      setStats(s); setCategories(c); setPeriods(p);
    } catch (e) {
      console.error(e);
    }
  }, []);

  useEffect(() => { refresh(); }, [refresh]);

  // Jump to the transactions tab focused on a specific transaction (from chat/variance evidence).
  const gotoTransaction = (id) => {
    setFocusTxnId(id);
    setTab("transactions");
  };

  const hasData = stats && stats.total_transactions > 0;

  return (
    <div className="app">
      <header className="top">
        <div>
          <h1>Financial Review</h1>
          <div className="sub">Automated categorization, monthly P&amp;L, variance analysis, and an AI analyst</div>
        </div>
      </header>

      {hasData && (
        <div className="grid-3">
          <div className="stat">
            <div className="label">Transactions</div>
            <div className="value">{stats.total_transactions}</div>
          </div>
          <div className="stat">
            <div className="label">Months</div>
            <div className="value">{stats.periods}</div>
          </div>
          <div className="stat">
            <div className="label">Needs review</div>
            <div className="value" style={{ color: stats.needs_review ? "var(--amber)" : "var(--green)" }}>
              {stats.needs_review}
            </div>
          </div>
        </div>
      )}

      <div className="tabs">
        {TABS.map((t) => (
          <div
            key={t.key}
            className={`tab ${tab === t.key ? "active" : ""}`}
            onClick={() => setTab(t.key)}
          >
            {t.label}
          </div>
        ))}
      </div>

      {tab === "ingest" && (
        <Ingest
          onIngested={async () => { await refresh(); setTab("transactions"); }}
          onCleared={refresh}
          stats={stats}
        />
      )}
      {tab === "transactions" && (
        <Transactions
          categories={categories}
          focusTxnId={focusTxnId}
          clearFocus={() => setFocusTxnId(null)}
          onChanged={refresh}
        />
      )}
      {tab === "pnl" && <PnL periods={periods} />}
      {tab === "variance" && <Variance periods={periods} gotoTransaction={gotoTransaction} />}
      {tab === "review" && (
        <Review categories={categories} onChanged={refresh} gotoTransaction={gotoTransaction} />
      )}
      {tab === "chat" && <Chat gotoTransaction={gotoTransaction} />}

      {!hasData && tab !== "ingest" && (
        <div className="panel empty">No data yet. Go to the Ingest tab and load a transaction file.</div>
      )}
    </div>
  );
}
