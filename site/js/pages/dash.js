import { api } from '../api.js';
import { startPoll, stopPoll } from '../router.js';
import { toast } from '../toast.js';

export async function dashPage() {
  const root = document.getElementById('page-container');
  if (!root) return;

  root.innerHTML = `<div style="text-align:center; padding:40px; color:var(--text-2);">Loading platform telemetry...</div>`;

  let state = {};
  let session = {};
  let trades = [];

  async function loadData() {
    try {
      const [st, sess, tr] = await Promise.all([
        api.getState().catch(() => ({})),
        api.getSession().catch(() => ({})),
        api.getTrades().catch(() => ({ trades: [] })),
      ]);
      state = st || {};
      session = sess || {};
      trades = Array.isArray(tr) ? tr : (tr.trades || []);
      render();
    } catch(err) {
      toast(err.message || 'Error loading dashboard data', 'error');
    }
  }

  function render() {
    const settings = state.settings || {};
    const heartbeat = state.heartbeat || {};
    const trainingLocked = !!settings.training_locked;

    // Mode
    const mode = (settings.mode || heartbeat.mode || 'demo').toLowerCase();
    const isReal = mode === 'real';

    // Account financials
    const balance = typeof heartbeat.balance === 'number' ? heartbeat.balance : 10000.00;
    const equity = typeof heartbeat.equity === 'number' ? heartbeat.equity : balance;
    const freeMargin = typeof heartbeat.free_margin === 'number' ? heartbeat.free_margin : (equity * 0.95);
    const todayPnl = equity - balance;

    // Heartbeat recency check (2 minutes)
    const hbEpoch = heartbeat.timestamp || 0;
    const nowSec = Math.floor(Date.now() / 1000);
    const isRecent = hbEpoch > 0 && (nowSec - hbEpoch) < 120;
    const botPower = settings.power !== false;

    let runnerStatusText = 'Bot idle';
    let runnerDotClass = 'dot-paused';

    if (trainingLocked) {
      runnerStatusText = 'Training — bot paused';
      runnerDotClass = 'dot-train';
    } else if (isRecent && botPower) {
      runnerStatusText = 'Bot running';
      runnerDotClass = 'dot-live';
    } else if (!botPower) {
      runnerStatusText = 'Bot stopped (power OFF)';
      runnerDotClass = 'dot-paused';
    }

    // Top status update
    const topStatus = document.getElementById('top-status-text');
    const topDot = document.querySelector('#top-status .dot');
    const topMode = document.getElementById('top-mode');
    if (topStatus) topStatus.textContent = runnerStatusText;
    if (topDot) topDot.className = `dot ${runnerDotClass}`;
    if (topMode) {
      topMode.textContent = mode.toUpperCase();
      topMode.className = `badge ${isReal ? 'badge-warning' : 'badge-muted'}`;
    }

    // Positions (open only)
    const openPositions = trades.filter(t => !t.close_utc && !t.closed_at);

    // Models list from session
    const modelAllocations = session.models || session.allocations || [];

    const riskStatus = settings[`risk_status_${mode}`] || state.risk_status || {};
    const isTargetHit = riskStatus.status === 'daily_target_reached';
    const isLimitHit = riskStatus.status === 'daily_limit_reached';

    root.innerHTML = `
      ${(isTargetHit || isLimitHit) ? `
        <div class="card" style="border-left: 4px solid ${isTargetHit ? 'var(--profit)' : 'var(--loss)'}; background:${isTargetHit ? 'var(--profit-dim)' : 'var(--loss-dim)'}; margin-bottom:16px;">
          <div style="display:flex; justify-content:space-between; align-items:center; flex-wrap:wrap; gap:12px;">
            <div>
              <div style="font-weight:700; font-size:14px; color:${isTargetHit ? 'var(--profit)' : 'var(--loss)'};">
                ${isTargetHit ? '🎯 Daily Profit Target Reached' : '🛑 Daily Loss Limit Reached'}
              </div>
              <div style="font-size:12px; color:var(--text-2); margin-top:2px;">
                ${riskStatus.reason || 'New trades paused for today'}. Counter resets automatically at 00:00:00 UTC (or clear manually).
              </div>
            </div>
            <div style="display:flex; align-items:center; gap:8px;">
              <button id="dash-clear-limit-btn" class="btn btn-ghost btn-sm" style="font-size:11px;">Clear Limit State</button>
              <a href="#risk" class="btn btn-primary btn-sm" style="font-size:11px;">Manage Risk Overrides</a>
            </div>
          </div>
        </div>
      ` : ''}

      <!-- TOP BALANCE & RUNNER STATUS CARD -->
      <div class="card">
        <div style="display:flex; flex-wrap:wrap; align-items:flex-start; justify-content:space-between; gap:16px; margin-bottom:20px;">
          <div>
            <div style="font-size:11px; font-weight:700; color:var(--text-3); text-transform:uppercase; letter-spacing:0.05em; margin-bottom:4px;">
              Live Account Equity
            </div>
            <div class="tabular" style="font-size:36px; font-weight:800; color:var(--text); letter-spacing:-0.03em; line-height:1.1;">
              $${equity.toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}
            </div>
            <div style="display:flex; align-items:center; gap:12px; margin-top:8px; font-size:12px;">
              <span style="color:var(--text-2);">Balance: <strong class="tabular" style="color:var(--text);">$${balance.toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}</strong></span>
              <span style="color:var(--text-3);">·</span>
              <span style="color:var(--text-2);">Free Margin: <strong class="tabular" style="color:var(--text);">$${freeMargin.toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}</strong></span>
              <span style="color:var(--text-3);">·</span>
              <span>Today's P&L: <strong class="tabular ${todayPnl >= 0 ? 'badge badge-profit' : 'badge badge-loss'}">${todayPnl >= 0 ? '+' : ''}$${todayPnl.toFixed(2)}</strong></span>
            </div>
          </div>

          <div style="display:flex; flex-direction:column; align-items:flex-end; gap:10px;">
            <div style="display:flex; align-items:center; gap:8px;">
              <button id="mode-toggle-btn" class="btn btn-ghost btn-sm" style="font-size:11px; text-transform:uppercase; font-weight:700;">
                <span class="badge ${isReal ? 'badge-warning' : 'badge-muted'}">${mode} MODE</span>
                <span>Switch to ${isReal ? 'DEMO' : 'REAL'}</span>
              </button>
            </div>
            <div style="display:flex; align-items:center; gap:6px; font-size:12px; color:var(--text-2);">
              <span class="dot ${runnerDotClass}"></span>
              <span style="font-weight:600; color:var(--text);">${runnerStatusText}</span>
              ${heartbeat.loginid ? `<span class="tabular" style="color:var(--text-3);">(${heartbeat.loginid})</span>` : ''}
            </div>
          </div>
        </div>

        <!-- BOT CONTROLS BAR -->
        <div style="display:flex; flex-wrap:wrap; align-items:center; justify-content:space-between; gap:12px; padding-top:16px; border-top:1px solid var(--border);">
          <div style="display:flex; align-items:center; gap:10px;">
            <button
              id="bot-toggle-btn"
              class="btn ${botPower ? 'btn-ghost' : 'btn-primary'}"
              ${trainingLocked ? 'disabled title="Training in progress — bot execution locked"' : ''}
            >
              <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"><polygon points="5 3 19 12 5 21 5 3"/></svg>
              <span>${botPower ? 'BOT ACTIVE (TURN OFF)' : 'START BOT (TURN ON)'}</span>
            </button>

            <button
              id="kill-switch-btn"
              class="btn btn-danger"
              ${settings.halt ? 'style="opacity:0.7;"' : ''}
            >
              <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"><circle cx="12" cy="12" r="10"/><line x1="15" y1="9" x2="9" y2="15"/><line x1="9" y1="9" x2="15" y2="15"/></svg>
              <span>${settings.halt ? 'PLATFORM HALTED' : 'KILL SWITCH'}</span>
            </button>
          </div>

          <div style="font-size:11px; color:var(--text-3);">
            ${trainingLocked ? '⚠ Bot trade execution locked during model training' : 'Windows MT5 Bot running via GitHub Actions self-chain'}
          </div>
        </div>
      </div>

      <!-- SESSION CAPITAL POOL CARD -->
      <div class="card">
        <div class="card-header">
          <div>
            <div class="card-title">Session Capital Pool Allocation</div>
            <div style="font-size:12px; color:var(--text-2); margin-top:2px;">
              Configures isolated margin budget and global loss protections across models.
            </div>
          </div>
          <div class="tabular" style="font-size:13px; color:var(--text-2);">
            Active Pool: <strong style="color:var(--text); font-size:15px;">$${(session.pool_amount || balance).toLocaleString('en-US', { minimumFractionDigits: 2 })}</strong>
          </div>
        </div>

        <form id="pool-form" style="display:grid; grid-template-columns:repeat(auto-fit, minmax(200px, 1fr)) 120px; gap:12px; align-items:end;">
          <div>
            <label style="display:block; font-size:11px; font-weight:600; color:var(--text-2); margin-bottom:4px;">
              Set Session Balance ($)
            </label>
            <input
              id="pool-balance-input"
              type="number"
              step="50"
              min="100"
              value="${session.pool_amount || balance}"
              style="width:100%; font-family:var(--font-mono);"
            />
          </div>

          <div>
            <label style="display:block; font-size:11px; font-weight:600; color:var(--text-2); margin-bottom:4px;">
              Global Stop-Loss (% of pool)
            </label>
            <input
              id="pool-sl-input"
              type="number"
              step="0.5"
              min="0.5"
              max="25"
              value="${settings.global_sl_pct || 5.0}"
              style="width:100%; font-family:var(--font-mono);"
            />
          </div>

          <div>
            <label style="display:block; font-size:11px; font-weight:600; color:var(--text-2); margin-bottom:4px;">
              Global Take-Profit (% of pool)
            </label>
            <input
              id="pool-tp-input"
              type="number"
              step="0.5"
              min="1"
              max="50"
              value="${settings.global_tp_pct || 10.0}"
              style="width:100%; font-family:var(--font-mono);"
            />
          </div>

          <button type="submit" class="btn btn-primary" style="height:37px;">
            Save Pool
          </button>
        </form>
      </div>

      <!-- ACTIVE MODELS TABLE -->
      <div class="card">
        <div class="card-header">
          <div class="card-title">Active Pair Models & Allocation</div>
          <span style="font-size:12px; color:var(--text-2);">${modelAllocations.length} Assigned</span>
        </div>

        <div class="table-wrap">
          <table>
            <thead>
              <tr>
                <th>Pair / Symbol</th>
                <th>Capital Share</th>
                <th>Status</th>
                <th style="text-align:right;">Control</th>
              </tr>
            </thead>
            <tbody>
              ${
                modelAllocations.length === 0
                  ? `
                    <tr>
                      <td colspan="4" style="text-align:center; padding:32px 16px; color:var(--text-2);">
                        No trained models assigned yet.
                        <div style="margin-top:8px;">
                          <a href="#training" class="btn btn-primary btn-sm">Go to Training to train your first pair</a>
                        </div>
                      </td>
                    </tr>
                  `
                  : modelAllocations.map(m => {
                    const pair = m.pair || m.symbol;
                    const capital = m.capital || (balance / Math.max(1, modelAllocations.length));
                    const enabled = m.enabled !== false;
                    return `
                      <tr>
                        <td>
                          <strong style="color:var(--text); font-size:14px;">${pair}</strong>
                          <span style="font-size:11px; color:var(--text-3); margin-left:6px;">M1 Scalper</span>
                        </td>
                        <td class="tabular">$${Number(capital).toFixed(2)}</td>
                        <td>
                          <span class="badge ${enabled ? 'badge-profit' : 'badge-muted'}">
                            ${enabled ? 'Trading Active' : 'Paused'}
                          </span>
                        </td>
                        <td style="text-align:right;">
                          <button
                            class="btn btn-ghost btn-sm model-toggle-btn"
                            data-pair="${pair}"
                            data-enabled="${enabled}"
                          >
                            ${enabled ? 'Pause' : 'Resume'}
                          </button>
                        </td>
                      </tr>
                    `;
                  }).join('')
              }
            </tbody>
          </table>
        </div>
      </div>

      <!-- OPEN POSITIONS TABLE -->
      <div class="card">
        <div class="card-header">
          <div class="card-title">Live Open Positions (${openPositions.length})</div>
          <span style="font-size:12px; color:var(--text-3); font-family:var(--font-mono);">
            Zero Unhedged Orders
          </span>
        </div>

        <div class="table-wrap">
          <table>
            <thead>
              <tr>
                <th>Ticket</th>
                <th>Pair</th>
                <th>Side</th>
                <th>Lots</th>
                <th>Open Price</th>
                <th>Current Price</th>
                <th>Stop Loss</th>
                <th>Floating P&L</th>
              </tr>
            </thead>
            <tbody>
              ${
                openPositions.length === 0
                  ? `
                    <tr>
                      <td colspan="8" style="text-align:center; padding:32px 16px; color:var(--text-2);">
                        No open positions. Bot scalper evaluates on completed M1 bars.
                      </td>
                    </tr>
                  `
                  : openPositions.map(p => {
                    const pnl = Number(p.net_pnl || p.profit || 0);
                    return `
                      <tr>
                        <td class="tabular" style="color:var(--text-3);">#${p.ticket || p.id}</td>
                        <td><strong>${p.symbol || p.pair}</strong></td>
                        <td>
                          <span class="badge ${p.side === 'buy' || p.side === 'BUY' ? 'badge-profit' : 'badge-loss'}">
                            ${(p.side || 'BUY').toUpperCase()}
                          </span>
                        </td>
                        <td class="tabular">${p.volume || p.lots || 0.01}</td>
                        <td class="tabular">${p.open_price || p.price || '-'}</td>
                        <td class="tabular font-bold">${p.current_price || p.price || '-'}</td>
                        <td class="tabular" style="color:var(--loss);">${p.sl || p.stop_loss || '-'}</td>
                        <td class="tabular font-bold ${pnl >= 0 ? 'badge-profit' : 'badge-loss'}" style="font-size:14px;">
                          ${pnl >= 0 ? '+' : ''}$${pnl.toFixed(2)}
                        </td>
                      </tr>
                    `;
                  }).join('')
              }
            </tbody>
          </table>
        </div>
      </div>
    `;

    bindEvents();

    // Start polling if bot is active and heartbeat is recent
    if (isRecent && botPower && !trainingLocked) {
      startPoll(async () => {
        try {
          const st = await api.getState();
          state = st || {};
          render();
        } catch(_) {}
      }, 15000);
    } else {
      stopPoll();
    }
  }

  function bindEvents() {
    // Mode toggle
    const modeBtn = document.getElementById('mode-toggle-btn');
    if (modeBtn) {
      modeBtn.addEventListener('click', async () => {
        const currentMode = (state.settings?.mode || 'demo').toLowerCase();
        const nextMode = currentMode === 'demo' ? 'real' : 'demo';
        if (nextMode === 'real') {
          if (!confirm('SWITCH TO REAL ACCOUNT MODE?\n\nReal capital will be executed on Deriv MT5. Ensure risk limits are set!')) {
            return;
          }
        }
        try {
          await api.saveSettings({ mode: nextMode });
          toast(`Switched mode to ${nextMode.toUpperCase()}`, 'success');
          loadData();
        } catch(e) {
          toast(e.message, 'error');
        }
      });
    }

    // Bot toggle
    const botBtn = document.getElementById('bot-toggle-btn');
    if (botBtn) {
      botBtn.addEventListener('click', async () => {
        const currentPower = state.settings?.power !== false;
        try {
          if (currentPower) {
            await api.saveSettings({ power: false });
            toast('Bot execution power turned OFF', 'warn');
          } else {
            await api.saveSettings({ power: true, halt: false });
            await api.dispatchWorkflow('bot.yml', { mode: state.settings?.mode || 'demo' });
            toast('Dispatched bot workflow on GitHub Actions', 'success');
          }
          loadData();
        } catch(e) {
          toast(e.message, 'error');
        }
      });
    }

    // Kill switch
    const killBtn = document.getElementById('kill-switch-btn');
    if (killBtn) {
      killBtn.addEventListener('click', async () => {
        if (!confirm('TRIGGER EMERGENCY KILL SWITCH?\n\nThis immediately sets halt=true on the coordinator. The bot will stop trading immediately.')) {
          return;
        }
        try {
          await api.saveSettings({ halt: true, power: false });
          toast('Emergency kill switch triggered!', 'error');
          loadData();
        } catch(e) {
          toast(e.message, 'error');
        }
      });
    }

    // Clear limit state from banner
    document.getElementById('dash-clear-limit-btn')?.addEventListener('click', async () => {
      try {
        await api.clearDailyLimit(mode);
        toast('Daily limit cleared — trading resumed', 'success');
        loadData();
      } catch(e) {
        toast(e.message, 'error');
      }
    });

    // Pool form
    const poolForm = document.getElementById('pool-form');
    if (poolForm) {
      poolForm.addEventListener('submit', async (e) => {
        e.preventDefault();
        const bal = parseFloat(document.getElementById('pool-balance-input').value);
        const sl = parseFloat(document.getElementById('pool-sl-input').value);
        const tp = parseFloat(document.getElementById('pool-tp-input').value);

        try {
          await Promise.all([
            api.allocateSession({ pool_amount: bal }),
            api.saveSettings({ global_sl_pct: sl, global_tp_pct: tp }),
          ]);
          toast('Session pool & risk limits saved!', 'success');
          loadData();
        } catch(err) {
          toast(err.message, 'error');
        }
      });
    }

    // Model toggle buttons
    document.querySelectorAll('.model-toggle-btn').forEach(btn => {
      btn.addEventListener('click', async () => {
        const pair = btn.dataset.pair;
        const currentEnabled = btn.dataset.enabled === 'true';
        try {
          await api.overrideSession({
            pair,
            action: currentEnabled ? 'pause' : 'resume'
          });
          toast(`${pair} ${currentEnabled ? 'paused' : 'resumed'}`, 'info');
          loadData();
        } catch(e) {
          toast(e.message, 'error');
        }
      });
    });
  }

  loadData();
}
