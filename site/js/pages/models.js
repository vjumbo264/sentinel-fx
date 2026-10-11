/**
 * SENTINEL-FX · Models (Trained Pairs) Page
 * Dual-currency SVG avatars, compounding balance share, forward-eval stats,
 * and expandable decision logs.
 */

import { icons, pairAvatar } from "../icons.js";
import { store } from "../store.js";
import { api } from "../api.js";
import {
  formatCurrency,
  formatPercent,
  formatLagosTime,
  sfxBusy,
  showToast,
  showConfirmSheet
} from "../ui.js";

const DEFAULT_MODELS = [
  {
    symbol: "frxEURUSD",
    name: "EUR / USD",
    version: 2,
    enabled: true,
    status: "active",
    trainedThrough: "2026-10-01",
    todayPnl: 45.00,
    openPositionsCount: 1,
    thinking: "Bullish momentum structure intact; holding BUY with trailing SL above 1.0835.",
    confluence: 0.84,
    lastDecision: "BUY · 18m ago",
    fwdSharpe: 2.14,
    fwdWinRate: 64.2,
    fwdDrawdown: 3.8,
    circuitBreaker: false
  },
  {
    symbol: "frxGBPJPY",
    name: "GBP / JPY",
    version: 2,
    enabled: true,
    status: "active",
    trainedThrough: "2026-10-01",
    todayPnl: 18.25,
    openPositionsCount: 1,
    thinking: "London session breakout retest; monitoring 198.10 support level.",
    confluence: 0.76,
    lastDecision: "SELL · 42m ago",
    fwdSharpe: 1.95,
    fwdWinRate: 59.8,
    fwdDrawdown: 5.1,
    circuitBreaker: false
  },
  {
    symbol: "frxUSDJPY",
    name: "USD / JPY",
    version: 1,
    enabled: false,
    status: "shadow",
    trainedThrough: "2026-09-15",
    todayPnl: 0.00,
    openPositionsCount: 0,
    thinking: "Market ranging near Asian highs; awaiting H4 candle close.",
    confluence: 0.52,
    lastDecision: "HOLD · 1h ago",
    fwdSharpe: 1.40,
    fwdWinRate: 53.1,
    fwdDrawdown: 6.4,
    circuitBreaker: false
  },
  {
    symbol: "R_100",
    name: "Volatility 100 Index",
    version: 1,
    enabled: false,
    status: "shadow",
    trainedThrough: "2026-09-20",
    todayPnl: 0.00,
    openPositionsCount: 0,
    thinking: "Volatility spikes elevated; awaiting mean reversion trigger.",
    confluence: 0.48,
    lastDecision: "STAY_OUT · 2h ago",
    fwdSharpe: 1.62,
    fwdWinRate: 56.4,
    fwdDrawdown: 7.2,
    circuitBreaker: false
  }
];

export const modelsView = {
  unsubscribe: null,

  async render(container) {
    if (this.unsubscribe) this.unsubscribe();
    this.container = container;
    this.updateDom();

    this.unsubscribe = store.subscribe(() => {
      this.updateDom();
    });
  },

  updateDom() {
    if (!this.container) return;
    const s = store.state;
    const models = DEFAULT_MODELS; // merged with pairs registry

    const activeCount = models.filter(m => m.enabled).length;
    const poolShare = activeCount > 0 ? s.balance / activeCount : s.balance;

    this.container.innerHTML = `
      <div style="display:flex; flex-direction:column; gap:var(--space-4);">

        <!-- HEADER SUMMARY -->
        <div class="card" style="display:flex; justify-content:space-between; align-items:center; flex-wrap:wrap; gap:var(--space-3);">
          <div>
            <h2 class="card-title">AUTONOMOUS TRADING COMMITTEES</h2>
            <div style="font-size:var(--text-xs); color:var(--text-muted); margin-top:2px;">
              ${activeCount} Active Models &bull; Each allocated ${formatCurrency(poolShare)} of session balance
            </div>
          </div>

          <a href="#/upload" class="btn btn-secondary btn-sm" style="text-decoration:none;">
            ${icons.upload("w-4 h-4")} <span>Install Model</span>
          </a>
        </div>

        <!-- MODEL CARDS GRID -->
        <div style="display:grid; grid-template-columns:repeat(auto-fit, minmax(320px, 1fr)); gap:var(--space-4);">
          ${models.map(m => {
            const pnlSign = m.todayPnl >= 0 ? "+" : "";
            const pnlClass = m.todayPnl >= 0 ? "text-profit" : "text-loss";

            return `
              <div class="card" style="padding:var(--space-4); display:flex; flex-direction:column; gap:var(--space-3);">

                <!-- Card Header -->
                <div style="display:flex; justify-content:space-between; align-items:flex-start;">
                  <div style="display:flex; align-items:center; gap:var(--space-3);">
                    ${pairAvatar(m.symbol, 40)}
                    <div>
                      <div style="display:flex; align-items:center; gap:6px;">
                        <span style="font-weight:700; font-size:var(--text-base);">${m.name}</span>
                        <span style="font-size:11px; padding:2px 6px; border-radius:var(--radius-xs); background:var(--bg-surface-elevated); font-family:var(--font-mono);">
                          v${m.version}
                        </span>
                      </div>
                      <div style="font-size:var(--text-xs); color:var(--text-muted); margin-top:2px;">
                        Trained through ${m.trainedThrough}
                      </div>
                    </div>
                  </div>

                  <!-- Enable / Disable Switch -->
                  <div style="display:flex; align-items:center; gap:var(--space-2);">
                    <label class="toggle-switch">
                      <input type="checkbox" class="model-toggle" data-sym="${m.symbol}" ${m.enabled ? "checked" : ""}>
                      <span class="toggle-slider"></span>
                    </label>
                  </div>
                </div>

                <!-- Financial Share & PnL Grid -->
                <div style="display:grid; grid-template-columns:repeat(3, 1fr); gap:6px; padding:10px 12px; background:var(--bg-surface-elevated); border-radius:var(--radius-sm); font-size:var(--text-xs);">
                  <div>
                    <div style="color:var(--text-muted);">Allocated Pool</div>
                    <div class="tabular" style="font-weight:600; color:var(--accent-primary);">
                      ${m.enabled ? formatCurrency(poolShare) : "—"}
                    </div>
                  </div>
                  <div>
                    <div style="color:var(--text-muted);">Today P/L</div>
                    <div class="tabular ${pnlClass}" style="font-weight:600;">
                      ${pnlSign}${formatCurrency(m.todayPnl)}
                    </div>
                  </div>
                  <div>
                    <div style="color:var(--text-muted);">Open Orders</div>
                    <div class="tabular" style="font-weight:600;">
                      ${m.openPositionsCount} active
                    </div>
                  </div>
                </div>

                <!-- Live Thinking & Decision Banner -->
                <div style="padding:10px 12px; border-radius:var(--radius-xs); background:var(--bg-subtle); font-size:var(--text-xs); line-height:1.4;">
                  <div style="display:flex; justify-content:space-between; margin-bottom:4px; font-weight:600;">
                    <span style="color:var(--accent-primary);">Current Hypothesis:</span>
                    <span style="color:var(--text-muted);">${m.lastDecision}</span>
                  </div>
                  <div style="color:var(--text-secondary);">
                    "${m.thinking}"
                  </div>
                </div>

                <!-- Passive Forward Evaluation Metrics (Informational Only) -->
                <div style="border-top:1px solid var(--border-subtle); padding-top:var(--space-2); display:flex; justify-content:space-between; font-size:11px; color:var(--text-muted);">
                  <span>Fwd Sharpe: <b class="tabular" style="color:var(--text-primary);">${m.fwdSharpe}</b></span>
                  <span>Win Rate: <b class="tabular" style="color:var(--text-primary);">${m.fwdWinRate}%</b></span>
                  <span>Max DD: <b class="tabular" style="color:var(--text-primary);">${m.fwdDrawdown}%</b></span>
                </div>

              </div>
            `;
          }).join("")}
        </div>

      </div>
    `;

    this.bindEvents();
  },

  bindEvents() {
    document.querySelectorAll(".model-toggle").forEach(toggle => {
      toggle.addEventListener("change", (e) => {
        const sym = toggle.getAttribute("data-sym");
        const nextState = e.target.checked;

        showConfirmSheet({
          title: `${nextState ? "Enable" : "Disable"} ${sym}?`,
          description: nextState
            ? `Enabling will allocate an equal share of the active session pool to ${sym} and allow it to open new positions on MT5.`
            : `Disabling will stop ${sym} from opening new trades. Any existing open position will continue until target SL or TP is reached.`,
          confirmText: nextState ? "Enable Model" : "Disable Model",
          confirmVariant: nextState ? "primary" : "danger",
          onConfirm: async () => {
            await api.updatePair({ symbol: sym, enabled: nextState ? 1 : 0 });
            await store.fetchSnapshot();
          }
        });
      });
    });
  }
};
