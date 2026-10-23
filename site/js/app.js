import { register, handleRoute, navigate } from './router.js';
import { dashPage } from './pages/dash.js';
import { riskPage } from './pages/risk.js';
import { trainingPage } from './pages/training.js';
import { historyPage } from './pages/history.js';
import { settingsPage } from './pages/settings.js';
import { loginPage } from './pages/login.js';
import { api, getToken } from './api.js';

// Build navigation
function buildNav() {
  const pages = [
    {
      id: 'dash',
      label: 'Dashboard',
      icon: '<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><rect width="7" height="9" x="3" y="3" rx="1"/><rect width="7" height="5" x="14" y="3" rx="1"/><rect width="7" height="9" x="14" y="12" rx="1"/><rect width="7" height="5" x="3" y="16" rx="1"/></svg>'
    },
    {
      id: 'risk',
      label: 'Risk & Overrides',
      icon: '<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z"/></svg>'
    },
    {
      id: 'training',
      label: 'Training',
      icon: '<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M12 2v20"/><path d="m17 5-5-3-5 3"/><path d="m17 19-5 3-5-3"/><path d="M2 12h20"/></svg>'
    },
    {
      id: 'history',
      label: 'History',
      icon: '<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M3 12a9 9 0 1 0 9-9 9.75 9.75 0 0 0-6.74 2.74L3 8"/><path d="M3 3v5h5"/><path d="M12 7v5l4 2"/></svg>'
    },
    {
      id: 'settings',
      label: 'Settings',
      icon: '<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="12" cy="12" r="3"/><path d="M19.4 15a1.65 1.65 0 0 0 .33 1.82l.06.06a2 2 0 0 1 0 2.83 2 2 0 0 1-2.83 0l-.06-.06a1.65 1.65 0 0 0-1.82-.33 1.65 1.65 0 0 0-1 1.51V21a2 2 0 0 1-2 2 2 2 0 0 1-2-2v-.09A1.65 1.65 0 0 0 9 19.4a1.65 1.65 0 0 0-1.82.33l-.06.06a2 2 0 0 1-2.83 0 2 2 0 0 1 0-2.83l.06-.06a1.65 1.65 0 0 0 .33-1.82 1.65 1.65 0 0 0-1.51-1H3a2 2 0 0 1-2-2 2 2 0 0 1 2-2h.09A1.65 1.65 0 0 0 4.6 9a1.65 1.65 0 0 0-.33-1.82l-.06-.06a2 2 0 0 1 0-2.83 2 2 0 0 1 2.83 0l.06.06a1.65 1.65 0 0 0 1.82.33H9a1.65 1.65 0 0 0 1-1.51V3a2 2 0 0 1 2-2 2 2 0 0 1 2 2v.09a1.65 1.65 0 0 0 1 1.51 1.65 1.65 0 0 0 1.82-.33l.06-.06a2 2 0 0 1 2.83 0 2 2 0 0 1 0 2.83l-.06.06a1.65 1.65 0 0 0-.33 1.82V9a1.65 1.65 0 0 0 1.51 1H21a2 2 0 0 1 2 2 2 2 0 0 1-2 2h-.09a1.65 1.65 0 0 0-1.51 1z"/></svg>'
    },
  ];

  // Desktop rail
  const rail = document.getElementById('rail-nav');
  if (rail) {
    rail.innerHTML = pages.map(p => `
      <a href="#${p.id}" class="rail-link" data-page="${p.id}">
        ${p.icon}
        <span>${p.label}</span>
      </a>
    `).join('');
  }

  // Mobile bottom tabs
  document.querySelectorAll('.tab').forEach(btn => {
    btn.addEventListener('click', () => navigate(btn.dataset.page));
  });
}

// Training lock banner status check
async function refreshBanner() {
  try {
    const state = await api.getState();
    const locked = !!state?.settings?.training_locked;
    const banner = document.getElementById('train-banner');
    if (banner) {
      banner.classList.toggle('visible', locked);
      if (locked && state?.settings?.training_lock_reason) {
        banner.textContent = `⚠ TRAINING IN PROGRESS (${state.settings.training_lock_reason}) — Bot paused, trade execution paused until training completes`;
      }
    }
  } catch(_) {}
}

// Real-time clock (UTC+1 West Africa Time / Lagos)
function startClock() {
  const el = document.getElementById('rail-clock');
  if (!el) return;
  const update = () => {
    const now = new Date(Date.now() + 60 * 60 * 1000); // WAT is UTC+1
    el.textContent = now.toUTCString().slice(17, 25) + ' WAT';
  };
  update();
  setInterval(update, 1000);
}

// Auth gate
function isAuth() {
  return !!getToken();
}

register('login', loginPage);
register('dash', () => isAuth() ? dashPage() : navigate('login'));
register('risk', () => isAuth() ? riskPage() : navigate('login'));
register('training', () => isAuth() ? trainingPage() : navigate('login'));
register('history', () => isAuth() ? historyPage() : navigate('login'));
register('settings', settingsPage);

window.addEventListener('DOMContentLoaded', () => {
  buildNav();
  startClock();
  refreshBanner();
  setInterval(refreshBanner, 30000);
  handleRoute();
});

// Auto-route on initial script load if DOM is already ready
if (document.readyState === 'complete' || document.readyState === 'interactive') {
  buildNav();
  startClock();
  refreshBanner();
  handleRoute();
}
