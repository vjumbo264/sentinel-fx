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
  let mt5Config = {
    demo_login: '41286446',
    demo_server: 'Deriv-Demo',
    real_login: '10357278',
    real_server: 'DerivSVG-Server'
  };
  let testLoginResult = null;

  async function loadData() {
    try {
      const [st, hl, mt5, tlr] = await Promise.all([
        api.getState().catch(() => ({})),
        api.getHealth().catch(() => ({})),
        api.getMt5Config().catch(() => ({})),
        api.getTestLoginResult().catch(() => ({})),
      ]);
      state = st || {};
      health = hl || {};
      if (mt5 && mt5.config) mt5Config = { ...mt5Config, ...mt5.config };
      if (tlr && tlr.result) testLoginResult = tlr.result;
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

    const hbDate = heartbeat.ts
      ? new Date(heartbeat.ts).toUTCString()
      : (heartbeat.timestamp ? new Date(heartbeat.timestamp * 1000).toUTCString() : 'No recent heartbeat');

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
      <!-- MT5 ACCOUNT CREDENTIALS (H4) -->
      <div class="card">
        <div class="card-header">
          <div>
            <div class="card-title">MT5 account</div>
            <div style="font-size:12px; color:var(--text-2); margin-top:2px;">
              Deriv MetaTrader 5 broker credentials for demo and real accounts. Password is write-only and encrypted with libsodium.
            </div>
          </div>
          <span class="badge badge-profit">Deriv MetaTrader 5</span>
        </div>

        <div style="display:grid; grid-template-columns:repeat(auto-fit, minmax(220px, 1fr)); gap:12px; margin-bottom:14px;">
          <div>
            <label style="display:block; font-size:11px; font-weight:600; color:var(--text-2); margin-bottom:4px;">Demo Login ID</label>
            <input id="mt5-demo-login" type="text" value="${mt5Config.demo_login || '41286446'}" class="input" style="width:100%; font-family:var(--font-mono); font-size:12px;" />
          </div>
          <div>
            <label style="display:block; font-size:11px; font-weight:600; color:var(--text-2); margin-bottom:4px;">Demo Server</label>
            <input id="mt5-demo-server" type="text" value="${mt5Config.demo_server || 'Deriv-Demo'}" class="input" style="width:100%; font-family:var(--font-mono); font-size:12px;" />
          </div>
          <div>
            <label style="display:block; font-size:11px; font-weight:600; color:var(--text-2); margin-bottom:4px;">Real Login ID</label>
            <input id="mt5-real-login" type="text" value="${mt5Config.real_login || '10357278'}" class="input" style="width:100%; font-family:var(--font-mono); font-size:12px;" />
          </div>
          <div>
            <label style="display:block; font-size:11px; font-weight:600; color:var(--text-2); margin-bottom:4px;">Real Server</label>
            <input id="mt5-real-server" type="text" value="${mt5Config.real_server || 'DerivSVG-Server'}" class="input" style="width:100%; font-family:var(--font-mono); font-size:12px;" />
          </div>
          <div style="grid-column: 1 / -1;">
            <label style="display:block; font-size:11px; font-weight:600; color:var(--text-2); margin-bottom:4px;">
              Password (Write-Only: never shown, never logged, never returned by API)
            </label>
            <input id="mt5-password" type="password" placeholder="Enter new password to update (write-only, leaves existing if empty)" class="input" style="width:100%; font-family:var(--font-mono); font-size:12px;" autocomplete="new-password" />
            <div style="font-size:11px; color:var(--text-3); margin-top:4px;">
              Password is write-only. It is encrypted in the browser with libsodium sealed box directly to GitHub Actions secrets (MT5_PASSWORD).
            </div>
          </div>
        </div>

        <div style="display:flex; flex-wrap:wrap; align-items:center; justify-content:space-between; gap:10px; padding-top:14px; border-top:1px solid var(--border);">
          <div style="display:flex; gap:8px;">
            <button id="save-mt5-btn" class="btn btn-primary btn-sm">Save MT5 Account</button>
            <button id="test-login-btn" class="btn btn-ghost btn-sm">Test Login (Demo)</button>
          </div>
          <button id="restart-bot-creds-btn" class="btn btn-ghost btn-sm" style="font-size:11px;">
            Restart Bot with New Credentials
          </button>
        </div>

        <div id="test-login-status" style="margin-top:12px; font-size:12px; display:${testLoginResult ? 'block' : 'none'};">
          ${testLoginResult ? `
            <div style="padding:10px 14px; border-radius:var(--radius-sm); border:1px solid ${testLoginResult.ok ? 'var(--profit)' : 'var(--loss)'}; background:${testLoginResult.ok ? 'rgba(16, 185, 129, 0.1)' : 'rgba(239, 68, 68, 0.1)'}; color:${testLoginResult.ok ? 'var(--profit)' : 'var(--loss)'};">
              <strong>${testLoginResult.ok ? '✓ MT5 Login Passed' : '✗ MT5 Login Failed'}:</strong>
              ${testLoginResult.ok ? `Connected to ${testLoginResult.server || 'Deriv'} (${testLoginResult.login || 'Demo'}) | Balance: $${(testLoginResult.balance || 0).toLocaleString()} ${testLoginResult.currency || 'USD'}` : testLoginResult.error}
              <span style="font-size:10px; color:var(--text-3); margin-left:8px;">(${new Date(testLoginResult.timestamp_utc).toLocaleTimeString()})</span>
            </div>
          ` : ''}
        </div>

        <div style="margin-top:12px; font-size:11px; color:var(--text-3); background:var(--bg-input); padding:10px; border-radius:var(--radius-sm); border:1px solid var(--border-sub);">
          ℹ The running bot picks up new credentials at the next handover or restart. Click <strong>Restart Bot with New Credentials</strong> to execute an atomic zero-gap handover.
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

    // Save MT5 Account credentials
    document.getElementById('save-mt5-btn')?.addEventListener('click', async () => {
      const demoLogin = document.getElementById('mt5-demo-login')?.value.trim();
      const demoServer = document.getElementById('mt5-demo-server')?.value.trim();
      const realLogin = document.getElementById('mt5-real-login')?.value.trim();
      const realServer = document.getElementById('mt5-real-server')?.value.trim();
      const pwd = document.getElementById('mt5-password')?.value;

      try {
        // 1. Save configuration in Worker
        await api.saveMt5Config({
          demo_login: demoLogin,
          demo_server: demoServer,
          real_login: realLogin,
          real_server: realServer,
        });

        // 2. Update repository secrets via libsodium
        if (demoLogin) await api.setRepoSecret('MT5_DEMO_LOGIN', demoLogin);
        if (demoServer) await api.setRepoSecret('MT5_DEMO_SERVER', demoServer);
        if (realLogin) await api.setRepoSecret('MT5_REAL_LOGIN', realLogin);
        if (realServer) await api.setRepoSecret('MT5_REAL_SERVER', realServer);

        // 3. Update password secret if provided (write-only)
        if (pwd && pwd.length > 0) {
          await api.setRepoSecret('MT5_PASSWORD', pwd);
          const pwdInput = document.getElementById('mt5-password');
          if (pwdInput) pwdInput.value = '';
        }

        toast('MT5 Account configuration & secrets saved securely', 'success');
        await loadData();
      } catch(e) {
        toast('Failed to save MT5 configuration: ' + e.message, 'error');
      }
    });

    // Test Login (dispatches test-login.yml workflow)
    document.getElementById('test-login-btn')?.addEventListener('click', async () => {
      try {
        toast('Dispatching MT5 login test workflow...', 'info');
        const statusDiv = document.getElementById('test-login-status');
        if (statusDiv) {
          statusDiv.style.display = 'block';
          statusDiv.innerHTML = `
            <div style="padding:10px 14px; border-radius:var(--radius-sm); border:1px solid var(--border); background:var(--bg-input); color:var(--text-2);">
              ⏳ Connecting to Deriv MT5 terminal (running test-login workflow on Actions)...
            </div>
          `;
        }
        await api.dispatchWorkflow('test-login.yml', { mode: 'demo' });
        toast('Workflow dispatched. Testing credentials on MT5 terminal...', 'info');

        let attempts = 0;
        const pollTimer = setInterval(async () => {
          attempts++;
          try {
            const res = await api.getTestLoginResult();
            if (res && res.result) {
              testLoginResult = res.result;
              render();
              clearInterval(pollTimer);
              if (res.result.ok) {
                toast('MT5 login test passed successfully!', 'success');
              } else {
                toast('MT5 login test failed: ' + res.result.error, 'error');
              }
            }
          } catch(_) {}
          if (attempts >= 15) clearInterval(pollTimer);
        }, 4000);
      } catch(e) {
        toast('Failed to dispatch test-login: ' + e.message, 'error');
      }
    });

    // Restart Bot with new credentials (zero-gap handover)
    document.getElementById('restart-bot-creds-btn')?.addEventListener('click', async () => {
      if (!confirm('Restart the bot with updated credentials using atomic zero-gap handover?')) return;
      try {
        await api.dispatchWorkflow('bot.yml', { mode: 'demo', chain: 'true' });
        toast('Zero-gap bot handover dispatched with new credentials', 'success');
      } catch(e) {
        toast('Failed to restart bot: ' + e.message, 'error');
      }
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
