/**
 * SENTINEL-FX · Active Trades Desk
 * Card list on mobile, high-density table on desktop.
 * Pips, PnL, SL/TP levels, break-even SL action, and close-half.
 */

import { icons, pairAvatar } from "../icons.js";
import { store } from "../store.js";
import { api } from "../api.js";
import {
  formatCurrency,
  formatPercent,
  formatPips,
  formatLots,
  formatLagosTime,
  sfxBusy,
  showToast,
  showConfirmSheet
} from "../ui.js";

export const tradesView = {
  unsubscribe: null,
  groupBy: "symbol", // 'symbol' | 'model'

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
    const positions = s.positions || [];

    const totalPnl = positions.reduce((acc, p) => acc + (p.pnl || 0), 0);
    const totalLots = positions.reduce((acc, p) => acc + (p.volume || 0), 0);
    const pnlSign = totalPnl >= 0 ? "+" : "";
    const pnlClass = totalPnl >= 0 ? "text-profit" : "text-loss";

    this.container.innerHTML = `
      <div style="display:flex; flex-direction:column; gap:var(--space-4);">

        <!-- TRADES SUMMARY BAR -->
        <div class="card" style="display:flex; justify-content:space-between; align-items:center; flex-wrap:wrap; gap:var(--space-3);">
          <div>
            <div class="card-title">CFD POSITIONS DESK</div>
            <div style="display:flex; align-items:baseline; gap:var(--space-2); margin-top:2px;">
              <span class="tabular" style="font-size:var(--text-xl); font-weight:700;">${positions.length} Open</span>
              <span style="font-size:var(--text-xs); color:var(--text-muted);">&bull;</span>
              <span class="tabular ${pnlClass}" style="font-size:var(--text-lg); font-weight:700;">
                ${pnlSign}${formatCurrency(totalPnl)}
              </span>
              <span style="font-size:var(--text-xs); color:var(--text-muted);">(${formatLots(totalLots)} total)</span>
            </div>
          </div>

          <div style="display:flex; gap:var(--space-2); align-items:center;">
            <!-- Group By Selector -->
            <div style="display:inline-flex; background:var(--bg-surface-elevated); border-radius:var(--radius-sm); padding:2px;">
              <button id="group-sym-btn" class="btn btn-sm ${this.groupBy === "symbol" ? "btn-secondary" : "btn-ghost"}" style="min-height:32px; padding:0 8px; font-size:12px;">
                By Symbol
              </button>
              <button id="group-model-btn" class="btn btn-sm ${this.groupBy === "model" ? "btn-secondary" : "btn-ghost"}" style="min-height:32px; padding:0 8px; font-size:12px;">
                By Model
              </button>
            </div>

            <button id="btn-trades-refresh" class="btn btn-secondary btn-sm" style="min-height:36px;">
              ${icons.refresh("w-4 h-4")} <span>Refresh</span>
            </button>
          </div>
        </div>

        <!-- EMPTY STATE -->
        ${positions.length === 0 ? `
          <div class="card" style="text-align:center; padding:var(--space-10) var(--space-4);">
            <div style="margin-bottom:var(--space-3); color:var(--text-muted);">${icons.trades("w-12 h-12")}</div>
            <h3 style="font-family:var(--font-display); font-size:var(--text-lg); font-weight:700; margin-bottom:var(--space-1);">Flat · Zero Exposure</h3>
            <p style="font-size:var(--text-sm); color:var(--text-secondary); max-width:440px; margin:0 auto var(--space-4);">
              All pairs are flat. Autonomous models are screening current M1/M15 market structures against trained entry thresholds.
            </p>
            <a href="#/chart" class="btn btn-primary" style="display:inline-flex;">
              ${icons.chart("w-4 h-4")} <span>Open Candlestick Chart</span>
            </a>
          </div>
        ` : `
          <!-- MOBILE CARDS VIEW (<1024px) -->
          <div class="mobile-trades-list" style="display:flex; flex-direction:column; gap:var(--space-3);">
            ${positions.map((pos, idx) => {
              const sideClass = pos.side === "BUY" ? "badge-side-buy" : "badge-side-sell";
              const pnlClass = pos.pnl >= 0 ? "text-profit" : "text-loss";
              const pnlSign = pos.pnl >= 0 ? "+" : "";
              const pips = pos.pips || (pos.pnl * 10);
              const pctOfBal = s.balance > 0 ? (pos.pnl / s.balance) * 100 : 0;

              return `
                <div class="card" style="padding:var(--space-4);">
                  <!-- Card Header -->
                  <div style="display:flex; justify-content:space-between; align-items:flex-start; margin-bottom:var(--space-3);">
                    <div style="display:flex; align-items:center; gap:var(--space-3);">
                      ${pairAvatar(pos.symbol, 38)}
                      <div>
                        <div style="display:flex; align-items:center; gap:6px;">
                          <span style="font-weight:700; font-size:var(--text-base);">${pos.symbol}</span>
                          <span class="${sideClass}">${pos.side}</span>
                        </div>
                        <div style="font-size:var(--text-xs); color:var(--text-muted); margin-top:2px;">
                          <span class="tabular">${formatLots(pos.volume)}</span> &bull; <span style="color:var(--accent-primary); font-weight:600;">${pos.modelId}</span>
                        </div>
                      </div>
                    </div>

                    <!-- Money P/L + Pips -->
                    <div style="text-align:right;">
                      <div class="tabular ${pnlClass}" style="font-size:var(--text-lg); font-weight:700;">
                        ${pnlSign}${formatCurrency(pos.pnl)}
                      </div>
                      <div class="tabular" style="font-size:var(--text-xs); color:var(--text-muted);">
                        ${formatPips(pips)} (${pnlSign}${formatPercent(pctOfBal)})
                      </div>
                    </div>
                  </div>

                  <!-- Execution Levels (Entry, Current, SL, TP) -->
                  <div style="display:grid; grid-template-columns:repeat(4, 1fr); gap:6px; padding:10px 12px; background:var(--bg-surface-elevated); border-radius:var(--radius-sm); margin-bottom:var(--space-3); font-size:var(--text-xs);">
                    <div>
                      <div style="color:var(--text-muted);">Entry</div>
                      <div class="tabular" style="font-weight:600;">${pos.openPrice}</div>
                    </div>
                    <div>
                      <div style="color:var(--text-muted);">Current</div>
                      <div class="tabular" style="font-weight:600;">${pos.currentPrice}</div>
                    </div>
                    <div>
                      <div style="color:var(--loss);">SL</div>
                      <div class="tabular" style="font-weight:600;">${pos.sl > 0 ? pos.sl : "—"}</div>
                    </div>
                    <div>
                      <div style="color:var(--profit);">TP</div>
                      <div class="tabular" style="font-weight:600;">${pos.tp > 0 ? pos.tp : "—"}</div>
                    </div>
                  </div>

                  <!-- Model Reasoning Drawer Toggle -->
                  <details style="margin-bottom:var(--space-3); font-size:var(--text-xs);">
                    <summary style="cursor:pointer; color:var(--text-muted); font-weight:600; padding:2px 0;">
                      AI Model Hypothesis &bull; View Decision
                    </summary>
                    <div style="margin-top:6px; padding:8px 10px; background:var(--bg-subtle); border-radius:var(--radius-xs); line-height:1.4; color:var(--text-secondary);">
                      ${pos.reason}
                    </div>
                  </details>

                  <!-- Tactical Actions -->
                  <div style="display:flex; gap:var(--space-2); border-top:1px solid var(--border-subtle); padding-top:var(--space-3);">
                    <button class="btn btn-secondary btn-sm action-be-btn" data-ticket="${pos.ticket}" data-symbol="${pos.symbol}" data-entry="${pos.openPrice}" style="flex:1;">
                      BE Stop Loss
                    </button>
                    <button class="btn btn-secondary btn-sm action-close-half-btn" data-ticket="${pos.ticket}" data-symbol="${pos.symbol}" style="flex:1;">
                      Close Half
                    </button>
                    <button class="btn btn-danger btn-sm action-close-pos-btn" data-ticket="${pos.ticket}" data-symbol="${pos.symbol}" style="flex:1;">
                      Close
                    </button>
                  </div>
                </div>
              `;
            }).join("")}
          </div>
        `}
      </div>
    `;

    this.bindEvents();
  },

  bindEvents() {
    // Group-by buttons
    const symBtn = document.getElementById("group-sym-btn");
    const modelBtn = document.getElementById("group-model-btn");
    if (symBtn && modelBtn) {
      symBtn.addEventListener("click", () => {
        this.groupBy = "symbol";
        this.updateDom();
      });
      modelBtn.addEventListener("click", () => {
        this.groupBy = "model";
        this.updateDom();
      });
    }

    // Refresh button
    const refreshBtn = document.getElementById("btn-trades-refresh");
    if (refreshBtn) {
      refreshBtn.addEventListener("click", () => {
        sfxBusy(refreshBtn, async () => {
          await store.fetchSnapshot();
        }, { pending: "Refreshing positions...", ok: "Positions updated" });
      });
    }

    // Break-even SL button
    document.querySelectorAll(".action-be-btn").forEach(btn => {
      btn.addEventListener("click", () => {
        const sym = btn.getAttribute("data-symbol");
        const entry = btn.getAttribute("data-entry");

        showConfirmSheet({
          title: `Move SL to Break-Even (${sym})?`,
          description: `This adjusts the server-side Stop Loss directly to your entry price (${entry}), eliminating downside market risk.`,
          confirmText: "Lock Break-Even",
          confirmVariant: "primary",
          onConfirm: async () => {
            await api.overrideSession(sym, "pause", `Move SL to Break-Even at ${entry}`);
            await store.fetchSnapshot();
          }
        });
      });
    });

    // Close half position
    document.querySelectorAll(".action-close-half-btn").forEach(btn => {
      btn.addEventListener("click", () => {
        const sym = btn.getAttribute("data-symbol");
        showConfirmSheet({
          title: `Close 50% Volume on ${sym}?`,
          description: "This closes half of the current position lots to secure partial floating profit, letting the remainder run.",
          confirmText: "Close Half",
          confirmVariant: "primary",
          onConfirm: async () => {
            await api.overrideSession(sym, "pause", "Close half volume");
            await store.fetchSnapshot();
          }
        });
      });
    });

    // Close full position
    document.querySelectorAll(".action-close-pos-btn").forEach(btn => {
      btn.addEventListener("click", () => {
        const sym = btn.getAttribute("data-symbol");
        showConfirmSheet({
          title: `Close Position on ${sym}?`,
          description: "This closes this CFD market order immediately at the current market price.",
          confirmText: "Close Position",
          confirmVariant: "danger",
          onConfirm: async () => {
            await api.overrideSession(sym, "pause", "Immediate manual position close");
            await store.fetchSnapshot();
          }
        });
      });
    });
  }
};
