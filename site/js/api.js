/**
 * SENTINEL-FX · API Client Layer
 * Resilient communications with Cloudflare Worker API & GitHub Actions.
 * Exponential backoff for GET queries, in-memory auth header, timeout protection.
 * Strict real-data only: real endpoints only.
 */

const API_BASE = "https://sentinel-fx-worker.vjumbo264.workers.dev";
const GITHUB_REPO = "vjumbo264/sentinel-fx";

class ApiClient {
  constructor() {
    this.token = this.loadToken();
    this.onUnauthorized = null;
  }

  loadToken() {
    try {
      return localStorage.getItem("sentinel_pat") || "";
    } catch (_) {
      return "";
    }
  }

  setToken(pat) {
    this.token = pat ? pat.trim() : "";
    try {
      if (this.token) {
        localStorage.setItem("sentinel_pat", this.token);
      } else {
        localStorage.removeItem("sentinel_pat");
      }
    } catch (_) {}
  }

  getHeaders() {
    const headers = {
      "Content-Type": "application/json"
    };
    if (this.token) {
      headers["Authorization"] = "Bearer " + this.token;
    }
    return headers;
  }

  async fetchWithTimeout(url, options = {}, timeoutMs = 10000) {
    const controller = new AbortController();
    const timer = setTimeout(() => controller.abort(), timeoutMs);

    try {
      const response = await fetch(url, {
        ...options,
        signal: controller.signal
      });
      clearTimeout(timer);
      return response;
    } catch (err) {
      clearTimeout(timer);
      if (err.name === "AbortError") {
        throw new Error("Request timed out after 10s");
      }
      throw err;
    }
  }

  async request(endpoint, options = {}, retries = 2) {
    const url = endpoint.startsWith("http") ? endpoint : `${API_BASE}${endpoint}`;
    const opts = {
      ...options,
      headers: {
        ...this.getHeaders(),
        ...(options.headers || {})
      }
    };

    let attempt = 0;
    while (attempt <= retries) {
      try {
        const res = await this.fetchWithTimeout(url, opts);
        if (!res.ok) {
          if (res.status === 401 || res.status === 403) {
            if (this.onUnauthorized) {
              try { this.onUnauthorized(res.status); } catch (_) {}
            }
          }
          const errData = await res.json().catch(() => ({}));
          const errMsg = errData.error || `HTTP ${res.status}: ${res.statusText}`;
          throw new Error(errMsg);
        }
        return await res.json();
      } catch (err) {
        attempt++;
        if (attempt > retries || opts.method === "POST" || opts.method === "PUT" || opts.method === "DELETE") {
          throw err;
        }
        await new Promise((r) => setTimeout(r, Math.pow(2, attempt) * 400));
      }
    }
  }

  async checkHealth() {
    return this.request("/api/health");
  }

  async checkAuth() {
    return this.request("/api/auth/check");
  }

  async getState() {
    return this.request("/api/state");
  }

  async getSession() {
    return this.request("/api/session");
  }

  async getTrades() {
    return this.request("/api/trades");
  }

  async getPairs() {
    return this.request("/api/pairs");
  }

  // B1: live candle-data index served by the Worker (never a stale bundled copy).
  async getDataIndex() {
    return this.request("/api/data/index");
  }

  async getTrackedPairs() {
    return this.request("/api/data/tracked-pairs");
  }

  async getCandles(symbol = "frxEURUSD", granularity = 60, count = 300) {
    return this.request(`/api/candles?symbol=${encodeURIComponent(symbol)}&granularity=${granularity}&count=${count}`);
  }

  async getNews() {
    return this.request("/api/news");
  }

  async getLogs(level = null, limit = 100) {
    const q = level ? `?level=${level}&limit=${limit}` : `?limit=${limit}`;
    return this.request(`/api/logs${q}`);
  }

  async saveSettings(settings) {
    return this.request("/api/settings", {
      method: "POST",
      body: JSON.stringify(settings)
    });
  }

  async updatePair(pairData) {
    return this.request("/api/pairs/update", {
      method: "POST",
      body: JSON.stringify(pairData)
    });
  }

  async resetDemoBalance() {
    return this.request("/api/account/reset-demo-balance", {
      method: "POST"
    });
  }

  async allocateSession(balance, mode = "demo") {
    return this.request("/api/session/allocate", {
      method: "POST",
      body: JSON.stringify({ balance, mode })
    });
  }

  async overrideSession(symbol, action, note = "") {
    return this.request("/api/session/override", {
      method: "POST",
      body: JSON.stringify({ symbol, action, note })
    });
  }

  async uploadStagingAsset(assetName, buffer) {
    const url = `${API_BASE}/api/upload/staging-asset?name=${encodeURIComponent(assetName)}`;
    const headers = {
      ...this.getHeaders(),
      "Content-Type": "application/zip"
    };

    const res = await this.fetchWithTimeout(url, {
      method: "POST",
      headers,
      body: buffer
    }, 30000);

    if (!res.ok) {
      const t = await res.text();
      throw new Error(`Upload failed (${res.status}): ${t}`);
    }
    return res.json();
  }

  async dispatchWorkflow(workflowFile, ref = "main", inputs = {}) {
    if (!this.token) {
      throw new Error("GitHub PAT required to dispatch workflows.");
    }

    const url = `https://api.github.com/repos/${GITHUB_REPO}/actions/workflows/${workflowFile}/dispatches`;
    const res = await fetch(url, {
      method: "POST",
      headers: {
        "Authorization": "Bearer " + this.token,
        "Accept": "application/vnd.github+json",
        "Content-Type": "application/json"
      },
      body: JSON.stringify({ ref, inputs })
    });

    if (!res.ok) {
      // F1: surface GitHub's error readably (message + per-input errors), never a raw JSON dump
      const raw = await res.text();
      let detail = "";
      try {
        const j = JSON.parse(raw);
        detail = j.message || "";
        if (j.errors) {
          const errs = Array.isArray(j.errors) ? j.errors : [j.errors];
          const bits = errs.map((e) => (typeof e === "string" ? e : (e.message || e.code || ""))).filter(Boolean);
          if (bits.length) detail += (detail ? " — " : "") + bits.join("; ");
        }
      } catch (_) {
        detail = raw.slice(0, 160);
      }
      throw new Error(`Workflow dispatch failed (${res.status}): ${detail || res.statusText}`);
    }
    return { ok: true, workflow: workflowFile };
  }

  /**
   * Latest dispatch of a workflow on main, optionally only runs created after `sinceIso`.
   * Used by the Train desk to show queued/running/finished inline on the symbol row.
   */
  async getLatestWorkflowRun(workflowFile, sinceIso = null) {
    try {
      const data = await this.getWorkflowRuns(workflowFile);
      const runs = (data.workflow_runs || []).filter((r) => {
        if (r.head_branch !== "main") return false;
        if (sinceIso && new Date(r.created_at).getTime() < new Date(sinceIso).getTime() - 60000) return false;
        return true;
      });
      return runs[0] || null; // API returns newest first
    } catch (_) {
      return null;
    }
  }

  async getWorkflowRuns(workflowFile) {
    const url = `https://api.github.com/repos/${GITHUB_REPO}/actions/workflows/${workflowFile}/runs?per_page=5`;
    const headers = {
      "Accept": "application/vnd.github+json"
    };
    if (this.token) headers["Authorization"] = "Bearer " + this.token;

    const res = await fetch(url, { headers });
    if (!res.ok) return { workflow_runs: [] };
    return res.json();
  }
}

export const api = new ApiClient();
export { API_BASE };
