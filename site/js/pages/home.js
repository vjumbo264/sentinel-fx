/**
 * SENTINEL-FX · Home / Dashboard Page
 * Institutional hero balance card, compounding pool, runner handover,
 * top open positions, high-impact news radar, and quick actions.
 *
 * F3: no store subscription — the router forces a fresh snapshot before render,
 *     and poll ticks never rebuild this page (no more mid-tap resets).
 * F4: every Account Valuation field is honest: real values when the runner has
 *     reported them, otherwise a consistent "No runner data yet" state —
 *     no fake zeros, no green gain pill, no infinity margin level.
 * F2: compounding card shows the real session pool, per-model share, used and
 *     remaining share from /api/session data, with a shortcut to set the pool.
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
  showConfirmSheet
} from "../ui.js";

const NO_DATA = '<span class="val-missing">No runner data yet</span>';

export const homeView = {
  async render(container) {
    this.container = container;
    this.updateDom();
  },

  updateDom() {
    if (!this.container) return;
    const s = store.state;
    const hasRunnerData = s.balance !== null && s.balance !== undefined;

    // Daily PnL pill only when we actually have a balance to anchor it to
    const pnlPct = hasRunnerData && s.balance > 0 ? (s.todayPnl / s.balance) * 100 : null;
    const showPnlPill = hasRunnerData && (s.todayTrades > 0 || s.todayPnl !== 0);

    // F2: real session pool data from /api/session
    const enabledModels = s.models.filter(m => m.enabled);
    const enabledCount = enabledModels.length;
    const activeLedgers = (s.ledgers || []).filter(l => l.active);
    const poolTotal = s.session && s.session.starting_balance != null
      ? Number(s.session.starting_balance)
      : (activeLedgers.length ? activeLedgers.reduce((a, l) => a + Number(l.allocated || 0), 0) : null);
    const perModelShare = poolTotal !== null && enabledCount > 0 ? poolTotal / enabledCount : null;
    const shareUsed = activeLedgers.length
      ? activeLedgers.reduce((a, l) => a + Math.max(0, Number(l.allocated || 0) - Number(l.balance || 0)), 0)
      : null;
    const shareRemaining = activeLedgers.length
      ? activeLedgers.reduce((a, l) => a + Number(l.balance || 0), 0)
      : null;

    // Top open positions
    const topPositions = [...s.positions]
      .sort((a, b) => Math.abs(b.pnl || 0) - Math.abs(a.pnl || 0))
      .slice(0, 3);

    this.container.innerHTML = `
      <div style="display:flex; flex-direction:column; gap:var(--space-5);">

        <!-- HERO BALANCE CARD -->
        <section class="hero-card">
          <div style="display:flex; justify-content:space-between; align-items:flex-start; margin-bottom:var(--space-2); flex-wrap:wrap; gap:var(--space-2);">
            <div>
              <div class="card-title">ACCOUNT VALUATION</div>
              <div class="hero-balance tabular">${hasRunnerData ? formatCurrency(s.balance) : "—"}</div>
              ${!hasRunnerData ? `<div style="font-size:var(--text-xs); color:var(--text-muted); margin-top:2px;">No runner data yet · awaiting MT5 heartbeat</div>` : ""}
            </div>
            <div style="display:flex; gap:var(--space-2); align-items:center;">
              ${showPnlPill ? `
                <span class="${s.todayPnl >= 0 ? "badge-profit" : "badge-loss"} tabular" style="font-size:var(--text-sm); padding:6px 10px;">
                  ${s.todayPnl >= 0 ? icons.arrowUp() : icons.arrowDown()} ${s.todayPnl >= 0 ? "+" : ""}${formatCurrency(s.todayPnl)} (${pnlPct !== null ? (pnlPct >= 0 ? "+" : "") + formatPercent(pnlPct) : "—"})
                </span>
              ` : ""}
              ${s.mode === "demo" ? `
                <button id="btn-reset-demo" class="btn btn-secondary btn-sm" aria-label="Reset Demo Balance to $10,000">
                  Reset $10k
                </button>
              ` : ""}
            </div>
          </div>

          <!-- Hero Metrics Grid — all fields honest when no runner data -->
          <div class="hero-metrics-grid">
            <div class="metric-item">
              <span class="metric-label">Equity</span>
              <span class="metric-val tabular">${hasRunnerData ? formatCurrency(s.equity) : NO_DATA}</span>
            </div>
            <div class="metric-item">
              <span class="metric-label">Free Margin</span>
              <span class="metric-val tabular">${hasRunnerData ? formatCurrency(s.freeMargin) : NO_DATA}</span>
            </div>
            <div class="metric-item">
              <span class="metric-label">Used Margin</span>
              <span class="metric-val tabular">${hasRunnerData ? formatCurrency(s.usedMargin) : NO_DATA}</span>
            </div>
            <div class="metric-item">
              <span class="metric-label">Margin Level</span>
              <span class="metric-val tabular">${hasRunnerData ? (s.marginLevel !== null && s.marginLevel !== undefined ? `${Number(s.marginLevel).toFixed(1)}%` : "No open margin") : NO_DATA}</span>
            </div>
          </div>
        </section>

        <!-- RUNNER & COMPOUNDING 2-COLUMN GRID -->
        <div style="display:grid; grid-template-columns:repeat(auto-fit, minmax(280px, 1fr)); gap:var(--space-4);">

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
                  <span class="tabular" style="font-weight:600;">${s.heartbeat.loginid} (${s.heartbeat.currency || "USD"})</span>
                </div>
              ` : ""}
              <div style="display:flex; justify-content:space-between; font-size:var(--text-sm);">
                <span style="color:var(--text-muted);">Handover Status</span>
                ${s.runnerActive ? `<span style="color:var(--profit); font-weight:600;">Zero-Gap (~3h50m cycle)</span>` : `<span style="color:var(--text-muted);">Runner Idle</span>`}
              </div>
              <div style="display:flex; justify-content:space-between; font-size:var(--text-sm);">
                <span style="color:var(--text-muted);">Execution Engine</span>
                <span>Deriv MT5 (Linux wine-6092)</span>
              </div>
            </div>

            <div style="display:flex; gap:var(--space-2); flex-wrap:wrap;">
              <button id="btn-toggle-runner" class="btn btn-secondary btn-sm" style="flex:1;">
                ${icons.play("w-4 h-4")} <span>Dispatch Runner</span>
              </button>
              <button id="btn-close-all" class="btn btn-danger btn-sm" style="flex:1;">
                ${icons.kill("w-4 h-4")} <span>Close All</span>
              </button>
            </div>
          </section>

          <!-- COMPOUNDING POOL STATUS (F2: real session data) -->
          <section class="card">
            <div class="card-header">
              <span class="card-title">COMPOUNDING ALLOCATION</span>
              <div style="display:flex; gap:4px;">
                <a href="#/risk" class="btn btn-ghost btn-sm" style="font-size:var(--text-xs); padding:0 6px; text-decoration:none;">Set Pool</a>
                <button id="btn-reallocate" class="btn btn-ghost btn-sm" style="font-size:var(--text-xs); padding:0 6px;" ${poolTotal === null ? "disabled" : ""}>
                  Reallocate
                </button>
              </div>
            </div>

            <div style="display:flex; flex-direction:column; gap:var(--space-3); margin-bottom:var(--space-4);">
              <div style="display:flex; justify-content:space-between; font-size:var(--text-sm);">
                <span style="color:var(--text-muted);">Session Balance Pool</span>
                <span class="tabular" style="font-weight:700;">${poolTotal !== null ? formatCurrency(poolTotal) : NO_DATA}</span>
              </div>
              <div style="display:flex; justify-content:space-between; font-size:var(--text-sm);">
                <span style="color:var(--text-muted);">Active Models</span>
                <span class="tabular" style="font-weight:600;">${enabledCount} enabled</span>
              </div>
              <div style="display:flex; justify-content:space-between; font-size:var(--text-sm);">
                <span style="color:var(--text-muted);">Per-Model Pool Share</span>
                <span class="tabular" style="font-weight:600; color:var(--accent-primary);">${perModelShare !== null ? formatCurrency(perModelShare) : NO_DATA}</span>
              </div>
              <div style="display:flex; justify-content:space-between; font-size:var(--text-sm);">
                <span style="color:var(--text-muted);">Share Used / Remaining</span>
                <span class="tabular" style="font-weight:600;">
                  ${shareUsed !== null ? `${formatCurrency(shareUsed)} / ${formatCurrency(shareRemaining)}` : NO_DATA}
                </span>
              </div>
            </div>

            <div style="padding:10px 12px; border-radius:var(--radius-sm); background:var(--bg-surface-elevated); font-size:var(--text-xs); color:var(--text-secondary); line-height:1.4;">
              Each active pair model is assigned an equal share of the session pool. Realized profits compound back into the shared pool automatically. Set the pool amount on the Risk &amp; Auth page.
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
                  <div style="display:flex; align-items:center; justify-content:space-between; padding:10px 12px; background:var(--bg-surface-elevated); border-radius:var(--radius-sm); gap:var(--space-2); flex-wrap:wrap;">
                    <div style="display:flex; align-items:center; gap:var(--space-3); min-width:0;">
                      ${pairAvatar(pos.symbol, 32)}
                      <div style="min-width:0;">
                        <div style="display:flex; align-items:center; gap:6px; flex-wrap:wrap;">
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
                let pairs = [];
                try { pairs = typeof ev.affected_pairs === "string" ? JSON.parse(ev.affected_pairs || "[]") : (ev.affected_pairs || []); } catch (_) {}
                const impactClass = (ev.impact || "").toLowerCase() === "high" ? "#dc2626" : ((ev.impact || "").toLowerCase() === "medium" ? "#eab308" : "#3b82f6");
                return `
                  <div style="display:flex; align-items:center; justify-content:space-between; padding:10px 12px; border-radius:var(--radius-sm); background:var(--bg-surface-elevated); gap:var(--space-2);">
                    <div style="display:flex; align-items:center; gap:var(--space-3); min-width:0;">
                      <span style="background:${impactClass}; color:#fff; font-size:11px; font-weight:800; padding:3px 6px; border-radius:4px; flex-shrink:0;">${ev.currency || "ALL"}</span>
                      <div style="min-width:0;">
                        <div style="font-weight:600; font-size:var(--text-sm);">${ev.title}</div>
                        ${pairs.length > 0 ? `<div style="font-size:var(--text-xs); color:var(--text-muted);">Affects: ${pairs.join(", ")}</div>` : ""}
                      </div>
                    </div>
                    <div style="text-align:right; flex-shrink:0;">
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
    // Reset Demo Balance button (demo mode only, real endpoint, confirm first)
    const resetBtn = document.getElementById("btn-reset-demo");
    if (resetBtn) {
      resetBtn.addEventListener("click", () => {
        showConfirmSheet({
          title: "Reset Demo Balance?",
          description: "Resets the DEMO account to $10,000.00 via /api/account/reset-demo-balance (Deriv demo top-up + D1 session zeroing). Real accounts are never touched.",
          confirmText: "Reset $10,000.00",
          confirmVariant: "primary",
          onConfirm: async () => {
            const res = await api.resetDemoBalance();
            await store.fetchSnapshot(true);
            this.updateDom();
            if (!res || res.ok !== true) throw new Error((res && res.error) || "Reset failed");
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
        }, { pending: "Dispatching bot.yml...", ok: "Runner dispatched" }).catch(() => {});
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
            await store.fetchSnapshot(true);
            this.updateDom();
          }
        });
      });
    }

    // Reallocate pool evenly (uses the configured pool when present)
    const reallocBtn = document.getElementById("btn-reallocate");
    if (reallocBtn) {
      reallocBtn.addEventListener("click", () => {
        const s = store.state;
        const pool = s.session && s.session.starting_balance != null
          ? Number(s.session.starting_balance)
          : s.balance;
        showConfirmSheet({
          title: "Reallocate Compounding Pool?",
          description: `Evenly splits the session pool (${pool != null ? formatCurrency(pool) : "current balance"}) across all currently enabled pair models in D1.`,
          confirmText: "Distribute Pool Equally",
          confirmVariant: "primary",
          onConfirm: async () => {
            await api.allocateSession(pool, s.mode);
            await store.fetchSnapshot(true);
            this.updateDom();
          }
        });
      });
    }
  }
};
