/**
 * SENTINEL-FX · Central Reactive Store & Polling Supervisor
 * Tracks MT5 runner heartbeat, open CFD positions, model ledgers, and trade history.
 * Automatically halts polling when the tab is hidden to save battery & data.
 * Pure real data: real data exclusively.
 */

import { api } from "./api.js";

class Store {
  constructor() {
    this.state = {
      isAuth: !!api.token,
      authError: null,
      mode: "demo", // "demo" | "real"
      balance: null,
      equity: null,
      freeMargin: null,
      marginLevel: 0,
      usedMargin: 0,
      todayPnl: 0,
      todayTrades: 0,
      todayWins: 0,
      heartbeat: null,
      runnerActive: false,
      runnerHandoverSeconds: 13800, // 3h50m countdown window
      positions: [],
      history: [],
      models: [],
      ledgers: [],
      overrides: [],
      news: [],
      logs: [],
      loading: true,
      lastError: null,
      lastUpdated: null
    };

    this.subscribers = new Set();
    this.pollInterval = null;
    this.pollFreq = 4000; // 4 seconds

    // Hook unauthorized callback to gate app
    api.onUnauthorized = (status) => {
      this.setAuth(false, "Authentication expired or unauthorized. Please connect your GitHub PAT.");
    };

    // Visibility API support to avoid background polling thrashing
    document.addEventListener("visibilitychange", () => {
      if (document.hidden) {
        this.stopPolling();
      } else {
        if (this.state.isAuth) {
          this.fetchSnapshot();
          this.startPolling();
        }
      }
    });

    // Initial load if token is available
    if (this.state.isAuth) {
      this.fetchSnapshot();
      this.startPolling();
    } else {
      this.state.loading = false;
    }
  }

  setAuth(isAuth, authError = null) {
    this.state.isAuth = !!isAuth;
    this.state.authError = authError;
    if (!isAuth) {
      this.stopPolling();
    } else {
      this.startPolling();
      this.fetchSnapshot();
    }
    this.notify();
  }

  subscribe(fn) {
    this.subscribers.add(fn);
    fn(this.state);
    return () => this.subscribers.delete(fn);
  }

  notify() {
    this.subscribers.forEach((fn) => {
      try { fn(this.state); } catch (e) { console.error("Store listener error:", e); }
    });
  }

  startPolling() {
    if (this.pollInterval) return;
    this.pollInterval = setInterval(() => {
      this.fetchSnapshot();
    }, this.pollFreq);
  }

  stopPolling() {
    if (this.pollInterval) {
      clearInterval(this.pollInterval);
      this.pollInterval = null;
    }
  }

  async fetchSnapshot() {
    if (!this.state.isAuth) return;

    try {
      const [sysState, sessionData, tradesData, pairsData, newsData] = await Promise.allSettled([
        api.getState(),
        api.getSession(),
        api.getTrades(),
        api.getPairs(),
        api.getNews()
      ]);

      if (sysState.status === "fulfilled" && sysState.value) {
        const d = sysState.value;
        const hb = d.heartbeat || {};
        const isLive = hb.ts && (Date.now() - new Date(hb.ts).getTime() < 120000);

        this.state.heartbeat = hb;
        this.state.runnerActive = !!isLive;
        this.state.mode = hb.mode || (d.settings && d.settings.mode) || "demo";
        this.state.balance = hb.balance !== null && hb.balance !== undefined ? Number(hb.balance) : null;

        if (d.today) {
          this.state.todayPnl = Number(d.today.pnl || 0);
          this.state.todayTrades = Number(d.today.trades || 0);
          this.state.todayWins = Number(d.today.wins || 0);
        }
      }

      if (sessionData.status === "fulfilled" && sessionData.value) {
        const s = sessionData.value;
        this.state.ledgers = s.ledger || [];
        this.state.overrides = s.overrides || [];
      }

      if (tradesData.status === "fulfilled" && tradesData.value) {
        const allTrades = tradesData.value.trades || [];
        const open = [];
        const closed = [];
        allTrades.forEach((t) => {
          if (!t.close_utc) {
            open.push({
              ticket: t.contract_id || t.id,
              symbol: t.pair,
              side: (t.side || "BUY").toUpperCase(),
              volume: Number(t.stake || 0.01),
              openPrice: Number(t.open_price || t.entry_price || 0),
              currentPrice: Number(t.current_price || t.open_price || 0),
              sl: Number(t.sl || 0),
              tp: Number(t.tp || 0),
              pnl: Number(t.pnl || 0),
              openTime: t.open_utc,
              modelId: t.pair,
              reason: t.reason || "Automated MT5 Execution"
            });
          } else {
            closed.push(t);
          }
        });

        const openPnl = open.reduce((acc, p) => acc + (p.pnl || 0), 0);
        this.state.positions = open;
        this.state.history = closed;
        if (this.state.balance !== null) {
          this.state.equity = this.state.balance + openPnl;
          this.state.usedMargin = open.reduce((acc, p) => acc + (p.volume * 1000 * 0.01), 0);
          this.state.freeMargin = Math.max(0, this.state.equity - this.state.usedMargin);
          this.state.marginLevel = this.state.usedMargin > 0 ? (this.state.equity / this.state.usedMargin) * 100 : 0;
        } else {
          this.state.equity = null;
          this.state.usedMargin = 0;
          this.state.freeMargin = null;
          this.state.marginLevel = 0;
        }
      }

      if (pairsData.status === "fulfilled" && pairsData.value) {
        this.state.models = pairsData.value.pairs || [];
      }

      if (newsData.status === "fulfilled" && newsData.value) {
        this.state.news = newsData.value.events || [];
      }

      this.state.loading = false;
      this.state.lastError = null;
      this.state.lastUpdated = new Date();
      this.notify();
    } catch (err) {
      this.state.loading = false;
      this.state.lastError = err.message || String(err);
      this.notify();
    }
  }
}

export const store = new Store();
