/**
 * SENTINEL-FX · Closed Trade History & Performance Journal
 * Metrics header, daily PnL performance bars, search & filters, CSV export.
 */

import { icons, pairAvatar } from "../icons.js";
import { store } from "../store.js";
import { api } from "../api.js";
import {
  formatCurrency,
  formatPercent,
  formatPips,
  formatLots,
  formatLagosDate,
  formatLagosTime,
  sfxBusy,
  showToast
} from "../ui.js";

export const historyView = {
  unsubscribe: null,
  searchQuery: "",
  filterOutcome: "all", // 'all' | 'win' | 'loss'
  filterSymbol: "all",

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
    let trades = s.history || [];

    // Fallback sample closed trades for demonstration if database has 0 historical entries
    if (trades.length === 0 && s.demoReviewMode) {
      trades = this.getSampleHistory();
    }

    // Filter trades
    const filtered = trades.filter((t) => {
      if (this.filterOutcome === "win" && (t.pnl || 0) <= 0) return false;
      if (this.filterOutcome === "loss" && (t.pnl || 0) >= 0) return false;
      if (this.filterSymbol !== "all" && t.pair !== this.filterSymbol) return false;
      if (this.searchQuery) {
        const q = this.searchQuery.toLowerCase();
        const sym = (t.pair || "").toLowerCase();
        const reason = (t.reason || "").toLowerCase();
        const ticket = String(t.contract_id || t.id || "");
        if (!sym.includes(q) && !reason.includes(q) && !ticket.includes(q)) return false;
      }
      return true;
    });

    // Summary calculations
    const totalTrades = trades.length;
    const wins = trades.filter(t => (t.pnl || 0) > 0);
    const losses = trades.filter(t => (t.pnl || 0) < 0);
    const winRate = totalTrades > 0 ? (wins.length / totalTrades) * 100 : 0;
    const netPnl = trades.reduce((acc, t) => acc + (t.pnl || 0), 0);
    const totalWinMoney = wins.reduce((acc, t) => acc + (t.pnl || 0), 0);
    const totalLossMoney = Math.abs(losses.reduce((acc, t) => acc + (t.pnl || 0), 0));
    const profitFactor = totalLossMoney > 0 ? (totalWinMoney / totalLossMoney) : (totalWinMoney > 0 ? 99 : 1.0);
    const avgWin = wins.length > 0 ? totalWinMoney / wins.length : 0;
    const avgLoss = losses.length > 0 ? totalLossMoney / losses.length : 0;

    const netSign = netPnl >= 0 ? "+" : "";
    const netClass = netPnl >= 0 ? "text-profit" : "text-loss";

    this.container.innerHTML = `
      <div style="display:flex; flex-direction:column; gap:var(--space-4);">

        <!-- HEADER & CSV EXPORT -->
        <div style="display:flex; justify-content:space-between; align-items:center; flex-wrap:wrap; gap:var(--space-3);">
          <div>
            <h2 class="card-title">TRADE AUDIT JOURNAL</h2>
            <div style="font-size:var(--text-xs); color:var(--text-muted); margin-top:2px;">
              Permanent execution history across all models
            </div>
          </div>

          <button id="btn-export-csv" class="btn btn-secondary btn-sm" aria-label="Export trade history to CSV">
            ${icons.download("w-4 h-4")} <span>Export CSV</span>
          </button>
        </div>

        <!-- STICKY SUMMARY METRICS CARD -->
        <section class="card" style="padding:var(--space-4);">
          <div style="display:grid; grid-template-columns:repeat(auto-fit, minmax(130px, 1fr)); gap:var(--space-3);">
            <div>
              <div style="font-size:var(--text-xs); color:var(--text-muted);">Net Realized P/L</div>
              <div class="tabular ${netClass}" style="font-size:var(--text-xl); font-weight:700;">
                ${netSign}${formatCurrency(netPnl)}
              </div>
            </div>

            <div>
              <div style="font-size:var(--text-xs); color:var(--text-muted);">Win Rate</div>
              <div class="tabular" style="font-size:var(--text-xl); font-weight:700;">
                ${winRate.toFixed(1)}% <span style="font-size:var(--text-xs); color:var(--text-muted); font-weight:400;">(${wins.length}/${totalTrades})</span>
              </div>
            </div>

            <div>
              <div style="font-size:var(--text-xs); color:var(--text-muted);">Profit Factor</div>
              <div class="tabular" style="font-size:var(--text-xl); font-weight:700; color:var(--accent-primary);">
                ${profitFactor.toFixed(2)}
              </div>
            </div>

            <div>
              <div style="font-size:var(--text-xs); color:var(--text-muted);">Avg Win / Loss</div>
              <div class="tabular" style="font-size:var(--text-sm); font-weight:600; margin-top:4px;">
                <span class="text-profit">+${formatCurrency(avgWin)}</span> / <span class="text-loss">-${formatCurrency(avgLoss)}</span>
              </div>
            </div>
          </div>
        </section>

        <!-- SEARCH & FILTER BAR -->
        <div style="display:flex; gap:var(--space-2); flex-wrap:wrap; align-items:center;">
          <input id="input-history-search" class="input" type="text" placeholder="Search pair, ticket, reason..." value="${this.searchQuery}" style="flex:1; min-width:180px;">

          <div style="display:inline-flex; background:var(--bg-surface-elevated); border-radius:var(--radius-sm); padding:2px;">
            <button id="filter-all-btn" class="btn btn-sm ${this.filterOutcome === "all" ? "btn-secondary" : "btn-ghost"}" style="min-height:36px; padding:0 10px;">All</button>
            <button id="filter-win-btn" class="btn btn-sm ${this.filterOutcome === "win" ? "btn-secondary" : "btn-ghost"}" style="min-height:36px; padding:0 10px; color:var(--profit);">Wins</button>
            <button id="filter-loss-btn" class="btn btn-sm ${this.filterOutcome === "loss" ? "btn-secondary" : "btn-ghost"}" style="min-height:36px; padding:0 10px; color:var(--loss);">Losses</button>
          </div>
        </div>

        <!-- JOURNAL ENTRIES -->
        ${filtered.length === 0 ? `
          <div class="card" style="text-align:center; padding:var(--space-8) var(--space-4);">
            <div style="color:var(--text-muted); margin-bottom:var(--space-2);">${icons.history("w-8 h-8")}</div>
            <div style="font-weight:600; margin-bottom:4px;">No Closed Trades Found</div>
            <div style="font-size:var(--text-sm); color:var(--text-muted);">Completed orders will appear here with execution timestamps and P/L.</div>
          </div>
        ` : `
          <div style="display:flex; flex-direction:column; gap:var(--space-2);">
            ${filtered.map(t => {
              const pnl = Number(t.pnl || 0);
              const isWin = pnl > 0;
              const sign = pnl >= 0 ? "+" : "";
              const pnlColor = isWin ? "text-profit" : "text-loss";
              const sideBadge = (t.side || "BUY").toUpperCase() === "BUY" ? "badge-side-buy" : "badge-side-sell";
              const dateStr = t.close_utc ? formatLagosDate(t.close_utc) : "Today";
              const timeStr = t.close_utc ? formatLagosTime(t.close_utc) : "—";

              return `
                <div class="card" style="padding:12px 14px; display:flex; justify-content:space-between; align-items:center;">
                  <div style="display:flex; align-items:center; gap:var(--space-3);">
                    ${pairAvatar(t.pair, 34)}
                    <div>
                      <div style="display:flex; align-items:center; gap:6px;">
                        <span style="font-weight:700; font-size:var(--text-sm);">${t.pair}</span>
                        <span class="${sideBadge}">${t.side || "BUY"}</span>
                        <span style="font-size:11px; color:var(--text-muted);">${formatLots(t.stake)}</span>
                      </div>
                      <div style="font-size:var(--text-xs); color:var(--text-muted); margin-top:2px;">
                        <span>${dateStr} ${timeStr}</span> &bull; <span>${t.reason || "Autonomous exit"}</span>
                      </div>
                    </div>
                  </div>

                  <div style="text-align:right;">
                    <div class="tabular ${pnlColor}" style="font-weight:700; font-size:var(--text-base);">
                      ${sign}${formatCurrency(pnl)}
                    </div>
                    <div class="tabular" style="font-size:var(--text-xs); color:var(--text-muted);">
                      ${formatPips(pnl * 10)}
                    </div>
                  </div>
                </div>
              `;
            }).join("")}
          </div>
        `}

      </div>
    `;

    this.bindEvents(filtered);
  },

  bindEvents(currentList) {
    // Search input
    const searchInput = document.getElementById("input-history-search");
    if (searchInput) {
      searchInput.addEventListener("input", (e) => {
        this.searchQuery = e.target.value;
        this.updateDom();
      });
    }

    // Outcome filters
    const filterAll = document.getElementById("filter-all-btn");
    const filterWin = document.getElementById("filter-win-btn");
    const filterLoss = document.getElementById("filter-loss-btn");

    if (filterAll) filterAll.addEventListener("click", () => { this.filterOutcome = "all"; this.updateDom(); });
    if (filterWin) filterWin.addEventListener("click", () => { this.filterOutcome = "win"; this.updateDom(); });
    if (filterLoss) filterLoss.addEventListener("click", () => { this.filterOutcome = "loss"; this.updateDom(); });

    // CSV Export button
    const exportBtn = document.getElementById("btn-export-csv");
    if (exportBtn) {
      exportBtn.addEventListener("click", () => {
        sfxBusy(exportBtn, async () => {
          this.downloadCsv(currentList);
        }, { pending: "Preparing CSV...", ok: "CSV downloaded" });
      });
    }
  },

  downloadCsv(trades) {
    const headers = ["Ticket", "Symbol", "Side", "Lots", "PnL", "Open_UTC", "Close_UTC", "Reason"];
    const rows = trades.map(t => [
      t.contract_id || t.id || "",
      t.pair || "",
      t.side || "BUY",
      t.stake || 0.01,
      t.pnl || 0,
      t.open_utc || "",
      t.close_utc || "",
      `"${(t.reason || "").replace(/"/g, '""')}"`
    ]);

    const csvContent = [headers.join(","), ...rows.map(r => r.join(","))].join("\n");
    const blob = new Blob([csvContent], { type: "text/csv;charset=utf-8;" });
    const url = URL.createObjectURL(blob);
    const link = document.createElement("a");
    link.setAttribute("href", url);
    link.setAttribute("download", `sentinel_trades_${new Date().toISOString().slice(0,10)}.csv`);
    document.body.appendChild(link);
    link.click();
    document.body.removeChild(link);
  },

  getSampleHistory() {
    return [
      { id: 9011, contract_id: "T-9011", pair: "frxEURUSD", side: "BUY", stake: 0.15, pnl: 34.20, open_utc: "2026-10-10T12:00:00Z", close_utc: "2026-10-10T13:45:00Z", reason: "Target TP reached at 1.08750" },
      { id: 9010, contract_id: "T-9010", pair: "frxGBPJPY", side: "SELL", stake: 0.10, pnl: 48.50, open_utc: "2026-10-10T09:15:00Z", close_utc: "2026-10-10T11:20:00Z", reason: "Trend exhaustion + trailing stop" },
      { id: 9009, contract_id: "T-9009", pair: "frxUSDJPY", side: "BUY", stake: 0.10, pnl: -12.40, open_utc: "2026-10-10T06:30:00Z", close_utc: "2026-10-10T07:10:00Z", reason: "Server Stop Loss triggered cleanly" },
      { id: 9008, contract_id: "T-9008", pair: "frxEURUSD", side: "BUY", stake: 0.20, pnl: 52.10, open_utc: "2026-10-09T14:00:00Z", close_utc: "2026-10-09T16:30:00Z", reason: "Breakout continuation target achieved" }
    ];
  }
};
