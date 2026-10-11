function getSvgDim(cls) {
  if (cls.includes("w-3") || cls.includes("icon-xs")) return 12;
  if (cls.includes("w-4") || cls.includes("icon-sm")) return 16;
  if (cls.includes("w-5") || cls.includes("icon-md")) return 20;
  if (cls.includes("w-6") || cls.includes("icon-lg")) return 24;
  if (cls.includes("w-8") || cls.includes("icon-xl")) return 32;
  if (cls.includes("w-10")) return 40;
  if (cls.includes("w-12") || cls.includes("icon-2xl")) return 48;
  return 20;
}

/**
 * SENTINEL-FX · Inline SVG Iconography & Pair Flag Badges
 * Precise 24x24 icons and dual-currency SVG avatars (no external images).
 */

export const icons = {
  lock: (cls = "w-4 h-4") => `
    <svg class="icon ${cls}" width="${getSvgDim(cls)}" height="${getSvgDim(cls)}" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
      <rect x="3" y="11" width="18" height="11" rx="2" ry="2"/>
      <path d="M7 11V7a5 5 0 0 1 10 0v4"/>
    </svg>
  `,

  logOut: (cls = "w-4 h-4") => `
    <svg class="icon ${cls}" width="${getSvgDim(cls)}" height="${getSvgDim(cls)}" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
      <path d="M9 21H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h4"/>
      <polyline points="16 17 21 12 16 7"/>
      <line x1="21" y1="12" x2="9" y2="12"/>
    </svg>
  `,

  sentinel: (cls = "w-5 h-5") => `
    <svg class="icon ${cls}" width="${getSvgDim(cls)}" height="${getSvgDim(cls)}" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
      <path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z"/>
      <path d="m9 12 2 2 4-4"/>
    </svg>
  `,

  home: (cls = "w-5 h-5") => `
    <svg class="icon ${cls}" width="${getSvgDim(cls)}" height="${getSvgDim(cls)}" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
      <path d="m3 9 9-7 9 7v11a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2z"/>
      <polyline points="9 22 9 12 15 12 15 22"/>
    </svg>
  `,

  trades: (cls = "w-5 h-5") => `
    <svg class="icon ${cls}" width="${getSvgDim(cls)}" height="${getSvgDim(cls)}" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
      <polyline points="22 7 13.5 15.5 8.5 10.5 2 17"/>
      <polyline points="16 7 22 7 22 13"/>
    </svg>
  `,

  chart: (cls = "w-5 h-5") => `
    <svg class="icon ${cls}" width="${getSvgDim(cls)}" height="${getSvgDim(cls)}" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
      <path d="M3 3v18h18"/>
      <path d="M7 16v-4"/>
      <path d="M7 12V8"/>
      <path d="M13 14v-2"/>
      <path d="M13 12v-5"/>
      <path d="M19 18v-8"/>
      <path d="M19 10V6"/>
    </svg>
  `,

  models: (cls = "w-5 h-5") => `
    <svg class="icon ${cls}" width="${getSvgDim(cls)}" height="${getSvgDim(cls)}" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
      <rect x="4" y="4" width="16" height="16" rx="2"/>
      <rect x="9" y="9" width="6" height="6"/>
      <line x1="9" y1="1" x2="9" y2="4"/>
      <line x1="15" y1="1" x2="15" y2="4"/>
      <line x1="9" y1="20" x2="9" y2="23"/>
      <line x1="15" y1="20" x2="15" y2="23"/>
      <line x1="20" y1="9" x2="23" y2="9"/>
      <line x1="20" y1="15" x2="23" y2="15"/>
      <line x1="1" y1="9" x2="4" y2="9"/>
      <line x1="1" y1="15" x2="4" y2="15"/>
    </svg>
  `,

  more: (cls = "w-5 h-5") => `
    <svg class="icon ${cls}" width="${getSvgDim(cls)}" height="${getSvgDim(cls)}" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
      <circle cx="12" cy="12" r="1"/>
      <circle cx="19" cy="12" r="1"/>
      <circle cx="5" cy="12" r="1"/>
    </svg>
  `,

  history: (cls = "w-5 h-5") => `
    <svg class="icon ${cls}" width="${getSvgDim(cls)}" height="${getSvgDim(cls)}" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
      <circle cx="12" cy="12" r="10"/>
      <polyline points="12 6 12 12 16 14"/>
    </svg>
  `,

  train: (cls = "w-5 h-5") => `
    <svg class="icon ${cls}" width="${getSvgDim(cls)}" height="${getSvgDim(cls)}" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
      <polygon points="13 2 3 14 12 14 11 22 21 10 12 10 13 2"/>
    </svg>
  `,

  upload: (cls = "w-5 h-5") => `
    <svg class="icon ${cls}" width="${getSvgDim(cls)}" height="${getSvgDim(cls)}" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
      <path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/>
      <polyline points="17 8 12 3 7 8"/>
      <line x1="12" y1="3" x2="12" y2="15"/>
    </svg>
  `,

  risk: (cls = "w-5 h-5") => `
    <svg class="icon ${cls}" width="${getSvgDim(cls)}" height="${getSvgDim(cls)}" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
      <path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z"/>
      <path d="M12 8v4"/>
      <path d="M12 16h.01"/>
    </svg>
  `,

  settings: (cls = "w-5 h-5") => `
    <svg class="icon ${cls}" width="${getSvgDim(cls)}" height="${getSvgDim(cls)}" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
      <circle cx="12" cy="12" r="3"/>
      <path d="M19.4 15a1.65 1.65 0 0 0 .33 1.82l.06.06a2 2 0 0 1 0 2.83 2 2 0 0 1-2.83 0l-.06-.06a1.65 1.65 0 0 0-1.82-.33 1.65 1.65 0 0 0-1 1.51V21a2 2 0 0 1-2 2 2 2 0 0 1-2-2v-.09A1.65 1.65 0 0 0 9 19.4a1.65 1.65 0 0 0-1.82.33l-.06.06a2 2 0 0 1-2.83 0 2 2 0 0 1 0-2.83l.06-.06a1.65 1.65 0 0 0 .33-1.82 1.65 1.65 0 0 0-1.51-1H3a2 2 0 0 1-2-2 2 2 0 0 1 2-2h.09A1.65 1.65 0 0 0 4.6 9a1.65 1.65 0 0 0-.33-1.82l-.06-.06a2 2 0 0 1 0-2.83 2 2 0 0 1 2.83 0l.06.06a1.65 1.65 0 0 0 1.82.33H9a1.65 1.65 0 0 0 1-1.51V3a2 2 0 0 1 2-2 2 2 0 0 1 2 2v.09a1.65 1.65 0 0 0 1 1.51 1.65 1.65 0 0 0 1.82-.33l.06-.06a2 2 0 0 1 2.83 0 2 2 0 0 1 0 2.83l-.06.06a1.65 1.65 0 0 0-.33 1.82V9a1.65 1.65 0 0 0 1.51 1H21a2 2 0 0 1 2 2 2 2 0 0 1-2 2h-.09a1.65 1.65 0 0 0-1.51 1z"/>
    </svg>
  `,

  refresh: (cls = "w-4 h-4") => `
    <svg class="icon ${cls}" width="${getSvgDim(cls)}" height="${getSvgDim(cls)}" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
      <polyline points="23 4 23 10 17 10"/>
      <polyline points="1 20 1 14 7 14"/>
      <path d="M3.51 9a9 9 0 0 1 14.85-3.36L23 10M1 14l4.64 4.36A9 9 0 0 0 20.49 15"/>
    </svg>
  `,

  play: (cls = "w-4 h-4") => `
    <svg class="icon ${cls}" width="${getSvgDim(cls)}" height="${getSvgDim(cls)}" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
      <polygon points="5 3 19 12 5 21 5 3"/>
    </svg>
  `,

  pause: (cls = "w-4 h-4") => `
    <svg class="icon ${cls}" width="${getSvgDim(cls)}" height="${getSvgDim(cls)}" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
      <rect x="6" y="4" width="4" height="16"/>
      <rect x="14" y="4" width="4" height="16"/>
    </svg>
  `,

  kill: (cls = "w-4 h-4") => `
    <svg class="icon ${cls}" width="${getSvgDim(cls)}" height="${getSvgDim(cls)}" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
      <polygon points="7.86 2 16.14 2 22 7.86 22 16.14 16.14 22 7.86 22 2 16.14 2 7.86 7.86 2"/>
      <line x1="12" y1="8" x2="12" y2="12"/>
      <line x1="12" y1="16" x2="12.01" y2="16"/>
    </svg>
  `,

  check: (cls = "w-4 h-4") => `
    <svg class="icon ${cls}" width="${getSvgDim(cls)}" height="${getSvgDim(cls)}" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
      <polyline points="20 6 9 17 4 12"/>
    </svg>
  `,

  x: (cls = "w-4 h-4") => `
    <svg class="icon ${cls}" width="${getSvgDim(cls)}" height="${getSvgDim(cls)}" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
      <line x1="18" y1="6" x2="6" y2="18"/>
      <line x1="6" y1="6" x2="18" y2="18"/>
    </svg>
  `,

  copy: (cls = "w-4 h-4") => `
    <svg class="icon ${cls}" width="${getSvgDim(cls)}" height="${getSvgDim(cls)}" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
      <rect x="9" y="9" width="13" height="13" rx="2" ry="2"/>
      <path d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1"/>
    </svg>
  `,

  chevronRight: (cls = "w-4 h-4") => `
    <svg class="icon ${cls}" width="${getSvgDim(cls)}" height="${getSvgDim(cls)}" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
      <polyline points="9 18 15 12 9 6"/>
    </svg>
  `,

  arrowUp: (cls = "w-3 h-3") => `
    <svg class="icon ${cls}" width="${getSvgDim(cls)}" height="${getSvgDim(cls)}" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
      <line x1="12" y1="19" x2="12" y2="5"/>
      <polyline points="5 12 12 5 19 12"/>
    </svg>
  `,

  arrowDown: (cls = "w-3 h-3") => `
    <svg class="icon ${cls}" width="${getSvgDim(cls)}" height="${getSvgDim(cls)}" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
      <line x1="12" y1="5" x2="12" y2="19"/>
      <polyline points="19 12 12 19 5 12"/>
    </svg>
  `,

  download: (cls = "w-4 h-4") => `
    <svg class="icon ${cls}" width="${getSvgDim(cls)}" height="${getSvgDim(cls)}" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
      <path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/>
      <polyline points="7 10 12 15 17 10"/>
      <line x1="12" y1="15" x2="12" y2="3"/>
    </svg>
  `,

  sun: (cls = "w-4 h-4") => `
    <svg class="icon ${cls}" width="${getSvgDim(cls)}" height="${getSvgDim(cls)}" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
      <circle cx="12" cy="12" r="5"/>
      <line x1="12" y1="1" x2="12" y2="3"/>
      <line x1="12" y1="21" x2="12" y2="23"/>
      <line x1="4.22" y1="4.22" x2="5.64" y2="5.64"/>
      <line x1="18.36" y1="18.36" x2="19.78" y2="19.78"/>
      <line x1="1" y1="12" x2="3" y2="12"/>
      <line x1="21" y1="12" x2="23" y2="12"/>
      <line x1="4.22" y1="19.78" x2="5.64" y2="18.36"/>
      <line x1="18.36" y1="5.64" x2="19.78" y2="4.22"/>
    </svg>
  `,

  moon: (cls = "w-4 h-4") => `
    <svg class="icon ${cls}" width="${getSvgDim(cls)}" height="${getSvgDim(cls)}" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
      <path d="M21 12.79A9 9 0 1 1 11.21 3 7 7 0 0 0 21 12.79z"/>
    </svg>
  `,

  autoTheme: (cls = "w-4 h-4") => `
    <svg class="icon ${cls}" width="${getSvgDim(cls)}" height="${getSvgDim(cls)}" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
      <rect x="2" y="3" width="20" height="14" rx="2" ry="2"/>
      <line x1="8" y1="21" x2="16" y2="21"/>
      <line x1="12" y1="17" x2="12" y2="21"/>
    </svg>
  `,

  alert: (cls = "w-4 h-4") => `
    <svg class="icon ${cls}" width="${getSvgDim(cls)}" height="${getSvgDim(cls)}" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
      <circle cx="12" cy="12" r="10"/>
      <line x1="12" y1="8" x2="12" y2="12"/>
      <line x1="12" y1="16" x2="12.01" y2="16"/>
    </svg>
  `
};

/**
 * Currency badge helper for forex & synthetic pair avatars (F4 redesign).
 * Single rounded chip with the FULL instrument code so nothing clips:
 *   frxEURUSD -> "EURUSD", frxXAUUSD -> "XAUUSD" (gold), R_100 -> "V100",
 *   1HZ100V   -> "1sV100". No overlapping circles, no cut-off letters.
 */
const CURRENCY_COLORS = {
  EUR: "#2563eb", GBP: "#7c3aed", USD: "#334155", JPY: "#dc2626",
  AUD: "#0891b2", CAD: "#b91c1c", CHF: "#475569", NZD: "#059669",
  XAU: "#b45309", XAG: "#64748b"
};

export function pairAvatar(symbol, size = 36) {
  const clean = String(symbol || "").replace(/^frx/, "").toUpperCase();
  let code = clean;
  let bg = "#2563eb";

  if (/^[A-Z]{6}$/.test(clean)) {
    code = clean;
    bg = CURRENCY_COLORS[clean.slice(0, 3)] || "#2563eb";
  } else if (clean.startsWith("R_")) {
    code = "V" + clean.slice(2); // Volatility index, e.g. R_100 -> V100
    bg = "#7c3aed";
  } else if (/^1HZ\d+V$/.test(clean)) {
    code = "1sV" + clean.replace(/^1HZ(\d+)V$/, "$1"); // 1-second volatility
    bg = "#0891b2";
  } else if (clean.startsWith("CRASH") || clean.startsWith("BOOM")) {
    code = clean;
    bg = clean.startsWith("CRASH") ? "#dc2626" : "#16a34a";
  }

  const width = Math.round(size * 1.6);
  const fontSize = Math.max(9, Math.round(size * 0.3));

  return `
    <div class="pair-avatar" title="${symbol}" style="min-width:${width}px; height:${size}px; font-size:${fontSize}px; background:${bg}; padding:0 7px;">
      ${code}
    </div>
  `;
}
