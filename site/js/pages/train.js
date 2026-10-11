/**
 * SENTINEL-FX · CFD Model Training Desk (Playbook Generator)
 * Real symbols from registry, real data readiness gated on data/index.json.
 * Zero fabricated rows or synthetic spread constants.
 *
 * F1: "Fetch Data" dispatches fetch-candles.yml with EXACTLY the inputs the
 *     workflow declares (symbols / granularity / mode), shows queued/running/
 *     finished inline on the row, and flips to Ready only when the data index
 *     confirms the asset. GitHub API errors surface as readable text.
 * F3: page state (active chip, selections, fetch status) survives poll ticks;
 *     poll notifications never rebuild this page (no store subscription).
 * F4: chip bar is a non-overlapping, nowrap, horizontally scrollable row with
 *     a fade edge; the active chip is scrolled into view.
 */

import { icons, pairAvatar } from "../icons.js";
import { api } from "../api.js";
import { sfxBusy, showToast } from "../ui.js";
import { getPageState, setPageState } from "../pageState.js";

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

const CATEGORIES = [
  ["majors", "Forex Majors"],
  ["minors", "Minors & Crosses"],
  ["metals", "Metals (Gold)"],
  ["synthetics", "Synthetics (24/7)"],
  ["all", "All Instruments"]
];

// F1: single source of truth for the workflow_dispatch contract.
// These names MUST match .github/workflows/fetch-candles.yml inputs.
const FETCH_WORKFLOW = "fetch-candles.yml";
const WF_IN = Object.freeze({ symbols: "symbols", granularity: "granularity", mode: "mode" });
const ACTIONS_URL = `https://github.com/vjumbo264/sentinel-fx/actions/workflows/${FETCH_WORKFLOW}`;

export const trainView = {
  dataIndex: {},

  ps() {
    return getPageState("train", {
      currentCategory: "majors",
      selectedSymbols: ["frxEURUSD"],
      fetchStatus: {} // sym -> { phase, text, url }
    });
  },

  async render(container) {
    this.container = container;
    await this.reloadIndex();

    const ps = this.ps();
    container.innerHTML = `
      <div style="display:flex; flex-direction:column; gap:var(--space-4);">

        <div class="card" style="padding:var(--space-4);">
          <h2 class="card-title" style="margin-bottom:var(--space-1);">CFD MODEL TRAINING GENERATOR</h2>
          <p style="font-size:var(--text-sm); color:var(--text-secondary); line-height:1.5; margin-bottom:var(--space-3);">
            SENTINEL-FX trains specialized single-pair AI committees whose sole objective is to compound balance.
            Select pairs with confirmed historical candle datasets in releases, generate the training prompt, and execute with your preferred LLM.
          </p>

          <!-- F4: non-overlapping chip bar, horizontal scroll + fade edge -->
          <div class="chip-fade" style="border-top:1px solid var(--border-subtle); padding-top:var(--space-2);">
            <div class="chip-scroll" id="train-chip-row">
              ${CATEGORIES.map(([cat, label]) => `
                <button class="btn btn-sm cat-chip ${ps.currentCategory === cat ? "btn-primary" : "btn-ghost"}" data-cat="${cat}">${label}</button>
              `).join("")}
            </div>
          </div>
        </div>

        <div id="train-rows" style="display:flex; flex-direction:column; gap:var(--space-4);"></div>
      </div>
    `;

    this.bindStaticEvents();
    this.updateRows();

    // Restore chip row scroll + bring active chip into view (F4)
    requestAnimationFrame(() => {
      const active = this.container.querySelector(".cat-chip.btn-primary");
      if (active) active.scrollIntoView({ behavior: "instant", inline: "center", block: "nearest" });
    });
  },

  async reloadIndex() {
    // The data index confirms which assets actually exist in the data-01 release.
    try {
      const res = await fetch("./data/index.json?ts=" + Date.now());
      this.dataIndex = res.ok ? await res.json() : {};
    } catch (_) {
      this.dataIndex = {};
    }
  },

  indexEntry(sym) {
    const e = this.dataIndex[sym];
    if (!e || !(e.rows || e.ready)) return null;
    const first = e.first_utc || e.first || null;
    const last = e.last_utc || e.last || null;
    return {
      rows: Number(e.rows || 0),
      first: first ? String(first).slice(0, 10) : null,
      last: last ? String(last).slice(0, 10) : null
    };
  },

  updateRows() {
    const rowsEl = this.container && this.container.querySelector("#train-rows");
    if (!rowsEl) return;
    const ps = this.ps();

    const filtered = SYMBOL_REGISTRY.filter(item =>
      ps.currentCategory === "all" ? true : item.cat === ps.currentCategory
    );

    const selected = new Set(ps.selectedSymbols);
    const allSelectedReady = selected.size > 0 && [...selected].every(sym => !!this.indexEntry(sym));

    rowsEl.innerHTML = `
      <div style="display:flex; flex-direction:column; gap:var(--space-2);">
        ${filtered.map(item => {
          const isChecked = selected.has(item.sym);
          const entry = this.indexEntry(item.sym);
          const st = ps.fetchStatus[item.sym];
          const rowsText = entry ? entry.rows.toLocaleString() + " rows" : "";
          const spanText = entry && entry.first && entry.last ? ` · ${entry.first} → ${entry.last}` : "";

          return `
            <div class="card" style="padding:12px 14px; display:flex; justify-content:space-between; align-items:center; gap:var(--space-2); flex-wrap:wrap;">
              <div style="display:flex; align-items:center; gap:var(--space-3); min-width:0;">
                <input type="checkbox" class="pair-checkbox" data-sym="${item.sym}" ${isChecked ? "checked" : ""} style="width:18px; height:18px; accent-color:var(--accent-primary); cursor:pointer; flex-shrink:0;">
                ${pairAvatar(item.sym, 32)}
                <div style="min-width:0;">
                  <div style="display:flex; align-items:center; gap:6px; flex-wrap:wrap;">
                    <span style="font-weight:700; font-size:var(--text-sm);">${item.name}</span>
                    <span style="font-size:11px; color:var(--text-muted); font-family:var(--font-mono);">${item.sym.replace(/^frx/, "")}</span>
                  </div>
                  <div style="font-size:var(--text-xs); color:var(--text-muted); margin-top:2px;">
                    Precision: ${item.digits}d · Status: ${entry ? "Dataset Ready" : "Data Not Downloaded"}
                  </div>
                </div>
              </div>

              <div style="display:flex; align-items:center; gap:8px; flex-shrink:0;">
                ${st && !entry ? `
                  <span id="fetch-status-${item.sym}" style="font-size:11px; color:var(--text-muted); display:inline-flex; align-items:center; gap:5px;">
                    ${st.phase === "queued" || st.phase === "in_progress" ? '<span class="btn-spinner" aria-hidden="true"></span>' : ""}
                    <a href="${st.url || ACTIONS_URL}" target="_blank" rel="noopener" style="color:inherit; text-decoration:underline;">${st.text}</a>
                  </span>
                ` : ""}
                ${entry ? `
                  <span class="badge-profit" style="font-size:11px; padding:4px 8px; white-space:nowrap;">
                    ${icons.check("w-3 h-3")} Ready (${rowsText}${spanText})
                  </span>
                ` : `
                  <button class="btn btn-secondary btn-sm btn-fetch-data" data-sym="${item.sym}" ${st && (st.phase === "queued" || st.phase === "in_progress") ? "disabled" : ""} style="min-height:32px; padding:0 8px; font-size:12px;">
                    Fetch Data
                  </button>
                `}
              </div>
            </div>
          `;
        }).join("")}
      </div>

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

      <div class="card" style="position:sticky; bottom:calc(68px + env(safe-area-inset-bottom, 16px)); z-index:30; background:var(--bg-surface); padding:var(--space-3) var(--space-4); display:flex; justify-content:space-between; align-items:center; flex-wrap:wrap; gap:var(--space-2); box-shadow:var(--shadow-modal);">
        <div>
          <span style="font-weight:700; font-size:var(--text-sm);">${selected.size} Selected</span>
          <span style="font-size:var(--text-xs); color:var(--text-muted); display:block;">
            ${allSelectedReady ? "All selected pairs confirmed in data index" : "Data not downloaded: fetch candles first"}
          </span>
        </div>
        <button id="btn-copy-playbook" class="btn btn-primary" ${!allSelectedReady ? "disabled" : ""} style="min-height:42px;">
          ${icons.copy("w-4 h-4")} <span>Copy Playbook Prompt</span>
        </button>
      </div>
    `;

    this.bindRowEvents();
  },

  setFetchStatus(sym, status) {
    const ps = this.ps();
    ps.fetchStatus[sym] = status;
    setPageState("train", { fetchStatus: ps.fetchStatus });
    this.updateRows();
  },

  async dispatchAndTrack(btn, sym) {
    const entry = this.indexEntry(sym);
    // F1: send exactly the declared workflow inputs — symbols (plural),
    // granularity, and mode (incremental when an asset already exists, else full).
    const inputs = {
      [WF_IN.symbols]: sym,
      [WF_IN.granularity]: "60",
      [WF_IN.mode]: entry ? "incremental" : "full"
    };

    const dispatchedAt = new Date().toISOString();
    await api.dispatchWorkflow(FETCH_WORKFLOW, "main", inputs);
    this.setFetchStatus(sym, { phase: "queued", text: "Queued on GitHub Actions", url: ACTIONS_URL });

    // Poll the workflow run state and mirror it inline on the row
    for (let i = 0; i < 40; i++) {
      await new Promise(r => setTimeout(r, 6000));
      let run = null;
      try { run = await api.getLatestWorkflowRun(FETCH_WORKFLOW, dispatchedAt); } catch (_) {}
      if (!run) continue;

      if (run.status === "queued" || run.status === "waiting") {
        this.setFetchStatus(sym, { phase: "queued", text: "Queued", url: run.html_url });
      } else if (run.status === "in_progress") {
        this.setFetchStatus(sym, { phase: "in_progress", text: "Running fetch…", url: run.html_url });
      } else if (run.status === "completed") {
        if (run.conclusion === "success") {
          this.setFetchStatus(sym, { phase: "completed", text: "Fetch finished — verifying index…", url: run.html_url });
          // F1: flip to Ready ONLY when the data index confirms the asset
          for (let j = 0; j < 10; j++) {
            await this.reloadIndex();
            if (this.indexEntry(sym)) {
              const ps = this.ps();
              delete ps.fetchStatus[sym];
              setPageState("train", { fetchStatus: ps.fetchStatus });
              this.updateRows();
              showToast(`${sym} dataset confirmed in release data-01`, "success");
              return;
            }
            await new Promise(r => setTimeout(r, 6000));
          }
          this.setFetchStatus(sym, { phase: "completed", text: "Run finished; index not updated yet — open Actions log", url: run.html_url });
        } else {
          this.setFetchStatus(sym, { phase: "failed", text: `Run ${run.conclusion || "failed"} — open Actions log`, url: run.html_url });
        }
        return;
      }
    }
    this.setFetchStatus(sym, { phase: "queued", text: "Still running — open Actions", url: ACTIONS_URL });
  },

  bindStaticEvents() {
    this.container.querySelectorAll(".cat-chip").forEach(btn => {
      btn.addEventListener("click", () => {
        const cat = btn.getAttribute("data-cat");
        if (!cat) return;
        setPageState("train", { currentCategory: cat });
        this.container.querySelectorAll(".cat-chip").forEach(b => {
          const on = b.getAttribute("data-cat") === cat;
          b.classList.toggle("btn-primary", on);
          b.classList.toggle("btn-ghost", !on);
        });
        // F4: keep the active chip visible inside the scrollable row
        btn.scrollIntoView({ behavior: "smooth", inline: "center", block: "nearest" });
        this.updateRows();
      });
    });
  },

  bindRowEvents() {
    this.container.querySelectorAll(".pair-checkbox").forEach(box => {
      box.addEventListener("change", (e) => {
        const sym = box.getAttribute("data-sym");
        const ps = this.ps();
        const set = new Set(ps.selectedSymbols);
        if (e.target.checked) set.add(sym); else set.delete(sym);
        setPageState("train", { selectedSymbols: [...set] });
        this.updateRows();
      });
    });

    this.container.querySelectorAll(".btn-fetch-data").forEach(btn => {
      btn.addEventListener("click", () => {
        const sym = btn.getAttribute("data-sym");
        sfxBusy(btn, () => this.dispatchAndTrack(btn, sym), {
          pending: `Queuing ${sym}...`,
          ok: `Fetch dispatched for ${sym} — tracking run on the row`
        }).catch(() => {});
      });
    });

    const copyBtn = this.container.querySelector("#btn-copy-playbook");
    if (copyBtn) {
      copyBtn.addEventListener("click", () => {
        const syms = this.ps().selectedSymbols.join(", ");
        const promptText = `# SENTINEL-FX CFD TRAINING PLAYBOOK\n\nInstruments: ${syms}\nObjective: Compound balance with zero martingale. Mandatory server-side SL on every position.\n\nFollow TRAIN_PROMPT.md architecture.`;
        navigator.clipboard.writeText(promptText);
        showToast("Training prompt copied to clipboard", "success");
      });
    }
  }
};
