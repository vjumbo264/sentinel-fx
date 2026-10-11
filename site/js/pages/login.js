/**
 * SENTINEL-FX · Login Gate & PAT Verification Screen
 * Secure client-side PAT input, real /api/auth/check verification,
 * and safe localStorage persistence in try/catch. Never logs or prints tokens.
 */

import { icons } from "../icons.js";
import { api } from "../api.js";
import { store } from "../store.js";
import { router } from "../router.js";
import { sfxBusy, showToast } from "../ui.js";

export const loginView = {
  container: null,

  async render(container) {
    this.container = container;
    this.updateDom();
  },

  updateDom() {
    if (!this.container) return;

    const authError = store.state.authError;

    this.container.innerHTML = `
      <div style="min-height: calc(100vh - 120px); display:flex; align-items:center; justify-content:center; padding:var(--space-4);">
        <div class="card" style="width:100%; max-width:480px; padding:var(--space-6); box-shadow:var(--shadow-modal); border:1px solid var(--border-medium);">
          
          <!-- Logo & Header -->
          <div style="text-align:center; margin-bottom:var(--space-5);">
            <div style="display:inline-flex; align-items:center; justify-content:center; width:52px; height:52px; border-radius:var(--radius-md); background:var(--bg-surface-elevated); color:var(--accent-primary); margin-bottom:var(--space-3); border:1px solid var(--border-subtle);">
              ${icons.sentinel("w-8 h-8")}
            </div>
            <h1 style="font-family:var(--font-display); font-size:var(--text-xl); font-weight:800; letter-spacing:-0.02em; margin-bottom:var(--space-1);">
              SENTINEL-FX TERMINAL
            </h1>
            <p style="font-size:var(--text-sm); color:var(--text-secondary); line-height:1.4;">
              Autonomous CFD Forex Terminal · Secure Authorization
            </p>
          </div>

          <!-- Error Alert Banner (if 401 or failed attempt) -->
          ${authError ? `
            <div style="padding:10px 14px; border-radius:var(--radius-sm); background:var(--loss-subtle); border:1px solid var(--loss); color:var(--loss); font-size:var(--text-xs); line-height:1.4; margin-bottom:var(--space-4); display:flex; align-items:flex-start; gap:var(--space-2);">
              <span style="flex-shrink:0; margin-top:2px;">${icons.alert("w-4 h-4")}</span>
              <div>${authError}</div>
            </div>
          ` : ""}

          <!-- Explanation -->
          <div style="padding:12px; border-radius:var(--radius-sm); background:var(--bg-surface-elevated); margin-bottom:var(--space-4); font-size:var(--text-xs); color:var(--text-secondary); line-height:1.5;">
            <div style="font-weight:600; color:var(--text-primary); margin-bottom:4px; display:flex; align-items:center; gap:6px;">
              ${icons.lock("w-3 h-3 text-accent")} GitHub Personal Access Token (PAT)
            </div>
            Access requires a fine-grained or classic GitHub PAT with <b>push</b> or <b>admin</b> rights to <code>vjumbo264/sentinel-fx</code>.
            The token is verified via Worker <code>/api/auth/check</code> and stored locally on your device only.
          </div>

          <!-- Login Form -->
          <form id="login-form" style="display:flex; flex-direction:column; gap:var(--space-4);" onsubmit="return false;">
            <div>
              <label for="login-pat-input" style="display:block; font-size:var(--text-xs); font-weight:600; margin-bottom:6px; color:var(--text-secondary);">
                GitHub PAT
              </label>
              <input 
                type="password" 
                id="login-pat-input" 
                class="input" 
                placeholder="github_pat_..." 
                autocomplete="off" 
                spellcheck="false" 
                style="font-family:var(--font-mono); font-size:var(--text-sm); min-height:46px;"
              >
            </div>

            <!-- Validation Result Box -->
            <div id="login-feedback" style="display:none; font-size:var(--text-xs); padding:8px 12px; border-radius:var(--radius-sm);"></div>

            <!-- Submit Button -->
            <button type="submit" id="btn-login-submit" class="btn btn-primary" style="min-height:46px; font-weight:700; width:100%;">
              <span>Connect Terminal</span>
            </button>
          </form>

          <!-- Security Footnote -->
          <div style="margin-top:var(--space-5); text-align:center; font-size:11px; color:var(--text-muted); line-height:1.4;">
            Worker: <code>sentinel-fx-worker.vjumbo264.workers.dev</code><br>
            Zero server-side token storage · AES transport TLS 1.3
          </div>

        </div>
      </div>
    `;

    this.bindEvents();
  },

  bindEvents() {
    const form = document.getElementById("login-form");
    const input = document.getElementById("login-pat-input");
    const submitBtn = document.getElementById("btn-login-submit");
    const feedback = document.getElementById("login-feedback");

    const handleLogin = async () => {
      const val = input ? input.value.trim() : "";
      if (!val) {
        if (feedback) {
          feedback.style.display = "block";
          feedback.style.background = "var(--loss-subtle)";
          feedback.style.color = "var(--loss)";
          feedback.textContent = "Please enter your GitHub PAT to connect.";
        }
        return;
      }

      await sfxBusy(submitBtn, async () => {
        if (feedback) feedback.style.display = "none";
        
        api.setToken(val);
        const res = await api.checkAuth();

        if (res && res.ok) {
          store.setAuth(true, null);
          showToast(`Connected: push access confirmed on ${res.repo || "sentinel-fx"}`, "success");
          router.navigate("dash");
        } else {
          api.setToken("");
          store.setAuth(false, "Authorization check failed. Push permissions required.");
          throw new Error("Authorization check failed");
        }
      }, {
        pending: "Verifying with Worker...",
        ok: "Connected successfully",
        err: "Authentication failed"
      }).catch(err => {
        api.setToken("");
        if (feedback) {
          feedback.style.display = "block";
          feedback.style.background = "var(--loss-subtle)";
          feedback.style.color = "var(--loss)";
          feedback.textContent = `Error: ${err.message || "Invalid or unauthorized PAT"}`;
        }
      });
    };

    if (form) {
      form.addEventListener("submit", (e) => {
        e.preventDefault();
        handleLogin();
      });
    }

    if (submitBtn) {
      submitBtn.addEventListener("click", (e) => {
        e.preventDefault();
        handleLogin();
      });
    }
  }
};
