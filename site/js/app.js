import { BUILD_INFO } from "./version.js";
/**
 * SENTINEL-FX · Main Application Entrypoint
 * Orchestrates navigation shell, reactive store, mode management, and page views.
 */

import { icons } from "./icons.js";
import { themeController } from "./theme.js";
import { api } from "./api.js";
import { store } from "./store.js";
import { router } from "./router.js";
import { sfxBusy, showToast, showConfirmSheet, formatLagosTime } from "./ui.js";

// Page Views
import { loginView } from "./pages/login.js";
import { homeView } from "./pages/home.js";
import { tradesView } from "./pages/trades.js";
import { chartView } from "./pages/chart.js";
import { modelsView } from "./pages/models.js";
import { historyView } from "./pages/history.js";
import { trainView } from "./pages/train.js";
import { uploadView } from "./pages/upload.js";
import { riskView } from "./pages/risk.js";
import { settingsView } from "./pages/settings.js";

function mountIcons() {
  const mount = (id, html) => {
    const el = document.getElementById(id);
    if (el) el.innerHTML = html;
  };

  mount("brand-icon-root", icons.sentinel("w-6 h-6"));
  mount("rail-logo-root", icons.sentinel("w-6 h-6"));
  mount("refresh-icon-root", icons.refresh("w-4 h-4"));

  // Desktop rail icons
  mount("icon-dash", icons.home("w-5 h-5"));
  mount("icon-trades", icons.trades("w-5 h-5"));
  mount("icon-chart", icons.chart("w-5 h-5"));
  mount("icon-models", icons.models("w-5 h-5"));
  mount("icon-history", icons.history("w-5 h-5"));
  mount("icon-train", icons.train("w-5 h-5"));
  mount("icon-upload", icons.upload("w-5 h-5"));
  mount("icon-risk", icons.risk("w-5 h-5"));
  mount("icon-settings", icons.settings("w-5 h-5"));

  // Mobile bottom bar icons
  mount("m-icon-dash", icons.home("w-5 h-5"));
  mount("m-icon-trades", icons.trades("w-5 h-5"));
  mount("m-icon-chart", icons.chart("w-5 h-5"));
  mount("m-icon-models", icons.models("w-5 h-5"));
  mount("m-icon-more", icons.more("w-5 h-5"));

  // More drawer icons
  mount("m-sheet-icon-history", icons.history("w-6 h-6"));
  mount("m-sheet-icon-train", icons.train("w-6 h-6"));
  mount("m-sheet-icon-upload", icons.upload("w-6 h-6"));
  mount("m-sheet-icon-risk", icons.risk("w-6 h-6"));
  mount("m-sheet-icon-settings", icons.settings("w-5 h-5"));
  mount("m-sheet-chevron", icons.chevronRight("w-4 h-4 text-muted"));
  mount("icon-close-more", icons.x("w-5 h-5"));
}

function initShellEvents() {
  // Quick refresh button
  const refreshBtn = document.getElementById("btn-top-refresh");
  if (refreshBtn) {
    refreshBtn.addEventListener("click", () => {
      sfxBusy(refreshBtn, async () => {
        await store.fetchSnapshot();
      }, { pending: "Refreshing...", ok: "Data updated" });
    });
  }

  // Mode Pill switcher (DEMO vs REAL confirmation)
  const modePill = document.getElementById("top-mode-pill");
  if (modePill) {
    modePill.addEventListener("click", () => {
      const current = store.state.mode;
      const target = current === "demo" ? "real" : "demo";

      if (target === "real") {
        showConfirmSheet({
          title: "Switch to REAL CFD Trading?",
          description: "WARNING: Real mode executes live trades on your Deriv MT5 real account using real capital. The MT5 bot enforces strict server-side Stop Loss, but market risk applies.",
          confirmText: "Enable REAL Trading",
          confirmVariant: "danger",
          onConfirm: async () => {
            await api.saveSettings({ mode: "real" });
            store.state.mode = "real";
            store.notify();
          }
        });
      } else {
        showConfirmSheet({
          title: "Return to DEMO Mode?",
          description: "Switches execution back to demo risk-free environment ($10,000 balance).",
          confirmText: "Switch to Demo",
          confirmVariant: "primary",
          onConfirm: async () => {
            await api.saveSettings({ mode: "demo" });
            store.state.mode = "demo";
            store.notify();
          }
        });
      }
    });
  }

  // Mobile More Drawer
  const moreBtn = document.getElementById("btn-open-more");
  const moreBackdrop = document.getElementById("more-sheet-backdrop");
  const closeMoreBtn = document.getElementById("btn-close-more");

  if (moreBtn && moreBackdrop) {
    moreBtn.addEventListener("click", (e) => {
      e.preventDefault();
      moreBackdrop.classList.add("open");
    });
  }

  if (closeMoreBtn && moreBackdrop) {
    closeMoreBtn.addEventListener("click", () => {
      moreBackdrop.classList.remove("open");
    });
  }

  if (moreBackdrop) {
    moreBackdrop.addEventListener("click", (e) => {
      if (e.target === moreBackdrop) {
        moreBackdrop.classList.remove("open");
      }
    });
    // Close drawer when any sheet link is tapped
    moreBackdrop.querySelectorAll(".more-sheet-link").forEach((link) => {
      link.addEventListener("click", () => {
        moreBackdrop.classList.remove("open");
      });
    });
  }

  // Bottom nav tab navigation
  document.querySelectorAll(".bottom-tab:not(#btn-open-more)").forEach((tab) => {
    tab.addEventListener("click", () => {
      const route = tab.getAttribute("data-route");
      if (route) router.navigate(route);
    });
  });

  // Clock ticker in rail (Lagos time UTC+1)
  setInterval(() => {
    const clockEl = document.getElementById("rail-clock");
    if (clockEl) clockEl.textContent = formatLagosTime();
  }, 1000);
}

function bindStoreToShell() {
  store.subscribe((state) => {
    // Mode pill update
    const modePill = document.getElementById("top-mode-pill");
    const modeText = document.getElementById("mode-text");
    if (modePill && modeText) {
      modeText.textContent = state.mode.toUpperCase();
      if (state.mode === "real") {
        modePill.className = "mode-pill real";
      } else {
        modePill.className = "mode-pill demo";
      }
    }

    // Runner dot
    const runnerDot = document.getElementById("runner-dot");
    if (runnerDot) {
      runnerDot.className = state.runnerActive ? "dot-live" : "dot-paused";
    }
  });
}

function registerRoutes() {
  router.register("login", loginView);
  router.register("dash", homeView);
  router.register("trades", tradesView);
  router.register("chart", chartView);
  router.register("models", modelsView);
  router.register("history", historyView);
  router.register("train", trainView);
  router.register("upload", uploadView);
  router.register("risk", riskView);
  router.register("settings", settingsView);
}

// Bootstrap
window.addEventListener("DOMContentLoaded", () => {
  mountIcons();
  const railBuild = document.getElementById("rail-build-id"); if (railBuild) railBuild.textContent = BUILD_INFO.buildId;
  initShellEvents();
  bindStoreToShell();
  registerRoutes();
  router.handleRoute();
});

// Offline Network Banner Listener
function initNetworkListeners() {
  const showOfflineAlert = () => {
    let banner = document.getElementById("network-offline-banner");
    if (!banner) {
      banner = document.createElement("div");
      banner.id = "network-offline-banner";
      banner.style.cssText = "position:sticky; top:56px; z-index:45; background:var(--warning); color:#fff; text-align:center; padding:6px 12px; font-size:12px; font-weight:600;";
      banner.textContent = "Offline · Displaying cached terminal data. Reconnecting when internet is restored...";
      const header = document.querySelector(".top-bar");
      if (header && header.parentNode) {
        header.parentNode.insertBefore(banner, header.nextSibling);
      }
    }
  };

  const removeOfflineAlert = () => {
    const banner = document.getElementById("network-offline-banner");
    if (banner) banner.remove();
    showToast("Internet connection restored", "success");
    store.fetchSnapshot();
  };

  window.addEventListener("offline", showOfflineAlert);
  window.addEventListener("online", removeOfflineAlert);

  if (!navigator.onLine) {
    showOfflineAlert();
  }
}

window.addEventListener("DOMContentLoaded", initNetworkListeners);
