// Thin API client. All calls go to the FastAPI backend.
// In local dev, Vite proxies /api → http://127.0.0.1:8000.
// In production (Vercel), both frontend and backend are on the same domain.
const BASE = "";

async function req(path, options = {}) {
  const res = await fetch(`${BASE}/api${path}`, {
    headers: { "Content-Type": "application/json" },
    ...options,
  });
  if (!res.ok) {
    let detail = res.statusText;
    try {
      const body = await res.json();
      detail = body.detail || detail;
    } catch { }
    throw new Error(detail);
  }
  return res.json();
}

export const api = {
  health: () => req("/health"),
  stats: () => req("/stats"),
  categories: () => req("/categories"),
  periods: () => req("/periods"),

  ingest: async (file, replace = true) => {
    const form = new FormData();
    form.append("file", file);
    const res = await fetch(`${BASE}/api/ingest?replace=${replace}`, {
      method: "POST",
      body: form,
    });
    if (!res.ok) {
      const body = await res.json().catch(() => ({}));
      throw new Error(body.detail || "Ingest failed");
    }
    return res.json();
  },

  transactions: (period, categoryKey) => {
    const q = new URLSearchParams();
    if (period) q.set("period", period);
    if (categoryKey) q.set("category_key", categoryKey);
    const qs = q.toString();
    return req(`/transactions${qs ? "?" + qs : ""}`);
  },

  correctCategory: (id, categoryKey, saveCorrection = true) =>
    req(`/transactions/${id}/category`, {
      method: "POST",
      body: JSON.stringify({ category_key: categoryKey, save_correction: saveCorrection }),
    }),

  resolve: (id) => req(`/transactions/${id}/resolve`, { method: "POST" }),

  reset: () => req("/reset", { method: "POST" }),
  review: () => req("/review"),
  aiCategorizeReview: () => req("/review/ai-categorize", { method: "POST" }),
  pnl: (period) => req(`/pnl${period ? "?period=" + period : ""}`),
  pnlRange: (start, end) => {
    const q = new URLSearchParams();
    if (start) q.set("start", start);
    if (end) q.set("end", end);
    return req(`/pnl?${q.toString()}`);
  },
  variance: (prior, current) => {
    const q = new URLSearchParams();
    if (prior) q.set("prior", prior);
    if (current) q.set("current", current);
    const qs = q.toString();
    return req(`/variance${qs ? "?" + qs : ""}`);
  },
  significant: () => req("/variance/significant"),
  chat: (question) =>
    req("/chat", { method: "POST", body: JSON.stringify({ question }) }),
};

export function money(n) {
  if (n === null || n === undefined) return "—";
  return n.toLocaleString("en-US", { style: "currency", currency: "USD" });
}

export function pct(n) {
  if (n === null || n === undefined) return "—";
  return (n * 100).toFixed(1) + "%";
}
