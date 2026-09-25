import React, { useState } from "react";
import { api } from "../api.js";

const MONTH_NAMES = [
  "Jan", "Feb", "Mar", "Apr", "May", "Jun",
  "Jul", "Aug", "Sep", "Oct", "Nov", "Dec",
];

function monthLabel(period) {
  const [year, mm] = period.split("-");
  return `${MONTH_NAMES[parseInt(mm, 10) - 1]} ${year}`;
}

export default function Ingest({ onIngested, onCleared, stats }) {
  const [file, setFile] = useState(null);
  const [busy, setBusy] = useState(false);
  const [result, setResult] = useState(null);
  const [error, setError] = useState(null);

  const upload = async () => {
    if (!file) return;
    setBusy(true); setError(null); setResult(null);
    try {
      const res = await api.ingest(file, true);
      setResult(res);
      // After a fast, deterministic ingest, let the AI refine the transactions that
      // rules were unsure about. This keeps ingest quick while still using AI where
      // interpretation is valuable (the ambiguous items). Failures are non-fatal.
      try { await api.aiCategorizeReview(); } catch { /* ignore */ }
      await onIngested();
    } catch (e) {
      setError(e.message);
    } finally {
      setBusy(false);
    }
  };

  const clearAll = async () => {
    setBusy(true); setError(null); setResult(null);
    try {
      await api.reset();
      setFile(null);
      await onCleared();
    } catch (e) {
      setError(e.message);
    } finally {
      setBusy(false);
    }
  };

  const loaded = stats && stats.total_transactions > 0;

  return (
    <div className="panel">
      <h2>Ingest financial data</h2>
      <p className="muted small">Upload a bank transaction file (.xlsx or .csv).</p>

      <div className="row" style={{ marginTop: 12 }}>
        <input
          type="file"
          accept=".xlsx,.xlsm,.csv"
          onChange={(e) => setFile(e.target.files[0])}
        />
        <button onClick={upload} disabled={!file || busy}>
          {busy ? "Ingesting…" : "Ingest file"}
        </button>
        {loaded && (
          <button className="secondary" onClick={clearAll} disabled={busy}>
            Clear all data
          </button>
        )}
      </div>

      {error && <p className="error" style={{ marginTop: 12 }}>Error: {error}</p>}

      {result && (
        <p className="pos" style={{ marginTop: 16 }}>
          Ingested {result.ingested} transactions across {result.periods.length} month(s):{" "}
          {result.periods.map(monthLabel).join(", ")}.
        </p>
      )}

      {loaded && !result && (
        <div className="stat" style={{ marginTop: 16 }}>
          <div className="label">Currently loaded</div>
          <div className="value">{stats.total_transactions} transactions</div>
          <div className="muted small" style={{ marginTop: 4 }}>
            {stats.periods} month(s) · {stats.needs_review} flagged for review
          </div>
        </div>
      )}

      {!loaded && !result && (
        <p className="muted small" style={{ marginTop: 16 }}>
          No data loaded yet. Choose a file above and click “Ingest file”.
        </p>
      )}
    </div>
  );
}
