/**
 * SENTINEL-FX · Theme Controller
 * Automatic OS/browser light & dark mode via prefers-color-scheme.
 * Switches LIVE on system change without page reload.
 */

class ThemeController {
  constructor() {
    this.storageKey = "sentinel_theme";
    this.mediaQuery = window.matchMedia("(prefers-color-scheme: dark)");
    this.currentSetting = this.loadPreference(); // 'auto' | 'light' | 'dark'
    this.listeners = new Set();

    // Listen for live system theme changes
    if (this.mediaQuery.addEventListener) {
      this.mediaQuery.addEventListener("change", () => {
        if (this.currentSetting === "auto") {
          this.applyTheme();
        }
      });
    }

    this.applyTheme();
  }

  loadPreference() {
    try {
      return localStorage.getItem(this.storageKey) || "auto";
    } catch (_) {
      return "auto";
    }
  }

  savePreference(pref) {
    this.currentSetting = pref;
    try {
      localStorage.setItem(this.storageKey, pref);
    } catch (_) {}
    this.applyTheme();
  }

  isDark() {
    if (this.currentSetting === "dark") return true;
    if (this.currentSetting === "light") return false;
    return this.mediaQuery.matches;
  }

  applyTheme() {
    const root = document.documentElement;
    const isDark = this.isDark();

    if (this.currentSetting === "auto") {
      root.removeAttribute("data-theme");
    } else {
      root.setAttribute("data-theme", this.currentSetting);
    }

    // Update browser theme-color meta tag for Android top bar
    const metaTheme = document.querySelector('meta[name="theme-color"]:not([media])');
    if (metaTheme) {
      metaTheme.setAttribute("content", isDark ? "#080c14" : "#f8fafc");
    }

    // Notify listeners (e.g. lightweight-charts)
    const event = new CustomEvent("sentinel-theme-change", {
      detail: { isDark, theme: isDark ? "dark" : "light", setting: this.currentSetting }
    });
    window.dispatchEvent(event);
    this.listeners.forEach(fn => {
      try { fn(isDark); } catch (_) {}
    });
  }

  onChange(callback) {
    this.listeners.add(callback);
    return () => this.listeners.delete(callback);
  }
}

export const themeController = new ThemeController();
