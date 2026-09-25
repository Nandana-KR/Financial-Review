import React, { useEffect, useMemo, useState, useRef } from "react";
import { api, money } from "../api.js";

const MONTH_NAMES = [
  "January", "February", "March", "April", "May", "June",
  "July", "August", "September", "October", "November", "December",
];

export default function Transactions({ categories, focusTxnId, clearFocus, onChanged }) {
  const [allTxns, setAllTxns] = useState([]);
  const [mode, setMode] = useState("month");   // "month" | "range"
  const [selYear, setSelYear] = useState("");
  const [selMonth, setSelMonth] = useState(""); // "01".."12"
  const [fromDate, setFromDate] = useState("");
  const [toDate, setToDate] = useState("");
  const [loading, setLoading] = useState(false);
  const [toast, setToast] = useState(null);
  const rowRefs = useRef({});

  const catByKey = useMemo(() => {
    const m = {};
    categories.forEach((c) => (m[c.key] = c));
    return m;
  }, [categories]);

  const load = async () => {
    setLoading(true);
    try {
      setAllTxns(await api.transactions());
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => { load(); /* eslint-disable-next-line */ }, []);

  const yearOptions = useMemo(() => {
    const years = [];
    for (let y = 2000; y <= 2030; y++) years.push(String(y));
    return years;
  }, []);
  const allMonths = MONTH_NAMES.map((name, i) => ({ value: String(i + 1).padStart(2, "0"), label: name }));

  // Filter transactions based on the active mode.
  const txns = useMemo(() => {
    return allTxns.filter((t) => {
      if (mode === "month") {
        if (selYear && !t.txn_date.startsWith(selYear + "-")) return false;
        if (selMonth && t.txn_date.slice(5, 7) !== selMonth) return false;
        return true;
      }
      // range mode
      if (fromDate && t.txn_date < fromDate) return false;
      if (toDate && t.txn_date > toDate) return false;
      return true;
    });
  }, [allTxns, mode, selYear, selMonth, fromDate, toDate]);

  const clearRange = () => { setFromDate(""); setToDate(""); };
  const clearMonth = () => { setSelYear(""); setSelMonth(""); };

  // Scroll to and briefly highlight a focused transaction (from evidence links).
  useEffect(() => {
    if (focusTxnId && rowRefs.current[focusTxnId]) {
      rowRefs.current[focusTxnId].scrollIntoView({ behavior: "smooth", block: "center" });
      const el = rowRefs.current[focusTxnId];
      el.style.outline = "2px solid var(--accent)";
      const t = setTimeout(() => { el.style.outline = "none"; clearFocus(); }, 2500);
      return () => clearTimeout(t);
    }
  }, [focusTxnId, txns, clearFocus]);

  const correct = async (id, categoryKey) => {
    await api.correctCategory(id, categoryKey, true);
    setToast("Category saved. Similar transactions were updated too.");
    setTimeout(() => setToast(null), 2500);
    await load();
    await onChanged();
  };

  const flagged = txns.filter((t) => t.needs_review && !t.resolved).length;

  return (
    <div className="panel">
      <div className="row">
        <h2 style={{ margin: 0 }}>Transactions</h2>
        <div className="spacer" />
        <div className="segmented">
          <button className={mode === "month" ? "seg active" : "seg"} onClick={() => setMode("month")}>By Month</button>
          <button className={mode === "range" ? "seg active" : "seg"} onClick={() => setMode("range")}>Date Range</button>
        </div>
      </div>

      <div className="row" style={{ marginTop: 14 }}>
        {mode === "month" ? (
          <>
            <label className="muted small">Year</label>
            <select value={selYear} onChange={(e) => setSelYear(e.target.value)}>
              <option value="">All years</option>
              {yearOptions.map((y) => <option key={y} value={y}>{y}</option>)}
            </select>
            <label className="muted small">Month</label>
            <select value={selMonth} onChange={(e) => setSelMonth(e.target.value)}>
              <option value="">All months</option>
              {allMonths.map((m) => <option key={m.value} value={m.value}>{m.label}</option>)}
            </select>
            {(selYear || selMonth) && (
              <button className="secondary" onClick={clearMonth}>Clear</button>
            )}
          </>
        ) : (
          <>
            <label className="muted small">From</label>
            <input type="date" value={fromDate} onChange={(e) => setFromDate(e.target.value)} />
            <label className="muted small">To</label>
            <input type="date" value={toDate} onChange={(e) => setToDate(e.target.value)} />
            {(fromDate || toDate) && (
              <button className="secondary" onClick={clearRange}>Clear</button>
            )}
          </>
        )}
      </div>

      <p className="muted small" style={{ marginTop: 12 }}>
        {txns.length} transactions{flagged ? ` · ${flagged} flagged for review` : ""}
      </p>

      {loading ? (
        <div className="empty">Loading…</div>
      ) : txns.length === 0 ? (
        <div className="empty">
          {(mode === "month" && (selYear || selMonth)) || (mode === "range" && (fromDate || toDate))
            ? "No transactions for the selected filter."
            : "No transactions loaded."}
        </div>
      ) : (
        <div className="table-scroll">
          <table>
            <thead>
              <tr>
                <th>Date</th>
                <th>Description</th>
                <th className="num">Amount</th>
                <th>Category</th>
                <th>Included in Report</th>
                <th>Status</th>
              </tr>
            </thead>
            <tbody>
              {txns.map((t) => {
                const cat = catByKey[t.category_key];
                const isPnl = cat ? cat.is_pnl : false;
                const needsReview = t.needs_review && !t.resolved;
                return (
                  <tr
                    key={t.id}
                    ref={(el) => (rowRefs.current[t.id] = el)}
                    className={needsReview ? "review-row" : ""}
                  >
                    <td className="muted small">{t.txn_date}</td>
                    <td>{t.description}</td>
                    <td className={"num " + (t.amount >= 0 ? "pos" : "neg")}>
                      {money(t.amount)}
                    </td>
                    <td>
                      <select
                        value={t.category_key}
                        onChange={(e) => correct(t.id, e.target.value)}
                      >
                        {categories.map((c) => (
                          <option key={c.key} value={c.key}>{c.label}</option>
                        ))}
                      </select>
                    </td>
                    <td>
                      <span
                        className={"pill " + (isPnl ? "pill-yes" : "pill-no")}
                        title={isPnl
                          ? "Counts in the Profit & Loss report (income or expense)"
                          : "Not part of the report (transfer, loan, owner draw, etc.)"}
                      >
                        {isPnl ? "Yes" : "No"}
                      </span>
                    </td>
                    <td>
                      {needsReview ? (
                        <span className="pill flag" title={t.review_reason}>Needs review</span>
                      ) : (
                        <span className="pill pill-ok">OK</span>
                      )}
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      )}

      {toast && <div className="toast">{toast}</div>}
    </div>
  );
}
