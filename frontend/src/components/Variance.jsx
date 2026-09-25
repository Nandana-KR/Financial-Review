import React, { useEffect, useState } from "react";
import { api, money, pct } from "../api.js";

export default function Variance({ periods, gotoTransaction }) {
  const [prior, setPrior] = useState("");
  const [current, setCurrent] = useState("");
  const [report, setReport] = useState(null);
  const [error, setError] = useState(null);
  const [expanded, setExpanded] = useState(null);

  useEffect(() => {
    if (periods.length >= 2) {
      setPrior(periods[periods.length - 2]);
      setCurrent(periods[periods.length - 1]);
    }
  }, [periods.join(",")]);

  useEffect(() => {
    if (!prior || !current || prior === current) return;
    (async () => {
      setError(null);
      try {
        setReport(await api.variance(prior, current));
      } catch (e) {
        setError(e.message);
      }
    })();
  }, [prior, current]);

  if (periods.length < 2)
    return <div className="panel empty">Need at least two periods to compare.</div>;

  return (
    <div className="panel">
      <div className="row">
        <h2 style={{ margin: 0 }}>Variance analysis</h2>
        <div className="spacer" />
        <label className="muted small">From</label>
        <input type="month" value={prior} onChange={(e) => setPrior(e.target.value)} />
        <label className="muted small">To</label>
        <input type="month" value={current} onChange={(e) => setCurrent(e.target.value)} />
      </div>


      {error && <p className="error">{error}</p>}

      {report && (
        <>
          <h3>Summary lines</h3>
          <table>
            <thead>
              <tr>
                <th>Line</th>
                <th className="num">{report.prior_period}</th>
                <th className="num">{report.current_period}</th>
                <th className="num">Change</th>
                <th className="num">%</th>
              </tr>
            </thead>
            <tbody>
              {report.line_variances.map((lv) => (
                <tr key={lv.line} className={lv.material ? "material" : ""}>
                  <td>{lv.label}{lv.material && <span className="pill flag small" style={{ marginLeft: 8 }}>material</span>}</td>
                  <td className="num">{money(lv.prior)}</td>
                  <td className="num">{money(lv.current)}</td>
                  <td className={"num " + (lv.delta >= 0 ? "pos" : "neg")}>{money(lv.delta)}</td>
                  <td className="num muted">{pct(lv.pct_change)}</td>
                </tr>
              ))}
            </tbody>
          </table>

          <h3>Category drivers</h3>
          <table>
            <thead>
              <tr>
                <th>Category</th>
                <th>Section</th>
                <th className="num">{report.prior_period}</th>
                <th className="num">{report.current_period}</th>
                <th className="num">Change</th>
              </tr>
            </thead>
            <tbody>
              {report.category_variances
                .filter((cv) => Math.abs(cv.delta) > 0.01)
                .map((cv) => (
                  <React.Fragment key={cv.category_key}>
                    <tr
                      className={"clickable " + (cv.material ? "material" : "")}
                      onClick={() => setExpanded(expanded === cv.category_key ? null : cv.category_key)}
                    >
                      <td>
                        {cv.label}
                        {cv.material && <span className="pill flag small" style={{ marginLeft: 8 }}>material</span>}
                      </td>
                      <td className="muted small">{cv.section}</td>
                      <td className="num">{money(cv.prior)}</td>
                      <td className="num">{money(cv.current)}</td>
                      <td className={"num " + (cv.delta >= 0 ? "pos" : "neg")}>{money(cv.delta)}</td>
                    </tr>
                    {expanded === cv.category_key && (
                      <tr>
                        <td colSpan={5}>
                          <DriverTxns ids={cv.driving_txn_ids} period={report.current_period}
                            categoryKey={cv.category_key} gotoTransaction={gotoTransaction} />
                        </td>
                      </tr>
                    )}
                  </React.Fragment>
                ))}
            </tbody>
          </table>
        </>
      )}
    </div>
  );
}

function DriverTxns({ ids, period, categoryKey, gotoTransaction }) {
  const [rows, setRows] = useState(null);
  useEffect(() => {
    (async () => {
      const all = await api.transactions(period, categoryKey);
      setRows(all);
    })();
  }, [period, categoryKey]);

  if (!rows) return <div className="muted small">Loading evidence…</div>;
  if (!rows.length) return <div className="muted small">No transactions in this period.</div>;

  return (
    <div style={{ padding: "6px 0" }}>
      <div className="muted small" style={{ marginBottom: 6 }}>
        {rows.length} transaction(s) in {period}. Click to view in the ledger.
      </div>
      <table>
        <tbody>
          {rows
            .slice()
            .sort((a, b) => Math.abs(b.amount) - Math.abs(a.amount))
            .slice(0, 15)
            .map((t) => (
              <tr key={t.id} className="clickable" onClick={() => gotoTransaction(t.id)}>
                <td className="muted small">{t.txn_date}</td>
                <td>{t.description}</td>
                <td className={"num " + (t.amount >= 0 ? "pos" : "neg")}>{money(t.amount)}</td>
              </tr>
            ))}
        </tbody>
      </table>
    </div>
  );
}
