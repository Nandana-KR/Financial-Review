import React, { useEffect, useState } from "react";
import { api, money } from "../api.js";

export default function Review({ categories, onChanged, gotoTransaction }) {
  const [items, setItems] = useState([]);
  const [loading, setLoading] = useState(true);

  const load = async () => {
    setLoading(true);
    try {
      setItems(await api.review());
    } finally {
      setLoading(false);
    }
  };
  useEffect(() => { load(); }, []);

  const correct = async (id, key) => {
    await api.correctCategory(id, key, true);
    await load();
    await onChanged();
  };
  const resolve = async (id) => {
    await api.resolve(id);
    await load();
    await onChanged();
  };

  return (
    <div className="panel">
      <h2 style={{ margin: 0 }}>Items requiring review</h2>

      {loading ? (
        <div className="empty">Loading…</div>
      ) : items.length === 0 ? (
        <div className="empty pos">Nothing needs review.</div>
      ) : (
        <div className="table-scroll">
          <table>
            <thead>
              <tr>
                <th>Date</th>
                <th>Description</th>
                <th className="num">Amount</th>
                <th>Reason</th>
                <th>Assign category</th>
                <th></th>
              </tr>
            </thead>
            <tbody>
              {items.map((t) => (
                <tr key={t.id} className="review-row">
                  <td className="muted small">{t.txn_date}</td>
                  <td className="clickable" onClick={() => gotoTransaction(t.id)}>{t.description}</td>
                  <td className={"num " + (t.amount >= 0 ? "pos" : "neg")}>{money(t.amount)}</td>
                  <td className="muted small">{t.review_reason}</td>
                  <td>
                    <select defaultValue={t.category_key} onChange={(e) => correct(t.id, e.target.value)}>
                      {categories.map((c) => (
                        <option key={c.key} value={c.key}>{c.label}</option>
                      ))}
                    </select>
                  </td>
                  <td>
                    <button className="secondary" onClick={() => resolve(t.id)}>Resolve</button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
