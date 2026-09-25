import React, { useState, useRef, useEffect } from "react";
import { api } from "../api.js";

// General suggested questions that work for any dataset (no specific month named).
const SUGGESTIONS = [
  "How much did we spend on payroll each month?",
  "What drove the increase in food costs?",
  "Which transactions need my attention?",
  "What changed most significantly over the review period?",
];

export default function Chat({ gotoTransaction }) {
  const [log, setLog] = useState([]);
  const [input, setInput] = useState("");
  const [busy, setBusy] = useState(false);
  const [txnMap, setTxnMap] = useState({});
  const endRef = useRef(null);

  // Load all transactions once so evidence can be shown with readable labels.
  useEffect(() => {
    (async () => {
      try {
        const all = await api.transactions();
        const m = {};
        all.forEach((t) => { m[t.id] = t; });
        setTxnMap(m);
      } catch { /* ignore */ }
    })();
  }, []);

  useEffect(() => {
    endRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [log, busy]);

  const ask = async (question) => {
    const q = (question ?? input).trim();
    if (!q || busy) return;
    setInput("");
    setLog((l) => [...l, { role: "user", text: q }]);
    setBusy(true);
    try {
      const res = await api.chat(q);
      setLog((l) => [...l, {
        role: "bot",
        text: res.answer,
        evidence: res.evidence_txn_ids || [],
      }]);
    } catch (e) {
      setLog((l) => [...l, { role: "bot", text: "Sorry, something went wrong: " + e.message, evidence: [] }]);
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="panel">
      <h2>AI Financial Analyst</h2>

      {/* Suggestions show until the conversation starts, then collapse to save space. */}
      {log.length === 0 && (
        <div className="suggestions">
          {SUGGESTIONS.map((s) => (
            <span key={s} className="chip" onClick={() => ask(s)}>{s}</span>
          ))}
        </div>
      )}

      <div className="chat-log">
        {log.length === 0 && (
          <div className="empty">Ask a question or tap a suggestion above.</div>
        )}
        {log.map((m, i) => (
          <div key={i} className={`msg ${m.role}`}>
            {m.text}
            {m.role === "bot" && m.evidence && m.evidence.length > 0 && (
              <div className="evidence">
                <span className="muted">
                  Backed by {m.evidence.length} transaction{m.evidence.length > 1 ? "s" : ""}.
                  Click one to view it in the ledger:
                </span>
                <div className="evidence-chips">
                  {(m.expanded ? m.evidence : m.evidence.slice(0, 6)).map((id) => {
                    const t = txnMap[id];
                    const label = t
                      ? `${t.txn_date} · ${t.description.slice(0, 28)}${t.description.length > 28 ? "…" : ""}`
                      : `Transaction ${id}`;
                    return (
                      <a key={id} className="ev-chip" onClick={() => gotoTransaction(id)}>
                        {label}
                      </a>
                    );
                  })}
                  {m.evidence.length > 6 && (
                    <span
                      className="ev-more"
                      onClick={() =>
                        setLog((l) => l.map((x, xi) => (xi === i ? { ...x, expanded: !x.expanded } : x)))
                      }
                    >
                      {m.expanded ? "show fewer" : `show ${m.evidence.length - 6} more`}
                    </span>
                  )}
                </div>
              </div>
            )}
          </div>
        ))}
        {busy && (
          <div className="msg bot thinking">
            <span className="dot" />
            <span className="dot" />
            <span className="dot" />
          </div>
        )}
        <div ref={endRef} />
      </div>

      <div className="row">
        <input
          type="text"
          style={{ flex: 1 }}
          placeholder="Ask about revenue, payroll, variances, review items…"
          value={input}
          onChange={(e) => setInput(e.target.value)}
          onKeyDown={(e) => e.key === "Enter" && ask()}
          disabled={busy}
        />
        <button onClick={() => ask()} disabled={busy || !input.trim()}>
          {busy ? "Thinking…" : "Ask"}
        </button>
      </div>
    </div>
  );
}
