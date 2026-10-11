/**
 * SENTINEL-FX · Shared UI Helpers & Button Feedback Manager
 * Strict single-flight execution, tactile button feedback, accessible sheets & formatters.
 */

import { icons } from "./icons.js";

/**
 * Shared Button Feedback Helper (sfxBusy)
 * Disables button, shows spinner + status, prevents repeated presses,
 * and surfaces a clean feedback toast upon completion or failure.
 */
export async function sfxBusy(btn, work, opts = {}) {
  if (!btn) return;
  if (btn.dataset.busy === "1") return; // double-press guard

  btn.dataset.busy = "1";
  const origHtml = btn.innerHTML;
  btn.disabled = true;

  const pendingText = opts.pending || "Working...";
  btn.innerHTML = `
    <span class="btn-spinner" aria-hidden="true"></span>
    <span>${pendingText}</span>
  `;

  try {
    const result = await work();
    showToast(opts.ok || "Action completed", "success");
    return result;
  } catch (err) {
    const msg = opts.err ? `${opts.err}: ${err.message || err}` : (err.message || String(err));
    showToast(msg, "error");
    throw err;
  } finally {
    btn.dataset.busy = "";
    btn.disabled = false;
    btn.innerHTML = origHtml;
  }
}

/**
 * Accessible Toast Manager
 */
export function showToast(message, type = "info", duration = 4000) {
  let root = document.getElementById("toast-root");
  if (!root) {
    root = document.createElement("div");
    root.id = "toast-root";
    root.setAttribute("role", "status");
    root.setAttribute("aria-live", "polite");
    document.body.appendChild(root);
  }

  const toast = document.createElement("div");
  toast.className = `toast toast-${type}`;

  let iconHtml = icons.sentinel("w-4 h-4 text-accent");
  if (type === "success") iconHtml = icons.check("w-4 h-4 text-profit");
  if (type === "error") iconHtml = icons.alert("w-4 h-4 text-loss");

  toast.innerHTML = `
    <div style="flex-shrink:0;">${iconHtml}</div>
    <div style="flex:1; line-height:1.4;">${escapeHtml(message)}</div>
  `;

  root.appendChild(toast);

  const timeoutId = setTimeout(() => {
    toast.style.transition = "opacity 0.25s ease, transform 0.25s ease";
    toast.style.opacity = "0";
    toast.style.transform = "translateY(8px)";
    setTimeout(() => toast.remove(), 260);
  }, duration);

  toast.addEventListener("click", () => {
    clearTimeout(timeoutId);
    toast.remove();
  });
}

/**
 * Accessible Confirm Sheet / Dialog
 */
export function showConfirmSheet({
  title,
  description,
  confirmText = "Confirm",
  confirmVariant = "primary", // 'primary' | 'danger'
  onConfirm
}) {
  return new Promise((resolve) => {
    const backdrop = document.createElement("div");
    backdrop.className = "sheet-backdrop";
    backdrop.setAttribute("role", "dialog");
    backdrop.setAttribute("aria-modal", "true");

    const confirmBtnClass = confirmVariant === "danger" ? "btn-danger" : "btn-primary";

    backdrop.innerHTML = `
      <div class="sheet-container">
        <div class="sheet-handle"></div>
        <div style="margin-bottom: var(--space-4);">
          <h3 style="font-family:var(--font-display); font-size:var(--text-lg); font-weight:700; margin-bottom:var(--space-2);">${escapeHtml(title)}</h3>
          <p style="font-size:var(--text-sm); color:var(--text-secondary); line-height:1.5;">${escapeHtml(description)}</p>
        </div>
        <div style="display:flex; gap:var(--space-3); margin-top:var(--space-5);">
          <button id="sheet-cancel-btn" class="btn btn-secondary" style="flex:1;">Cancel</button>
          <button id="sheet-confirm-btn" class="btn ${confirmBtnClass}" style="flex:1;">${escapeHtml(confirmText)}</button>
        </div>
      </div>
    `;

    document.body.appendChild(backdrop);
    requestAnimationFrame(() => backdrop.classList.add("open"));

    const close = (confirmed = false) => {
      backdrop.classList.remove("open");
      setTimeout(() => {
        backdrop.remove();
        resolve(confirmed);
      }, 250);
    };

    const cancelBtn = backdrop.querySelector("#sheet-cancel-btn");
    const confirmBtn = backdrop.querySelector("#sheet-confirm-btn");

    cancelBtn.addEventListener("click", () => close(false));
    confirmBtn.addEventListener("click", async () => {
      if (onConfirm) {
        await sfxBusy(confirmBtn, onConfirm, { pending: "Processing..." });
      }
      close(true);
    });

    backdrop.addEventListener("click", (e) => {
      if (e.target === backdrop) close(false);
    });

    const keyHandler = (e) => {
      if (e.key === "Escape") {
        document.removeEventListener("keydown", keyHandler);
        close(false);
      }
    };
    document.addEventListener("keydown", keyHandler);
  });
}

/**
 * Format Currency (USD default)
 */
export function formatCurrency(amount, currency = "USD") {
  if (amount === null || amount === undefined || isNaN(amount)) return "—";
  return new Intl.NumberFormat("en-US", {
    style: "currency",
    currency,
    minimumFractionDigits: 2,
    maximumFractionDigits: 2
  }).format(amount);
}

/**
 * Format Pips
 */
export function formatPips(pips) {
  if (pips === null || pips === undefined || isNaN(pips)) return "0.0 pips";
  const sign = pips > 0 ? "+" : "";
  return `${sign}${Number(pips).toFixed(1)} pips`;
}

/**
 * Format Lots
 */
export function formatLots(volume) {
  if (!volume || isNaN(volume)) return "0.01 lots";
  return `${Number(volume).toFixed(2)} lots`;
}

/**
 * Format Percent
 */
export function formatPercent(pct) {
  if (pct === null || pct === undefined || isNaN(pct)) return "0.00%";
  const sign = pct > 0 ? "+" : "";
  return `${sign}${Number(pct).toFixed(2)}%`;
}

/**
 * Format Lagos Time (UTC+1)
 */
export function formatLagosTime(dateInput = new Date()) {
  const d = typeof dateInput === "string" ? new Date(dateInput) : dateInput;
  if (isNaN(d.getTime())) return "—";
  return new Intl.DateTimeFormat("en-GB", {
    timeZone: "Africa/Lagos",
    hour: "2-digit",
    minute: "2-digit",
    second: "2-digit",
    hour12: false
  }).format(d);
}

export function formatLagosDate(dateInput = new Date()) {
  const d = typeof dateInput === "string" ? new Date(dateInput) : dateInput;
  if (isNaN(d.getTime())) return "—";
  return new Intl.DateTimeFormat("en-GB", {
    timeZone: "Africa/Lagos",
    year: "numeric",
    month: "short",
    day: "numeric"
  }).format(d);
}

/**
 * Escape HTML
 */
export function escapeHtml(str) {
  if (!str) return "";
  return String(str)
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&#39;");
}
