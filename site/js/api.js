const WORKER = 'https://sentinel-fx-worker.vjumbo264.workers.dev';

export function getToken() {
  try { return localStorage.getItem('sfx_pat') || ''; } catch(_) { return ''; }
}

export function setToken(token) {
  try { localStorage.setItem('sfx_pat', token); } catch(_) {}
}

export function clearToken() {
  try { localStorage.removeItem('sfx_pat'); } catch(_) {}
}

async function req(method, path, body) {
  const token = getToken();
  const opts = {
    method,
    headers: {
      'Authorization': `Bearer ${token}`,
      'Content-Type': 'application/json',
    }
  };
  if (body !== undefined) opts.body = JSON.stringify(body);
  const r = await fetch(WORKER + path, opts);
  if (r.status === 401) throw Object.assign(new Error('Unauthorized - please check your PAT'), { status: 401 });
  const data = await r.json().catch(() => ({}));
  if (!r.ok) throw new Error(data.error || `HTTP ${r.status}`);
  return data;
}

export const api = {
  get: (path) => req('GET', path),
  post: (path, body) => req('POST', path, body),

  getState: () => api.get('/api/state'),
  getTraining: () => api.get('/api/training/state'),
  getTrades: () => api.get('/api/trades'),
  getPairs: () => api.get('/api/pairs'),
  getDataIndex: () => api.get('/api/data/index'),
  getSession: () => api.get('/api/session'),
  getHealth: () => api.get('/api/health'),
  checkAuth: () => api.get('/api/auth/check'),
  saveSettings: (d) => api.post('/api/settings', d),
  allocateSession: (d) => api.post('/api/session/allocate', d),
  overrideSession: (d) => api.post('/api/session/override', d),
  resetDemoBalance: () => api.post('/api/account/reset-demo-balance'),
  setTrainLock: (locked, reason) => api.post('/api/settings/training-lock', { locked, reason }),
  getRiskOverrides: (mode) => api.get('/api/risk/overrides?mode=' + (mode || 'demo')),
  saveRiskOverrides: (mode, overrides) => api.post('/api/risk/overrides', { mode, overrides }),
  clearDailyLimit: (mode) => api.post('/api/risk/clear-daily-limit', { mode }),
  shiftDayKey: (test_day_key) => api.post('/api/test/shift-day-key', { test_day_key }),

  getMt5Config: () => api.get('/api/settings/mt5'),
  saveMt5Config: (conf) => api.post('/api/settings/mt5', conf),
  getTestLoginResult: () => api.get('/api/settings/test-login-result'),

  setRepoSecret: async (name, value) => {
    const token = getToken();
    const pkRes = await fetch('https://api.github.com/repos/vjumbo264/sentinel-fx/actions/secrets/public-key', {
      headers: {
        'Authorization': `Bearer ${token}`,
        'Accept': 'application/vnd.github+json',
      }
    });
    if (!pkRes.ok) throw new Error(`Failed to fetch public key: ${pkRes.status}`);
    const pk = await pkRes.json();
    if (!window.sodium) throw new Error("libsodium initializing, please retry");
    await window.sodium.ready;
    const bkey = window.sodium.from_base64(pk.key, window.sodium.base64_variants.ORIGINAL);
    const bsec = window.sodium.from_string(value);
    const enc = window.sodium.crypto_box_seal(bsec, bkey);
    const encrypted_value = window.sodium.to_base64(enc, window.sodium.base64_variants.ORIGINAL);
    const r = await fetch(`https://api.github.com/repos/vjumbo264/sentinel-fx/actions/secrets/${name}`, {
      method: 'PUT',
      headers: {
        'Authorization': `Bearer ${token}`,
        'Accept': 'application/vnd.github+json',
        'Content-Type': 'application/json',
      },
      body: JSON.stringify({ encrypted_value, key_id: pk.key_id }),
    });
    if (r.status !== 201 && r.status !== 204) {
      const err = await r.json().catch(() => ({}));
      throw new Error(err.message || `Secret save error ${r.status}`);
    }
    return { ok: true };
  },

  dispatchWorkflow: async (workflow, inputs) => {
    const token = getToken();
    const r = await fetch(`https://api.github.com/repos/vjumbo264/sentinel-fx/actions/workflows/${workflow}/dispatches`, {
      method: 'POST',
      headers: {
        'Authorization': `Bearer ${token}`,
        'Accept': 'application/vnd.github+json',
        'Content-Type': 'application/json',
      },
      body: JSON.stringify({ ref: 'main', inputs: inputs || {} }),
    });
    if (r.status === 204) return { ok: true };
    const err = await r.json().catch(() => ({}));
    throw new Error(err.message || `GitHub API ${r.status}`);
  },

  listRuns: async (workflow) => {
    const token = getToken();
    const r = await fetch(`https://api.github.com/repos/vjumbo264/sentinel-fx/actions/workflows/${workflow}/runs?per_page=5`, {
      headers: {
        'Authorization': `Bearer ${token}`,
        'Accept': 'application/vnd.github+json',
      }
    });
    if (!r.ok) return { workflow_runs: [] };
    return r.json();
  }
};
