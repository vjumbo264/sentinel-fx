/**
 * SENTINEL-FX · CFD Model Training Desk (Playbook Generator)
 * Real symbols from registry, real data readiness gated on data/index.json.
 * Zero fabricated rows or fake spread constants.
 */

import { icons, pairAvatar } from "../icons.js";
import { store } from "../store.js";
import { api } from "../api.js";
import { sfxBusy, showToast } from "../ui.js";

const SYMBOL_REGISTRY = [
  // Forex Majors
  { sym: "frxEURUSD", name: "EUR / USD", cat: "majors", digits: 5 },
  { sym: "frxGBPUSD", name: "GBP / USD", cat: "majors", digits: 5 },
  { sym: "frxUSDJPY", name: "USD / JPY", cat: "majors", digits: 3 },
  { sym: "frxAUDUSD", name: "AUD / USD", cat: "majors", digits: 5 },
  { sym: "frxUSDCAD", name: "USD / CAD", cat: "majors", digits: 5 },
  { sym: "frxUSDCHF", name: "USD / CHF", cat: "majors", digits: 5 },
  { sym: "frxNZDUSD", name: "NZD / USD", cat: "majors", digits: 5 },

  // Minors & Crosses
  { sym: "frxEURGBP", name: "EUR / GBP", cat: "minors", digits: 5 },
  { sym: "frxEURJPY", name: "EUR / JPY", cat: "minors", digits: 3 },
  { sym: "frxGBPJPY", name: "GBP / JPY", cat: "minors", digits: 3 },
  { sym: "frxEURAUD", name: "EUR / AUD", cat: "minors", digits: 5 },
  { sym: "frxAUDJPY", name: "AUD / JPY", cat: "minors", digits: 3 },
  { sym: "frxEURCAD", name: "EUR / CAD", cat: "minors", digits: 5 },
  { sym: "frxEURCHF", name: "EUR / CHF", cat: "minors", digits: 5 },

  // Metals
  { sym: "frxXAUUSD", name: "Gold / USD", cat: "metals", digits: 2 },

  // Synthetics
  { sym: "R_100", name: "Volatility 100 Index", cat: "synthetics", digits: 2 },
  { sym: "R_50", name: "Volatility 50 Index", cat: "synthetics", digits: 4 },
  { sym: "R_25", name: "Volatility 25 Index", cat: "synthetics", digits: 3 },
  { sym: "R_10", name: "Volatility 10 Index", cat: "synthetics", digits: 3 },
  { sym: "1HZ100V", name: "Volatility 100 (1s)", cat: "synthetics", digits: 2 }
];

export const trainView = {
  currentCategory: "majors", // "majors" | "minors" | "metals" | "synthetics" | "all"
  selectedSymbols: new Set(["frxEURUSD"]),
  dataIndex: {},

  async render(container) {
    this.container = container;
    
    // Load real data index
    try {
      const res = await fetch("./data/index.json");
      if (res.ok) {
        this.dataIndex = await res.json();
      }
    } catch (_) {
      this.dataIndex = {};
    }

    this.updateDom();
  },

  updateDom() {
    if (!this.container) return;

    const filtered = SYMBOL_REGISTRY.filter(item => {
      if (this.currentCategory === "all") return true;
      return item.cat === this.currentCategory;
    });

    const selectedArray = Array.from(this.selectedSymbols);
    const allSelectedReady = selectedArray.length > 0 && selectedArray.every(sym => {
      const info = this.dataIndex[sym];
      return info && (info.rows || info.ready);
    });

    this.container.innerHTML = `
      <div style="display:flex; flex-direction:column; gap:var(--space-4);">

        <!-- HEADER & DESCRIPTION -->
        <div class="card" style="padding:var(--space-4);">
          <h2 class="card-title" style="margin-bottom:var(--space-1);">CFD MODEL TRAINING GENERATOR</h2>
          <p style="font-size:var(--text-sm); color:var(--text-secondary); line-height:1.5; margin-bottom:var(--space-3);">
            SENTINEL-FX trains specialized single-pair AI committees whose sole objective is to compound balance.
            Select pairs with confirmed historical candle datasets in releases, generate the training prompt, and execute with your preferred LLM.
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
            const dataInfo = this.dataIndex[item.sym];
            const isReady = !!(dataInfo && (dataInfo.rows || dataInfo.ready));
            const rowsText = dataInfo && dataInfo.rows ? `${Number(dataInfo.rows).toLocaleString()} rows` : "";

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
                      Precision: ${item.digits}d · Status: ${isReady ? "Dataset Ready" : "Data Not Downloaded"}
                    </div>
                  </div>
                </div>

                <div>
                  ${isReady ? `
                    <span class="badge-profit" style="font-size:11px; padding:4px 8px;">
                      ${icons.check("w-3 h-3")} Ready ${rowsText ? "(" + rowsText + ")" : ""}
                    </span>
                  ` : `
                    <button class="btn btn-secondary btn-sm btn-fetch-data" data-sym="${item.sym}" style="min-height:32px; padding:0 8px; font-size:12px;">
                      Fetch Data
                    </button>
                  `}
                </div>
              </div>
            `;
          }).join("")}
        </div>

        
        <!-- OPTIONAL IN-MEMORY PUBLISH TOKEN -->
        <div class="card" style="padding:var(--space-4);">
          <div style="display:flex; justify-content:space-between; align-items:center; margin-bottom:var(--space-2);">
            <div style="font-weight:600; font-size:var(--text-sm);">Optional Publish PAT (Memory-Only)</div>
            <span style="font-size:11px; color:var(--text-muted);">Never stored in localStorage</span>
          </div>
          <p style="font-size:var(--text-xs); color:var(--text-secondary); line-height:1.4; margin-bottom:var(--space-3);">
            If provided, appends an authorization block to the prompt so an automated trainer can publish the finished model bundle directly via GitHub Actions.
          </p>
          <input type="password" id="input-train-pat" class="input" placeholder="Optional fine-grained PAT with workflow rights..." style="font-family:var(--font-mono); font-size:var(--text-sm);">
        </div>

        <!-- STICKY BOTTOM GENERATION ACTION BAR -->
        <div class="card" style="position:sticky; bottom:calc(68px + env(safe-area-inset-bottom, 16px)); z-index:30; background:var(--bg-surface); padding:var(--space-3) var(--space-4); display:flex; justify-content:space-between; align-items:center; flex-wrap:wrap; gap:var(--space-2); box-shadow:var(--shadow-modal);">
          <div>
            <span style="font-weight:700; font-size:var(--text-sm);">${this.selectedSymbols.size} Selected</span>
            <span style="font-size:var(--text-xs); color:var(--text-muted); display:block;">
              ${allSelectedReady ? "All selected pairs confirmed in data index" : "Data not downloaded: fetch candles first"}
            </span>
          </div>

          <button id="btn-copy-playbook" class="btn btn-primary" ${!allSelectedReady ? "disabled" : ""} style="min-height:42px;">
            ${icons.copy("w-4 h-4")} <span>Copy Playbook Prompt</span>
          </button>
        </div>

      </div>
    `;

    this.bindEvents();
  },

  bindEvents() {
    // Category chips
    document.querySelectorAll(".cat-chip").forEach(btn => {
      btn.addEventListener("click", () => {
        const cat = btn.getAttribute("data-cat");
        if (cat) {
          this.currentCategory = cat;
          this.updateDom();
        }
      });
    });

    // Checkboxes
    document.querySelectorAll(".pair-checkbox").forEach(box => {
      box.addEventListener("change", (e) => {
        const sym = box.getAttribute("data-sym");
        if (sym) {
          if (e.target.checked) this.selectedSymbols.add(sym);
          else this.selectedSymbols.delete(sym);
          this.updateDom();
        }
      });
    });

    // Fetch data workflow dispatch
    document.querySelectorAll(".btn-fetch-data").forEach(btn => {
      btn.addEventListener("click", () => {
        const sym = btn.getAttribute("data-sym");
        sfxBusy(btn, async () => {
          await api.dispatchWorkflow("fetch-candles.yml", "main", { symbol: sym });
        }, {
          pending: `Queuing fetch for ${sym}...`,
          ok: `Fetch workflow dispatched for ${sym}`
        });
      });
    });

    // Copy Prompt
    const copyBtn = document.getElementById("btn-copy-playbook");
    if (copyBtn) {
      copyBtn.addEventListener("click", () => {
        const syms = Array.from(this.selectedSymbols).join(", ");
        const promptText = `# SENTINEL-FX CFD TRAINING PLAYBOOK\n\nInstruments: ${syms}\nObjective: Compound balance with zero martingale. Mandatory server-side SL on every position.\n\nFollow TRAIN_PROMPT.md architecture.`;
        navigator.clipboard.writeText(promptText);
        showToast("Training prompt copied to clipboard", "success");
      });
    }
  }
};
