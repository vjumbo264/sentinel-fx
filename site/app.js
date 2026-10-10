/**
 * SENTINEL-FX Control Terminal (site/app.js)
 * Modern fintech dashboard for autonomous multi-pair trading.
 */
'use strict';

const API_BASE = "https://sentinel-fx-worker.vjumbo264.workers.dev";
const REPO = "vjumbo264/sentinel-fx";

let PAT = localStorage.getItem("sentinel_pat") || "";
let STATE = null;
let chart = null, candleSeries = null, wsPub = null, curPair = "R_100";
let chartPairs = [], curChartCategory = "volatility";
let curNewsFilter = "all", curPairsFilter = "all", curTrainFilter = "all";
let lastCandles = [], chartRO = null, chartTimer = null, chartRetry = 0;
let pendingModelFile = null, pendingModelData = null;

const PAIR_METADATA = {
  // Volatility Indices (24/7)
  "R_10": { name: "Volatility 10 Index", cat: "volatility", isSynth: true, minDur: "5s", defaultDur: 60, defaultUnit: "s" },
  "R_25": { name: "Volatility 25 Index", cat: "volatility", isSynth: true, minDur: "5s", defaultDur: 60, defaultUnit: "s" },
  "R_50": { name: "Volatility 50 Index", cat: "volatility", isSynth: true, minDur: "5s", defaultDur: 60, defaultUnit: "s" },
  "R_75": { name: "Volatility 75 Index", cat: "volatility", isSynth: true, minDur: "5s", defaultDur: 60, defaultUnit: "s" },
  "R_100": { name: "Volatility 100 Index", cat: "volatility", isSynth: true, minDur: "5s", defaultDur: 60, defaultUnit: "s" },
  // 1-Second Volatility Indices (24/7)
  "1HZ10V": { name: "Volatility 10 (1s) Index", cat: "volatility_1s", isSynth: true, minDur: "5s", defaultDur: 60, defaultUnit: "s" },
  "1HZ25V": { name: "Volatility 25 (1s) Index", cat: "volatility_1s", isSynth: true, minDur: "5s", defaultDur: 60, defaultUnit: "s" },
  "1HZ50V": { name: "Volatility 50 (1s) Index", cat: "volatility_1s", isSynth: true, minDur: "5s", defaultDur: 60, defaultUnit: "s" },
  "1HZ75V": { name: "Volatility 75 (1s) Index", cat: "volatility_1s", isSynth: true, minDur: "5s", defaultDur: 60, defaultUnit: "s" },
  "1HZ100V": { name: "Volatility 100 (1s) Index", cat: "volatility_1s", isSynth: true, minDur: "5s", defaultDur: 60, defaultUnit: "s" },
  "1HZ150V": { name: "Volatility 150 (1s) Index", cat: "volatility_1s", isSynth: true, minDur: "5s", defaultDur: 60, defaultUnit: "s" },
  "1HZ250V": { name: "Volatility 250 (1s) Index", cat: "volatility_1s", isSynth: true, minDur: "5s", defaultDur: 60, defaultUnit: "s" },
  "1HZ300V": { name: "Volatility 300 (1s) Index", cat: "volatility_1s", isSynth: true, minDur: "5s", defaultDur: 60, defaultUnit: "s" },
  // Forex Pairs (Intraday floor >= 15m)
  "frxEURUSD": { name: "EUR / USD", cat: "forex", isSynth: false, minDur: "15m", defaultDur: 15, defaultUnit: "m" },
  "frxGBPUSD": { name: "GBP / USD", cat: "forex", isSynth: false, minDur: "15m", defaultDur: 15, defaultUnit: "m" },
  "frxUSDJPY": { name: "USD / JPY", cat: "forex", isSynth: false, minDur: "15m", defaultDur: 15, defaultUnit: "m" },
  "frxAUDUSD": { name: "AUD / USD", cat: "forex", isSynth: false, minDur: "15m", defaultDur: 15, defaultUnit: "m" },
  "frxUSDCAD": { name: "USD / CAD", cat: "forex", isSynth: false, minDur: "15m", defaultDur: 15, defaultUnit: "m" },
  "frxUSDCHF": { name: "USD / CHF", cat: "forex", isSynth: false, minDur: "15m", defaultDur: 15, defaultUnit: "m" },
  "frxNZDUSD": { name: "NZD / USD", cat: "forex", isSynth: false, minDur: "15m", defaultDur: 15, defaultUnit: "m" },
  "frxEURGBP": { name: "EUR / GBP", cat: "forex", isSynth: false, minDur: "15m", defaultDur: 15, defaultUnit: "m" },
  "frxEURJPY": { name: "EUR / JPY", cat: "forex", isSynth: false, minDur: "15m", defaultDur: 15, defaultUnit: "m" },
  "frxGBPJPY": { name: "GBP / JPY", cat: "forex", isSynth: false, minDur: "15m", defaultDur: 15, defaultUnit: "m" },
  "frxEURAUD": { name: "EUR / AUD", cat: "forex", isSynth: false, minDur: "15m", defaultDur: 15, defaultUnit: "m" },
  "frxAUDJPY": { name: "AUD / JPY", cat: "forex", isSynth: false, minDur: "15m", defaultDur: 15, defaultUnit: "m" },
  "frxEURCAD": { name: "EUR / CAD", cat: "forex", isSynth: false, minDur: "15m", defaultDur: 15, defaultUnit: "m" },
  "frxEURCHF": { name: "EUR / CHF", cat: "forex", isSynth: false, minDur: "15m", defaultDur: 15, defaultUnit: "m" },
};

function $(id) { return document.getElementById(id); }

async function api(path, opts = {}) {
  const headers = Object.assign({
    "Authorization": `Bearer ${PAT}`,
    "Content-Type": "application/json"
  }, opts.headers || {});
  const res = await fetch(`${API_BASE}${path}`, {
    method: opts.method || "GET",
    headers,
    body: opts.body ? JSON.stringify(opts.body) : undefined
  });
  return res.json();
}

async function gh(path, opts = {}) {
  const res = await fetch(`https://api.github.com${path}`, {
    method: opts.method || "GET",
    headers: {
      "Authorization": `Bearer ${PAT}`,
      "Accept": "application/vnd.github+json",
      "Content-Type": "application/json"
    },
    body: opts.body ? JSON.stringify(opts.body) : undefined
  });
  return res;
}

// ---------- CONNECT ----------
async function connect() {
  const p = $("pat").value.trim();
  if (!p) return;
  PAT = p;
  $("authMsg").textContent = "Validating repository access...";
  try {
    const r = await gh(`/repos/${REPO}`);
    if (!r.ok) {
      $("authMsg").innerHTML = "<span style='color:#ef4444'>Access denied: verify PAT permissions for " + REPO + "</span>";
      return;
    }
    localStorage.setItem("sentinel_pat", PAT);
    $("auth").classList.add("hidden");
    $("app").classList.remove("hidden");
    await refresh();
    setInterval(refresh, 15000);
    initChart();
    loadLogs();
  } catch (e) {
    $("authMsg").innerHTML = "<span style='color:#ef4444'>Connection error: " + e.message + "</span>";
  }
}

async function refresh() {
  try {
    STATE = await api("/api/state");
    if (!STATE || STATE.error) return;
    renderDash();
    renderPairs();
    renderRisk();
    renderNews();
    renderTrades();
    renderTrain();
  } catch (err) {
    console.error("Refresh failed", err);
  }
}

// ---------- DASHBOARD ----------
function renderDash() {
  const hb = STATE.heartbeat;
  const online = hb && (Date.now() - new Date(hb.ts).getTime() < 120000);
  $("botDot").className = "status-dot" + (online ? " on" : "");
  $("botStatusText").textContent = online ? "Bot Live" : "Bot Offline";

  const hbMode = hb && hb.mode ? hb.mode : null;
  const bl = $("balLabel");
  if (bl) {
    bl.textContent = `Balance (${hbMode ? hbMode.toUpperCase() : "DEMO"})${hb && hb.loginid ? " · " + hb.loginid : ""}`;
  }
  const bal = hb && hb.balance != null ? Number(hb.balance) : null;
  $("balance").textContent = bal != null ? `$${bal.toFixed(2)}` : "—";

  const t = STATE.today || { pnl: 0, trades: 0, wins: 0 };
  const pnlNum = Number(t.pnl || 0);
  $("pnl").textContent = (pnlNum >= 0 ? "+" : "") + `$${pnlNum.toFixed(2)}`;
  $("pnl").style.color = pnlNum >= 0 ? "var(--accent-green)" : "var(--accent-red)";

  const wr = t.trades > 0 ? (t.wins / t.trades * 100).toFixed(0) : "0";
  $("todayWinRate").textContent = t.trades > 0 ? `${wr}%` : "—";
  $("todayTradesCount").textContent = t.trades || 0;

  const m = (STATE.settings && STATE.settings.mode) || "demo";
  $("modeBadge").textContent = m.toUpperCase();
  $("modeBadge").className = "mode-pill" + (m === "real" ? " real" : "");

  const switching = hbMode && hbMode !== m;
  const isKill = STATE.settings && STATE.settings.kill;
  const isPowerOff = STATE.settings && STATE.settings.power === false;
  $("flags").innerHTML = (isKill ? "<span class='badge badge-red'>KILL ACTIVE</span> " : "") +
                         (isPowerOff ? "<span class='badge badge-amber'>POWER OFF</span> " : "") +
                         (switching ? `<span class='badge badge-blue'>Switching to ${m.toUpperCase()}...</span>` : "");
}

async function togglePower() {
  const on = !(STATE.settings && STATE.settings.power === false);
  if (on) {
    await gh(`/repos/${REPO}/actions/workflows/bot.yml/dispatches`, {
      method: "POST",
      body: { ref: "main", inputs: { mode: STATE.settings.mode || "demo" } }
    });
  }
  await api("/api/settings", { method: "POST", body: { power: !on } });
  refresh();
}

async function toggleKill() {
  const k = !(STATE.settings && STATE.settings.kill);
  await api("/api/settings", { method: "POST", body: { kill: k } });
  refresh();
}

async function toggleMode() {
  const cur = (STATE.settings && STATE.settings.mode) || "demo";
  const nxt = cur === "demo" ? "real" : "demo";
  if (nxt === "real" && !confirm("SWITCH TO REAL MONEY?\nAll trades for verified pairs will execute with REAL funds.\nAre you sure?")) {
    return;
  }
  await api("/api/settings", { method: "POST", body: { mode: nxt } });
  refresh();
}

// ---------- CHART ----------
function lagosTz(epoch) { return epoch + 3600; }

function isForexMarketClosed() {
  const d = new Date(), day = d.getUTCDay(), h = d.getUTCHours();
  return day === 6 || (day === 0 && h < 21) || (day === 5 && h >= 21);
}

function setChartStatus(t, cls) {
  const e = $("chartStatus");
  if (!e) return;
  e.textContent = t;
  e.style.color = cls === "err" ? "var(--accent-red)" : cls === "ok" ? "var(--accent-green)" : "var(--text-dim)";
}

function initChart() {
  const el = $("chart");
  if (!el || chart) return;
  chart = LightweightCharts.createChart(el, {
    width: el.clientWidth || 600,
    height: 320,
    layout: { background: { color: "#090d16" }, textColor: "#94a3b8" },
    grid: { vertLines: { color: "#131d2e" }, horzLines: { color: "#131d2e" } },
    timeScale: { timeVisible: true, secondsVisible: true, borderColor: "#1e293b" },
    rightPriceScale: { borderColor: "#1e293b" }
  });
  candleSeries = chart.addCandlestickSeries({
    upColor: "#10b981", downColor: "#ef4444", wickUpColor: "#10b981", wickDownColor: "#ef4444"
  });

  if (window.ResizeObserver) {
    chartRO = new ResizeObserver(() => {
      try { chart.applyOptions({ width: el.clientWidth, height: 320 }); } catch (_) {}
    });
    chartRO.observe(el);
  }
  setChartCategory("volatility");
}

function setChartCategory(cat) {
  curChartCategory = cat;
  document.querySelectorAll("#chartCategoryTabs .filter-btn").forEach(b => {
    b.classList.toggle("active", b.getAttribute("onclick").includes(`'${cat}'`));
  });
  renderChartTabs();
}

function renderChartTabs() {
  const el = $("pairTabs");
  if (!el) return;
  el.innerHTML = "";

  const allPairs = (STATE && STATE.pairs) || [];
  const syms = allPairs.map(p => p.symbol);
  const filtered = Object.keys(PAIR_METADATA).filter(s => {
    const meta = PAIR_METADATA[s];
    return meta && meta.cat === curChartCategory;
  });

  if (!filtered.includes(curPair)) {
    curPair = filtered[0] || "R_100";
  }

  filtered.forEach(s => {
    const meta = PAIR_METADATA[s] || { name: s };
    const b = document.createElement("button");
    b.className = "pair-tab" + (s === curPair ? " on" : "");
    b.textContent = s.replace("frx", "");
    b.title = meta.name;
    b.onclick = () => {
      if (curPair === s) return;
      curPair = s;
      renderChartTabs();
      subCandles(curPair);
    };
    el.appendChild(b);
  });

  subCandles(curPair);
}

function teardownChartWs() {
  if (chartTimer) { clearTimeout(chartTimer); chartTimer = null; }
  if (wsPub) {
    try { wsPub.onclose = null; wsPub.close(); } catch (_) {}
    wsPub = null;
  }
}

async function loadTradeMarkers(sym) {
  try {
    const r = await api("/api/trades");
    const m = (r.trades || []).filter(t => t.pair === sym && t.open_utc).map(t => {
      const iso = t.open_utc.includes("T") ? t.open_utc : t.open_utc.replace(" ", "T");
      const e = Math.floor(new Date(iso.endsWith("Z") ? iso : iso + "Z").getTime() / 1000);
      return {
        time: lagosTz(e),
        position: t.side === "CALL" ? "belowBar" : "aboveBar",
        color: t.side === "CALL" ? "#10b981" : "#ef4444",
        shape: t.side === "CALL" ? "arrowUp" : "arrowDown",
        text: `${t.side} ($${t.stake})`
      };
    }).filter(x => lastCandles.length && x.time >= lastCandles[0].time && x.time <= lastCandles[lastCandles.length - 1].time);
    if (m.length && candleSeries) candleSeries.setMarkers(m);
  } catch (_) {}
}

function subCandles(sym) {
  teardownChartWs();
  if (candleSeries) candleSeries.setData([]);
  lastCandles = [];
  chartRetry = 0;

  const isSynth = sym.startsWith("R_") || sym.startsWith("1HZ");
  setChartStatus("Connecting to live Deriv feed...", "");

  const sock = new WebSocket("wss://ws.derivws.com/websockets/v3?app_id=1089");
  wsPub = sock;
  let gotData = false;

  sock.onopen = () => {
    setChartStatus("Connected · Subscribing to " + (PAIR_METADATA[sym]?.name || sym) + "...", "ok");
    sock.send(JSON.stringify({
      ticks_history: sym,
      style: "candles",
      granularity: 60,
      count: 300,
      end: "latest",
      adjust_start_time: 1,
      subscribe: 1
    }));
  };

  sock.onmessage = e => {
    let d;
    try { d = JSON.parse(e.data); } catch (_) { return; }
    if (d.error) {
      setChartStatus("Deriv feed: " + (d.error.message || "error"), "err");
      return;
    }
    if (d.msg_type === "candles" && d.candles) {
      gotData = true;
      lastCandles = d.candles.map(c => ({
        time: lagosTz(+c.epoch),
        open: +c.open, high: +c.high, low: +c.low, close: +c.close
      })).sort((a, b) => a.time - b.time);
      candleSeries.setData(lastCandles);
      const statusText = isSynth ? "● Live 24/7 Feed Active" :
        (isForexMarketClosed() ? "Forex Closed (Weekend) — Last Candles" : "● Live Forex Feed Active");
      setChartStatus(statusText, isSynth || !isForexMarketClosed() ? "ok" : "");
      loadTradeMarkers(sym);
    } else if (d.msg_type === "ohlc" && d.ohlc) {
      const c = d.ohlc;
      const cand = {
        time: lagosTz(+c.open_time),
        open: +c.open, high: +c.high, low: +c.low, close: +c.close
      };
      if (!isFinite(cand.time)) return;
      if (!lastCandles.length || cand.time > lastCandles[lastCandles.length - 1].time) {
        lastCandles.push(cand);
      } else {
        lastCandles[lastCandles.length - 1] = cand;
      }
      candleSeries.update(cand);
    }
  };

  sock.onerror = () => setChartStatus("WS Connection Error — retrying...", "err");
  sock.onclose = () => {
    if (wsPub !== sock) return;
    if (!gotData) setChartStatus("WS Closed — reconnecting...", "err");
    const wait = Math.min(15000, 1000 * Math.pow(2, Math.min(4, chartRetry++)));
    chartTimer = setTimeout(() => { if (curPair === sym) subCandles(sym); }, wait);
  };
}

// ---------- PAIRS TAB ----------
function filterPairsList(cat) {
  curPairsFilter = cat;
  document.querySelectorAll("#pairsFilterBar .filter-btn").forEach(b => {
    b.classList.toggle("active", b.getAttribute("onclick").includes(`'${cat}'`));
  });
  renderPairs();
}

function renderPairs() {
  const el = $("pairList");
  if (!el) return;
  el.innerHTML = "";

  const pairs = (STATE && STATE.pairs) || [];
  const filtered = pairs.filter(p => {
    if (curPairsFilter === "all") return true;
    const meta = PAIR_METADATA[p.symbol] || {};
    return meta.cat === curPairsFilter;
  });

  filtered.forEach(p => {
    const meta = PAIR_METADATA[p.symbol] || { name: p.symbol, isSynth: false, defaultDur: 15, defaultUnit: "m" };
    const div = document.createElement("div");
    div.className = "pair-card";

    // Verdict and readiness
    const hasPass = p.verdict === "pass";
    const statusBadge = hasPass ?
      "<span class='badge badge-green'>VERIFIED PASS (REAL OK)</span>" :
      "<span class='badge badge-amber'>DEMO READY (TESTABLE)</span>";
    
    // Duration options
    let durationHTML = "";
    if (meta.isSynth) {
      const curDur = p.duration || meta.defaultDur || 60;
      const curUnit = p.duration_unit || meta.defaultUnit || "s";
      durationHTML = `
        <div class="control-group">
          <label>Contract Duration</label>
          <select onchange="updatePairDuration('${p.symbol}', this.value)">
            <option value="5s" ${curDur==5&&curUnit=='s'?'selected':''}>5 Seconds (Ultra-Fast)</option>
            <option value="15s" ${curDur==15&&curUnit=='s'?'selected':''}>15 Seconds (Fast)</option>
            <option value="30s" ${curDur==30&&curUnit=='s'?'selected':''}>30 Seconds</option>
            <option value="60s" ${curDur==60&&curUnit=='s'?'selected':''}>1 Minute (60s)</option>
            <option value="2m" ${curDur==2&&curUnit=='m'?'selected':''}>2 Minutes</option>
            <option value="5m" ${curDur==5&&curUnit=='m'?'selected':''}>5 Minutes</option>
            <option value="15m" ${curDur==15&&curUnit=='m'?'selected':''}>15 Minutes</option>
          </select>
        </div>
      `;
    } else {
      durationHTML = `
        <div class="control-group">
          <label>Contract Duration</label>
          <select disabled style="opacity: 0.7;">
            <option selected>15 Minutes (Forex Floor)</option>
          </select>
        </div>
      `;
    }

    div.innerHTML = `
      <div class="pair-card-header">
        <div>
          <div class="pair-title">${p.symbol}</div>
          <div class="pair-desc">${meta.name} · ${meta.isSynth ? "24/7 Synthetic" : "Forex"}</div>
        </div>
        <div>${statusBadge}</div>
      </div>

      <div style="display: flex; align-items: center; justify-content: space-between; background: #090d16; padding: 8px 12px; border-radius: 6px; border: 1px solid var(--border-color); margin-top: 4px;">
        <span style="font-weight: 700; font-size: 13px;">Enable Trading (Demo)</span>
        <label style="display: inline-flex; align-items: center; cursor: pointer;">
          <input type="checkbox" style="width: 20px; height: 20px; cursor: pointer;" ${p.enabled ? "checked" : ""} onchange="setPair('${p.symbol}', 'enabled', this.checked ? 1 : 0)">
        </label>
      </div>

      <div class="pair-controls">
        ${durationHTML}
        <div class="control-group">
          <label>Stake Fraction (%)</label>
          <input type="number" step="0.005" min="0.005" max="0.10" value="${p.stake_pct || 0.01}" onchange="setPair('${p.symbol}', 'stake_pct', +this.value)">
        </div>
        <div class="control-group">
          <label>Min Stake ($)</label>
          <input type="number" step="0.05" min="0.35" value="${p.min_stake || 0.35}" onchange="setPair('${p.symbol}', 'min_stake', +this.value)">
        </div>
        <div class="control-group">
          <label>Max Stake ($)</label>
          <input type="number" step="1.0" min="0.35" value="${p.max_stake || 10}" onchange="setPair('${p.symbol}', 'max_stake', +this.value)">
        </div>
      </div>
    `;
    el.appendChild(div);
  });
}

async function updatePairDuration(sym, val) {
  let dur = 60, unit = "s";
  if (val.endsWith("s")) {
    dur = parseInt(val); unit = "s";
  } else if (val.endsWith("m")) {
    dur = parseInt(val); unit = "m";
  }
  await api("/api/pairs/update", {
    method: "POST",
    body: { symbol: sym, duration: dur, duration_unit: unit }
  });
  refresh();
}

async function setPair(sym, k, v) {
  await api("/api/pairs/update", { method: "POST", body: { symbol: sym, [k]: v } });
  refresh();
}

// ---------- UPLOAD MODEL (.sfxmodel.zip) ----------
$("modelFile").addEventListener("change", async (e) => {
  const file = e.target.files[0];
  if (!file) return;
  pendingModelFile = file;

  $("uploadProgress").textContent = `Reading ${file.name} (${(file.size / 1024 / 1024).toFixed(2)} MB)...`;

  try {
    const zip = await JSZip.loadAsync(file);
    const manifestFile = zip.file("manifest.json");
    if (!manifestFile) {
      $("uploadProgress").innerHTML = "<span style='color:#ef4444'>Invalid bundle: manifest.json missing inside zip</span>";
      return;
    }
    const manifestText = await manifestFile.async("text");
    const manifest = JSON.parse(manifestText);
    pendingModelData = manifest;

    let planSummary = "Plan included";
    const planFile = zip.file("analysis_plan.json");
    if (planFile) {
      const plan = JSON.parse(await planFile.async("text"));
      planSummary = `${(plan.nodes || []).length} nodes (${(plan.nodes || []).filter(n => n.type === 'analyst').length} analysts)`;
    }

    $("modelInfo").innerHTML = `
      <div style="font-weight: 800; font-size: 15px; color: #fff; margin-bottom: 4px;">
        📦 ${manifest.symbol} (Version ${manifest.version || 2})
      </div>
      <div class="dim">
        Files: ${(manifest.files || []).length} files declared · Architecture: ${planSummary}
      </div>
      <div style="margin-top: 6px;">
        <span class="badge badge-blue">Schema v${manifest.schema_version || 2}</span>
        <span class="badge badge-green">Ready to Stage</span>
      </div>
    `;
    $("modelPreview").classList.remove("hidden");
    $("uploadProgress").textContent = "Bundle verified. Click Upload to stage and validate.";
  } catch (err) {
    $("uploadProgress").innerHTML = "<span style='color:#ef4444'>Failed to inspect zip: " + err.message + "</span>";
  }
});

async function uploadModelBundle() {
  if (!pendingModelFile || !pendingModelData) return;
  const btn = $("uploadModelBtn");
  btn.disabled = true;
  btn.textContent = "Uploading to Staging...";

  const sym = pendingModelData.symbol;
  const ver = pendingModelData.version || 2;
  const assetName = `${sym}_v${ver}.sfxmodel.zip`;

  try {
    $("uploadProgress").textContent = `Uploading ${assetName} via worker proxy...`;
    const res = await fetch(`${API_BASE}/api/upload/staging-asset?name=${encodeURIComponent(assetName)}`, {
      method: "POST",
      headers: {
        "Authorization": `Bearer ${PAT}`,
        "Content-Type": "application/zip"
      },
      body: pendingModelFile
    });
    const uploadRes = await res.json();
    if (!uploadRes.ok) {
      throw new Error(uploadRes.error || "Staging upload failed");
    }

    $("uploadProgress").textContent = `Asset staged! Dispatching publish-model workflow for ${sym} v${ver}...`;
    const wf = await gh(`/repos/${REPO}/actions/workflows/publish-model.yml/dispatches`, {
      method: "POST",
      body: {
        ref: "main",
        inputs: {
          symbol: sym,
          version: String(ver),
          min_trades: "0" // allows demo testing
        }
      }
    });

    if (!wf.ok) {
      throw new Error("Workflow dispatch failed");
    }

    $("uploadProgress").innerHTML = `
      <div style="color: var(--accent-green); font-weight: 700; margin-bottom: 4px;">
        ✓ Staged &amp; Dispatched Successfully!
      </div>
      <div class="dim">
        GitHub Actions is now running full validation on <b>${assetName}</b>.<br>
        Check the Actions tab or wait for the model to automatically register.
      </div>
    `;
    btn.disabled = false;
    btn.textContent = "Upload & Dispatch Full Validation";
  } catch (err) {
    $("uploadProgress").innerHTML = `<span style='color:#ef4444'>Upload Error: ${err.message}</span>`;
    btn.disabled = false;
    btn.textContent = "Retry Upload";
  }
}

// ---------- TRAIN TAB ----------
function filterTrainCategory(cat) {
  curTrainFilter = cat;
  document.querySelectorAll("#train .filter-bar .filter-btn").forEach(b => {
    if (b.getAttribute("onclick")?.includes(`'${cat}'`)) {
      b.classList.add("active");
    } else if (b.getAttribute("onclick")?.includes("filterTrainCategory")) {
      b.classList.remove("active");
    }
  });
  renderTrain();
}

function selectAllTrain(check) {
  document.querySelectorAll(".trainChk").forEach(c => {
    if (c.closest("label").style.display !== "none") c.checked = check;
  });
}

async function renderTrain() {
  const host = $("trainPairs");
  if (!host) return;
  let idx = {};
  try {
    idx = await (await fetch(`https://raw.githubusercontent.com/${REPO}/main/data/index.json`)).json();
  } catch (_) {}

  const pairs = Object.keys(PAIR_METADATA);
  host.innerHTML = pairs.map(s => {
    const meta = PAIR_METADATA[s];
    const isVisible = curTrainFilter === "all" || meta.cat === curTrainFilter;
    const d = idx[s];
    const ageH = d ? Math.round((Date.now() - Date.parse(d.last_checked_utc)) / 3600e3) : null;
    const ready = d && ageH < 26;

    return `
      <label style="display:${isVisible ? 'flex' : 'none'}; align-items:center; justify-content:space-between; padding:8px 10px; border-bottom:1px solid #131b2e; cursor:pointer;">
        <div style="display:flex; align-items:center; gap:8px;">
          <input type="checkbox" class="trainChk" value="${s}">
          <div>
            <b style="color:#fff;">${s}</b>
            <span class="dim" style="margin-left:6px;">${meta.name}</span>
          </div>
        </div>
        <div>
          ${ready ? `<span class="badge badge-green">Ready (${d.rows} candles)</span>` :
                    `<span class="badge badge-amber">Needs Refresh</span>`}
        </div>
      </label>
    `;
  }).join("");

  $("copyPromptBtn").onclick = copyTrainPrompt;
}

async function copyTrainPrompt() {
  const chosen = [...document.querySelectorAll(".trainChk:checked")].map(c => c.value);
  if (!chosen.length) {
    $("trainStatus").innerHTML = "<span style='color:#ef4444'>Please select at least one pair to train.</span>";
    return;
  }

  const selectedDuration = $("trainDuration").value;
  let tpl = "";
  try {
    tpl = await (await fetch(`https://raw.githubusercontent.com/${REPO}/main/TRAIN_PROMPT.md`)).text();
  } catch (_) {
    tpl = "# SENTINEL-FX Model Training Prompt\n";
  }

  let prompt = tpl + `\n\n## RUN PARAMETERS\nPAIR_SYMBOLS:\n` +
    chosen.map(s => `- ${s} (${PAIR_METADATA[s]?.name || s})`).join("\n") +
    `\nTRADE_DURATION: ${selectedDuration}\nPAYOUT_ASSUMPTION: 0.85\n`;

  const pat = $("publishPat").value.trim();
  if (pat) {
    prompt += `\n-----BEGIN PUBLISH ACCESS-----\nGitHub PAT: ${pat}\nPublish command: python tools/publish_model.py <bundle.sfxmodel.zip> --symbol <SYMBOL> --version 2 --token ${pat}\n-----END PUBLISH ACCESS-----\n`;
  }

  try {
    await navigator.clipboard.writeText(prompt);
  } catch (_) {
    const ta = document.createElement("textarea");
    ta.value = prompt;
    document.body.appendChild(ta);
    ta.select();
    document.execCommand("copy");
    ta.remove();
  }
  $("publishPat").value = "";

  // Dispatch data fetch if any stale
  try {
    await gh(`/repos/${REPO}/actions/workflows/fetch-candles.yml/dispatches`, {
      method: "POST",
      body: {
        ref: "main",
        inputs: {
          symbols: chosen.join(","),
          mode: $("fullRefetch").checked ? "full" : "incremental"
        }
      }
    });
    $("trainStatus").innerHTML = `
      <div style="color:var(--accent-green); font-weight:700;">✓ Prompt copied to clipboard!</div>
      <div class="dim">Candle fetch dispatched in Actions for ${chosen.length} pairs. Paste the prompt to your training AI.</div>
    `;
  } catch (e) {
    $("trainStatus").innerHTML = `<div style="color:var(--accent-green);">✓ Prompt copied to clipboard! (Data refresh dispatch skipped: ${e.message})</div>`;
  }
}

// ---------- NEWS TAB (ACCURACY VERIFICATION) ----------
function filterNewsView(filter) {
  curNewsFilter = filter;
  document.querySelectorAll("#news .filter-bar .filter-btn").forEach(b => {
    b.classList.toggle("active", b.getAttribute("onclick").includes(`'${filter}'`));
  });
  renderNews();
}

function parseNumber(s) {
  if (!s) return null;
  const clean = String(s).replace(/[^\d.-]/g, '');
  const n = parseFloat(clean);
  return isNaN(n) ? null : n;
}

function renderNews() {
  api("/api/news").then(r => {
    const el = $("newsList");
    if (!el) return;
    el.innerHTML = "";

    const events = r.events || [];
    const reactions = r.reactions || [];
    const now = Date.now();

    // Group reactions by event_key
    const rxMap = {};
    reactions.forEach(rx => {
      rxMap[rx.event_key] = rx;
    });

    const filtered = events.filter(e => {
      const t = new Date(e.utc_time).getTime();
      const isPast = now >= t + 15 * 60 * 1000;
      if (curNewsFilter === "past") return isPast;
      if (curNewsFilter === "upcoming") return !isPast;
      return true;
    });

    if (!filtered.length) {
      el.innerHTML = "<div class='card dim' style='text-align:center;'>No news events found for this filter.</div>";
      return;
    }

    filtered.forEach(e => {
      const t = new Date(e.utc_time);
      const lagos = new Date(t.getTime() + 3600e3);
      const isPast = now >= (t.getTime() + 15 * 60 * 1000);
      const div = document.createElement("div");
      div.className = "news-item";

      // Prediction direction based on forecast vs previous
      const fc = parseNumber(e.forecast);
      const pv = parseNumber(e.previous);
      let predictedDirection = "NEUTRAL";
      if (fc !== null && pv !== null) {
        if (fc > pv) predictedDirection = "BULLISH (UP)";
        else if (fc < pv) predictedDirection = "BEARISH (DOWN)";
      }

      // Check reaction if past
      const rx = rxMap[e.id];
      let accuracyBadge = "";
      let reactionText = "Awaiting market candles reconciliation";

      if (isPast) {
        if (rx) {
          const move = rx.move_15m || rx.move_5m || 0;
          reactionText = `Pair ${rx.pair}: 5m move = ${rx.move_5m > 0 ? "+" : ""}${rx.move_5m}p, 15m move = ${rx.move_15m > 0 ? "+" : ""}${rx.move_15m}p`;
          if (predictedDirection.includes("UP")) {
            if (move > 0.2) accuracyBadge = "<span class='badge badge-green'>✓ PREDICTION ACCURATE</span>";
            else if (move < -0.2) accuracyBadge = "<span class='badge badge-red'>✗ PREDICTION INACCURATE</span>";
            else accuracyBadge = "<span class='badge badge-amber'>• FLAT / NEUTRAL MOVE</span>";
          } else if (predictedDirection.includes("DOWN")) {
            if (move < -0.2) accuracyBadge = "<span class='badge badge-green'>✓ PREDICTION ACCURATE</span>";
            else if (move > 0.2) accuracyBadge = "<span class='badge badge-red'>✗ PREDICTION INACCURATE</span>";
            else accuracyBadge = "<span class='badge badge-amber'>• FLAT / NEUTRAL MOVE</span>";
          } else {
            accuracyBadge = "<span class='badge badge-blue'>• COMPLETED</span>";
          }
        } else {
          accuracyBadge = "<span class='badge badge-amber'>• REACTION PENDING</span>";
        }
      } else {
        accuracyBadge = "<span class='badge badge-blue'>UPCOMING</span>";
      }

      div.innerHTML = `
        <div class="news-item-header">
          <div>
            <span class="badge ${e.impact === 'High' ? 'badge-red' : e.impact === 'Medium' ? 'badge-amber' : 'badge-blue'}">${e.currency} · ${e.impact || 'Low'} Impact</span>
            <div class="news-title" style="margin-top:4px;">${e.title}</div>
            <div class="news-meta">
              ${lagos.toISOString().slice(0, 16).replace("T", " ")} Lagos time · Forecast: ${e.forecast || "—"} · Prev: ${e.previous || "—"}
            </div>
          </div>
          <div>${accuracyBadge}</div>
        </div>

        ${isPast ? `
          <div class="news-verdict-box">
            <span class="dim">Predicted Direction: <b style="color:#fff;">${predictedDirection}</b></span>
            <span class="dim">${reactionText}</span>
          </div>
        ` : ''}
      `;
      el.appendChild(div);
    });
  });
}

// ---------- TRADES TAB ----------
function renderTrades() {
  api("/api/trades").then(r => {
    const el = $("tradeList");
    if (!el) return;
    const list = r.trades || [];
    if (!list.length) {
      el.innerHTML = "<div class='dim' style='text-align:center; padding:16px;'>No trades recorded yet.</div>";
      return;
    }
    el.innerHTML = `
      <table>
        <thead>
          <tr>
            <th>Time (Lagos)</th>
            <th>Pair</th>
            <th>Side</th>
            <th>Stake</th>
            <th>PnL</th>
            <th>Result</th>
            <th>Mode</th>
          </tr>
        </thead>
        <tbody>
          ${list.map(t => {
            const pnl = Number(t.pnl || 0);
            const pnlColor = pnl > 0 ? "color:var(--accent-green)" : pnl < 0 ? "color:var(--accent-red)" : "";
            const tTime = t.open_utc ? new Date(new Date(t.open_utc).getTime() + 3600e3).toISOString().slice(11, 19) : "—";
            return `
              <tr>
                <td class="dim">${tTime}</td>
                <td><b>${t.pair}</b></td>
                <td><span class="badge ${t.side === 'CALL' ? 'badge-green' : 'badge-red'}">${t.side}</span></td>
                <td>$${Number(t.stake).toFixed(2)}</td>
                <td style="${pnlColor}"><b>${(pnl >= 0 ? "+" : "") + pnl.toFixed(2)}</b></td>
                <td><span class="badge ${t.result === 'won' ? 'badge-green' : t.result === 'lost' ? 'badge-red' : 'badge-amber'}">${t.result || 'open'}</span></td>
                <td><span class="badge ${t.mode === 'real' ? 'badge-red' : 'badge-blue'}">${(t.mode || 'demo').toUpperCase()}</span></td>
              </tr>
            `;
          }).join("")}
        </tbody>
      </table>
    `;
  });
}

// ---------- LOGS TAB ----------
async function loadLogs() {
  const lv = $("logLevel").value;
  const r = await api("/api/logs?limit=150" + (lv ? "&level=" + lv : ""));
  const el = $("logList");
  if (!el) return;
  el.innerHTML = (r.logs || []).map(l => {
    const cls = l.level === "warn" ? "warn" : l.level === "error" ? "error" : "info";
    return `<div class="${cls}">[${l.ts ? l.ts.slice(11, 19) : ""}] [${l.level.toUpperCase()}] ${l.pair ? l.pair + ": " : ""}${l.message}</div>`;
  }).join("");
}

// ---------- RISK & SETTINGS ----------
function renderRisk() {
  const s = (STATE && STATE.settings) || {};
  const f = $("riskForm");
  if (!f) return;
  f.innerHTML = `
    <h3>Account Risk Controls</h3>
    <p class="dim" style="margin-bottom:12px;">Day resets midnight Africa/Lagos (UTC+1). Automatic loss protection.</p>
    <div style="display:grid; grid-template-columns:repeat(auto-fit, minmax(200px, 1fr)); gap:10px;">
      <div>
        <label class="dim">Daily Loss Cap ($)</label>
        <input id="r_loss" type="number" step="0.5" value="${s.daily_loss ?? -1}">
      </div>
      <div>
        <label class="dim">Daily Profit Target ($)</label>
        <input id="r_target" type="number" step="0.5" value="${s.daily_target ?? -1}">
      </div>
      <div>
        <label class="dim">Goal Balance ($)</label>
        <input id="r_goal" type="number" step="1.0" value="${s.goal_balance ?? 0}">
      </div>
    </div>
    <button class="btn btn-primary" onclick="saveRisk()">Save Risk Settings</button>

    <h3 style="margin-top:20px;">Deriv API Token Update</h3>
    <p class="dim" style="margin-bottom:8px;">Saved directly to repository GitHub Secrets. Never visible to users.</p>
    <input id="d_token" type="password" placeholder="DERIV_BEARER_TOKEN">
    <input id="d_appid" placeholder="DERIV_APP_ID">
    <button class="btn btn-secondary" onclick="saveDeriv()">Update Deriv Secrets</button>
    <div id="tokMsg" class="dim" style="margin-top:6px;"></div>
  `;
}

async function saveRisk() {
  await api("/api/settings", {
    method: "POST",
    body: {
      daily_loss: +$("r_loss").value,
      daily_target: +$("r_target").value,
      goal_balance: +$("r_goal").value
    }
  });
  refresh();
}

async function saveDeriv() {
  await sodium.ready;
  const kr = await gh(`/repos/${REPO}/actions/secrets/public-key`);
  const k = await kr.json();

  async function put(name, val) {
    const bin = sodium.from_string(val);
    const kb = sodium.from_base64(k.key, sodium.base64_variants.ORIGINAL);
    const enc = sodium.crypto_box_seal(bin, kb);
    await gh(`/repos/${REPO}/actions/secrets/${name}`, {
      method: "PUT",
      body: {
        encrypted_value: sodium.to_base64(enc, sodium.base64_variants.ORIGINAL),
        key_id: k.key_id
      }
    });
  }

  if ($("d_token").value) await put("DERIV_BEARER_TOKEN", $("d_token").value);
  if ($("d_appid").value) await put("DERIV_APP_ID", $("d_appid").value);
  $("tokMsg").innerHTML = "<span style='color:var(--accent-green)'>✓ Secrets encrypted & saved to GitHub.</span>";
  $("d_token").value = "";
}

// ---------- NAV ----------
document.querySelectorAll("nav button").forEach(b => {
  b.onclick = () => {
    document.querySelectorAll("nav button").forEach(x => x.classList.remove("on"));
    b.classList.add("on");
    document.querySelectorAll(".page").forEach(x => x.classList.remove("on"));
    const pageId = b.dataset.p;
    $(pageId).classList.add("on");
    if (pageId === "logs") loadLogs();
  };
});

if (PAT) {
  $("pat").value = PAT;
  connect();
}
