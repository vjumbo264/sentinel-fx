/**
 * SENTINEL-FX · Models (Trained Pairs) Page
 * Real models from /api/pairs. Zero fabricated models or invented thoughts.
 * Honest empty state when no models are installed.
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

export const modelsView = {
  pairsData: null,

  // F3: no store subscription — poll ticks never rebuild this page.
  async render(container) {
    this.container = container;

    try {
      this.pairsData = await api.getPairs();
    } catch (_) {
      this.pairsData = null;
    }

    this.updateDom();
  },

  updateDom() {
    if (!this.container) return;
    const s = store.state;
    const pairs = (this.pairsData && this.pairsData.pairs) || s.models || [];
    const packs = (this.pairsData && this.pairsData.packs) || [];
    const modelsList = (this.pairsData && this.pairsData.models) || [];
    const fwdList = (this.pairsData && this.pairsData.forward) || [];

    // Real installed models: pairs with pack_version > 0 or present in packs/models tables
    const installed = pairs.filter(p => (p.pack_version && p.pack_version > 0) || p.status === "installed" || p.status === "active");

    const activeCount = installed.filter(m => m.enabled).length;
    const poolShare = (activeCount > 0 && s.balance !== null) ? s.balance / activeCount : null;

    this.container.innerHTML = `
      <div style="display:flex; flex-direction:column; gap:var(--space-4);">

        <!-- HEADER SUMMARY -->
        <div class="card" style="display:flex; justify-content:space-between; align-items:center; flex-wrap:wrap; gap:var(--space-3);">
          <div>
            <h2 class="card-title">AUTONOMOUS TRADING MODELS</h2>
            <div style="font-size:var(--text-xs); color:var(--text-muted); margin-top:2px;">
              ${installed.length === 0 ? "No models installed in system" : `${activeCount} Active · ${poolShare !== null ? "Each allocated " + formatCurrency(poolShare) : "Pool awaiting runner balance"}`}
            </div>
          </div>

          <div style="display:flex; gap:var(--space-2);">
            <a href="#/train" class="btn btn-secondary btn-sm" style="text-decoration:none;">
              ${icons.train("w-4 h-4")} <span>Train Model</span>
            </a>
            <a href="#/upload" class="btn btn-secondary btn-sm" style="text-decoration:none;">
              ${icons.upload("w-4 h-4")} <span>Install Bundle</span>
            </a>
          </div>
        </div>

        <!-- EMPTY STATE OR MODEL CARDS -->
        ${installed.length === 0 ? `
          <div class="card" style="text-align:center; padding:var(--space-10) var(--space-4);">
            <div style="margin-bottom:var(--space-3); color:var(--text-muted);">${icons.models("w-12 h-12")}</div>
            <h3 style="font-family:var(--font-display); font-size:var(--text-lg); font-weight:700; margin-bottom:var(--space-1);">No Models Installed</h3>
            <p style="font-size:var(--text-sm); color:var(--text-secondary); max-width:460px; margin:0 auto var(--space-4);">
              No trained model bundles have been installed into the live MT5 engine yet. Generate playbooks on the Train desk or upload a verified .sfxmodel.zip bundle.
            </p>
            <div style="display:flex; justify-content:center; gap:var(--space-3);">
              <a href="#/train" class="btn btn-primary" style="text-decoration:none;">
                ${icons.train("w-4 h-4")} <span>Open Train Desk</span>
              </a>
              <a href="#/upload" class="btn btn-secondary" style="text-decoration:none;">
                ${icons.upload("w-4 h-4")} <span>Upload .sfxmodel.zip</span>
              </a>
            </div>
          </div>
        ` : `
          <div style="display:grid; grid-template-columns:repeat(auto-fit, minmax(320px, 1fr)); gap:var(--space-4);">
            ${installed.map(m => {
              const displayName = m.symbol.replace(/^frx/, "");
              const fwd = fwdList.find(f => f.symbol === m.symbol) || null;
              const fwdMetrics = fwd && fwd.metrics ? (typeof fwd.metrics === "string" ? JSON.parse(fwd.metrics) : fwd.metrics) : null;

              return `
                <div class="card" style="padding:var(--space-4); display:flex; flex-direction:column; gap:var(--space-3);">
                  <div style="display:flex; justify-content:space-between; align-items:flex-start;">
                    <div style="display:flex; align-items:center; gap:var(--space-3);">
                      ${pairAvatar(m.symbol, 40)}
                      <div>
                        <div style="display:flex; align-items:center; gap:6px;">
                          <span style="font-weight:700; font-size:var(--text-base);">${displayName}</span>
                          <span style="font-size:11px; padding:2px 6px; border-radius:var(--radius-xs); background:var(--bg-surface-elevated); font-family:var(--font-mono);">
                            v${m.pack_version || 1}
                          </span>
                        </div>
                        <div style="font-size:var(--text-xs); color:var(--text-muted); margin-top:2px;">
                          Verdict: ${m.verdict || "untested"} · Status: ${m.status || "ready"}
                        </div>
                      </div>
                    </div>

                    <label class="toggle-switch">
                      <input type="checkbox" class="model-toggle" data-sym="${m.symbol}" ${m.enabled ? "checked" : ""}>
                      <span class="toggle-slider"></span>
                    </label>
                  </div>

                  <div style="display:grid; grid-template-columns:repeat(3, 1fr); gap:6px; padding:10px 12px; background:var(--bg-surface-elevated); border-radius:var(--radius-sm); font-size:var(--text-xs);">
                    <div>
                      <div style="color:var(--text-muted);">Allocated Share</div>
                      <div class="tabular" style="font-weight:600; color:var(--accent-primary);">
                        ${m.enabled && poolShare !== null ? formatCurrency(poolShare) : "—"}
                      </div>
                    </div>
                    <div>
                      <div style="color:var(--text-muted);">Min Stake</div>
                      <div class="tabular" style="font-weight:600;">
                        ${m.min_stake || 0.35}
                      </div>
                    </div>
                    <div>
                      <div style="color:var(--text-muted);">Max Stake</div>
                      <div class="tabular" style="font-weight:600;">
                        ${m.max_stake || 10.0}
                      </div>
                    </div>
                  </div>

                  ${fwdMetrics ? `
                    <div style="border-top:1px solid var(--border-subtle); padding-top:var(--space-2); display:flex; justify-content:space-between; font-size:11px; color:var(--text-muted);">
                      <span>Fwd Sharpe: <b class="tabular" style="color:var(--text-primary);">${fwdMetrics.sharpe || "—"}</b></span>
                      <span>Win Rate: <b class="tabular" style="color:var(--text-primary);">${fwdMetrics.win_rate ? fwdMetrics.win_rate + "%" : "—"}</b></span>
                      <span>Max DD: <b class="tabular" style="color:var(--text-primary);">${fwdMetrics.drawdown ? fwdMetrics.drawdown + "%" : "—"}</b></span>
                    </div>
                  ` : `
                    <div style="border-top:1px solid var(--border-subtle); padding-top:var(--space-2); font-size:11px; color:var(--text-muted);">
                      Forward eval metrics: Pending daily simulation
                    </div>
                  `}
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
    document.querySelectorAll(".model-toggle").forEach(toggle => {
      toggle.addEventListener("change", (e) => {
        const sym = toggle.getAttribute("data-sym");
        const nextState = e.target.checked;

        showConfirmSheet({
          title: `${nextState ? "Enable" : "Disable"} ${sym}?`,
          description: nextState
            ? `Enabling will allocate an equal share of the active session pool to ${sym} and allow it to open new positions on MT5.`
            : `Disabling will stop ${sym} from opening new trades.`,
          confirmText: nextState ? "Enable Model" : "Disable Model",
          confirmVariant: nextState ? "primary" : "danger",
          onConfirm: async () => {
            await api.updatePair({ symbol: sym, enabled: nextState ? 1 : 0 });
            await store.fetchSnapshot(true);
            try { this.pairsData = await api.getPairs(); } catch (_) {}
            this.updateDom();
          }
        });
      });
    });
  }
};
