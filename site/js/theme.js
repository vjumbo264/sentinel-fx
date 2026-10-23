// Automatic & Manual Theme Manager (Auto / Dark / Light)

const STORAGE_KEY = 'sfx_theme';
const darkQuery = window.matchMedia('(prefers-color-scheme: dark)');

export function getThemeSetting() {
  try {
    return localStorage.getItem(STORAGE_KEY) || 'auto';
  } catch(_) {
    return 'auto';
  }
}

export function isDarkActive() {
  const setting = getThemeSetting();
  if (setting === 'auto') {
    return darkQuery.matches;
  }
  return setting === 'dark';
}

export function applyTheme(setting) {
  try {
    localStorage.setItem(STORAGE_KEY, setting);
  } catch(_) {}

  const isDark = setting === 'auto' ? darkQuery.matches : setting === 'dark';
  document.documentElement.setAttribute('data-theme', isDark ? 'dark' : 'light');
  document.documentElement.style.colorScheme = isDark ? 'dark' : 'light';

  // Dispatch custom event so settings page or other listeners update immediately
  window.dispatchEvent(new CustomEvent('theme-change', { detail: { setting, isDark } }));
}

// Listen to OS-level theme changes automatically
darkQuery.addEventListener('change', () => {
  if (getThemeSetting() === 'auto') {
    applyTheme('auto');
  }
});
