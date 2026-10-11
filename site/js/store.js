/**
 * SENTINEL-FX · Central Reactive Store & Polling Supervisor
 * Tracks MT5 runner heartbeat, open CFD positions, model ledgers, and trade history.
 * Automatically halts polling when the tab is hidden to save battery & data.
 * Pure real data: real data exclusively.
 *
 * F3: fetchSnapshot now diffs every slice and only calls notify() when something
 * actually changed, so 4-second poll ticks never rebuild pages and wipe local
 * UI state (chips, filters, scroll, form drafts).
 */

import { api } from "./api.js";

function numEq(a, b, eps = 0.005) {
  if (a === null || a === undefined) return b === null || b === undefined;
  if (b === null || b === undefined) return false;
  return Math.abs(Number(a) - Number(b)) < eps;
}

function jsonEq(a, b) {
  try { return JSON.stringify(a) === JSON.stringify(b); } catch (_) { return false; }
}

function positionsEq(a, b) {
  if (a.length !== b.length) return false;
  for (let i = 0; i < a.length; i++) {
    const x = a[i], y = b[i];
    if (x.ticket !== y.ticket || x.symbol !== y.symbol || x.side !== y.side) return false;
    if (!numEq(x.pnl, y.pnl, 0.01) || !numEq(x.currentPrice, y.currentPrice, 1e-8)) return false;
  }
  return true;
}

function historyEq(a, b) {
  if (a.length !== b.length) return false;
  // cheap head/tail fingerprint; trades are append/settle only
  const fp = (t) => t ? `${t.contract_id || t.id}|${t.close_utc || ""}|${t.pnl || 0}` : "";
  return fp(a[0]) === fp(b[0]) && fp(a[a.length - 1]) === fp(b[b.length - 1]);
}

class Store {
  constructor() {
    this.state = {
      isAuth: !!api.token,
      authError: null,
      mode: "demo", // "demo" | "real"
      balance: null,
      equity: null,
      freeMargin: null,
      marginLevel: null,
      usedMargin: null,
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
      session: null,
      settings: {},
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

  /**
   * F3: merge `next` into state, returning true only if any slice really changed.
   * lastUpdated always refreshes but never triggers a notify on its own.
   */
  _mergeChanged(next) {
    let changed = false;
    const s = this.state;

    const setScalar = (key, eq) => {
      if (!(eq ? eq(s[key], next[key]) : s[key] === next[key])) { s[key] = next[key]; changed = true; }
    };
    const setNum = (key) => {
      if (!numEq(s[key], next[key])) { s[key] = next[key]; changed = true; }
    };

    ["mode", "todayTrades", "todayWins", "runnerActive", "loading", "lastError"].forEach(k => setScalar(k));
    ["balance", "equity", "freeMargin", "marginLevel", "usedMargin", "todayPnl"].forEach(k => setNum(k));
    // heartbeat.ts legitimately changes every poll; compare the content only
    const hbEq = (a, b) => jsonEq(a && { ...a, ts: 0 }, b && { ...b, ts: 0 });
    setScalar("heartbeat", hbEq);
    ["models", "ledgers", "overrides", "session", "settings", "news"].forEach(k => setScalar(k, jsonEq));

    if (!positionsEq(s.positions, next.positions)) { s.positions = next.positions; changed = true; }
    if (!historyEq(s.history, next.history)) { s.history = next.history; changed = true; }

    s.lastUpdated = new Date();
    return changed;
  }

  async fetchSnapshot(force = false) {
    if (!this.state.isAuth) return;

    try {
      const [sysState, sessionData, tradesData, pairsData, newsData] = await Promise.allSettled([
        api.getState(),
        api.getSession(),
        api.getTrades(),
        api.getPairs(),
        api.getNews()
      ]);

      const next = {
        mode: this.state.mode,
        balance: this.state.balance,
        equity: this.state.equity,
        freeMargin: this.state.freeMargin,
        marginLevel: this.state.marginLevel,
        usedMargin: this.state.usedMargin,
        todayPnl: this.state.todayPnl,
        todayTrades: this.state.todayTrades,
        todayWins: this.state.todayWins,
        heartbeat: this.state.heartbeat,
        runnerActive: this.state.runnerActive,
        positions: this.state.positions,
        history: this.state.history,
        models: this.state.models,
        ledgers: this.state.ledgers,
        overrides: this.state.overrides,
        session: this.state.session,
        settings: this.state.settings,
        news: this.state.news,
        loading: false,
        lastError: null
      };

      if (sysState.status === "fulfilled" && sysState.value) {
        const d = sysState.value;
        const hb = d.heartbeat || {};
        const isLive = hb.ts && (Date.now() - new Date(hb.ts).getTime() < 120000);

        next.heartbeat = hb;
        next.runnerActive = !!isLive;
        next.mode = hb.mode || (d.settings && d.settings.mode) || "demo";
        next.settings = d.settings || {};
        next.balance = hb.balance !== null && hb.balance !== undefined ? Number(hb.balance) : null;
        // Prefer real broker-reported equity / free margin from the heartbeat
        next.equity = hb.equity !== null && hb.equity !== undefined ? Number(hb.equity) : null;
        next.freeMargin = hb.free_margin !== null && hb.free_margin !== undefined ? Number(hb.free_margin) : null;

        if (d.today) {
          next.todayPnl = Number(d.today.pnl || 0);
          next.todayTrades = Number(d.today.trades || 0);
          next.todayWins = Number(d.today.wins || 0);
        }
      }

      if (sessionData.status === "fulfilled" && sessionData.value) {
        const sv = sessionData.value;
        next.ledgers = sv.ledger || [];
        next.overrides = sv.overrides || [];
        next.session = sv.session || null;
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

        next.positions = open;
        next.history = closed;

        if (next.balance !== null) {
          const openPnl = open.reduce((acc, p) => acc + (p.pnl || 0), 0);
          if (next.equity === null) next.equity = next.balance + openPnl;
          next.usedMargin = open.reduce((acc, p) => acc + (p.volume * 1000 * 0.01), 0);
          if (next.freeMargin === null) next.freeMargin = Math.max(0, next.equity - next.usedMargin);
          next.marginLevel = next.usedMargin > 0 ? (next.equity / next.usedMargin) * 100 : null;
        } else {
          // No runner data: keep every valuation field honestly null (F4)
          next.equity = null;
          next.usedMargin = null;
          next.freeMargin = null;
          next.marginLevel = null;
        }
      }

      if (pairsData.status === "fulfilled" && pairsData.value) {
        next.models = pairsData.value.pairs || [];
      }

      if (newsData.status === "fulfilled" && newsData.value) {
        next.news = newsData.value.events || [];
      }

      const changed = this._mergeChanged(next);
      if (changed || force) this.notify();
    } catch (err) {
      const msg = err.message || String(err);
      const changed = this.state.lastError !== msg || this.state.loading;
      this.state.loading = false;
      this.state.lastError = msg;
      if (changed || force) this.notify();
    }
  }
}

export const store = new Store();
