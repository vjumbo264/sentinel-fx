import { api } from '../api.js';
import { toast } from '../toast.js';

export async function riskPage() {
  const root = document.getElementById('page-container');
  if (!root) return;

  root.innerHTML = `<div style="text-align:center; padding:40px; color:var(--text-2);">Loading risk configuration...</div>`;

  let mode = 'demo';
  let overrides = {
    take_profit: { enabled: false, unit: 'money', value: null },
    stop_loss: { enabled: false, unit: 'money', value: null },
    daily_profit_target: { enabled: false, unit: 'money', value: null, close_open_on_hit: false },
    daily_loss_limit: { enabled: false, unit: 'money', value: null, close_open_on_hit: false },
    trade_weekends: false,
  };
  let riskStatus = { status: 'normal', today_pnl: 0, realized_pnl: 0, floating_pnl: 0 };
  let testDayKey = null;

  async function loadData() {
    try {
      const res = await api.getRiskOverrides(mode);
      if (res.overrides) overrides = { ...overrides, ...res.overrides };
      if (res.risk_status) riskStatus = res.risk_status;
      testDayKey = res.test_day_key;
      render();
    } catch(err) {
      toast(err.message || 'Error loading risk overrides', 'error');
    }
  }

  function render() {
    const isTargetHit = riskStatus.status === 'daily_target_reached';
    const isLimitHit = riskStatus.status === 'daily_limit_reached';
    const nowUtc = new Date();
    const utcString = nowUtc.toISOString().slice(11, 19) + ' UTC';
    const watString = new Date(nowUtc.getTime() + 3600000).toISOString().slice(11, 19) + ' WAT';

    root.innerHTML = `
      <div style="display:flex; justify-content:space-between; align-items:center; margin-bottom:16px; flex-wrap:wrap; gap:10px;">
        <div>
          <h2 style="font-size:18px; font-weight:700; color:var(--text);">Risk & Protection Overrides</h2>
          <div style="font-size:12px; color:var(--text-2); margin-top:2px;">
            Autonomous model risk parameters, independent profit targets, and protective circuit limits.
          </div>
        </div>
        <div style="display:flex; gap:8px;">
          <button id="mode-demo-btn" class="btn ${mode === 'demo' ? 'btn-primary' : 'btn-ghost'} btn-sm">Demo Account</button>
          <button id="mode-real-btn" class="btn ${mode === 'real' ? 'btn-primary' : 'btn-ghost'} btn-sm">Real Account</button>
        </div>
      </div>

      <!-- DAY BOUNDARY & STATUS BANNER -->
      <div class="card" style="border-left: 4px solid ${isTargetHit ? 'var(--profit)' : isLimitHit ? 'var(--loss)' : 'var(--accent)'}; margin-bottom:16px;">
        <div style="display:flex; justify-content:space-between; align-items:center; flex-wrap:wrap; gap:12px;">
          <div>
            <div style="font-size:11px; text-transform:uppercase; letter-spacing:0.5px; color:var(--text-3); font-weight:600;">
              UTC Trading Day Boundary
            </div>
            <div style="font-size:14px; font-weight:700; color:var(--text); margin-top:2px;">
              Resets Daily at 00:00:00 UTC
            </div>
            <div style="font-size:12px; color:var(--text-2); margin-top:2px;">
              Current: <span class="tabular font-mono" style="color:var(--text);">${utcString}</span> · Lagos: <span class="tabular font-mono" style="color:var(--text);">${watString}</span>
              ${testDayKey ? ` · <span class="badge badge-warning">Simulated Date: ${testDayKey}</span>` : ''}
            </div>
          </div>
          <div style="display:flex; align-items:center; gap:8px;">
            <span class="badge ${isTargetHit ? 'badge-profit' : isLimitHit ? 'badge-loss' : 'badge-muted'}" style="font-size:12px; padding:6px 10px;">
              Status: ${isTargetHit ? 'Daily Target Reached 🎯' : isLimitHit ? 'Daily Limit Reached 🛑' : 'Normal Trading Active'}
            </span>
            ${(isTargetHit || isLimitHit) ? `
              <button id="clear-limit-btn" class="btn btn-ghost btn-sm" style="font-size:11px;">Clear State</button>
            ` : ''}
          </div>
        </div>

        <div style="display:grid; grid-template-columns:repeat(auto-fit, minmax(140px, 1fr)); gap:10px; margin-top:14px; padding-top:12px; border-top:1px solid var(--border);">
          <div style="background:var(--bg-input); padding:10px; border-radius:var(--radius);">
            <div style="font-size:11px; color:var(--text-3);">Day Realized PnL</div>
            <div class="tabular" style="font-size:14px; font-weight:700; color:${(riskStatus.realized_pnl || 0) >= 0 ? 'var(--profit)' : 'var(--loss)'}; margin-top:2px;">
              ${(riskStatus.realized_pnl || 0) >= 0 ? '+' : ''}$${Number(riskStatus.realized_pnl || 0).toFixed(2)}
            </div>
          </div>
          <div style="background:var(--bg-input); padding:10px; border-radius:var(--radius);">
            <div style="font-size:11px; color:var(--text-3);">Floating Open PnL</div>
            <div class="tabular" style="font-size:14px; font-weight:700; color:${(riskStatus.floating_pnl || 0) >= 0 ? 'var(--profit)' : 'var(--loss)'}; margin-top:2px;">
              ${(riskStatus.floating_pnl || 0) >= 0 ? '+' : ''}$${Number(riskStatus.floating_pnl || 0).toFixed(2)}
            </div>
          </div>
          <div style="background:var(--bg-input); padding:10px; border-radius:var(--radius);">
            <div style="font-size:11px; color:var(--text-3);">Total Day PnL</div>
            <div class="tabular" style="font-size:14px; font-weight:700; color:${(riskStatus.today_pnl || 0) >= 0 ? 'var(--profit)' : 'var(--loss)'}; margin-top:2px;">
              ${(riskStatus.today_pnl || 0) >= 0 ? '+' : ''}$${Number(riskStatus.today_pnl || 0).toFixed(2)}
            </div>
          </div>
        </div>
      </div>

      <!-- THE 4 INDEPENDENT OPTIONAL OVERRIDES -->
      <div style="display:flex; flex-direction:column; gap:16px;">

        <!-- 1. FIXED TAKE PROFIT -->
        <div class="card">
          <div class="card-header">
            <div>
              <div class="card-title">1. Fixed Take Profit (TP)</div>
              <div style="font-size:12px; color:var(--text-2); margin-top:2px;">
                When OFF: Model's own targets decide. When ON: Fixed TP overrides model targets for new & open positions.
              </div>
            </div>
            <label style="display:flex; align-items:center; gap:8px; cursor:pointer;">
              <span style="font-size:12px; font-weight:600; color:${overrides.take_profit?.enabled ? 'var(--profit)' : 'var(--text-3)'};">
                ${overrides.take_profit?.enabled ? 'ON' : 'OFF'}
              </span>
              <input type="checkbox" id="tp-enable" ${overrides.take_profit?.enabled ? 'checked' : ''} style="cursor:pointer;" />
            </label>
          </div>

          <div style="display:grid; grid-template-columns: 1fr 140px; gap:12px; max-width:480px; align-items:center;">
            <div>
              <label style="display:block; font-size:11px; color:var(--text-3); margin-bottom:4px;">Take Profit Target (Unset is valid)</label>
              <input
                id="tp-val"
                type="number"
                step="any"
                placeholder="Optional (e.g. 50 or 5.0)"
                value="${overrides.take_profit?.value ?? ''}"
                style="width:100%;"
              />
            </div>
            <div>
              <label style="display:block; font-size:11px; color:var(--text-3); margin-bottom:4px;">Units</label>
              <select id="tp-unit" style="width:100%;">
                <option value="money" ${overrides.take_profit?.unit === 'money' ? 'selected' : ''}>$ (Money)</option>
                <option value="pct" ${overrides.take_profit?.unit === 'pct' ? 'selected' : ''}>% (% Pool)</option>
              </select>
            </div>
          </div>
        </div>

        <!-- 2. FIXED STOP LOSS -->
        <div class="card">
          <div class="card-header">
            <div>
              <div class="card-title">2. Fixed Stop Loss (SL)</div>
              <div style="font-size:12px; color:var(--text-2); margin-top:2px;">
                When OFF: Model's learned stops decide (server-side protective stop is ALWAYS attached). When ON: Fixed SL overrides model stops.
              </div>
            </div>
            <label style="display:flex; align-items:center; gap:8px; cursor:pointer;">
              <span style="font-size:12px; font-weight:600; color:${overrides.stop_loss?.enabled ? 'var(--profit)' : 'var(--text-3)'};">
                ${overrides.stop_loss?.enabled ? 'ON' : 'OFF'}
              </span>
              <input type="checkbox" id="sl-enable" ${overrides.stop_loss?.enabled ? 'checked' : ''} style="cursor:pointer;" />
            </label>
          </div>

          <div style="display:grid; grid-template-columns: 1fr 140px; gap:12px; max-width:480px; align-items:center;">
            <div>
              <label style="display:block; font-size:11px; color:var(--text-3); margin-bottom:4px;">Stop Loss Limit (Unset is valid)</label>
              <input
                id="sl-val"
                type="number"
                step="any"
                placeholder="Optional (e.g. 30 or 3.0)"
                value="${overrides.stop_loss?.value ?? ''}"
                style="width:100%;"
              />
            </div>
            <div>
              <label style="display:block; font-size:11px; color:var(--text-3); margin-bottom:4px;">Units</label>
              <select id="sl-unit" style="width:100%;">
                <option value="money" ${overrides.stop_loss?.unit === 'money' ? 'selected' : ''}>$ (Money)</option>
                <option value="pct" ${overrides.stop_loss?.unit === 'pct' ? 'selected' : ''}>% (% Pool)</option>
              </select>
            </div>
          </div>
        </div>

        <!-- 3. DAILY PROFIT TARGET -->
        <div class="card">
          <div class="card-header">
            <div>
              <div class="card-title">3. Daily Profit Target</div>
              <div style="font-size:12px; color:var(--text-2); margin-top:2px;">
                Stops opening new trades once realized + floating daily PnL hits target. Resets at 00:00 UTC automatically.
              </div>
            </div>
            <label style="display:flex; align-items:center; gap:8px; cursor:pointer;">
              <span style="font-size:12px; font-weight:600; color:${overrides.daily_profit_target?.enabled ? 'var(--profit)' : 'var(--text-3)'};">
                ${overrides.daily_profit_target?.enabled ? 'ON' : 'OFF'}
              </span>
              <input type="checkbox" id="dpt-enable" ${overrides.daily_profit_target?.enabled ? 'checked' : ''} style="cursor:pointer;" />
            </label>
          </div>

          <div style="display:grid; grid-template-columns: 1fr 140px; gap:12px; max-width:480px; align-items:center; margin-bottom:12px;">
            <div>
              <label style="display:block; font-size:11px; color:var(--text-3); margin-bottom:4px;">Daily Target Value (Unset is valid)</label>
              <input
                id="dpt-val"
                type="number"
                step="any"
                placeholder="Optional (e.g. 100 or 2.0)"
                value="${overrides.daily_profit_target?.value ?? ''}"
                style="width:100%;"
              />
            </div>
            <div>
              <label style="display:block; font-size:11px; color:var(--text-3); margin-bottom:4px;">Units</label>
              <select id="dpt-unit" style="width:100%;">
                <option value="money" ${overrides.daily_profit_target?.unit === 'money' ? 'selected' : ''}>$ (Money)</option>
                <option value="pct" ${overrides.daily_profit_target?.unit === 'pct' ? 'selected' : ''}>% (% Pool)</option>
              </select>
            </div>
          </div>

          <label style="display:flex; align-items:center; gap:8px; font-size:12px; color:var(--text-2); cursor:pointer;">
            <input type="checkbox" id="dpt-close-open" ${overrides.daily_profit_target?.close_open_on_hit ? 'checked' : ''} />
            <span>Also close all open positions when daily profit target is reached (default: OFF, honors protective stops)</span>
          </label>
        </div>

        <!-- 4. DAILY LOSS LIMIT -->
        <div class="card">
          <div class="card-header">
            <div>
              <div class="card-title">4. Daily Loss Limit</div>
              <div style="font-size:12px; color:var(--text-2); margin-top:2px;">
                Circuit-breaker that halts new trades if realized + floating daily drawdown reaches limit. Resets at 00:00 UTC automatically.
              </div>
            </div>
            <label style="display:flex; align-items:center; gap:8px; cursor:pointer;">
              <span style="font-size:12px; font-weight:600; color:${overrides.daily_loss_limit?.enabled ? 'var(--profit)' : 'var(--text-3)'};">
                ${overrides.daily_loss_limit?.enabled ? 'ON' : 'OFF'}
              </span>
              <input type="checkbox" id="dll-enable" ${overrides.daily_loss_limit?.enabled ? 'checked' : ''} style="cursor:pointer;" />
            </label>
          </div>

          <div style="display:grid; grid-template-columns: 1fr 140px; gap:12px; max-width:480px; align-items:center; margin-bottom:12px;">
            <div>
              <label style="display:block; font-size:11px; color:var(--text-3); margin-bottom:4px;">Daily Loss Limit (Unset is valid)</label>
              <input
                id="dll-val"
                type="number"
                step="any"
                placeholder="Optional (e.g. 50 or 1.5)"
                value="${overrides.daily_loss_limit?.value ?? ''}"
                style="width:100%;"
              />
            </div>
            <div>
              <label style="display:block; font-size:11px; color:var(--text-3); margin-bottom:4px;">Units</label>
              <select id="dll-unit" style="width:100%;">
                <option value="money" ${overrides.daily_loss_limit?.unit === 'money' ? 'selected' : ''}>$ (Money)</option>
                <option value="pct" ${overrides.daily_loss_limit?.unit === 'pct' ? 'selected' : ''}>% (% Pool)</option>
              </select>
            </div>
          </div>

          <label style="display:flex; align-items:center; gap:8px; font-size:12px; color:var(--text-2); cursor:pointer;">
            <input type="checkbox" id="dll-close-open" ${overrides.daily_loss_limit?.close_open_on_hit ? 'checked' : ''} />
            <span>Also close all open positions when daily loss limit is hit (default: OFF, honors protective stops)</span>
          </label>
        </div>

        <!-- 5. WEEKEND TRADING SETTING (H5) -->
        <div class="card">
          <div class="card-header">
            <div>
              <div class="card-title">Trade on weekends (synthetic indices only trade 24/7)</div>
              <div style="font-size:12px; color:var(--text-2); margin-top:2px;">
                Forex markets close on weekends. Default OFF keeps forex idle when closed, while synthetic indices trade 24/7.
              </div>
            </div>
            <label style="display:flex; align-items:center; gap:8px; cursor:pointer;">
              <span style="font-size:12px; font-weight:600; color:${overrides.trade_weekends ? 'var(--profit)' : 'var(--text-3)'};">
                ${overrides.trade_weekends ? 'ON' : 'OFF'}
              </span>
              <input type="checkbox" id="weekend-enable" ${overrides.trade_weekends ? 'checked' : ''} style="cursor:pointer;" />
            </label>
          </div>
        </div>

        <!-- ACTION BUTTONS -->
        <div style="display:flex; justify-content:space-between; align-items:center; flex-wrap:wrap; gap:12px; padding:16px; background:var(--bg-card); border:1px solid var(--border); border-radius:var(--radius-lg);">
          <div>
            <button id="save-risk-btn" class="btn btn-primary">Save Risk Overrides (${mode.toUpperCase()})</button>
            <span style="font-size:11px; color:var(--text-3); margin-left:8px;">Valid unset state: saves cleanly when empty or off</span>
          </div>

          <!-- TEST SIMULATION HOOKS -->
          <div style="display:flex; align-items:center; gap:8px;">
            <span style="font-size:11px; color:var(--text-3); text-transform:uppercase;">Test Hook:</span>
            <button id="simulate-rollover-btn" class="btn btn-ghost btn-sm" style="font-size:11px;">
              Simulate Day Rollover
            </button>
            ${testDayKey ? `
              <button id="reset-day-btn" class="btn btn-ghost btn-sm" style="font-size:11px; color:var(--loss);">
                Reset Date
              </button>
            ` : ''}
          </div>
        </div>

      </div>
    `;

    bindEvents();
  }

  function bindEvents() {
    // Mode toggles
    document.getElementById('mode-demo-btn')?.addEventListener('click', () => {
      mode = 'demo';
      loadData();
    });
    document.getElementById('mode-real-btn')?.addEventListener('click', () => {
      mode = 'real';
      loadData();
    });

    // Clear limit state
    document.getElementById('clear-limit-btn')?.addEventListener('click', async () => {
      try {
        await api.clearDailyLimit(mode);
        toast('Daily target / limit state cleared successfully', 'success');
        await loadData();
      } catch(e) {
        toast('Error clearing state: ' + e.message, 'error');
      }
    });

    // Test hook: Simulate day rollover
    document.getElementById('simulate-rollover-btn')?.addEventListener('click', async () => {
      try {
        const d = new Date();
        d.setDate(d.getDate() + 1);
        const nextDay = d.toISOString().slice(0, 10);
        await api.shiftDayKey(nextDay);
        toast(`Simulated day rolled to ${nextDay} (next day-boundary)`, 'info');
        await loadData();
      } catch(e) {
        toast(e.message, 'error');
      }
    });

    // Test hook: Reset day
    document.getElementById('reset-day-btn')?.addEventListener('click', async () => {
      try {
        await api.shiftDayKey(null);
        toast('Restored real UTC date', 'info');
        await loadData();
      } catch(e) {
        toast(e.message, 'error');
      }
    });

    // Save button
    document.getElementById('save-risk-btn')?.addEventListener('click', async () => {
      const tpVal = document.getElementById('tp-val')?.value.trim();
      const slVal = document.getElementById('sl-val')?.value.trim();
      const dptVal = document.getElementById('dpt-val')?.value.trim();
      const dllVal = document.getElementById('dll-val')?.value.trim();

      const newOverrides = {
        take_profit: {
          enabled: document.getElementById('tp-enable')?.checked || false,
          value: tpVal ? parseFloat(tpVal) : null,
          unit: document.getElementById('tp-unit')?.value || 'money',
        },
        stop_loss: {
          enabled: document.getElementById('sl-enable')?.checked || false,
          value: slVal ? parseFloat(slVal) : null,
          unit: document.getElementById('sl-unit')?.value || 'money',
        },
        daily_profit_target: {
          enabled: document.getElementById('dpt-enable')?.checked || false,
          value: dptVal ? parseFloat(dptVal) : null,
          unit: document.getElementById('dpt-unit')?.value || 'money',
          close_open_on_hit: document.getElementById('dpt-close-open')?.checked || false,
        },
        daily_loss_limit: {
          enabled: document.getElementById('dll-enable')?.checked || false,
          value: dllVal ? parseFloat(dllVal) : null,
          unit: document.getElementById('dll-unit')?.value || 'money',
          close_open_on_hit: document.getElementById('dll-close-open')?.checked || false,
        },
        trade_weekends: document.getElementById('weekend-enable')?.checked || false,
      };

      try {
        await api.saveRiskOverrides(mode, newOverrides);
        overrides = newOverrides;
        toast(`Risk overrides saved for ${mode.toUpperCase()} mode!`, 'success');
        render();
      } catch(e) {
        toast('Error saving risk overrides: ' + e.message, 'error');
      }
    });
  }

  loadData();
}
