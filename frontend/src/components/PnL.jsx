import React, { useEffect, useMemo, useState } from "react";
import { api, money } from "../api.js";

const MONTH_NAMES = [
  "January", "February", "March", "April", "May", "June",
  "July", "August", "September", "October", "November", "December",
];

function periodLabel(period) {
  const m = /^(\d{4})-(\d{2})$/.exec(period);
  if (!m) return period;
  return `${MONTH_NAMES[parseInt(m[2], 10) - 1]} ${m[1]}`;
}

function isEmptyPnl(p) {
  return !p || (p.revenue === 0 && p.cogs === 0 && p.payroll === 0 &&
    p.operating_expenses === 0);
}

function Statement({ pnl }) {
  const sections = pnl.lines_by_section || {};
  const line = (label, value, cls = "") => (
    <div className={`pnl-line ${cls}`}>
      <span>{label}</span>
      <span className={value < 0 ? "neg" : ""}>{money(value)}</span>
    </div>
  );
  const subLines = (sectionName) =>
    (sections[sectionName] || []).map((li) => (
      <div className="pnl-line sub" key={li.category_key}>
        <span>{li.label} <span className="muted small">({li.txn_count})</span></span>
        <span>{money(li.amount)}</span>
      </div>
    ));

  return (
    <div className="panel">
      <h2>{periodLabel(pnl.period)}</h2>
      {line("Revenue", pnl.revenue, "total")}
      {subLines("Revenue")}
      {line("Cost of Goods Sold", pnl.cogs, "total")}
      {subLines("Cost of Goods Sold")}
      {line("Gross Profit", pnl.gross_profit, "total")}
      {line("Payroll", pnl.payroll, "total")}
      {subLines("Payroll")}
      {line("Operating Expenses", pnl.operating_expenses, "total")}
      {subLines("Operating Expenses")}
      {line("Operating Profit", pnl.operating_profit, "total")}
      {Math.abs(pnl.excluded_non_pnl) > 0.01 && (
        <p className="muted small" style={{ marginTop: 10 }}>
          Excluded from P&L (transfers, owner draws, loans, capex, taxes):{" "}
          {money(pnl.excluded_non_pnl)} net.
        </p>
      )}
    </div>
  );
}

export default function PnL({ periods }) {
  const [monthly, setMonthly] = useState([]);      // all monthly P&Ls
  const [rangePnl, setRangePnl] = useState(null);   // P&L for a chosen date range
  const [loading, setLoading] = useState(true);

  const [mode, setMode] = useState("month");        // "month" | "range"
  const [selectedYear, setSelectedYear] = useState("");  // "" = all years
  const [selectedMonth, setSelectedMonth] = useState(""); // "01".."12" or "" = all
  const [monthPnl, setMonthPnl] = useState(null);   // P&L for a specific year+month
  const [fromDate, setFromDate] = useState("");
  const [toDate, setToDate] = useState("");

  useEffect(() => {
    (async () => {
      setLoading(true);
      try {
        const all = await api.pnl();
        const list = Array.isArray(all) ? all : [all];
        setMonthly(list);
        // Default the month-mode pickers to the first month that has data, so the
        // page opens on a real P&L rather than blank/"all".
        if (list.length && !selectedYear && !selectedMonth) {
          const [y, m] = list[0].period.split("-");
          setSelectedYear(y);
          setSelectedMonth(m);
        }
        // Default the date-range pickers to span the full data range.
        if (list.length && !fromDate && !toDate) {
          const first = list[0].period + "-01";
          const lastYM = list[list.length - 1].period;
          const [ly, lm] = lastYM.split("-").map(Number);
          const lastDay = new Date(ly, lm, 0).getDate();
          setFromDate(first);
          setToDate(`${lastYM}-${String(lastDay).padStart(2, "0")}`);
        }
      } finally {
        setLoading(false);
      }
    })();
    // eslint-disable-next-line
  }, [periods.join(",")]);

  // Full selectable year range (2000–2030), independent of the uploaded file.
  const yearOptions = useMemo(() => {
    const years = [];
    for (let y = 2000; y <= 2030; y++) years.push(String(y));
    return years;
  }, []);

  // All 12 months, always available regardless of what the file contains.
  const allMonths = MONTH_NAMES.map((name, i) => ({
    value: String(i + 1).padStart(2, "0"),
    label: name,
  }));

  // Fetch range P&L when in range mode with dates set.
  useEffect(() => {
    if (mode !== "range" || (!fromDate && !toDate)) { setRangePnl(null); return; }
    let cancelled = false;
    (async () => {
      try {
        const r = await api.pnlRange(fromDate || undefined, toDate || undefined);
        if (!cancelled) setRangePnl(r);
      } catch {
        if (!cancelled) setRangePnl(null);
      }
    })();
    return () => { cancelled = true; };
  }, [mode, fromDate, toDate]);

  // When a specific year AND month are chosen, fetch that period's P&L directly
  // (it may be a month with no data, which correctly returns zeros).
  const specificPeriod =
    mode === "month" && selectedYear && selectedMonth
      ? `${selectedYear}-${selectedMonth}`
      : "";

  useEffect(() => {
    if (!specificPeriod) { setMonthPnl(null); return; }
    let cancelled = false;
    (async () => {
      try {
        const r = await api.pnl(specificPeriod);
        if (!cancelled) setMonthPnl(r);
      } catch {
        if (!cancelled) setMonthPnl(null);
      }
    })();
    return () => { cancelled = true; };
  }, [specificPeriod]);

  // Cards to show when NOT viewing one specific period: filter the loaded monthly
  // P&Ls by year (if a year is chosen), else show all months that have data.
  const monthCards = useMemo(() => {
    if (selectedYear) return monthly.filter((p) => p.period.startsWith(selectedYear));
    return monthly;
  }, [monthly, selectedYear]);

  if (loading) return <div className="panel empty">Loading…</div>;
  if (!monthly.length) return <div className="panel empty">No P&L yet. Ingest a file first.</div>;

  return (
    <>
      <div className="panel">
        <div className="row">
          <h2 style={{ margin: 0 }}>Profit &amp; Loss</h2>
          <div className="spacer" />

          {/* Mode toggle */}
          <div className="segmented">
            <button
              className={mode === "month" ? "seg active" : "seg"}
              onClick={() => setMode("month")}
            >
              By Month
            </button>
            <button
              className={mode === "range" ? "seg active" : "seg"}
              onClick={() => setMode("range")}
            >
              Date Range
            </button>
          </div>
        </div>

        {/* Filter controls for the active mode */}
        <div className="row" style={{ marginTop: 14 }}>
          {mode === "month" ? (
            <>
              <label className="muted small">Year</label>
              <select value={selectedYear} onChange={(e) => setSelectedYear(e.target.value)}>
                <option value="">All years</option>
                {yearOptions.map((y) => <option key={y} value={y}>{y}</option>)}
              </select>
              <label className="muted small">Month</label>
              <select value={selectedMonth} onChange={(e) => setSelectedMonth(e.target.value)}>
                <option value="">All months</option>
                {allMonths.map((m) => (
                  <option key={m.value} value={m.value}>{m.label}</option>
                ))}
              </select>
            </>
          ) : (
            <>
              <label className="muted small">From</label>
              <input type="date" value={fromDate} onChange={(e) => setFromDate(e.target.value)} />
              <label className="muted small">To</label>
              <input type="date" value={toDate} onChange={(e) => setToDate(e.target.value)} />
              {(fromDate || toDate) && (
                <button className="secondary" onClick={() => { setFromDate(""); setToDate(""); }}>
                  Clear
                </button>
              )}
            </>
          )}
        </div>


      </div>

      {/* P&L cards */}
      {mode === "range" ? (
        (!fromDate && !toDate) ? (
          <div className="panel empty">Select a date range to view its P&L.</div>
        ) : rangePnl ? (
          <Statement pnl={rangePnl} />
        ) : (
          <div className="panel empty">No transactions in the selected date range.</div>
        )
      ) : specificPeriod ? (
        // A specific year + month is selected — show just that period's card.
        monthPnl ? (
          isEmptyPnl(monthPnl) ? (
            <div className="panel empty">
              No transactions in {periodLabel(specificPeriod)}.
            </div>
          ) : (
            <Statement pnl={monthPnl} />
          )
        ) : (
          <div className="panel empty">Loading…</div>
        )
      ) : selectedMonth && !selectedYear ? (
        // Month picked but no year — prompt for a year so we know which one.
        <div className="panel empty">Select a year to view that month's P&L.</div>
      ) : (
        <div className={monthCards.length === 1 ? "" : "grid-3"}>
          {monthCards.length
            ? monthCards.map((p) => <Statement key={p.period} pnl={p} />)
            : <div className="panel empty">No transactions for the selected year.</div>}
        </div>
      )}
    </>
  );
}
