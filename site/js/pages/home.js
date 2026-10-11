/**
 * SENTINEL-FX · Home / Dashboard Page
 * Institutional hero balance card, compounding pool, runner handover,
 * top open positions, high-impact news radar, and quick actions.
 */

import { icons, pairAvatar } from "../icons.js";
import { store } from "../store.js";
import { api } from "../api.js";
import {
  formatCurrency,
  formatPercent,
  formatLagosTime,
  formatPips,
  formatLots,
  sfxBusy,
  showToast,
  showConfirmSheet
} from "../ui.js";

export const homeView = {
  unsubscribe: null,

  async render(container) {
    if (this.unsubscribe) this.unsubscribe();

    this.container = container;
    this.updateDom();

    // Subscribe to store updates for real-time reactivity
    this.unsubscribe = store.subscribe(() => {
      this.updateDom();
    });
  },

  updateDom() {
    if (!this.container) return;
    const s = store.state;

    const pnlSign = s.todayPnl >= 0 ? "+" : "";
    const pnlClass = s.todayPnl >= 0 ? "badge-profit" : "badge-loss";
    const pnlArrow = s.todayPnl >= 0 ? icons.arrowUp() : icons.arrowDown();
    const pnlPct = s.balance > 0 ? (s.todayPnl / s.balance) * 100 : 0;

    // Active models in session
    const activeModelsCount = s.models.filter(m => m.enabled).length || 2;
    const perModelShare = activeModelsCount > 0 ? s.balance / activeModelsCount : s.balance;

    // Top open positions
    const topPositions = [...s.positions]
      .sort((a, b) => Math.abs(b.pnl || 0) - Math.abs(a.pnl || 0))
      .slice(0, 3);

    this.container.innerHTML = `
      <div style="display:flex; flex-direction:column; gap:var(--space-5);">

        <!-- HERO BALANCE CARD -->
        <section class="hero-card">
          <div style="display:flex; justify-content:space-between; align-items:flex-start; margin-bottom:var(--space-2);">
            <div>
              <div class="card-title">ACCOUNT VALUATION</div>
              <div class="hero-balance tabular">${s.balance !== null ? formatCurrency(s.balance) : "—"}</div>${s.balance === null ? `<div style="font-size:var(--text-xs); color:var(--text-muted); margin-top:2px;">Awaiting MT5 runner heartbeat</div>` : ""}
            </div>
            <div style="display:flex; gap:var(--space-2); align-items:center;">
              <span class="${pnlClass} tabular" style="font-size:var(--text-sm); padding:6px 10px;">
                ${pnlArrow} ${pnlSign}${formatCurrency(s.todayPnl)} (${pnlSign}${formatPercent(pnlPct)})
              </span>
              ${s.mode === "demo" ? `
                <button id="btn-reset-demo" class="btn btn-secondary btn-sm" aria-label="Reset Demo Balance to $10,000">
                  Reset $10k
                </button>
              ` : ""}
            </div>
          </div>

          <!-- Hero Metrics Grid -->
          <div class="hero-metrics-grid">
            <div class="metric-item">
              <span class="metric-label">Equity</span>
              <span class="metric-val tabular">${formatCurrency(s.equity)}</span>
            </div>
            <div class="metric-item">
              <span class="metric-label">Free Margin</span>
              <span class="metric-val tabular">${formatCurrency(s.freeMargin)}</span>
            </div>
            <div class="metric-item">
              <span class="metric-label">Used Margin</span>
              <span class="metric-val tabular">${formatCurrency(s.usedMargin)}</span>
            </div>
            <div class="metric-item">
              <span class="metric-label">Margin Level</span>
              <span class="metric-val tabular">${s.marginLevel > 0 ? `${s.marginLevel.toFixed(1)}%` : "∞"}</span>
            </div>
          </div>
        </section>

        <!-- RUNNER & COMPOUNDING 2-COLUMN GRID -->
        <div style="display:grid; grid-template-columns:repeat(auto-fit, minmax(300px, 1fr)); gap:var(--space-4);">

          <!-- RUNNER SUPERVISOR CARD -->
          <section class="card">
            <div class="card-header">
              <span class="card-title">MT5 RUNNER SUPERVISOR</span>
              <span class="status-indicator">
                <span class="${s.runnerActive ? "dot-live" : "dot-paused"}"></span>
                <span style="font-weight:600; font-size:var(--text-xs);">${s.runnerActive ? "ACTIVE" : "STANDBY"}</span>
              </span>
            </div>

            <div style="display:flex; flex-direction:column; gap:var(--space-3); margin-bottom:var(--space-4);">
              <div style="display:flex; justify-content:space-between; font-size:var(--text-sm);">
                <span style="color:var(--text-muted);">Last Heartbeat</span>
                <span class="tabular">${s.heartbeat?.ts ? formatLagosTime(s.heartbeat.ts) : "Waiting for bot"}</span>
              </div>
              ${s.heartbeat?.loginid ? `
                <div style="display:flex; justify-content:space-between; font-size:var(--text-sm);">
                  <span style="color:var(--text-muted);">Connected Account</span>
                  <span class="tabular" style="font-weight:600;">${s.heartbeat.loginid} (${s.heartbeat.currency || "USD"})` : ""}
                ${s.heartbeat?.loginid ? `</div>` : ""}
              <div style="display:flex; justify-content:space-between; font-size:var(--text-sm);">
                <span style="color:var(--text-muted);">Handover Status</span>
                ${s.runnerActive ? `<span style="color:var(--profit); font-weight:600;">Zero-Gap (~3h50m cycle)</span>` : `<span style="color:var(--text-muted);">Runner Idle</span>`}
              </div>
              <div style="display:flex; justify-content:space-between; font-size:var(--text-sm);">
                <span style="color:var(--text-muted);">Execution Engine</span>
                <span>Deriv MT5 (Linux wine-6092)</span>
              </div>
            </div>

            <!-- Quick Action Buttons -->
            <div style="display:flex; gap:var(--space-2); flex-wrap:wrap;">
              <button id="btn-toggle-runner" class="btn btn-secondary btn-sm" style="flex:1;">
                ${icons.play("w-4 h-4")} <span>Dispatch Runner</span>
              </button>
              <button id="btn-close-all" class="btn btn-danger btn-sm" style="flex:1;">
                ${icons.kill("w-4 h-4")} <span>Close All</span>
              </button>
            </div>
          </section>

          <!-- COMPONDING POOL STATUS -->
          <section class="card">
            <div class="card-header">
              <span class="card-title">COMPOUNDING ALLOCATION</span>
              <button id="btn-reallocate" class="btn btn-ghost btn-sm" style="font-size:var(--text-xs); padding:0 6px;">
                Reallocate
              </button>
            </div>

            <div style="display:flex; flex-direction:column; gap:var(--space-3); margin-bottom:var(--space-4);">
              <div style="display:flex; justify-content:space-between; font-size:var(--text-sm);">
                <span style="color:var(--text-muted);">Active Models</span>
                <span class="tabular" style="font-weight:600;">${activeModelsCount} enabled</span>
              </div>
              <div style="display:flex; justify-content:space-between; font-size:var(--text-sm);">
                <span style="color:var(--text-muted);">Per-Model Pool Share</span>
                <span class="tabular" style="font-weight:600; color:var(--accent-primary);">${formatCurrency(perModelShare)}</span>
              </div>
              <div style="display:flex; justify-content:space-between; font-size:var(--text-sm);">
                <span style="color:var(--text-muted);">Growth Multiplier</span>
                <span class="tabular" style="color:var(--profit); font-weight:600;">1.00x Base</span>
              </div>
            </div>

            <div style="padding:10px 12px; border-radius:var(--radius-sm); background:var(--bg-surface-elevated); font-size:var(--text-xs); color:var(--text-secondary); line-height:1.4;">
              Each active pair model is assigned equal stake of the total session pool. Realized profits compound back into the shared pool automatically.
            </div>
          </section>
        </div>

        <!-- TOP MOVERS / OPEN POSITIONS PREVIEW -->
        <section class="card">
          <div class="card-header">
            <span class="card-title">OPEN POSITIONS DESK (${s.positions.length})</span>
            <a href="#/trades" class="btn btn-ghost btn-sm" style="text-decoration:none;">
              View All ${icons.chevronRight("w-4 h-4")}
            </a>
          </div>

          ${s.positions.length === 0 ? `
            <div style="text-align:center; padding:var(--space-6) var(--space-4);">
              <div style="margin-bottom:var(--space-2); color:var(--text-muted);">${icons.trades("w-8 h-8")}</div>
              <div style="font-weight:600; margin-bottom:4px;">No Open Positions</div>
              <div style="font-size:var(--text-sm); color:var(--text-muted);">Models are scanning H1/M15 setups according to their policies.</div>
            </div>
          ` : `
            <div style="display:flex; flex-direction:column; gap:var(--space-2);">
              ${topPositions.map(pos => {
                const sideBadge = pos.side === "BUY" ? "badge-side-buy" : "badge-side-sell";
                const pnlClass = pos.pnl >= 0 ? "text-profit" : "text-loss";
                const pnlSign = pos.pnl >= 0 ? "+" : "";

                return `
                  <div style="display:flex; align-items:center; justify-content:space-between; padding:10px 12px; background:var(--bg-surface-elevated); border-radius:var(--radius-sm);">
                    <div style="display:flex; align-items:center; gap:var(--space-3);">
                      ${pairAvatar(pos.symbol, 34)}
                      <div>
                        <div style="display:flex; align-items:center; gap:6px;">
                          <span style="font-weight:700; font-size:var(--text-sm);">${pos.symbol}</span>
                          <span class="${sideBadge}">${pos.side}</span>
                        </div>
                        <div style="font-size:var(--text-xs); color:var(--text-muted);" class="tabular">
                          ${formatLots(pos.volume)} @ ${pos.openPrice}
                        </div>
                      </div>
                    </div>

                    <div style="text-align:right;">
                      <div class="tabular ${pnlClass}" style="font-weight:700; font-size:var(--text-sm);">
                        ${pnlSign}${formatCurrency(pos.pnl)}
                      </div>
                      <div class="tabular" style="font-size:var(--text-xs); color:var(--text-muted);">
                        ${formatPips(pos.pips || (pos.pnl * 10))}
                      </div>
                    </div>
                  </div>
                `;
              }).join("")}
            </div>
          `}
        </section>

        <!-- HIGH-IMPACT ECONOMIC RADAR -->
        <section class="card">
          <div class="card-header">
            <div style="display:flex; align-items:center; gap:6px;">
              <span class="card-title">ECONOMIC CALENDAR RADAR</span>
              <span style="background:var(--loss-subtle); color:var(--loss); font-size:10px; font-weight:700; padding:2px 6px; border-radius:var(--radius-xs);">HIGH IMPACT</span>
            </div>
            <span style="font-size:var(--text-xs); color:var(--text-muted);">Lagos Time (UTC+1)</span>
          </div>

          <div style="display:flex; flex-direction:column; gap:var(--space-2);">
            ${(!s.news || s.news.length === 0) ? `
              <div style="text-align:center; padding:var(--space-6); color:var(--text-muted); font-size:var(--text-sm);">
                No upcoming economic calendar events scheduled.
              </div>
            ` : `
              ${s.news.slice(0, 5).map(ev => {
                const pairs = typeof ev.affected_pairs === "string" ? JSON.parse(ev.affected_pairs || "[]") : (ev.affected_pairs || []);
                const impactClass = (ev.impact || "").toLowerCase() === "high" ? "#dc2626" : ((ev.impact || "").toLowerCase() === "medium" ? "#eab308" : "#3b82f6");
                return `
                  <div style="display:flex; align-items:center; justify-content:space-between; padding:10px 12px; border-radius:var(--radius-sm); background:var(--bg-surface-elevated);">
                    <div style="display:flex; align-items:center; gap:var(--space-3);">
                      <span style="background:${impactClass}; color:#fff; font-size:11px; font-weight:800; padding:3px 6px; border-radius:4px;">${ev.currency || "ALL"}</span>
                      <div>
                        <div style="font-weight:600; font-size:var(--text-sm);">${ev.title}</div>
                        ${pairs.length > 0 ? `<div style="font-size:var(--text-xs); color:var(--text-muted);">Affects: ${pairs.join(", ")}</div>` : ""}
                      </div>
                    </div>
                    <div style="text-align:right;">
                      <div class="tabular" style="font-weight:600; font-size:var(--text-sm); color:var(--warning);">${ev.utc_time ? formatLagosTime(ev.utc_time) : ""}</div>
                      <div style="font-size:11px; color:var(--text-muted);">Impact: ${ev.impact || "standard"}</div>
                    </div>
                  </div>
                `;
              }).join("")}
            `}
          </div>
        </section>

      </div>
    `;

    this.bindEvents();
  },

  bindEvents() {
    // Reset Demo Balance button
    const resetBtn = document.getElementById("btn-reset-demo");
    if (resetBtn) {
      resetBtn.addEventListener("click", () => {
        showConfirmSheet({
          title: "Reset Demo Balance?",
          description: "This resets your demo account balance back to $10,000.00 and zeroes today's demo PnL ledger in D1.",
          confirmText: "Reset $10,000.00",
          confirmVariant: "primary",
          onConfirm: async () => {
            await api.resetDemoBalance();
            await store.fetchSnapshot();
          }
        });
      });
    }

    // Dispatch runner button
    const dispatchBtn = document.getElementById("btn-toggle-runner");
    if (dispatchBtn) {
      dispatchBtn.addEventListener("click", () => {
        sfxBusy(dispatchBtn, async () => {
          await api.dispatchWorkflow("bot.yml");
          await store.fetchSnapshot();
        }, { pending: "Dispatching bot.yml...", ok: "Runner dispatched" });
      });
    }

    // Close All positions button
    const closeAllBtn = document.getElementById("btn-close-all");
    if (closeAllBtn) {
      closeAllBtn.addEventListener("click", () => {
        showConfirmSheet({
          title: "Close All Open CFD Positions?",
          description: "This signals the MT5 runner to immediately close all market positions at the current best market bid/ask.",
          confirmText: "Emergency Close All",
          confirmVariant: "danger",
          onConfirm: async () => {
            await api.overrideSession("*", "stop_all", "Emergency close all from dashboard");
            await store.fetchSnapshot();
          }
        });
      });
    }

    // Reallocate balance button
    const reallocBtn = document.getElementById("btn-reallocate");
    if (reallocBtn) {
      reallocBtn.addEventListener("click", () => {
        showConfirmSheet({
          title: "Reallocate Compounding Pool?",
          description: "Evenly splits current total balance across all currently enabled pair models in D1.",
          confirmText: "Distribute Pool Equally",
          confirmVariant: "primary",
          onConfirm: async () => {
            await api.allocateSession(store.state.balance, store.state.mode);
            await store.fetchSnapshot();
          }
        });
      });
    }
  }
};
