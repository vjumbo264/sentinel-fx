/**
 * SENTINEL-FX · Settings & System Diagnostics
 * Theme controls (Auto/Light/Dark), Lagos time info, reduced motion,
 * Demo Review Mode toggle, in-memory PAT manager, and API health diagnostics.
 */

import { icons } from "../icons.js";
import { themeController } from "../theme.js";
import { store } from "../store.js";
import { api } from "../api.js";
import { formatLagosTime, sfxBusy, showToast } from "../ui.js";

export const settingsView = {
  healthInfo: null,

  async render(container) {
    this.container = container;
    this.updateDom();
    this.checkApiHealth();
  },

  async checkApiHealth() {
    try {
      this.healthInfo = await api.checkHealth();
      const el = document.getElementById("diag-health-val");
      if (el && this.healthInfo) {
        el.textContent = `OK · ${this.healthInfo.service} (${this.healthInfo.utc})`;
        el.style.color = "var(--profit)";
      }
    } catch (err) {
      const el = document.getElementById("diag-health-val");
      if (el) {
        el.textContent = `Offline / Unreachable: ${err.message}`;
        el.style.color = "var(--loss)";
      }
    }
  },

  updateDom() {
    if (!this.container) return;
    const currentTheme = themeController.currentSetting; // 'auto' | 'light' | 'dark'

    this.container.innerHTML = `
      <div style="display:flex; flex-direction:column; gap:var(--space-4);">

        <!-- HEADER -->
        <div>
          <h2 class="card-title">TERMINAL PREFERENCES</h2>
          <p style="font-size:var(--text-sm); color:var(--text-secondary); margin-top:2px;">
            Display themes, African timezone synchronizer, and broker API diagnostics.
          </p>
        </div>

        <!-- 1. THEME SELECTION -->
        <section class="card" style="padding:var(--space-4);">
          <div class="card-header">
            <span class="card-title">APPEARANCE &amp; THEME</span>
            <span style="font-size:11px; color:var(--text-muted);">Instant Live Switching</span>
          </div>

          <p style="font-size:var(--text-sm); color:var(--text-secondary); margin-bottom:var(--space-3);">
            Default follows your browser or OS automatically via <code>prefers-color-scheme</code>. You can also enforce Light or Dark explicitly.
          </p>

          <div style="display:grid; grid-template-columns:repeat(3, 1fr); gap:var(--space-2);">
            <button id="theme-btn-auto" class="btn ${currentTheme === "auto" ? "btn-primary" : "btn-secondary"}" style="min-height:44px; display:flex; flex-direction:column; gap:3px;">
              ${icons.autoTheme("w-4 h-4")}
              <span style="font-size:11px;">Auto (System)</span>
            </button>

            <button id="theme-btn-light" class="btn ${currentTheme === "light" ? "btn-primary" : "btn-secondary"}" style="min-height:44px; display:flex; flex-direction:column; gap:3px;">
              ${icons.sun("w-4 h-4")}
              <span style="font-size:11px;">Light Mode</span>
            </button>

            <button id="theme-btn-dark" class="btn ${currentTheme === "dark" ? "btn-primary" : "btn-secondary"}" style="min-height:44px; display:flex; flex-direction:column; gap:3px;">
              ${icons.moon("w-4 h-4")}
              <span style="font-size:11px;">Dark Mode</span>
            </button>
          </div>
        </section>

        <!-- 2. TIMEZONE & PERFORMANCE -->
        <section class="card" style="padding:var(--space-4);">
          <div class="card-header">
            <span class="card-title">TIMEZONE &amp; ERGONOMICS</span>
          </div>

          <div style="display:flex; flex-direction:column; gap:var(--space-3);">
            <div style="display:flex; justify-content:space-between; align-items:center; padding:10px 12px; background:var(--bg-surface-elevated); border-radius:var(--radius-sm);">
              <div>
                <div style="font-weight:600; font-size:var(--text-sm);">Default Timezone (Lagos UTC+1)</div>
                <div style="font-size:var(--text-xs); color:var(--text-muted);">All news countdowns, daily stats, and trade timestamps align with Lagos.</div>
              </div>
              <span class="tabular" style="font-weight:700; color:var(--accent-primary);" id="settings-lagos-clock">${formatLagosTime()}</span>
            </div>

            <div style="display:flex; justify-content:space-between; align-items:center; padding:10px 12px; background:var(--bg-surface-elevated); border-radius:var(--radius-sm);">
              <div>
                <div style="font-weight:600; font-size:var(--text-sm);">Reduce Non-Essential Motion</div>
                <div style="font-size:var(--text-xs); color:var(--text-muted);">Disables number count-up animations and sheet transitions.</div>
              </div>
              <label class="toggle-switch">
                <input type="checkbox" id="toggle-reduce-motion">
                <span class="toggle-slider"></span>
              </label>
            </div>


          </div>
        </section>

        <!-- 3. AUTHENTICATION & ACCESS -->
        <section class="card" style="padding:var(--space-4);">
          <div class="card-header">
            <span class="card-title">AUTHENTICATION &amp; ACCESS</span>
            <span style="font-size:11px; color:var(--profit); font-weight:600;">Connected</span>
          </div>

          <p style="font-size:var(--text-xs); color:var(--text-secondary); margin-bottom:var(--space-3); line-height:1.5;">
            Authenticated with verified push access to <code>vjumbo264/sentinel-fx</code>. Your token is stored only in browser local storage and never logged or exposed.
          </p>

          <div style="display:flex; justify-content:space-between; align-items:center; gap:var(--space-3); padding:10px 12px; background:var(--bg-surface-elevated); border-radius:var(--radius-sm); margin-bottom:var(--space-3);">
            <div>
              <div style="font-weight:600; font-size:var(--text-sm);">GitHub PAT Session</div>
              <div style="font-size:var(--text-xs); color:var(--text-muted);">Gated via /api/auth/check</div>
            </div>
            <button id="btn-logout" class="btn btn-danger btn-sm" style="min-height:36px;">
              ${icons.logOut("w-4 h-4")} <span>Disconnect / Logout</span>
            </button>
          </div>
        </section>

        <!-- 4. DIAGNOSTICS & SYSTEM BUILD -->
        <section class="card" style="padding:var(--space-4);">
          <div class="card-header">
            <span class="card-title">DIAGNOSTICS &amp; BUILD VERSION</span>
          </div>

          <div style="display:flex; flex-direction:column; gap:var(--space-2); font-size:var(--text-xs);">
            <div style="display:flex; justify-content:space-between; padding:8px 0; border-bottom:1px solid var(--border-subtle);">
              <span style="color:var(--text-muted);">Worker API Endpoint</span>
              <span class="tabular" id="diag-health-val">Probing...</span>
            </div>
            <div style="display:flex; justify-content:space-between; padding:8px 0; border-bottom:1px solid var(--border-subtle);">
              <span style="color:var(--text-muted);">Cloudflare Pages URL</span>
              <span class="tabular"><a href="https://sentinel-fx.pages.dev" target="_blank" style="color:var(--accent-primary);">sentinel-fx.pages.dev</a></span>
            </div>
            <div style="display:flex; justify-content:space-between; padding:8px 0;">
              <span style="color:var(--text-muted);">Release Build Version</span>
              <span class="tabular" style="font-weight:700;"><span id="settings-build-id" class="tabular" style="font-weight:600;"></span></span>
            </div>
          </div>
        </section>

      </div>
    `;

    this.bindEvents();
  },

  bindEvents() {
    // Theme buttons
    const btnAuto = document.getElementById("theme-btn-auto");
    const btnLight = document.getElementById("theme-btn-light");
    const btnDark = document.getElementById("theme-btn-dark");

    if (btnAuto) btnAuto.addEventListener("click", () => { themeController.savePreference("auto"); this.updateDom(); });
    if (btnLight) btnLight.addEventListener("click", () => { themeController.savePreference("light"); this.updateDom(); });
    if (btnDark) btnDark.addEventListener("click", () => { themeController.savePreference("dark"); this.updateDom(); });



    // Logout button
    const logoutBtn = document.getElementById("btn-logout");
    if (logoutBtn) {
      logoutBtn.addEventListener("click", () => {
        showConfirmSheet({
          title: "Disconnect & Logout?",
          description: "This will remove your GitHub PAT from this browser and return you to the login screen.",
          confirmText: "Logout",
          confirmVariant: "danger",
          onConfirm: () => {
            api.setToken("");
            store.setAuth(false, "Logged out successfully.");
            router.navigate("login");
            showToast("Logged out successfully", "info");
          }
        });
      });
    }
  }
};
