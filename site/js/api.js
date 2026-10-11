/**
 * SENTINEL-FX · API Client Layer
 * Resilient communications with Cloudflare Worker API & GitHub Actions.
 * Exponential backoff for GET queries, in-memory auth header, timeout protection.
 */

const API_BASE = "https://sentinel-fx-worker.vjumbo264.workers.dev";
const GITHUB_REPO = "vjumbo264/sentinel-fx";

class ApiClient {
  constructor() {
    this.token = this.loadToken();
    this.demoData = false;
    try {
      this.demoData = localStorage.getItem("sentinel_demo_data") === "true";
    } catch (_) {}
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

  setDemoData(enabled) {
    this.demoData = !!enabled;
    try {
      localStorage.setItem("sentinel_demo_data", String(this.demoData));
    } catch (_) {}
  }

  getHeaders() {
    const headers = {
      "Content-Type": "application/json"
    };
    if (this.token) {
      headers["Authorization"] = `Bearer ${this.token}`;
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
          const errData = await res.json().catch(() => ({}));
          const errMsg = errData.error || `HTTP ${res.status}: ${res.statusText}`;
          throw new Error(errMsg);
        }
        return await res.json();
      } catch (err) {
        attempt++;
        if (attempt > retries || opts.method === "POST" || opts.method === "PUT") {
          throw err;
        }
        // Exponential backoff
        await new Promise((r) => setTimeout(r, Math.pow(2, attempt) * 400));
      }
    }
  }

  // Probe public health
  async checkHealth() {
    return this.request("/api/health");
  }

  // Probe Site Auth
  async checkAuth() {
    return this.request("/api/auth/check");
  }

  // System State (heartbeat, pairs, daily stats)
  async getState() {
    return this.request("/api/state");
  }

  // Session allocations, model ledgers, overrides
  async getSession() {
    return this.request("/api/session");
  }

  // Closed & open trades
  async getTrades() {
    return this.request("/api/trades");
  }

  // Registered models and forward metrics
  async getPairs() {
    return this.request("/api/pairs");
  }

  // Market Candlesticks for charting
  async getCandles(symbol = "frxEURUSD", granularity = 60, count = 300) {
    const sym = symbol.startsWith("frx") ? symbol : `frx${symbol}`;
    return this.request(`/api/candles?symbol=${encodeURIComponent(sym)}&granularity=${granularity}&count=${count}`);
  }

  // High-impact economic news calendar
  async getNews() {
    return this.request("/api/news");
  }

  // Execution and system logs
  async getLogs(level = null, limit = 100) {
    const q = level ? `?level=${level}&limit=${limit}` : `?limit=${limit}`;
    return this.request(`/api/logs${q}`);
  }

  // Save risk & bot settings
  async saveSettings(settings) {
    return this.request("/api/settings", {
      method: "POST",
      body: JSON.stringify(settings)
    });
  }

  // Update pair status/parameters
  async updatePair(pairData) {
    return this.request("/api/pairs/update", {
      method: "POST",
      body: JSON.stringify(pairData)
    });
  }

  // Reset Demo Balance ($10,000.00)
  async resetDemoBalance() {
    return this.request("/api/account/reset-demo-balance", {
      method: "POST"
    });
  }

  // Equal-Split balance allocation across enabled models
  async allocateSession(balance, mode = "demo") {
    return this.request("/api/session/allocate", {
      method: "POST",
      body: JSON.stringify({ balance, mode })
    });
  }

  // Owner override (pause, resume, stop_all)
  async overrideSession(symbol, action, note = "") {
    return this.request("/api/session/override", {
      method: "POST",
      body: JSON.stringify({ symbol, action, note })
    });
  }

  // Upload model bundle to staging release
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

  // Dispatch GitHub Action workflow
  async dispatchWorkflow(workflowFile, ref = "main", inputs = {}) {
    if (!this.token) {
      throw new Error("GitHub PAT required to dispatch workflows. Enter token in Settings.");
    }

    const url = `https://api.github.com/repos/${GITHUB_REPO}/actions/workflows/${workflowFile}/dispatches`;
    const res = await fetch(url, {
      method: "POST",
      headers: {
        "Authorization": `Bearer ${this.token}`,
        "Accept": "application/vnd.github+json",
        "Content-Type": "application/json"
      },
      body: JSON.stringify({ ref, inputs })
    });

    if (!res.ok) {
      const errText = await res.text();
      throw new Error(`Workflow dispatch failed (${res.status}): ${errText}`);
    }
    return { ok: true, workflow: workflowFile };
  }

  // Get workflow runs
  async getWorkflowRuns(workflowFile) {
    const url = `https://api.github.com/repos/${GITHUB_REPO}/actions/workflows/${workflowFile}/runs?per_page=5`;
    const headers = {
      "Accept": "application/vnd.github+json"
    };
    if (this.token) headers["Authorization"] = `Bearer ${this.token}`;

    const res = await fetch(url, { headers });
    if (!res.ok) return { workflow_runs: [] };
    return res.json();
  }
}

export const api = new ApiClient();
