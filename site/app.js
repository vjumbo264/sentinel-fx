/**
 * SENTINEL-FX Control Terminal (site/app.js)
 * Modern fintech dashboard for autonomous multi-pair trading.
 */
'use strict';

const API_BASE = "https://sentinel-fx-worker.vjumbo264.workers.dev";
const REPO = "vjumbo264/sentinel-fx";

let PAT = localStorage.getItem("sentinel_pat") || "";
let STATE = null;
let chartInstance = null, wsPub = null, wsPingInterval = null;
let curPair = null;
let curGranularity = 60; // default 1m
let chartCandles = [];
let chartRetry = 0;

/* FIX-F shared button feedback: sfxBusy(btn, promise, {pending,ok,err}) */
function sfxToast(msg, isErr){
  let t = document.getElementById('sfx-toast');
  if(!t){ t=document.createElement('div'); t.id='sfx-toast';
    t.style.cssText='position:fixed;left:50%;bottom:24px;transform:translateX(-50%);max-width:92vw;padding:10px 16px;border-radius:10px;font:14px/1.4 system-ui;z-index:9999;box-shadow:0 4px 18px rgba(0,0,0,.35);transition:opacity .25s'; document.body.appendChild(t);}
  t.textContent = msg; t.style.background = isErr?'#7f1d1d':'#14532d'; t.style.color='#fff'; t.style.opacity='1';
  clearTimeout(t._h); t._h=setTimeout(()=>t.style.opacity='0', 4200);
}
async function sfxBusy(btn, work, opts){
  opts = opts||{}; if(!btn || btn.dataset.busy==='1') return; // double-press guard
  btn.dataset.busy='1'; const old=btn.innerHTML;
  btn.disabled=true; btn.innerHTML='<span class="sfx-spin" style="display:inline-block;width:14px;height:14px;border:2px solid #fff;border-top-color:transparent;border-radius:50%;animation:sfxrot .7s linear infinite;vertical-align:-2px"></span> '+(opts.pending||'Working...');
  if(!document.getElementById('sfx-spin-css')){const st=document.createElement('style');st.id='sfx-spin-css';st.textContent='@keyframes sfxrot{to{transform:rotate(360deg)}}';document.head.appendChild(st);}
  try{ const r = await work(); sfxToast(opts.ok||'Done'); return r; }
  catch(e){ sfxToast((opts.err?opts.err+': ':'Error: ')+(e&&e.message||e), true); throw e; }
  finally{ btn.dataset.busy=''; btn.disabled=false; btn.innerHTML=old; }
}

let pendingModelFile = null, pendingModelData = null;
let curTrainFilter = "all";

const PAIR_METADATA = {
  // Volatility Indices (24/7)
  "R_10": { name: "Volatility 10 Index", cat: "volatility", isSynth: true, defaultDur: 60, defaultUnit: "s" },
  "R_25": { name: "Volatility 25 Index", cat: "volatility", isSynth: true, defaultDur: 60, defaultUnit: "s" },
  "R_50": { name: "Volatility 50 Index", cat: "volatility", isSynth: true, defaultDur: 60, defaultUnit: "s" },
  "R_75": { name: "Volatility 75 Index", cat: "volatility", isSynth: true, defaultDur: 60, defaultUnit: "s" },
  "R_100": { name: "Volatility 100 Index", cat: "volatility", isSynth: true, defaultDur: 60, defaultUnit: "s" },
  // 1-Second Volatility Indices (24/7)
  "1HZ10V": { name: "Volatility 10 (1s) Index", cat: "volatility_1s", isSynth: true, defaultDur: 60, defaultUnit: "s" },
  "1HZ25V": { name: "Volatility 25 (1s) Index", cat: "volatility_1s", isSynth: true, defaultDur: 60, defaultUnit: "s" },
  "1HZ50V": { name: "Volatility 50 (1s) Index", cat: "volatility_1s", isSynth: true, defaultDur: 60, defaultUnit: "s" },
  "1HZ75V": { name: "Volatility 75 (1s) Index", cat: "volatility_1s", isSynth: true, defaultDur: 60, defaultUnit: "s" },
  "1HZ100V": { name: "Volatility 100 (1s) Index", cat: "volatility_1s", isSynth: true, defaultDur: 60, defaultUnit: "s" },
  "1HZ150V": { name: "Volatility 150 (1s) Index", cat: "volatility_1s", isSynth: true, defaultDur: 60, defaultUnit: "s" },
  "1HZ250V": { name: "Volatility 250 (1s) Index", cat: "volatility_1s", isSynth: true, defaultDur: 60, defaultUnit: "s" },
  "1HZ300V": { name: "Volatility 300 (1s) Index", cat: "volatility_1s", isSynth: true, defaultDur: 60, defaultUnit: "s" },
  // Forex Pairs (Intraday floor >= 15m)
  "frxEURUSD": { name: "EUR / USD", cat: "forex", isSynth: false, defaultDur: 15, defaultUnit: "m" },
  "frxGBPUSD": { name: "GBP / USD", cat: "forex", isSynth: false, defaultDur: 15, defaultUnit: "m" },
  "frxUSDJPY": { name: "USD / JPY", cat: "forex", isSynth: false, defaultDur: 15, defaultUnit: "m" },
  "frxAUDUSD": { name: "AUD / USD", cat: "forex", isSynth: false, defaultDur: 15, defaultUnit: "m" },
  "frxUSDCAD": { name: "USD / CAD", cat: "forex", isSynth: false, defaultDur: 15, defaultUnit: "m" },
  "frxUSDCHF": { name: "USD / CHF", cat: "forex", isSynth: false, defaultDur: 15, defaultUnit: "m" },
  "frxNZDUSD": { name: "NZD / USD", cat: "forex", isSynth: false, defaultDur: 15, defaultUnit: "m" },
  "frxEURGBP": { name: "EUR / GBP", cat: "forex", isSynth: false, defaultDur: 15, defaultUnit: "m" },
  "frxEURJPY": { name: "EUR / JPY", cat: "forex", isSynth: false, defaultDur: 15, defaultUnit: "m" },
  "frxGBPJPY": { name: "GBP / JPY", cat: "forex", isSynth: false, defaultDur: 15, defaultUnit: "m" },
  "frxEURAUD": { name: "EUR / AUD", cat: "forex", isSynth: false, defaultDur: 15, defaultUnit: "m" },
  "frxAUDJPY": { name: "AUD / JPY", cat: "forex", isSynth: false, defaultDur: 15, defaultUnit: "m" },
  "frxEURCAD": { name: "EUR / CAD", cat: "forex", isSynth: false, defaultDur: 15, defaultUnit: "m" },
  "frxEURCHF": { name: "EUR / CHF", cat: "forex", isSynth: false, defaultDur: 15, defaultUnit: "m" },
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

// Helper: check if a pair has a trained model
function isPairTrained(p) {
  if (!p) return false;
  // Strictly filter: only pairs with an installed/active model pack or validated verdict
  return Boolean(
    (p.pack_version && Number(p.pack_version) > 0) ||
    p.status === "installed" ||
    p.status === "active" ||
    (p.verdict && p.verdict !== "untested")
  );
}

function getTrainedPairs() {
  const all = (STATE && STATE.pairs) || [];
  return all.filter(isPairTrained);
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
    renderChartTabsAndInit();
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

async function runBuyTest() {
  const btn = $("buyTestBtn");
  await sfxBusy(btn, async () => {
    const res = await gh(`/repos/${REPO}/actions/workflows/buy-test.yml/dispatches`, {
      method: "POST",
      body: {
        ref: "main",
        inputs: { symbol: curPair || "R_10", durations: "60" }
      }
    });
    if (!res.ok) {
      const err = await res.text();
      throw new Error(`Failed to dispatch buy test: ${err}`);
    }
    return res;
  }, {
    pending: "Testing buy...",
    ok: "Demo buy test dispatched! Watch Actions and Trades table.",
    err: "Buy test dispatch failed"
  });
}

// Reset Demo Balance
async function resetDemoBalance() {
  if (!confirm("Reset Deriv demo balance to $10,000.00 and clear today's PnL session stats?")) return;
  const btn = $("resetDemoBtn");
  if (btn) {
    btn.disabled = true;
    btn.textContent = "Resetting...";
  }
  try {
    const res = await api("/api/account/reset-demo-balance", { method: "POST" });
    if (res.ok) {
      if (STATE && STATE.heartbeat) {
        STATE.heartbeat.balance = 10000.00;
      }
      if ($("balance")) $("balance").textContent = "$10,000.00";
      if (res.deriv && res.deriv.data && res.deriv.data.balance) {
        alert("✓ Deriv demo account balance successfully reset to $" + res.deriv.data.balance + "!");
      } else {
        alert("✓ Deriv demo balance reset to $10,000.00!");
      }
      refresh();
    } else {
      // Fallback: trigger verified GitHub Actions pipeline
      await gh(`/repos/${REPO}/actions/workflows/test-reset-balance.yml/dispatches`, {
        method: "POST",
        body: { ref: "main" }
      });
      alert("✓ Deriv demo reset triggered via Actions pipeline! Refreshing in 5s...");
      setTimeout(refresh, 5000);
    }
  } catch (e) {
    try {
      await gh(`/repos/${REPO}/actions/workflows/test-reset-balance.yml/dispatches`, {
        method: "POST",
        body: { ref: "main" }
      });
      alert("✓ Deriv demo reset triggered via Actions! Balance updating...");
      setTimeout(refresh, 5000);
    } catch (err2) {
      alert("Reset error: " + e.message);
    }
  } finally {
    if (btn) {
      btn.disabled = false;
      btn.textContent = "Reset $10k";
    }
  }
}

// ---------- CHART.JS INTEGRATION ----------
const DERIV_WS_ENDPOINTS = [
  "wss://ws.derivws.com/websockets/v3?app_id=1089",
  "wss://ws.binaryws.com/websockets/v3?app_id=1089",
  "wss://ws.derivws.com/websockets/v3?app_id=36300",
  "wss://frontend.binaryws.com/websockets/v3?app_id=1089"
];
let wsEndpointIdx = 0;

function setChartStatus(t, cls) {
  const e = $("chartStatus");
  if (!e) return;
  e.textContent = t;
  e.style.color = cls === "err" ? "var(--accent-red)" : cls === "ok" ? "var(--accent-green)" : "var(--text-dim)";
}

function setTimeframe(sec, label) {
  curGranularity = sec;
  document.querySelectorAll("#tfSelector .filter-btn").forEach(b => {
    b.classList.toggle("active", b.textContent.trim() === label);
  });
  if (curPair) {
    subscribeDerivCandles(curPair);
  }
}

function renderChartTabsAndInit() {
  const tabsHost = $("pairTabs");
  if (!tabsHost) return;

  const trainedPairs = getTrainedPairs();
  if (!trainedPairs.length) {
    tabsHost.innerHTML = "<span class='dim' style='padding:6px;'>No trained models yet. Train or upload a model to view chart.</span>";
    setChartStatus("No trained pairs available.", "");
    teardownChartWs();
    if (chartInstance) {
      chartInstance.destroy();
      chartInstance = null;
    }
    return;
  }

  tabsHost.innerHTML = "";
  const trainedSyms = trainedPairs.map(p => p.symbol);
  
  // Prefer synthetic 24/7 pairs over closed forex pairs if curPair unset or invalid
  if (!curPair || !trainedSyms.includes(curPair)) {
    const synthFirst = trainedPairs.find(p => {
      const m = PAIR_METADATA[p.symbol];
      return m && m.isSynth;
    });
    curPair = synthFirst ? synthFirst.symbol : trainedSyms[0];
  }

  trainedSyms.forEach(s => {
    const meta = PAIR_METADATA[s] || { name: s };
    const b = document.createElement("button");
    b.className = "pair-tab" + (s === curPair ? " on" : "");
    b.textContent = s.replace("frx", "");
    b.title = meta.name;
    b.onclick = () => {
      if (curPair === s) return;
      curPair = s;
      renderChartTabsAndInit();
    };
    tabsHost.appendChild(b);
  });

  if (!wsPub || wsPub.readyState !== 1) {
    subscribeDerivCandles(curPair);
  }
}

function teardownChartWs() {
  if (wsPingInterval) { clearInterval(wsPingInterval); wsPingInterval = null; }
  if (wsPub) {
    try {
      if (wsPub.readyState === 1) {
        wsPub.send(JSON.stringify({ forget_all: "candles" }));
      }
      wsPub.onclose = null;
      wsPub.onerror = null;
      wsPub.close();
    } catch (_) {}
    wsPub = null;
  }
}

function initOrUpdateChart(candles, sym) {
  const canvas = $("chartCanvas");
  if (!canvas) return;

  const labels = candles.map(c => {
    const d = new Date((+c.epoch + 3600) * 1000); // Lagos time UTC+1
    return d.toISOString().slice(11, 16);
  });
  const prices = candles.map(c => +c.close);
  const isUp = prices.length > 1 && prices[prices.length - 1] >= prices[0];
  const lineColor = isUp ? "#10b981" : "#ef4444";
  const bgGradient = isUp ? "rgba(16, 185, 129, 0.12)" : "rgba(239, 68, 68, 0.12)";
  const tfLabel = curGranularity >= 60 ? `${curGranularity / 60}m` : `${curGranularity}s`;

  if (chartInstance) {
    chartInstance.data.labels = labels;
    chartInstance.data.datasets[0].data = prices;
    chartInstance.data.datasets[0].borderColor = lineColor;
    chartInstance.data.datasets[0].backgroundColor = bgGradient;
    chartInstance.data.datasets[0].label = `${sym} (${tfLabel})`;
    chartInstance.update("none");
    return;
  }

  const ctx = canvas.getContext("2d");
  chartInstance = new Chart(ctx, {
    type: "line",
    data: {
      labels,
      datasets: [{
        label: `${sym} (${tfLabel})`,
        data: prices,
        borderColor: lineColor,
        backgroundColor: bgGradient,
        borderWidth: 2,
        fill: true,
        tension: 0.15,
        pointRadius: 0,
        pointHoverRadius: 5,
        pointHoverBackgroundColor: lineColor
      }]
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      animation: false,
      interaction: { mode: "index", intersect: false },
      plugins: {
        legend: { display: false },
        tooltip: {
          backgroundColor: "#0b1220",
          borderColor: "#1e293b",
          borderWidth: 1,
          titleColor: "#94a3b8",
          bodyColor: "#ffffff",
          padding: 10,
          callbacks: {
            label: (ctx) => ` Price: $${Number(ctx.raw).toFixed(4)}`
          }
        }
      },
      scales: {
        x: {
          grid: { color: "#131d2e", drawBorder: false },
          ticks: { color: "#64748b", font: { size: 10 }, maxTicksLimit: 8 }
        },
        y: {
          grid: { color: "#131d2e", drawBorder: false },
          ticks: { color: "#64748b", font: { size: 10 } }
        }
      }
    }
  });
}

function subscribeDerivCandles(sym) {
  if (!sym) return;
  teardownChartWs();
  chartCandles = [];
  
  const tfLabel = curGranularity >= 60 ? `${curGranularity / 60}m` : `${curGranularity}s`;
  const meta = PAIR_METADATA[sym] || {};
  const isWeekend = [0, 6].includes(new Date().getUTCDay());
  
  if (!meta.isSynth && isWeekend) {
    setChartStatus(`Forex markets closed for the weekend · Select a synthetic index (e.g. R_100) for 24/7 stream`, "err");
    return;
  }

  setChartStatus(`Connecting live feed for ${sym} (${tfLabel})...`, "");

  const endpointUrl = DERIV_WS_ENDPOINTS[wsEndpointIdx];
  let sock;
  try {
    sock = new WebSocket(endpointUrl);
  } catch (err) {
    console.warn("WebSocket init error:", err);
    wsEndpointIdx = (wsEndpointIdx + 1) % DERIV_WS_ENDPOINTS.length;
    setTimeout(() => subscribeDerivCandles(sym), 1000);
    return;
  }
  
  wsPub = sock;

  sock.onopen = () => {
    chartRetry = 0;
    setChartStatus(`Live · Streaming ${sym} (${tfLabel})`, "ok");
    
    // Subscribe to candles
    sock.send(JSON.stringify({
      ticks_history: sym,
      style: "candles",
      granularity: curGranularity,
      count: 120,
      end: "latest",
      adjust_start_time: 1,
      subscribe: 1
    }));

    // 15-second keepalive ping to prevent idle connection drop
    wsPingInterval = setInterval(() => {
      if (sock.readyState === 1) {
        sock.send(JSON.stringify({ ping: 1 }));
      }
    }, 15000);
  };

  sock.onmessage = e => {
    let d;
    try { d = JSON.parse(e.data); } catch (_) { return; }
    
    if (d.error) {
      if (d.error.code === "MarketIsClosed" || (d.error.message && d.error.message.toLowerCase().includes("closed"))) {
        setChartStatus("Forex market is closed for the weekend · Synthetics trade 24/7", "err");
        return;
      }
      setChartStatus(`Deriv: ${d.error.message || 'error'}`, "err");
      return;
    }

    if (d.msg_type === "candles" && d.candles) {
      chartCandles = d.candles.sort((a, b) => +a.epoch - +b.epoch);
      initOrUpdateChart(chartCandles, sym);
      const last = chartCandles[chartCandles.length - 1];
      setChartStatus(`Live · ${sym} $${Number(last.close).toFixed(4)} (${tfLabel})`, "ok");
    } else if (d.msg_type === "ohlc" && d.ohlc) {
      const o = d.ohlc;
      const c = { epoch: o.open_time, open: o.open, high: o.high, low: o.low, close: o.close };
      if (!chartCandles.length || +c.epoch > +chartCandles[chartCandles.length - 1].epoch) {
        chartCandles.push(c);
        if (chartCandles.length > 150) chartCandles.shift();
      } else {
        chartCandles[chartCandles.length - 1] = c;
      }
      initOrUpdateChart(chartCandles, sym);
      setChartStatus(`Live · ${sym} $${Number(c.close).toFixed(4)} (${tfLabel})`, "ok");
    }
  };

  sock.onerror = () => {
    setChartStatus(`Reconnecting feed (endpoint ${wsEndpointIdx + 1}/${DERIV_WS_ENDPOINTS.length})...`, "err");
  };

  sock.onclose = () => {
    if (wsPub !== sock) return;
    // Rotate through fallback WebSocket endpoints
    wsEndpointIdx = (wsEndpointIdx + 1) % DERIV_WS_ENDPOINTS.length;
    setChartStatus(`Reconnecting feed (endpoint ${wsEndpointIdx + 1}/${DERIV_WS_ENDPOINTS.length})...`, "err");
    const wait = Math.min(8000, 1000 * Math.pow(1.5, Math.min(4, chartRetry++)));
    setTimeout(() => {
      if (curPair === sym) subscribeDerivCandles(sym);
    }, wait);
  };
}

// ---------- PAIRS TAB (ONLY TRAINED PAIRS) ----------
function renderPairs() {
  const el = $("pairList");
  if (!el) return;
  el.innerHTML = "";

  const trainedPairs = getTrainedPairs();

  if (!trainedPairs.length) {
    el.innerHTML = `
      <div class="card dim" style="grid-column: 1 / -1; text-align: center; padding: 40px 20px;">
        <div style="font-size: 32px; margin-bottom: 8px;">📊</div>
        <h3 style="color: #fff; margin-bottom: 6px;">No Trained Pairs Yet</h3>
        <p style="margin-bottom: 16px;">Only pairs with trained models appear here for trading. Use the tabs below to get started:</p>
        <div style="display:flex; justify-content:center; gap:10px;">
          <button class="btn btn-primary" onclick="document.querySelector('nav button[data-p=train]').click()">Go to Train Pairs</button>
          <button class="btn btn-secondary" onclick="document.querySelector('nav button[data-p=upload]').click()">Upload Model Bundle</button>
        </div>
      </div>
    `;
    return;
  }

  trainedPairs.forEach(p => {
    const meta = PAIR_METADATA[p.symbol] || { name: p.symbol, isSynth: false, defaultDur: 15, defaultUnit: "m" };
    const div = document.createElement("div");
    div.className = "pair-card";

    const hasPass = p.verdict === "pass";
    const statusBadge = hasPass ?
      "<span class='badge badge-green'>VERIFIED PASS (REAL OK)</span>" :
      "<span class='badge badge-amber'>DEMO READY (TESTABLE)</span>";

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
          <div class="pair-desc">${meta.name} · Model v${p.pack_version || 1}</div>
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
    const manifest = JSON.parse(await manifestFile.async("text"));
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

    if (!wf.ok) throw new Error("Workflow dispatch failed");

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

// ---------- TRAIN TAB (ALL 27 PAIRS) ----------
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

  let tpl = "";
  try {
    tpl = await (await fetch(`https://raw.githubusercontent.com/${REPO}/main/TRAIN_PROMPT.md`)).text();
  } catch (_) {
    tpl = "# SENTINEL-FX Model Training Prompt\n";
  }

  let prompt = tpl + `\n\n## RUN PARAMETERS\nPAIR_SYMBOLS:\n` +
    chosen.map(s => {
      const isFx = s.startsWith("frx");
      const durs = isFx ? "15m and above (Deriv intraday floor)" : "Deriv allowed durations (seconds, minutes)";
      return `- ${s} (${PAIR_METADATA[s]?.name || s}) | Allowed Durations: ${durs}`;
    }).join("\n") +
    `\nOBJECTIVE: Compounding Balance Growth (model reasons about duration and stake)\nPAYOUT_ASSUMPTION: 0.85\n`;

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

// ---------- NEWS TAB (CLEAN CALENDAR - NO OUTCOME CHECKING) ----------
function renderNews() {
  api("/api/news").then(r => {
    const el = $("newsList");
    if (!el) return;
    el.innerHTML = "";

    const events = r.events || [];
    if (!events.length) {
      el.innerHTML = "<div class='card dim' style='text-align:center;'>No economic calendar events available.</div>";
      return;
    }

    events.forEach(e => {
      const t = new Date(e.utc_time);
      const lagos = new Date(t.getTime() + 3600e3);
      const div = document.createElement("div");
      div.className = "news-item";

      const impactBadge = e.impact === 'High' ? 'badge-red' : e.impact === 'Medium' ? 'badge-amber' : 'badge-blue';

      div.innerHTML = `
        <div class="news-item-header">
          <div>
            <span class="badge ${impactBadge}">${e.currency} · ${e.impact || 'Low'} Impact</span>
            <div class="news-title" style="margin-top:4px;">${e.title}</div>
            <div class="news-meta">
              ${lagos.toISOString().slice(0, 16).replace("T", " ")} Lagos time · Forecast: ${e.forecast || "—"} · Prev: ${e.previous || "—"}
            </div>
          </div>
        </div>
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

/* FIX-F global wiring: every button shows pending state; clears when network settles. */
(function sfxGlobalBusy(){
  let pending = 0;
  const of = window.fetch.bind(window);
  window.fetch = function(...args){
    pending++;
    return of(...args).finally(()=>{ pending = Math.max(0, pending-1); if(!pending) document.querySelectorAll('button[data-sfx-auto-busy]').forEach(b=>{ b.disabled=false; b.classList.remove('sfx-auto-busy'); delete b.dataset.sfxAutoBusy; }); });
  };
  document.addEventListener('click', (e)=>{
    const b = e.target.closest('button');
    if(!b || b.disabled || b.dataset.noBusy || b.dataset.sfxAutoBusy) return;
    b.dataset.sfxAutoBusy = '1'; b.disabled = true; b.classList.add('sfx-auto-busy');
    setTimeout(()=>{ if(b.dataset.sfxAutoBusy){ b.disabled=false; delete b.dataset.sfxAutoBusy; b.classList.remove('sfx-auto-busy'); } }, 15000);
  }, true);
})();
/* sfx-global-busy */
