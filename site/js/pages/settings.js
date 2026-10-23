import { api, getToken, setToken, clearToken } from '../api.js';
import { getThemeSetting, applyTheme } from '../theme.js';
import { navigate } from '../router.js';
import { toast } from '../toast.js';

export async function settingsPage() {
  const root = document.getElementById('page-container');
  if (!root) return;

  root.innerHTML = `<div style="text-align:center; padding:40px; color:var(--text-2);">Loading platform configuration...</div>`;

  let state = {};
  let health = {};

  async function loadData() {
    try {
      const [st, hl] = await Promise.all([
        api.getState().catch(() => ({})),
        api.getHealth().catch(() => ({})),
      ]);
      state = st || {};
      health = hl || {};
      render();
    } catch(err) {
      toast(err.message || 'Error loading settings', 'error');
    }
  }

  function render() {
    const token = getToken();
    const hasToken = !!token;
    const maskedToken = token ? `${token.slice(0, 12)}...${token.slice(-4)}` : '';
    const currentTheme = getThemeSetting();
    const heartbeat = state.heartbeat || {};
    const settings = state.settings || {};

    const hbDate = heartbeat.timestamp
      ? new Date(heartbeat.timestamp * 1000).toUTCString()
      : 'No recent heartbeat';

    root.innerHTML = `
      <!-- GITHUB PAT AUTH SECTION -->
      <div class="card">
        <div class="card-header">
          <div>
            <div class="card-title">GitHub Authentication & API Access</div>
            <div style="font-size:12px; color:var(--text-2); margin-top:2px;">
              Used by the browser to dispatch bot and training workflows and communicate with coordinator worker.
            </div>
          </div>
          <div>
            <span class="badge ${hasToken ? 'badge-profit' : 'badge-loss'}">
              ${hasToken ? 'Connected ✓' : 'Not Connected'}
            </span>
          </div>
        </div>

        <div style="display:flex; flex-direction:column; gap:14px; max-width:540px;">
          <div>
            <label style="display:block; font-size:11px; font-weight:600; color:var(--text-2); margin-bottom:4px;">
              Personal Access Token (PAT)
            </label>
            <div style="display:flex; gap:8px;">
              <input
                id="settings-pat-input"
                type="password"
                value="${token}"
                placeholder="github_pat_..."
                style="flex:1; font-family:var(--font-mono); font-size:12px;"
              />
              <button id="update-pat-btn" class="btn btn-primary btn-sm">Update</button>
            </div>
            ${token ? `<div style="font-size:11px; color:var(--text-3); margin-top:4px; font-family:var(--font-mono);">Current: ${maskedToken}</div>` : ''}
          </div>

          <div style="display:flex; gap:8px;">
            <button id="test-auth-btn" class="btn btn-ghost btn-sm">
              Test Connection
            </button>
            <button id="disconnect-btn" class="btn btn-danger btn-sm">
              Disconnect PAT
            </button>
          </div>
        </div>
      </div>

      <!-- THEME SETTINGS -->
      <div class="card">
        <div class="card-header">
          <div>
            <div class="card-title">Interface Appearance</div>
            <div style="font-size:12px; color:var(--text-2); margin-top:2px;">
              Automatic dark and light UI with terminal aesthetics and system color-scheme detection.
            </div>
          </div>
          <span class="badge badge-muted">
            Active: ${currentTheme.toUpperCase()}
          </span>
        </div>

        <div style="display:flex; gap:10px;">
          <button
            class="btn ${currentTheme === 'auto' ? 'btn-primary' : 'btn-ghost'} btn-sm theme-btn"
            data-theme-setting="auto"
          >
            Auto (System)
          </button>
          <button
            class="btn ${currentTheme === 'dark' ? 'btn-primary' : 'btn-ghost'} btn-sm theme-btn"
            data-theme-setting="dark"
          >
            Dark Mode
          </button>
          <button
            class="btn ${currentTheme === 'light' ? 'btn-primary' : 'btn-ghost'} btn-sm theme-btn"
            data-theme-setting="light"
          >
            Light Mode
          </button>
        </div>
      </div>

      <!-- MT5 CREDENTIALS & DEMO RESET -->
      <div class="card">
        <div class="card-header">
          <div>
            <div class="card-title">Deriv MT5 Terminal Account</div>
            <div style="font-size:12px; color:var(--text-2); margin-top:2px;">
              Connected trading account executed on Windows Actions runner.
            </div>
          </div>
          <span class="badge badge-profit">Deriv MetaTrader 5</span>
        </div>

        <div style="display:grid; grid-template-columns:repeat(auto-fit, minmax(200px, 1fr)); gap:12px; margin-bottom:16px;">
          <div style="background:var(--bg-input); padding:12px; border-radius:var(--radius); border:1px solid var(--border);">
            <div style="font-size:11px; color:var(--text-3);">Account Login</div>
            <div class="tabular" style="font-size:14px; font-weight:700; color:var(--text); margin-top:2px;">
              ${heartbeat.loginid || '41286446 (Demo)'}
            </div>
          </div>

          <div style="background:var(--bg-input); padding:12px; border-radius:var(--radius); border:1px solid var(--border);">
            <div style="font-size:11px; color:var(--text-3);">Broker Server</div>
            <div style="font-size:14px; font-weight:700; color:var(--text); margin-top:2px;">
              Deriv-Demo / SVG
            </div>
          </div>

          <div style="background:var(--bg-input); padding:12px; border-radius:var(--radius); border:1px solid var(--border);">
            <div style="font-size:11px; color:var(--text-3);">Execution Mode</div>
            <div style="font-size:14px; font-weight:700; color:var(--text); margin-top:2px;">
              Hedging CFD
            </div>
          </div>
        </div>

        <div style="display:flex; align-items:center; justify-content:space-between; padding-top:14px; border-top:1px solid var(--border);">
          <div style="font-size:12px; color:var(--text-2);">
            Reset demo equity back to baseline $10,000 for training or paper trading evaluation.
          </div>
          <button id="reset-demo-btn" class="btn btn-ghost btn-sm">
            Reset Demo Balance ($10k)
          </button>
        </div>
      </div>

      <!-- SYSTEM & WORKER TELEMETRY -->
      <div class="card">
        <div class="card-header">
          <div>
            <div class="card-title">Coordinator Health & Heartbeat Telemetry</div>
            <div style="font-size:12px; color:var(--text-2); margin-top:2px;">
              Cloudflare Worker & D1 Database Coordinator
            </div>
          </div>
          <button id="refresh-health-btn" class="btn btn-ghost btn-sm">
            Refresh Health
          </button>
        </div>

        <div style="display:grid; grid-template-columns:repeat(auto-fit, minmax(220px, 1fr)); gap:12px; font-size:12px;">
          <div style="background:var(--bg-input); padding:12px; border-radius:var(--radius); border:1px solid var(--border);">
            <div style="color:var(--text-3);">Worker Endpoint</div>
            <div style="font-family:var(--font-mono); color:var(--text); margin-top:2px; word-break:break-all;">
              sentinel-fx-worker.vjumbo264.workers.dev
            </div>
          </div>

          <div style="background:var(--bg-input); padding:12px; border-radius:var(--radius); border:1px solid var(--border);">
            <div style="color:var(--text-3);">Worker Status / Latency</div>
            <div style="font-family:var(--font-mono); color:var(--profit); margin-top:2px;">
              ${health.status === 'ok' ? 'Healthy (OK)' : 'Online'} · UTC ${health.utc || new Date().toISOString().slice(11, 19)}
            </div>
          </div>

          <div style="background:var(--bg-input); padding:12px; border-radius:var(--radius); border:1px solid var(--border);">
            <div style="color:var(--text-3);">Last Bot Heartbeat</div>
            <div style="font-family:var(--font-mono); color:var(--text); margin-top:2px;">
              ${hbDate}
            </div>
          </div>

          <div style="background:var(--bg-input); padding:12px; border-radius:var(--radius); border:1px solid var(--border);">
            <div style="color:var(--text-3);">Training Lock Status</div>
            <div style="font-family:var(--font-mono); color:${settings.training_locked ? 'var(--warning)' : 'var(--text-2)'}; margin-top:2px;">
              ${settings.training_locked ? `Locked (${settings.training_lock_reason || 'active'})` : 'Unlocked (Normal)'}
            </div>
          </div>
        </div>
      </div>
    `;

    bindEvents();
  }

  function bindEvents() {
    // PAT update
    document.getElementById('update-pat-btn')?.addEventListener('click', () => {
      const val = document.getElementById('settings-pat-input').value.trim();
      if (!val) return;
      setToken(val);
      toast('PAT updated in localStorage', 'success');
      loadData();
    });

    // Test connection
    document.getElementById('test-auth-btn')?.addEventListener('click', async () => {
      try {
        await api.getHealth();
        toast('Connection verified — Worker is responsive!', 'success');
      } catch(e) {
        toast('Connection test failed: ' + e.message, 'error');
      }
    });

    // Disconnect
    document.getElementById('disconnect-btn')?.addEventListener('click', () => {
      clearToken();
      toast('PAT cleared. Redirecting to login...', 'info');
      navigate('login');
    });

    // Theme toggles
    document.querySelectorAll('.theme-btn').forEach(btn => {
      btn.addEventListener('click', () => {
        const theme = btn.dataset.themeSetting;
        applyTheme(theme);
        toast(`Appearance set to ${theme.toUpperCase()}`, 'info');
        render();
      });
    });

    // Reset demo balance
    document.getElementById('reset-demo-btn')?.addEventListener('click', async () => {
      if (!confirm('Reset demo balance to $10,000.00?')) return;
      try {
        await api.resetDemoBalance();
        toast('Demo balance reset to $10,000', 'success');
        loadData();
      } catch(e) {
        toast(e.message, 'error');
      }
    });

    // Refresh health
    document.getElementById('refresh-health-btn')?.addEventListener('click', async () => {
      await loadData();
      toast('Health data refreshed', 'info');
    });
  }

  loadData();
}
