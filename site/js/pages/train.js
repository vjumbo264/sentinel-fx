/**
 * SENTINEL-FX · CFD Model Training Desk (Playbook Generator)
 * Replaces legacy binary options trainer with pure CFD architecture.
 * Multi-select pair selector, data release gating, and prompt generator.
 */

import { icons, pairAvatar } from "../icons.js";
import { store } from "../store.js";
import { api } from "../api.js";
import { sfxBusy, showToast } from "../ui.js";

const SYMBOL_REGISTRY = [
  // Majors
  { sym: "frxEURUSD", name: "EUR / USD", cat: "majors", digits: 5, spread: 15, ready: true, rows: "525,600 rows" },
  { sym: "frxGBPUSD", name: "GBP / USD", cat: "majors", digits: 5, spread: 20, ready: true, rows: "525,600 rows" },
  { sym: "frxUSDJPY", name: "USD / JPY", cat: "majors", digits: 3, spread: 18, ready: true, rows: "525,600 rows" },
  { sym: "frxAUDUSD", name: "AUD / USD", cat: "majors", digits: 5, spread: 16, ready: true, rows: "525,600 rows" },
  { sym: "frxUSDCAD", name: "USD / CAD", cat: "majors", digits: 5, spread: 19, ready: false },
  { sym: "frxUSDCHF", name: "USD / CHF", cat: "majors", digits: 5, spread: 18, ready: false },
  { sym: "frxNZDUSD", name: "NZD / USD", cat: "majors", digits: 5, spread: 22, ready: false },

  // Minors & Crosses
  { sym: "frxEURGBP", name: "EUR / GBP", cat: "minors", digits: 5, spread: 17, ready: false },
  { sym: "frxEURJPY", name: "EUR / JPY", cat: "minors", digits: 3, spread: 21, ready: false },
  { sym: "frxGBPJPY", name: "GBP / JPY", cat: "minors", digits: 3, spread: 28, ready: true, rows: "525,600 rows" },
  { sym: "frxEURAUD", name: "EUR / AUD", cat: "minors", digits: 5, spread: 24, ready: false },
  { sym: "frxAUDJPY", name: "AUD / JPY", cat: "minors", digits: 3, spread: 22, ready: false },
  { sym: "frxEURCAD", name: "EUR / CAD", cat: "minors", digits: 5, spread: 25, ready: false },
  { sym: "frxEURCHF", name: "EUR / CHF", cat: "minors", digits: 5, spread: 20, ready: false },

  // Metals
  { sym: "frxXAUUSD", name: "Gold / USD", cat: "metals", digits: 2, spread: 35, ready: false },

  // Synthetics
  { sym: "R_100", name: "Volatility 100 Index", cat: "synthetics", digits: 2, spread: 25, ready: true, rows: "525,600 rows" },
  { sym: "R_50", name: "Volatility 50 Index", cat: "synthetics", digits: 4, spread: 15, ready: true, rows: "525,600 rows" },
  { sym: "R_25", name: "Volatility 25 Index", cat: "synthetics", digits: 3, spread: 12, ready: false },
  { sym: "R_10", name: "Volatility 10 Index", cat: "synthetics", digits: 3, spread: 10, ready: false },
  { sym: "1HZ100V", name: "Volatility 100 (1s)", cat: "synthetics", digits: 2, spread: 25, ready: false }
];

export const trainView = {
  currentCategory: "majors", // 'majors' | 'minors' | 'metals' | 'synthetics' | 'all'
  selectedSymbols: new Set(["frxEURUSD"]),

  async render(container) {
    this.container = container;
    this.updateDom();
  },

  updateDom() {
    if (!this.container) return;

    const filtered = SYMBOL_REGISTRY.filter(item => {
      if (this.currentCategory === "all") return true;
      return item.cat === this.currentCategory;
    });

    const selectedArray = Array.from(this.selectedSymbols);
    const allSelectedReady = selectedArray.every(sym => {
      const found = SYMBOL_REGISTRY.find(s => s.sym === sym);
      return found && found.ready;
    });

    this.container.innerHTML = `
      <div style="display:flex; flex-direction:column; gap:var(--space-4);">

        <!-- HEADER & DESCRIPTION -->
        <div class="card" style="padding:var(--space-4);">
          <h2 class="card-title" style="margin-bottom:var(--space-1);">CFD MODEL TRAINING GENERATOR</h2>
          <p style="font-size:var(--text-sm); color:var(--text-secondary); line-height:1.5; margin-bottom:var(--space-3);">
            SENTINEL-FX trains specialized single-pair AI committees whose sole objective is to compound balance.
            Select pairs with confirmed historical candle datasets, generate the training prompt, and hand it to any AI model.
          </p>

          <!-- CATEGORY FILTER CHIPS -->
          <div style="display:flex; gap:var(--space-2); overflow-x:auto; padding-top:var(--space-2); border-top:1px solid var(--border-subtle);">
            <button class="btn btn-sm cat-chip ${this.currentCategory === "majors" ? "btn-primary" : "btn-ghost"}" data-cat="majors">
              Forex Majors
            </button>
            <button class="btn btn-sm cat-chip ${this.currentCategory === "minors" ? "btn-primary" : "btn-ghost"}" data-cat="minors">
              Minors &amp; Crosses
            </button>
            <button class="btn btn-sm cat-chip ${this.currentCategory === "metals" ? "btn-primary" : "btn-ghost"}" data-cat="metals">
              Metals (Gold)
            </button>
            <button class="btn btn-sm cat-chip ${this.currentCategory === "synthetics" ? "btn-primary" : "btn-ghost"}" data-cat="synthetics">
              Synthetics (24/7)
            </button>
            <button class="btn btn-sm cat-chip ${this.currentCategory === "all" ? "btn-primary" : "btn-ghost"}" data-cat="all">
              All Instruments
            </button>
          </div>
        </div>

        <!-- PAIR TABLE / LIST -->
        <div style="display:flex; flex-direction:column; gap:var(--space-2);">
          ${filtered.map(item => {
            const isChecked = this.selectedSymbols.has(item.sym);

            return `
              <div class="card" style="padding:12px 14px; display:flex; justify-content:space-between; align-items:center;">
                <div style="display:flex; align-items:center; gap:var(--space-3);">
                  <input type="checkbox" class="pair-checkbox" data-sym="${item.sym}" ${isChecked ? "checked" : ""} style="width:18px; height:18px; accent-color:var(--accent-primary); cursor:pointer;">
                  ${pairAvatar(item.sym, 34)}
                  <div>
                    <div style="display:flex; align-items:center; gap:6px;">
                      <span style="font-weight:700; font-size:var(--text-sm);">${item.name}</span>
                      <span style="font-size:11px; color:var(--text-muted); font-family:var(--font-mono);">${item.sym.replace(/^frx/, "")}</span>
                    </div>
                    <div style="font-size:var(--text-xs); color:var(--text-muted); margin-top:2px;">
                      Spread: ${item.spread} pts &bull; Precision: ${item.digits}d
                    </div>
                  </div>
                </div>

                <!-- Status & Action Button -->
                <div>
                  ${item.ready ? `
                    <span class="badge-profit" style="font-size:11px; padding:4px 8px;">
                      ${icons.check("w-3 h-3")} Ready (${item.rows})
                    </span>
                  ` : `
                    <button class="btn btn-secondary btn-sm btn-fetch-data" data-sym="${item.sym}" style="min-height:32px; padding:0 8px; font-size:12px;">
                      Fetch Candles
                    </button>
                  `}
                </div>
              </div>
            `;
          }).join("")}
        </div>

        <!-- STICKY BOTTOM GENERATION ACTION BAR -->
        <div class="card" style="position:sticky; bottom:calc(68px + env(safe-area-inset-bottom, 16px)); z-index:30; background:var(--bg-surface); padding:var(--space-3) var(--space-4); display:flex; justify-content:space-between; align-items:center; flex-wrap:wrap; gap:var(--space-2); box-shadow:var(--shadow-modal);">
          <div>
            <span style="font-weight:700; font-size:var(--text-sm);">${this.selectedSymbols.size} Selected</span>
            <span style="font-size:var(--text-xs); color:var(--text-muted); display:block;">
              ${allSelectedReady ? "All selected pairs data ready" : "Some pairs require candle downloads"}
            </span>
          </div>

          <div style="display:flex; gap:var(--space-2);">
            <button id="btn-copy-train-prompt" class="btn btn-primary btn-sm" ${allSelectedReady && this.selectedSymbols.size > 0 ? "" : "disabled"} style="min-height:38px;">
              ${icons.copy("w-4 h-4")} <span>Copy AI Training Prompt</span>
            </button>
          </div>
        </div>

      </div>
    `;

    this.bindEvents();
  },

  bindEvents() {
    // Category chips
    document.querySelectorAll(".cat-chip").forEach(btn => {
      btn.addEventListener("click", () => {
        this.currentCategory = btn.getAttribute("data-cat");
        this.updateDom();
      });
    });

    // Checkboxes
    document.querySelectorAll(".pair-checkbox").forEach(box => {
      box.addEventListener("change", (e) => {
        const sym = e.target.getAttribute("data-sym");
        if (e.target.checked) {
          this.selectedSymbols.add(sym);
        } else {
          this.selectedSymbols.delete(sym);
        }
        this.updateDom();
      });
    });

    // Fetch data single button
    document.querySelectorAll(".btn-fetch-data").forEach(btn => {
      btn.addEventListener("click", () => {
        const sym = btn.getAttribute("data-sym");
        sfxBusy(btn, async () => {
          await api.dispatchWorkflow("fetch-candles.yml", "main", { symbol: sym });
        }, { pending: `Fetching ${sym}...`, ok: "Fetch workflow queued" });
      });
    });

    // Copy Prompt Button
    const copyBtn = document.getElementById("btn-copy-train-prompt");
    if (copyBtn) {
      copyBtn.addEventListener("click", () => {
        sfxBusy(copyBtn, async () => {
          const prompt = this.generateCfdPrompt(Array.from(this.selectedSymbols));
          await navigator.clipboard.writeText(prompt);
        }, { pending: "Generating playbook...", ok: "Prompt copied to clipboard!" });
      });
    }
  },

  generateCfdPrompt(symbols) {
    const symList = symbols.join(", ");
    return `# SENTINEL-FX CFD AI Training Playbook v3
## Target Instruments: [${symList}]
Objective: Maximize Compounding Growth with Mandatory Server-Side Stop Loss.

You are training a specialized CFD AI model committee for SENTINEL-FX on Deriv MT5.
Your sole mission is to grow the allocated balance with zero blowups.

### Invariants:
1. Every trade MUST emit a valid server-side Stop Loss (SL) at order time.
2. Max risk per trade: 1.0% of allocated balance.
3. Hybrid Committee: Policy Node (BUY, SELL, HOLD, STAY_OUT) + Confluence Threshold >= 0.70.
4. Two-Stage News Filter: Halt entries 15 minutes prior to High-Impact calendar releases.
5. Walk-Forward Stability: Test against post-trained out-of-sample candles.

Produce the self-contained bundle \`.sfxmodel.zip\` with \`plan.py\` implementing \`evaluate_cfd_setup(candles, news_state)\`.`;
  }
};
