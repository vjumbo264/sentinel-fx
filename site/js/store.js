/**
 * SENTINEL-FX · Central Reactive Store & Polling Supervisor
 * Tracks MT5 runner heartbeat, open CFD positions, model ledgers, and trade history.
 * Automatically halts polling when the tab is hidden to save battery & data.
 */

import { api } from "./api.js";

class Store {
  constructor() {
    this.state = {
      isAuth: false,
      mode: "demo", // 'demo' | 'real'
      balance: 10000.00,
      equity: 10000.00,
      freeMargin: 10000.00,
      marginLevel: 0,
      usedMargin: 0,
      todayPnl: 0,
      todayTrades: 0,
      todayWins: 0,
      heartbeat: null,
      runnerActive: false,
      runnerHandoverSeconds: 13800, // 3h50m countdown
      positions: [],
      history: [],
      models: [],
      ledgers: [],
      overrides: [],
      news: [],
      logs: [],
      loading: true,
      lastError: null,
      lastUpdated: null,
      demoReviewMode: api.demoData
    };

    this.subscribers = new Set();
    this.pollInterval = null;
    this.pollFreq = 4000; // 4 seconds

    // Visibility API support to avoid background thrashing
    document.addEventListener("visibilitychange", () => {
      if (document.hidden) {
        this.stopPolling();
      } else {
        this.fetchSnapshot();
        this.startPolling();
      }
    });

    // Initialize initial snapshot
    this.fetchSnapshot();
    this.startPolling();
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
    try {
      const [sysState, sessionData, tradesData, pairsData] = await Promise.allSettled([
        api.getState(),
        api.getSession(),
        api.getTrades(),
        api.getPairs()
      ]);

      if (sysState.status === "fulfilled" && sysState.value) {
        const d = sysState.value;
        const hb = d.heartbeat || {};
        const isLive = hb.ts && (Date.now() - new Date(hb.ts).getTime() < 120000);

        this.state.heartbeat = hb;
        this.state.runnerActive = !!isLive;
        this.state.mode = hb.mode || "demo";
        this.state.balance = Number(hb.balance ?? 10000.00);

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
        // Separate open positions vs closed trades
        const open = [];
        const closed = [];
        allTrades.forEach((t) => {
          if (!t.close_utc) {
            open.push({
              ticket: t.contract_id || t.id,
              symbol: t.pair,
              side: (t.side || "BUY").toUpperCase(),
              volume: Number(t.stake || 0.01),
              openPrice: Number(t.open_price || t.entry_price || 1.0850),
              currentPrice: Number(t.current_price || t.open_price || 1.0855),
              sl: Number(t.sl || 0),
              tp: Number(t.tp || 0),
              pnl: Number(t.pnl || 0),
              openTime: t.open_utc,
              modelId: t.pair,
              reason: t.reason || "Momentum + Volatility Confluence"
            });
          } else {
            closed.push(t);
          }
        });

        // Compute simulated or live equity & margin
        let openPnl = open.reduce((acc, p) => acc + (p.pnl || 0), 0);
        this.state.positions = open;
        this.state.history = closed;
        this.state.equity = this.state.balance + openPnl;
        this.state.usedMargin = open.reduce((acc, p) => acc + (p.volume * 1000 * 0.01), 0);
        this.state.freeMargin = Math.max(0, this.state.equity - this.state.usedMargin);
        this.state.marginLevel = this.state.usedMargin > 0 ? (this.state.equity / this.state.usedMargin) * 100 : 0;
      }

      if (pairsData.status === "fulfilled" && pairsData.value) {
        this.state.models = pairsData.value.pairs || [];
      }

      // If Demo Review Mode is explicitly turned on in settings and there are 0 positions,
      // provide realistic CFD sample positions so Victor can review every state cleanly.
      if (this.state.demoReviewMode && this.state.positions.length === 0) {
        this.applyDemoReviewData();
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

  applyDemoReviewData() {
    this.state.positions = [
      {
        ticket: 8124901,
        symbol: "EURUSD",
        side: "BUY",
        volume: 0.20,
        openPrice: 1.08420,
        currentPrice: 1.08645,
        sl: 1.08250,
        tp: 1.08950,
        pnl: 45.00,
        pips: 22.5,
        openTime: new Date(Date.now() - 3600000 * 2).toISOString(),
        modelId: "EURUSD-v2",
        reason: "H1 200 EMA pullback rejection + Volatility filter green"
      },
      {
        ticket: 8124908,
        symbol: "GBPJPY",
        side: "SELL",
        volume: 0.15,
        openPrice: 198.320,
        currentPrice: 198.140,
        sl: 198.600,
        tp: 197.500,
        pnl: 18.25,
        pips: 18.0,
        openTime: new Date(Date.now() - 1800000).toISOString(),
        modelId: "GBPJPY-v2",
        reason: "London breakout failure + RSI Bearish divergence"
      }
    ];
    this.state.equity = 10063.25;
    this.state.usedMargin = 350.00;
    this.state.freeMargin = 9713.25;
    this.state.marginLevel = 2875.2;
    this.state.todayPnl = 84.50;
    this.state.todayTrades = 5;
    this.state.todayWins = 4;
  }
}

export const store = new Store();
