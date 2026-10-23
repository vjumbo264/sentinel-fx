const routes = {};
let current = null;
let pollTimer = null;

export function register(page, mountFn) {
  routes[page] = mountFn;
}

export function navigate(page) {
  window.location.hash = '#' + page;
}

export function stopPoll() {
  if (pollTimer) {
    clearInterval(pollTimer);
    pollTimer = null;
  }
}

export function startPoll(fn, intervalMs) {
  stopPoll();
  pollTimer = setInterval(fn, intervalMs);
}

export function handleRoute() {
  const page = (window.location.hash.slice(1) || 'dash');
  stopPoll();
  if (routes[page]) {
    current = page;
    routes[page]();
  } else {
    navigate('dash');
    return;
  }
  // Update nav active state on rail and mobile bottom nav
  document.querySelectorAll('.tab, .rail-link').forEach(el => {
    el.classList.toggle('active', el.dataset.page === page);
  });
}

window.addEventListener('hashchange', handleRoute);
