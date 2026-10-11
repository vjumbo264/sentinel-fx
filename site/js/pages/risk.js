/**
 * SENTINEL-FX · Risk & Auth Management Desk
 * Session balance pool (owner-set), daily TP/SL with repeat-daily,
 * owner overrides (each individually toggled, default OFF),
 * MT5 credential verification, and emergency kill switch.
 *
 * F2: the owner can now set the session balance pool — validated 2-decimal
 *     amount, never above the available balance in the current mode, with a
 *     "Use full balance" shortcut and a percent slider, live equal-split
 *     preview, and shared pending/result feedback. Persisted through the real
 *     /api/session/allocate + /api/settings endpoints; saved values shown on
 *     reload. The bot reads them via /api/bot/session.
 * F3: no store subscription — poll ticks never rebuild this page.
 */

import { icons } from "../icons.js";
import { store } from "../store.js";
import { api } from "../api.js";
import {
  formatCurrency,
  sfxBusy,
  showToast,
  showConfirmSheet
} from "../ui.js";

function num(id, fallback = null) {
  const el = document.getElementById(id);
  if (!el) return fallback;
  const v = parseFloat(el.value);
  return isNaN(v) ? fallback : v;
}

export const riskView = {
  async render(container) {
    this.container = container;
    this.updateDom();
  },

  updateDom() {
    if (!this.container) return;
    const s = store.state;
    const st = s.settings || {};

    const enabledModels = s.models.filter(m => m.enabled);
    const enabledCount = enabledModels.length;
    const available = s.balance; // real balance for the current mode, or null

    // Saved values (persisted)
    const savedPool = s.session && s.session.starting_balance != null
      ? Number(s.session.starting_balance)
      : (st.session_pool != null ? Number(st.session_pool) : null);

    const dailyTpOn = !!st.daily_tp_enabled;
    const dailySlOn = !!st.daily_sl_enabled;
    const dailyTp = st.daily_target_usd != null ? Number(st.daily_target_usd) : 250;
    const dailySl = st.daily_loss_cap_usd != null ? Number(st.daily_loss_cap_usd) : 150;
    const repeatDaily = st.repeat_daily !== false && st.repeat_daily !== 0;

    const ovLotOn = !!st.ov_max_lot_enabled;
    const ovLot = st.ov_max_lot != null ? Number(st.ov_max_lot) : 0.5;
    const ovTpOn = !!st.ov_tp_enabled;
    const ovTp = st.ov_tp_usd != null ? Number(st.ov_tp_usd) : 100;
    const ovSlOn = !!st.ov_sl_enabled;
    const ovSl = st.ov_sl_usd != null ? Number(st.ov_sl_usd) : 50;

    const inputVal = savedPool !== null ? savedPool.toFixed(2) : (available !== null ? available.toFixed(2) : "");

    this.container.innerHTML = `
      <div style="display:flex; flex-direction:column; gap:var(--space-5);">

        <div>
          <h2 class="card-title">RISK GOVERNANCE &amp; CREDENTIALS</h2>
          <p style="font-size:var(--text-sm); color:var(--text-secondary); margin-top:2px;">
            Enforce capital allocation rules and account protections outside model decisions.
          </p>
        </div>

        <!-- 1. SESSION BALANCE POOL (F2) -->
        <section class="card" style="padding:var(--space-4);">
          <div class="card-header">
            <span class="card-title">SESSION BALANCE POOL</span>
            <span class="mode-pill ${s.mode}">${s.mode.toUpperCase()}</span>
          </div>

          <div style="display:flex; justify-content:space-between; font-size:var(--text-sm); margin-bottom:var(--space-3);">
            <span style="color:var(--text-muted);">Available ${s.mode} balance</span>
            <span class="tabular" style="font-weight:700;" id="risk-available">
              ${available !== null && available !== undefined ? formatCurrency(available) : "No runner data yet"}
            </span>
          </div>

          <label style="font-size:var(--text-xs); color:var(--text-muted); display:block; margin-bottom:6px;">Pool amount (USD, 2 decimals)</label>
          <div style="display:flex; gap:var(--space-2); margin-bottom:var(--space-3); flex-wrap:wrap;">
            <input id="input-pool-amount" class="input tabular" type="number" inputmode="decimal" step="0.01" min="0" value="${inputVal}" style="flex:1; min-width:140px;" ${available === null ? "disabled" : ""}>
            <button id="btn-pool-full" class="btn btn-secondary btn-sm" style="min-height:38px;" ${available === null ? "disabled" : ""}>Use full balance</button>
          </div>

          <label style="font-size:var(--text-xs); color:var(--text-muted); display:block; margin-bottom:6px;">Percent of available balance: <span id="pool-pct-label" class="tabular" style="color:var(--text-primary); font-weight:600;"></span></label>
          <input id="input-pool-pct" type="range" min="0" max="100" step="1" value="100" style="width:100%; accent-color:var(--accent-primary); margin-bottom:var(--space-3);" ${available === null ? "disabled" : ""}>

          <div id="pool-validation" style="font-size:var(--text-xs); color:var(--loss); min-height:16px; margin-bottom:var(--space-2);"></div>

          <div style="display:grid; grid-template-columns:repeat(auto-fit, minmax(150px, 1fr)); gap:var(--space-3); margin-bottom:var(--space-4); padding:10px 12px; background:var(--bg-surface-elevated); border-radius:var(--radius-sm);">
            <div>
              <div style="font-size:var(--text-xs); color:var(--text-muted);">Pool</div>
              <div id="pool-preview-total" class="tabular" style="font-size:var(--text-lg); font-weight:700;">—</div>
            </div>
            <div>
              <div style="font-size:var(--text-xs); color:var(--text-muted);">Enabled Models</div>
              <div class="tabular" style="font-size:var(--text-lg); font-weight:700;">${enabledCount}</div>
            </div>
            <div>
              <div style="font-size:var(--text-xs); color:var(--text-muted);">Equal Split / Model</div>
              <div id="pool-preview-share" class="tabular" style="font-size:var(--text-lg); font-weight:700; color:var(--accent-primary);">—</div>
            </div>
          </div>

          <button id="btn-save-pool" class="btn btn-primary" style="min-height:44px; width:100%;" ${available === null || enabledCount === 0 ? "disabled" : ""}>
            ${icons.check("w-4 h-4")} <span>Save Pool &amp; Allocate Evenly</span>
          </button>
          ${enabledCount === 0 ? `<div style="font-size:var(--text-xs); color:var(--text-muted); margin-top:6px;">Enable at least one model on the Models page before allocating.</div>` : ""}
        </section>

        <!-- 2. DAILY TP / SL CIRCUIT BREAKERS -->
        <section class="card" style="padding:var(--space-4);">
          <div class="card-header">
            <span class="card-title">DAILY CIRCUIT BREAKERS (LAGOS MIDNIGHT 00:00)</span>
            <span style="font-size:11px; color:var(--text-muted);">Enforced by Supervisor</span>
          </div>

          <div style="display:flex; flex-direction:column; gap:var(--space-3); margin-bottom:var(--space-3);">
            <div style="display:flex; justify-content:space-between; align-items:center; gap:var(--space-3); padding:10px 12px; background:var(--bg-surface-elevated); border-radius:var(--radius-sm);">
              <div style="flex:1; min-width:0;">
                <div style="font-weight:600; font-size:var(--text-sm);">Daily Take Profit</div>
                <div style="font-size:var(--text-xs); color:var(--text-muted);">Stop opening new trades once today's realized P/L reaches this target.</div>
              </div>
              <input id="input-daily-tp" class="input tabular" type="number" step="0.01" min="0" value="${dailyTp.toFixed(2)}" style="width:110px;" ${dailyTpOn ? "" : "disabled"}>
              <label class="toggle-switch">
                <input type="checkbox" id="toggle-daily-tp" ${dailyTpOn ? "checked" : ""}>
                <span class="toggle-slider"></span>
              </label>
            </div>

            <div style="display:flex; justify-content:space-between; align-items:center; gap:var(--space-3); padding:10px 12px; background:var(--bg-surface-elevated); border-radius:var(--radius-sm);">
              <div style="flex:1; min-width:0;">
                <div style="font-weight:600; font-size:var(--text-sm);">Daily Stop Loss</div>
                <div style="font-size:var(--text-xs); color:var(--text-muted);">Halt new trades when today's realized loss hits this cap.</div>
              </div>
              <input id="input-daily-sl" class="input tabular" type="number" step="0.01" min="0" value="${dailySl.toFixed(2)}" style="width:110px;" ${dailySlOn ? "" : "disabled"}>
              <label class="toggle-switch">
                <input type="checkbox" id="toggle-daily-sl" ${dailySlOn ? "checked" : ""}>
                <span class="toggle-slider"></span>
              </label>
            </div>

            <div style="display:flex; justify-content:space-between; align-items:center; padding:10px 12px; background:var(--bg-surface-elevated); border-radius:var(--radius-sm);">
              <div>
                <div style="font-weight:600; font-size:var(--text-sm);">Repeat Daily Automatically</div>
                <div style="font-size:var(--text-xs); color:var(--text-muted);">Counters reset every midnight in Lagos (UTC+1); limits re-arm.</div>
              </div>
              <label class="toggle-switch">
                <input type="checkbox" id="toggle-repeat-daily" ${repeatDaily ? "checked" : ""}>
                <span class="toggle-slider"></span>
              </label>
            </div>
          </div>

          <button id="btn-save-daily-limits" class="btn btn-primary btn-sm" style="min-height:38px;">
            Save Daily Thresholds
          </button>
        </section>

        <!-- 3. OWNER OVERRIDES (each toggleable, default OFF) -->
        <section class="card" style="padding:var(--space-4);">
          <div class="card-header">
            <span class="card-title">OWNER OVERRIDES (ENFORCED EXTERNALLY)</span>
          </div>

          <div style="display:flex; flex-direction:column; gap:var(--space-3); margin-bottom:var(--space-3);">
            <div style="display:flex; justify-content:space-between; align-items:center; gap:var(--space-3); padding:10px 12px; background:var(--bg-surface-elevated); border-radius:var(--radius-sm);">
              <div style="flex:1; min-width:0;">
                <div style="font-weight:600; font-size:var(--text-sm);">Max Exposure / Lot Clamp</div>
                <div style="font-size:var(--text-xs); color:var(--text-muted);">Clamps any single order volume regardless of model output.</div>
              </div>
              <input id="input-ov-lot" class="input tabular" type="number" step="0.01" min="0.01" value="${ovLot.toFixed(2)}" style="width:100px;" ${ovLotOn ? "" : "disabled"}>
              <label class="toggle-switch">
                <input type="checkbox" id="toggle-ov-lot" ${ovLotOn ? "checked" : ""}>
                <span class="toggle-slider"></span>
              </label>
            </div>

            <div style="display:flex; justify-content:space-between; align-items:center; gap:var(--space-3); padding:10px 12px; background:var(--bg-surface-elevated); border-radius:var(--radius-sm);">
              <div style="flex:1; min-width:0;">
                <div style="font-weight:600; font-size:var(--text-sm);">Owner Take Profit ($)</div>
                <div style="font-size:var(--text-xs); color:var(--text-muted);">Supervisor takes profit session-wide at this level.</div>
              </div>
              <input id="input-ov-tp" class="input tabular" type="number" step="0.01" min="0" value="${ovTp.toFixed(2)}" style="width:100px;" ${ovTpOn ? "" : "disabled"}>
              <label class="toggle-switch">
                <input type="checkbox" id="toggle-ov-tp" ${ovTpOn ? "checked" : ""}>
                <span class="toggle-slider"></span>
              </label>
            </div>

            <div style="display:flex; justify-content:space-between; align-items:center; gap:var(--space-3); padding:10px 12px; background:var(--bg-surface-elevated); border-radius:var(--radius-sm);">
              <div style="flex:1; min-width:0;">
                <div style="font-weight:600; font-size:var(--text-sm);">Owner Stop Loss ($)</div>
                <div style="font-size:var(--text-xs); color:var(--text-muted);">Supervisor flattens exposure if session drawdown hits this level.</div>
              </div>
              <input id="input-ov-sl" class="input tabular" type="number" step="0.01" min="0" value="${ovSl.toFixed(2)}" style="width:100px;" ${ovSlOn ? "" : "disabled"}>
              <label class="toggle-switch">
                <input type="checkbox" id="toggle-ov-sl" ${ovSlOn ? "checked" : ""}>
                <span class="toggle-slider"></span>
              </label>
            </div>
          </div>

          <button id="btn-save-overrides" class="btn btn-primary btn-sm" style="min-height:38px;">
            Save Owner Overrides
          </button>
        </section>

        <!-- 4. MT5 CONNECTIVITY -->
        <section class="card" style="padding:var(--space-4);">
          <div class="card-header">
            <span class="card-title">MT5 BROKER CONNECTIVITY</span>
            ${s.runnerActive
              ? `<span class="badge-profit" style="font-size:11px;">${icons.check("w-3 h-3")} CONNECTED</span>`
              : `<span style="font-size:11px; color:var(--text-muted);">No runner heartbeat</span>`}
          </div>

          <div style="display:flex; flex-direction:column; gap:var(--space-2); margin-bottom:var(--space-4); font-size:var(--text-sm);">
            <div style="display:flex; justify-content:space-between; padding:8px 0; border-bottom:1px solid var(--border-subtle);">
              <span style="color:var(--text-muted);">Broker Server</span>
              <span class="tabular">${s.runnerActive ? "Deriv MT5" : "—"}</span>
            </div>
            <div style="display:flex; justify-content:space-between; padding:8px 0; border-bottom:1px solid var(--border-subtle);">
              <span style="color:var(--text-muted);">MT5 Login ID</span>
              <span class="tabular">${s.heartbeat?.loginid ? s.heartbeat.loginid : "—"}</span>
            </div>
            <div style="display:flex; justify-content:space-between; padding:8px 0;">
              <span style="color:var(--text-muted);">Last Heartbeat</span>
              <span class="tabular">${s.heartbeat?.ts ? new Date(s.heartbeat.ts).toISOString().slice(11, 19) + " UTC" : "—"}</span>
            </div>
          </div>

          <button id="btn-test-mt5" class="btn btn-secondary btn-sm" style="min-height:38px;">
            ${icons.refresh("w-4 h-4")} <span>Dispatch MT5 Spike Test</span>
          </button>
        </section>

        <!-- MODE MANAGEMENT -->
        <section class="card" style="padding:var(--space-4);">
          <div class="card-header">
            <span class="card-title">TRADING ENVIRONMENT</span>
            <span class="mode-pill ${s.mode}">${s.mode.toUpperCase()}</span>
          </div>
          <div style="display:flex; justify-content:space-between; align-items:center; padding:10px 12px; background:var(--bg-surface-elevated); border-radius:var(--radius-sm); gap:var(--space-2); flex-wrap:wrap;">
            <div>
              <div style="font-weight:600; font-size:var(--text-sm);">Current Mode: ${s.mode === "real" ? "REAL Capital" : "DEMO Risk-Free"}</div>
              <div style="font-size:var(--text-xs); color:var(--text-muted);">Switch between paper execution and live MT5 capital.</div>
            </div>
            <button id="btn-risk-mode-switch" class="btn ${s.mode === "real" ? "btn-secondary" : "btn-primary"} btn-sm">
              Switch to ${s.mode === "real" ? "DEMO" : "REAL"}
            </button>
          </div>
        </section>

        <!-- 5. DANGER ZONE -->
        <section class="card" style="padding:var(--space-5); border-color:var(--loss-border); background:var(--loss-subtle);">
          <div style="display:flex; align-items:center; gap:var(--space-2); color:var(--loss); margin-bottom:var(--space-2);">
            ${icons.kill("w-6 h-6")}
            <h3 style="font-family:var(--font-display); font-weight:700; font-size:var(--text-base);">EMERGENCY KILL SWITCH</h3>
          </div>
          <p style="font-size:var(--text-sm); color:var(--text-primary); margin-bottom:var(--space-4); line-height:1.5;">
            Immediately revokes the active runner execution lease, closes all market orders across every currency pair, and freezes all bot dispatch cycles.
          </p>

          <button id="btn-emergency-kill" class="btn btn-danger" style="width:100%; min-height:48px; font-weight:700;">
            ${icons.kill("w-5 h-5")} <span>HALT ALL TRADING &amp; REVOKE LEASE</span>
          </button>
        </section>

      </div>
    `;

    this.bindEvents();
    this.refreshPoolPreview();
  },

  refreshPoolPreview() {
    const s = store.state;
    const available = s.balance;
    const enabledCount = s.models.filter(m => m.enabled).length;
    const amountEl = document.getElementById("input-pool-amount");
    const pctEl = document.getElementById("input-pool-pct");
    const pctLabel = document.getElementById("pool-pct-label");
    const totalEl = document.getElementById("pool-preview-total");
    const shareEl = document.getElementById("pool-preview-share");
    const valEl = document.getElementById("pool-validation");
    const saveBtn = document.getElementById("btn-save-pool");
    if (!amountEl || !totalEl) return;

    let val = parseFloat(amountEl.value);
    let msg = "";
    if (isNaN(val) || val <= 0) {
      val = null;
      msg = "Enter an amount greater than 0.";
    } else if (available !== null && val > available + 0.001) {
      msg = `Pool cannot exceed the available ${s.mode} balance (${formatCurrency(available)}).`;
    } else if (!/^\d+(\.\d{1,2})?$/.test(amountEl.value.trim())) {
      msg = "Use at most 2 decimal places.";
    }

    if (valEl) valEl.textContent = msg;
    if (totalEl) totalEl.textContent = val !== null && !msg ? formatCurrency(val) : "—";
    if (shareEl) shareEl.textContent = val !== null && !msg && enabledCount > 0 ? formatCurrency(Math.floor((val / enabledCount) * 100) / 100) : "—";
    if (pctLabel && available) pctLabel.textContent = val !== null ? `${Math.min(100, Math.round((val / available) * 100))}%` : "—";
    if (saveBtn) saveBtn.disabled = !!msg || val === null || enabledCount === 0 || available === null;
  },

  bindEvents() {
    const s = store.state;

    // ---- Pool controls
    const amountEl = document.getElementById("input-pool-amount");
    const pctEl = document.getElementById("input-pool-pct");
    const fullBtn = document.getElementById("btn-pool-full");

    if (amountEl) amountEl.addEventListener("input", () => this.refreshPoolPreview());
    if (pctEl) pctEl.addEventListener("input", () => {
      if (s.balance !== null && amountEl) {
        amountEl.value = ((s.balance * Number(pctEl.value)) / 100).toFixed(2);
      }
      this.refreshPoolPreview();
    });
    if (fullBtn) fullBtn.addEventListener("click", () => {
      if (s.balance !== null && amountEl) {
        amountEl.value = Number(s.balance).toFixed(2);
        if (pctEl) pctEl.value = 100;
      }
      this.refreshPoolPreview();
    });

    const savePoolBtn = document.getElementById("btn-save-pool");
    if (savePoolBtn) {
      savePoolBtn.addEventListener("click", () => {
        const val = parseFloat(amountEl.value);
        sfxBusy(savePoolBtn, async () => {
          await api.allocateSession(Number(val.toFixed(2)), store.state.mode);
          await api.saveSettings({ session_pool: Number(val.toFixed(2)), session_pool_mode: store.state.mode });
          await store.fetchSnapshot(true);
          this.updateDom();
        }, { pending: "Allocating pool...", ok: `Session pool of ${formatCurrency(val)} split evenly across enabled models` }).catch(() => {});
      });
    }

    // ---- Daily breakers: toggle enables its input; save persists real settings
    const wireToggle = (toggleId, inputId) => {
      const t = document.getElementById(toggleId);
      const i = document.getElementById(inputId);
      if (t && i) t.addEventListener("change", () => { i.disabled = !t.checked; });
    };
    wireToggle("toggle-daily-tp", "input-daily-tp");
    wireToggle("toggle-daily-sl", "input-daily-sl");
    wireToggle("toggle-ov-lot", "input-ov-lot");
    wireToggle("toggle-ov-tp", "input-ov-tp");
    wireToggle("toggle-ov-sl", "input-ov-sl");

    const saveLimitsBtn = document.getElementById("btn-save-daily-limits");
    if (saveLimitsBtn) {
      saveLimitsBtn.addEventListener("click", () => {
        const tpOn = document.getElementById("toggle-daily-tp")?.checked;
        const slOn = document.getElementById("toggle-daily-sl")?.checked;
        const tp = num("input-daily-tp", 250);
        const sl = num("input-daily-sl", 150);
        const repeat = document.getElementById("toggle-repeat-daily")?.checked;

        sfxBusy(saveLimitsBtn, async () => {
          await api.saveSettings({
            daily_tp_enabled: !!tpOn,
            daily_target_usd: Number(tp),
            daily_sl_enabled: !!slOn,
            daily_loss_cap_usd: Number(sl),
            repeat_daily: !!repeat
          });
          await store.fetchSnapshot(true);
        }, { pending: "Saving limits...", ok: "Daily risk rules saved" }).catch(() => {});
      });
    }

    const saveOvBtn = document.getElementById("btn-save-overrides");
    if (saveOvBtn) {
      saveOvBtn.addEventListener("click", () => {
        sfxBusy(saveOvBtn, async () => {
          await api.saveSettings({
            ov_max_lot_enabled: !!document.getElementById("toggle-ov-lot")?.checked,
            ov_max_lot: num("input-ov-lot", 0.5),
            ov_tp_enabled: !!document.getElementById("toggle-ov-tp")?.checked,
            ov_tp_usd: num("input-ov-tp", 100),
            ov_sl_enabled: !!document.getElementById("toggle-ov-sl")?.checked,
            ov_sl_usd: num("input-ov-sl", 50)
          });
          await store.fetchSnapshot(true);
          showToast("Owner overrides saved", "success");
        }, { pending: "Saving overrides...", ok: "Owner overrides saved" }).catch(() => {});
      });
    }

    // ---- Mode switch
    const modeSwitchBtn = document.getElementById("btn-risk-mode-switch");
    if (modeSwitchBtn) {
      modeSwitchBtn.addEventListener("click", () => {
        const nextMode = store.state.mode === "demo" ? "real" : "demo";
        showConfirmSheet({
          title: `Switch to ${nextMode.toUpperCase()} mode?`,
          description: nextMode === "real"
            ? "WARNING: Real mode executes live trades on your connected MT5 real account. Verify risk parameters before proceeding."
            : "Switches execution back to demo risk-free environment.",
          confirmText: `Switch to ${nextMode.toUpperCase()}`,
          confirmVariant: nextMode === "real" ? "danger" : "primary",
          onConfirm: async () => {
            await api.saveSettings({ mode: nextMode });
            store.state.mode = nextMode;
            store.notify();
            this.updateDom();
          }
        });
      });
    }

    // ---- MT5 spike test
    const testMt5Btn = document.getElementById("btn-test-mt5");
    if (testMt5Btn) {
      testMt5Btn.addEventListener("click", () => {
        sfxBusy(testMt5Btn, async () => {
          await api.dispatchWorkflow("mt5-spike.yml");
        }, { pending: "Dispatching MT5 spike...", ok: "MT5 spike dispatched — see Actions for the probe result" }).catch(() => {});
      });
    }

    // ---- Kill switch
    const killBtn = document.getElementById("btn-emergency-kill");
    if (killBtn) {
      killBtn.addEventListener("click", () => {
        showConfirmSheet({
          title: "ACTIVATE EMERGENCY KILL SWITCH?",
          description: "This will instantly halt all trading, revoke the runner lock in D1, and emergency close all open CFD positions.",
          confirmText: "EXECUTE KILL SWITCH",
          confirmVariant: "danger",
          onConfirm: async () => {
            await api.overrideSession("*", "stop_all", "Emergency kill switch pressed by owner");
            await store.fetchSnapshot(true);
          }
        });
      });
    }
  }
};
