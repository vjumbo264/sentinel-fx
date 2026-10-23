import { setToken, getToken, api } from '../api.js';
import { navigate } from '../router.js';
import { toast } from '../toast.js';

export function loginPage() {
  const root = document.getElementById('page-container');
  if (!root) return;

  const currentToken = getToken();

  root.innerHTML = `
    <div style="max-width:440px; margin:40px auto; padding:16px;">
      <div class="card" style="padding:28px;">
        <div style="text-align:center; margin-bottom:24px;">
          <div style="display:inline-flex; align-items:center; justify-content:center; width:48px; height:48px; border-radius:12px; background:var(--accent-dim); color:var(--accent); margin-bottom:12px;">
            <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"><polygon points="12 2 2 7 12 12 22 7 12 2"/><polyline points="2 17 12 22 22 17"/><polyline points="2 12 12 17 22 12"/></svg>
          </div>
          <h1 style="font-size:20px; font-weight:800; letter-spacing:-0.02em;">Connect to SENTINEL-FX</h1>
          <p style="font-size:12px; color:var(--text-2); margin-top:6px;">
            Enter your GitHub Personal Access Token (PAT) with repo & workflow dispatch permissions to access the coordinator.
          </p>
        </div>

        <form id="login-form" style="display:flex; flex-direction:column; gap:16px;">
          <div>
            <label style="display:block; font-size:12px; font-weight:600; color:var(--text-2); margin-bottom:6px;">
              GitHub Personal Access Token (PAT)
            </label>
            <input
              id="pat-input"
              type="password"
              placeholder="github_pat_..."
              value="${currentToken}"
              required
              style="width:100%; font-family:var(--font-mono); font-size:13px;"
            />
          </div>

          <div id="login-error" style="color:var(--loss); font-size:12px; display:none;"></div>

          <button id="login-btn" type="submit" class="btn btn-primary" style="width:100%;">
            Connect Platform
          </button>
        </form>

        <div style="margin-top:20px; padding-top:16px; border-top:1px solid var(--border); font-size:11px; color:var(--text-3); text-align:center; line-height:1.5;">
          Tokens are stored strictly in client-side localStorage and passed only via Bearer headers to the coordinator and GitHub Actions API.
        </div>
      </div>
    </div>
  `;

  const form = document.getElementById('login-form');
  const input = document.getElementById('pat-input');
  const btn = document.getElementById('login-btn');
  const err = document.getElementById('login-error');

  form.addEventListener('submit', async (e) => {
    e.preventDefault();
    const token = input.value.trim();
    if (!token) return;

    btn.disabled = true;
    btn.textContent = 'Verifying...';
    err.style.display = 'none';

    try {
      setToken(token);
      // Validate token by checking worker session/auth or GH API
      const res = await api.getSession().catch(async () => {
        // Fallback test GH API directly
        const gh = await fetch('https://api.github.com/user', {
          headers: { 'Authorization': `Bearer ${token}` }
        });
        if (!gh.ok) throw new Error('Invalid token or insufficient scope');
        return { ok: true };
      });

      toast('Connected successfully!', 'success');
      navigate('dash');
    } catch (e) {
      err.textContent = e.message || 'Authentication failed. Please verify your token.';
      err.style.display = 'block';
      btn.disabled = false;
      btn.textContent = 'Connect Platform';
    }
  });
}
