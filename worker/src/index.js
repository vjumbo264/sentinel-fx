/**
 * SENTINEL-FX Worker — middle layer between the control site, the D1 state,
 * and the GitHub-Actions bot.
 *
 * Auth:
 *   - Site:  Authorization: Bearer <GitHub PAT>   (verified to have push access
 *            to the repo; PAT is used by the browser only and never stored here)
 *   - Bot:   X-Bot-Secret: <BOT_SHARED_SECRET>
 *
 * CORS: open to the Pages origin (and localhost for dev).
 */

const GITHUB_REPO = "vjumbo264/sentinel-fx";

// B1: single source of truth for the candle-data index + tracked pairs.
// The fetch workflow commits data/index.json to the repo root and publishes it
// as a release asset; the site must read the LIVE version through the Worker,
// never a stale copy bundled into the Pages deployment.
const RAW_BASE = `https://raw.githubusercontent.com/${GITHUB_REPO}/main`;
const DATA_CACHE_TTL_MS = 5 * 1000; // 45s short cache
const _dataCache = new Map(); // path -> { body, status, at }

async function fetchRepoFile(path, token) {
  const cached = _dataCache.get(path);
  if (cached && Date.now() - cached.at < DATA_CACHE_TTL_MS) return cached;
  // Primary: GitHub Contents API with the caller's own PAT (reliable from
  // Workers; raw.githubusercontent.com aggressively rate-limits Worker IPs).
  const attempts = [];
  if (token) {
    attempts.push([`https://api.github.com/repos/${GITHUB_REPO}/contents/${path}?ref=main`, {
      "Authorization": `Bearer ${token}`,
      "Accept": "application/vnd.github.raw",
      "User-Agent": "sentinel-fx-worker",
    }]);
  }
  attempts.push([`${RAW_BASE}/${path}`, { "User-Agent": "sentinel-fx-worker" }]);
  if (path === "data/index.json") {
    attempts.push([`https://github.com/${GITHUB_REPO}/releases/download/data-01/index.json`, { "User-Agent": "sentinel-fx-worker" }]);
  }
  let lastErr = "no attempt";
  for (const [u, headers] of attempts) {
    try {
      const r = await fetch(u, { headers });
      if (r.ok) {
        const body = await r.text();
        JSON.parse(body); // Never cache a non-JSON upstream error page.
        const out = { body, status: 200, at: Date.now() };
        _dataCache.set(path, out);
        return out;
      }
      lastErr = `upstream ${r.status} for ${u}`;
    } catch (e) {
      lastErr = String(e && e.message || e);
    }
  }
  const out = { body: null, status: 502, at: Date.now(), error: lastErr };
  if (cached && cached.body != null) return { ...cached, stale: true };
  return out; // Negative responses are not cached.
}

async function serveRepoData(request, path) {
  const a = await verifySiteAuth(request);
  if (!a) return err("unauthorized", 401);
  const got = await fetchRepoFile(path, a.token);
  if (got.body === null || got.body === undefined) {
    return err(`data unavailable: ${got.error}`, 502);
  }
  return new Response(got.body, {
    status: 200,
    headers: { "Content-Type": "application/json", "Cache-Control": "no-store", ...CORS },
  });
}
const ALL_TRACKED = [
  "frxEURUSD", "frxGBPUSD", "frxUSDJPY", "frxAUDUSD", "frxUSDCAD",
  "frxUSDCHF", "frxNZDUSD", "frxEURGBP", "frxEURJPY", "frxGBPJPY",
  "frxEURAUD", "frxAUDJPY", "frxEURCAD", "frxEURCHF",
  "R_10", "R_25", "R_50", "R_75", "R_100",
  "1HZ10V", "1HZ25V", "1HZ50V", "1HZ75V", "1HZ100V",
  "1HZ150V", "1HZ250V", "1HZ300V"
];


const CORS = {
  "Access-Control-Allow-Origin": "*",
  "Access-Control-Allow-Methods": "GET,POST,PUT,DELETE,OPTIONS",
  "Access-Control-Allow-Headers": "Content-Type,Authorization,X-Bot-Secret",
};

function json(data, status = 200) {
  return new Response(JSON.stringify(data), {
    status,
    headers: { "Content-Type": "application/json", ...CORS },
  });
}
function err(message, status = 400) { return json({ error: message }, status); }

function nowUTC() { return new Date().toISOString().replace(/\.\d{3}Z$/, "Z"); }

// Lagos date key (UTC+1)
function lagosDate(d = new Date()) {
  const l = new Date(d.getTime() + 60 * 60 * 1000);
  return l.toISOString().slice(0, 10);
}

async function verifySiteAuth(request) {
  const auth = request.headers.get("Authorization") || "";
  const token = auth.replace(/^Bearer\s+/i, "").trim();
  if (!token) return null;
  try {
    const r = await fetch(`https://api.github.com/repos/${GITHUB_REPO}`, {
      headers: {
        Authorization: `token ${token}`,
        Accept: "application/vnd.github+json",
        "User-Agent": "sentinel-fx-worker",
      },
    });
    if (!r.ok) return null;
    const repo = await r.json();
    const perms = repo.permissions || {};
    if (perms.push || perms.admin || perms.maintain) {
      return { token };
    }
  } catch (_) { /* fallthrough */ }
  return null;
}

function verifyBotAuth(request, env) {
  const s = request.headers.get("X-Bot-Secret") || "";
  return s && env.BOT_SHARED_SECRET && s === env.BOT_SHARED_SECRET;
}

async function logLine(env, level, pair, message, data) {
  await env.DB.prepare(
    "INSERT INTO logs (ts, level, pair, message, data) VALUES (?,?,?,?,?)"
  ).bind(nowUTC(), level, pair || null, message, data ? JSON.stringify(data) : null).run();
}

export default {
  async fetch(request, env) {
    if (request.method === "OPTIONS") return new Response(null, { headers: CORS });
    const url = new URL(request.url);
    const path = url.pathname;
    const method = request.method;

    // Parse JSON body once for every non-GET request (site AND bot endpoints)
    let body = {};
    if (method !== "GET") body = await request.json().catch(() => ({}));

    try {

      // -------- public health
      if (path === "/api/health") {
        return json({ ok: true, service: "sentinel-fx-worker", utc: nowUTC() });
      }

      // Public read-only training state, sourced from the actual repository.
      if (path === "/api/training/state" && method === "GET") {
        try {
          const upstream = await fetch(`${RAW_BASE}/training_state.json`, {
            cf: { cacheTtl: 60 }, headers: { "User-Agent": "sentinel-fx-worker" }
          });
          if (!upstream.ok) return json({ error: "training state unavailable" }, 503);
          const state = await upstream.json();
          if (!Array.isArray(state.queue)) return json({ error: "invalid training state" }, 503);
          return json(state);
        } catch (_) {
          return json({ error: "training state unavailable" }, 503);
        }
      }

      // -------- site auth probe
      if (path === "/api/auth/check" && method === "GET") {
        const a = await verifySiteAuth(request);
        return a ? json({ ok: true, repo: GITHUB_REPO }) : err("unauthorized", 401);
      }

      // ============================ BOT ENDPOINTS ============================
      if (path.startsWith("/api/bot/")) {
        if (!verifyBotAuth(request, env)) return err("unauthorized", 401);

        if (path === "/api/bot/state" && method === "GET") {
          const settings = {};
          const rs = await env.DB.prepare("SELECT key, value FROM settings").all();
          for (const r of rs.results) settings[r.key] = JSON.parse(r.value);
          const pairs = await env.DB.prepare("SELECT * FROM pairs").all();
          const hb = await env.DB.prepare("SELECT * FROM heartbeat WHERE id=1").first();
          return json({ settings, pairs: pairs.results, heartbeat: hb, lagos_date: lagosDate() });
        }

        if (path === "/api/bot/heartbeat" && method === "POST") {
          // FIX-B: persist CONNECTED account identity; FIX3-F4: persist equity + free margin
          const cur = await env.DB.prepare("SELECT loginid, currency FROM heartbeat WHERE id=1").first();
          const loginid = body.loginid !== undefined ? body.loginid : (cur ? cur.loginid : null);
          const currency = body.currency !== undefined ? body.currency : (cur ? cur.currency : null);
          const SQL =
            "INSERT INTO heartbeat (id, ts, mode, balance, equity, free_margin, note, loginid, currency) VALUES (1,?,?,?,?,?,?,?,?) " +
            "ON CONFLICT(id) DO UPDATE SET ts=excluded.ts, mode=excluded.mode, balance=excluded.balance, " +
            "equity=excluded.equity, free_margin=excluded.free_margin, note=excluded.note, loginid=excluded.loginid, currency=excluded.currency";
          const ARGS = [nowUTC(), body.mode || null, body.balance ?? null, body.equity ?? null, body.free_margin ?? null, body.note || null, loginid, currency];
          try {
            await env.DB.prepare(SQL).bind(...ARGS).run();
          } catch (e) {
            // D1 migration-safe: add columns if the table predates them, then retry once
            if (String(e).includes("no column") || String(e).includes("equity")) {
              try { await env.DB.prepare("ALTER TABLE heartbeat ADD COLUMN equity REAL").run(); } catch (_) {}
              try { await env.DB.prepare("ALTER TABLE heartbeat ADD COLUMN free_margin REAL").run(); } catch (_) {}
              await env.DB.prepare(SQL).bind(...ARGS).run();
            } else { throw e; }
          }
          return json({ ok: true });
        }

        if (path === "/api/bot/settings" && method === "POST") {
          // bot-side settings writes (e.g. news cache, mode fallback)
          const b = body;
          for (const [k, v] of Object.entries(b)) {
            if (k.toLowerCase().includes("token") || k.toLowerCase().includes("secret")) {
              return err("refusing to store secrets in D1", 400);
            }
            await env.DB.prepare(
              "INSERT INTO settings (key, value, updated_utc) VALUES (?,?,?) " +
              "ON CONFLICT(key) DO UPDATE SET value=excluded.value, updated_utc=excluded.updated_utc"
            ).bind(k, JSON.stringify(v), nowUTC()).run();
          }
          return json({ ok: true });
        }

        if (path === "/api/bot/cfd-sync" && method === "POST") {
          if (body.mode !== "demo") return err("acceptance sync requires demo", 400);
          await env.DB.batch([
            env.DB.prepare("CREATE TABLE IF NOT EXISTS cfd_deals (ticket INTEGER PRIMARY KEY, position_id INTEGER, symbol TEXT, net REAL NOT NULL, data TEXT NOT NULL)"),
            env.DB.prepare("CREATE TABLE IF NOT EXISTS cfd_positions (ticket INTEGER PRIMARY KEY, data TEXT NOT NULL)"),
            env.DB.prepare("CREATE TABLE IF NOT EXISTS cfd_ownership (position_id INTEGER PRIMARY KEY, model_symbol TEXT NOT NULL,reason TEXT)"),
            env.DB.prepare("CREATE TABLE IF NOT EXISTS cfd_credits (ticket INTEGER PRIMARY KEY, model_symbol TEXT NOT NULL)")
          ]);
          for (const own of body.ownership||[]) {
            await env.DB.prepare("INSERT OR IGNORE INTO cfd_ownership VALUES (?,?,?)").bind(own.position_id,own.model_symbol,own.reason||null).run();
          }
          const stmts = [];
          for (const d of body.deals || []) {
            if (!(d.ticket > 0 && d.position_id > 0)) return err("invalid real deal ticket", 400);
            const net = Number(d.profit || 0) + Number(d.swap || 0) + Number(d.commission || 0) + Number(d.fee || 0);
            stmts.push(env.DB.prepare("INSERT OR IGNORE INTO cfd_deals VALUES (?,?,?,?,?)").bind(d.ticket, d.position_id, d.symbol, net, JSON.stringify(d)));
          }
          if (stmts.length) await env.DB.batch(stmts);
          for (const d of body.deals||[]) {
            const own=await env.DB.prepare("SELECT * FROM cfd_ownership WHERE position_id=?").bind(d.position_id).first();
            if(!own) continue;
            // The conditional credit and dedupe marker are one atomic transaction.
            await env.DB.batch([
              env.DB.prepare("UPDATE model_ledger SET balance=balance+(SELECT net FROM cfd_deals WHERE ticket=?),updated_utc=? WHERE symbol=? AND NOT EXISTS (SELECT 1 FROM cfd_credits WHERE ticket=?)").bind(d.ticket,nowUTC(),own.model_symbol,d.ticket),
              env.DB.prepare("INSERT OR IGNORE INTO cfd_credits VALUES (?,?)").bind(d.ticket,own.model_symbol)
            ]);
          }
          // Replacement is an authoritative broker snapshot, not generated positions.
          await env.DB.prepare("DELETE FROM cfd_positions").run();
          for (const pos of body.positions || []) {
            await env.DB.prepare("INSERT INTO cfd_positions VALUES (?,?)").bind(pos.ticket, JSON.stringify({...pos, model_id: body.model_id, reason: body.reason})).run();
          }
          const ids = [...new Set((body.deals || []).map(d => d.position_id))];
          let net = 0;
          for (const id of ids) {
            const row = await env.DB.prepare("SELECT SUM(net) AS net FROM cfd_deals WHERE position_id=?").bind(id).first();
            net += Number(row?.net || 0);
          }
          return json({ok:true, deals:(body.deals || []).length, positions:(body.positions || []).length, net});
        }

        if (path === "/api/bot/decision" && method === "POST") {
          await logLine(env, "decision", body.symbol, body.reason || "Policy decision", body);
          return json({ok:true});
        }

        if (path === "/api/bot/log" && method === "POST") {
          await logLine(env, body.level || "info", body.pair, body.message || "", body.data);
          return json({ ok: true });
        }

        if (path === "/api/bot/lock" && method === "POST") {
          const now = nowUTC();
          const lease = new Date(Date.now() + 60000).toISOString();
          const owner = String(body.owner || "");
          if (!owner) return err("owner required");
          const result = await env.DB.prepare(
            "INSERT INTO run_lock (id,owner,lease_until,updated_utc) VALUES (1,?,?,?) ON CONFLICT(id) DO UPDATE SET owner=excluded.owner,lease_until=excluded.lease_until,updated_utc=excluded.updated_utc WHERE run_lock.owner=excluded.owner OR run_lock.lease_until<=?"
          ).bind(owner,lease,now,now).run();
          return json({acquired:result.meta.changes===1, lease_until:lease});
        }

        if (path === "/api/bot/models" && method === "GET") {
          const result = await env.DB.prepare("SELECT symbol FROM pairs WHERE enabled=1 AND pack_version>0").all();
          return json({symbols:result.results.map(r=>r.symbol)});
        }
        if (path === "/api/bot/ready") {
          await env.DB.prepare("CREATE TABLE IF NOT EXISTS runner_ready (owner TEXT PRIMARY KEY,ts TEXT NOT NULL,models TEXT NOT NULL)").run();
          if (method === "POST") {
            if (body.mode!=="demo") return err("demo only",400);
            await env.DB.prepare("INSERT INTO runner_ready VALUES (?,?,?) ON CONFLICT(owner) DO UPDATE SET ts=excluded.ts,models=excluded.models").bind(body.owner,nowUTC(),JSON.stringify(body.models||[])).run();
            return json({ok:true});
          }
          const runners = await env.DB.prepare("SELECT * FROM runner_ready WHERE ts>? ORDER BY ts DESC").bind(new Date(Date.now()-60000).toISOString()).all();
          return json({runners:runners.results});
        }
        if (path === "/api/bot/transfer" && method === "POST") {
          const ready=await env.DB.prepare("SELECT * FROM runner_ready WHERE owner=? AND ts>?").bind(body.new_owner,new Date(Date.now()-60000).toISOString()).first();
          if (!ready) return json({transferred:false,reason:"successor not READY"});
          const lease=new Date(Date.now()+60000).toISOString();
          const result=await env.DB.prepare("UPDATE run_lock SET owner=?,lease_until=?,updated_utc=? WHERE id=1 AND owner=? AND lease_until>?").bind(body.new_owner,lease,nowUTC(),body.owner,nowUTC()).run();
          if(result.meta.changes===1) await logLine(env,"handover","*","READY-before-transfer",{from:body.owner,to:body.new_owner});
          return json({transferred:result.meta.changes===1});
        }

        if (path === "/api/bot/unlock" && method === "POST") {
          await env.DB.prepare("UPDATE run_lock SET lease_until=? WHERE id=1 AND owner=?")
            .bind(nowUTC(), body.owner || "").run();
          return json({ ok: true });
        }

        if (path === "/api/bot/trade" && method === "POST") {
          await env.DB.prepare(
            `INSERT INTO trades (contract_id, pair, side, stake, payout, open_utc, mode, model_prob, news_flag, reason)
             VALUES (?,?,?,?,?,?,?,?,?,?)
             ON CONFLICT(contract_id) DO NOTHING`
          ).bind(body.contract_id, body.pair, body.side, body.stake, body.payout ?? null,
                 nowUTC(), body.mode || "demo", body.model_prob ?? null,
                 body.news_flag || null, body.reason || null).run();
          return json({ ok: true });
        }

        if (path === "/api/bot/trade/settle" && method === "POST") {
          await env.DB.prepare(
            "UPDATE trades SET close_utc=?, result=?, pnl=? WHERE contract_id=?"
          ).bind(nowUTC(), body.result, body.pnl ?? 0, body.contract_id).run();
          // daily stats
          const d = lagosDate();
          await env.DB.prepare(
            `INSERT INTO daily_stats (lagos_date, pnl, trades, wins) VALUES (?,?,?,?)
             ON CONFLICT(lagos_date) DO UPDATE SET pnl=pnl+excluded.pnl, trades=trades+1, wins=wins+excluded.wins`
          ).bind(d, body.pnl ?? 0, 1, body.result === "win" ? 1 : 0).run();
          return json({ ok: true });
        }

        if (path === "/api/bot/news" && method === "POST") {
          const ev = body.events || [];
          const stmt = env.DB.prepare(
            `INSERT INTO news_events (id, utc_time, currency, title, impact, forecast, previous, affected_pairs)
             VALUES (?,?,?,?,?,?,?,?)
             ON CONFLICT(id) DO UPDATE SET forecast=excluded.forecast, previous=excluded.previous`
          );
          for (const e of ev) {
            await stmt.bind(e.id, e.utc_time, e.currency, e.title, e.impact,
                            e.forecast, e.previous, JSON.stringify(e.affected_pairs || [])).run();
          }
          return json({ ok: true, upserted: ev.length });
        }

        if (path === "/api/bot/news/reaction" && method === "POST") {
          await env.DB.prepare(
            "INSERT INTO news_reactions (event_key, pair, move_5m, move_15m, recorded_utc) VALUES (?,?,?,?,?)"
          ).bind(body.event_key, body.pair, body.move_5m ?? null, body.move_15m ?? null, nowUTC()).run();
          return json({ ok: true });
        }

        if (path === "/api/bot/news/reactions" && method === "GET") {
          const pair = url.searchParams.get("pair");
          const q = pair
            ? env.DB.prepare("SELECT * FROM news_reactions WHERE pair=? ORDER BY id DESC LIMIT 200").bind(pair)
            : env.DB.prepare("SELECT * FROM news_reactions ORDER BY id DESC LIMIT 200");
          const r = await q.all();
          return json({ reactions: r.results });
        }

        if (path === "/api/bot/forward" && method === "POST") {
          // FWD: forward-eval workflow stores rolling out-of-sample metrics
          await env.DB.prepare(
            "INSERT INTO forward_metrics (symbol, version, computed_utc, metrics) VALUES (?,?,?,?) " +
            "ON CONFLICT(symbol, version) DO UPDATE SET computed_utc=excluded.computed_utc, metrics=excluded.metrics"
          ).bind(body.symbol, body.version, nowUTC(), JSON.stringify(body.metrics || {})).run();
          return json({ ok: true });
        }

        if (path === "/api/bot/trades/open" && method === "GET") {
          const r = await env.DB.prepare("SELECT * FROM trades WHERE close_utc IS NULL").all();
          return json({ open: r.results });
        }

        if (path === "/api/bot/session" && method === "GET") {
          // FIX3-F2: the bot reads the owner-set pool, per-model shares and
          // session-scoped risk settings from here every cycle.
          const s = await env.DB.prepare("SELECT * FROM session ORDER BY id DESC LIMIT 1").all();
          const led = await env.DB.prepare("SELECT * FROM model_ledger ORDER BY symbol").all();
          const settings = {};
          const rs = await env.DB.prepare("SELECT key, value FROM settings").all();
          for (const r of rs.results) settings[r.key] = JSON.parse(r.value);
          return json({ session: s.results[0] || null, ledger: led.results, settings, lagos_date: lagosDate() });
        }

        if (path === "/api/bot/overrides" && method === "GET") {
          const ov = await env.DB.prepare("SELECT * FROM overrides ORDER BY symbol").all();
          return json({ overrides: ov.results });
        }

        if (path === "/api/bot/risk-status" && method === "POST") {
          const m = body.mode || "demo";
          await env.DB.prepare(
            "INSERT INTO settings (key, value, updated_utc) VALUES (?,?,?) " +
            "ON CONFLICT(key) DO UPDATE SET value=excluded.value, updated_utc=excluded.updated_utc"
          ).bind(`risk_status_${m}`, JSON.stringify(body), nowUTC()).run();
          return json({ ok: true });
        }

        return err("not found", 404);
      }

      // ============================ SITE ENDPOINTS ===========================
      const site = await verifySiteAuth(request);
      if (!site) return err("unauthorized", 401);

      // FIX-D: candle proxy so the site chart always renders through the Worker.
      if (path === "/api/candles" && method === "GET") {
        const symbol = url.searchParams.get("symbol") || "R_100";
        const gran = Math.max(1, parseInt(url.searchParams.get("granularity") || "60", 10) || 60);
        const count = Math.min(5000, Math.max(10, parseInt(url.searchParams.get("count") || "300", 10) || 300));

        // Check memory cache (10 seconds)
        const cacheKey = `${symbol}_${gran}`;
        const now = Date.now();
        if (globalThis._candlesCache && globalThis._candlesCache[cacheKey] && (now - globalThis._candlesCache[cacheKey].ts < 10000)) {
          const cached = globalThis._candlesCache[cacheKey];
          return json({ ok: true, symbol, granularity: gran, count: cached.candles.length, candles: cached.candles, source: "cache" });
        }

        try {
          const derivToken = env.DERIV_BEARER_TOKEN;
          const derivAppId = env.DERIV_APP_ID || "1089";
          let wsUrl = `wss://ws.derivws.com/websockets/v3?app_id=${derivAppId}`;

          // Authenticated OTP flow
          if (derivToken) {
            try {
              const accsRes = await fetch("https://api.derivws.com/trading/v1/options/accounts", {
                headers: {
                  "Authorization": `Bearer ${derivToken}`,
                  "Deriv-App-ID": derivAppId,
                  "Accept": "application/json",
                  "User-Agent": "sentinel-fx-worker/2.0"
                }
              });
              if (accsRes.ok) {
                const accsData = await accsRes.json();
                const accs = accsData.data || accsData.accounts || [];
                const demoAcc = accs.find(a =>
                  a.account_type === "demo" ||
                  String(a.loginid || a.account_id || "").startsWith("VRTC") ||
                  String(a.loginid || a.account_id || "").startsWith("DOT")
                ) || accs[0];

                if (demoAcc) {
                  const lid = demoAcc.account_id || demoAcc.loginid;
                  const otpRes = await fetch(`https://api.derivws.com/trading/v1/options/accounts/${lid}/otp`, {
                    method: "POST",
                    headers: {
                      "Authorization": `Bearer ${derivToken}`,
                      "Deriv-App-ID": derivAppId,
                      "Content-Type": "application/json",
                      "Accept": "application/json",
                      "User-Agent": "sentinel-fx-worker/2.0"
                    },
                    body: "{}"
                  });
                  if (otpRes.ok) {
                    const otpData = await otpRes.json();
                    if (otpData?.data?.url) {
                      wsUrl = otpData.data.url;
                    }
                  }
                }
              }
            } catch (authErr) {
              console.warn("Worker auth OTP fallback:", authErr);
            }
          }

          // Open outbound WebSocket in Cloudflare Workers
          const wsResponse = await fetch(wsUrl, {
            headers: {
              Upgrade: "websocket",
              Origin: "https://app.deriv.com",
              "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
            }
          });
          const sock = wsResponse.webSocket;
          if (!sock) {
            throw new Error("Deriv WebSocket upgrade failed");
          }
          sock.accept();

          const candles = await new Promise((resolve, reject) => {
            const timeout = setTimeout(() => {
              try { sock.close(); } catch (_) {}
              reject(new Error("Deriv ticks_history timeout"));
            }, 8000);

            sock.addEventListener("message", (ev) => {
              try {
                const msg = JSON.parse(ev.data);
                if (msg.error) {
                  clearTimeout(timeout);
                  try { sock.close(); } catch (_) {}
                  return reject(new Error(msg.error.message || "Deriv error"));
                }
                if (msg.candles) {
                  clearTimeout(timeout);
                  try { sock.close(); } catch (_) {}
                  return resolve(msg.candles);
                }
              } catch (_) {}
            });

            sock.addEventListener("error", (err) => {
              clearTimeout(timeout);
              try { sock.close(); } catch (_) {}
              reject(new Error("WebSocket connection error"));
            });

            sock.send(JSON.stringify({
              ticks_history: symbol,
              adjust_start_time: 1,
              count,
              end: "latest",
              granularity: gran,
              style: "candles",
              req_id: 1
            }));
          });

          candles.sort((a, b) => +a.epoch - +b.epoch);
          if (!globalThis._candlesCache) globalThis._candlesCache = {};
          globalThis._candlesCache[cacheKey] = { ts: now, candles };

          return json({ ok: true, symbol, granularity: gran, count: candles.length, candles });
        } catch (e) {
          const errMsg = (e && e.message) ? e.message : String(e);
          const isMarketClosed = errMsg.toLowerCase().includes("closed") || errMsg.toLowerCase().includes("market is closed");
          return json({
            error: errMsg,
            market_closed: isMarketClosed,
            symbol
          }, 200); // Valid response describing an unavailable upstream, never invented candles.
        }
      }

      // SESSION: per-model bankroll ledger + owner overrides
      if (path === "/api/session" && method === "GET") {
        const s = await env.DB.prepare("SELECT * FROM session ORDER BY id DESC LIMIT 1").all();
        const led = await env.DB.prepare("SELECT * FROM model_ledger ORDER BY symbol").all();
        const ov = await env.DB.prepare("SELECT * FROM overrides ORDER BY symbol").all();
        return json({ session: s.results[0] || null, ledger: led.results, overrides: ov.results });
      }

      if (path === "/api/session/allocate" && method === "POST") {
        // Equal-split allocation of the demo balance across active models.
        if (!(await verifySiteAuth(request))) return err("unauthorized", 401);
        const bal = Number(body.balance ?? 0);
        if (!(bal > 0)) return err("balance required", 400);
        const active = await env.DB.prepare(
          "SELECT symbol FROM model_ledger WHERE active=1"
        ).all();
        const syms = active.results.map(r => r.symbol);
        if (!syms.length) return err("no active models", 400);
        const share = Math.floor((bal / syms.length) * 100) / 100;
        const ts = nowUTC();
        for (const s2 of syms) {
          await env.DB.prepare(
            `INSERT INTO model_ledger (symbol, allocated, balance, active, updated_utc)
             VALUES (?,?,?,1,?)
             ON CONFLICT(symbol) DO UPDATE SET allocated=excluded.allocated, updated_utc=excluded.updated_utc`
          ).bind(s2, share, share, ts).run();
          await env.DB.prepare(
            "INSERT INTO ledger_events (ts, symbol, kind, amount, note) VALUES (?,?,?,?,?)"
          ).bind(ts, s2, "allocate", share, "equal-split of " + bal).run();
        }
        await env.DB.prepare(
          "INSERT INTO session (started_utc, mode, starting_balance, note) VALUES (?,?,?,?)"
        ).bind(ts, body.mode || "demo", bal, "allocated " + share + " x " + syms.length).run();
        return json({ ok: true, share, symbols: syms });
      }

      if (path === "/api/session/override" && method === "POST") {
        // Owner override: pause/resume a model or force stop-all. Bot must honor.
        if (!(await verifySiteAuth(request))) return err("unauthorized", 401);
        const symbol = body.symbol || "*";
        const action = body.action; // pause | resume | stop_all
        if (!["pause", "resume", "stop_all"].includes(action)) return err("bad action", 400);
        const ts = nowUTC();
        await env.DB.prepare(
          `INSERT INTO overrides (symbol, action, updated_utc) VALUES (?,?,?)
           ON CONFLICT(symbol) DO UPDATE SET action=excluded.action, updated_utc=excluded.updated_utc`
        ).bind(symbol, action, ts).run();
        await env.DB.prepare(
          "INSERT INTO ledger_events (ts, symbol, kind, amount, note) VALUES (?,?,?,?,?)"
        ).bind(ts, symbol, "override:" + action, 0, body.note || "owner override").run();
        return json({ ok: true });
      }

      if (path === "/api/session/ledger/event" && method === "POST") {
        // Bot posts realized PnL per trade here; ledger tracks each model's balance.
        if (request.headers.get("X-Bot-Secret") !== env.BOT_SHARED_SECRET) return err("unauthorized", 401);
        const ts = nowUTC();
        await env.DB.prepare(
          "INSERT INTO ledger_events (ts, symbol, kind, amount, note) VALUES (?,?,?,?,?)"
        ).bind(ts, body.symbol, body.kind || "trade", Number(body.amount ?? 0), body.note || null).run();
        await env.DB.prepare(
          `INSERT INTO model_ledger (symbol, allocated, balance, active, updated_utc)
           VALUES (?,0,?,1,?)
           ON CONFLICT(symbol) DO UPDATE SET balance=balance+excluded.balance, updated_utc=excluded.updated_utc`
        ).bind(body.symbol, Number(body.amount ?? 0), ts).run();
        return json({ ok: true });
      }

      if (path === "/api/state" && method === "GET") {
        const settings = {};
        const rs = await env.DB.prepare("SELECT key, value FROM settings").all();
        for (const r of rs.results) settings[r.key] = JSON.parse(r.value);
        let pairs = await env.DB.prepare("SELECT * FROM pairs").all();
        // Ensure all tracked forex and synthetic pairs exist
        const existingSyms = new Set((pairs.results || []).map(p => p.symbol));
        let seeded = false;
        for (const sym of ALL_TRACKED) {
          if (!existingSyms.has(sym)) {
            await env.DB.prepare(
              `INSERT OR IGNORE INTO pairs (symbol, enabled, shadow_mode, status, min_stake, max_stake, stake_pct, max_consec_losses, pack_version, verdict, has_custom_code, updated_utc)
               VALUES (?, 0, 0, 'ready', 0.35, 10.0, 0.01, 3, 0, 'untested', 0, ?)`
            ).bind(sym, nowUTC()).run();
            seeded = true;
          }
        }
        if (seeded) {
          pairs = await env.DB.prepare("SELECT * FROM pairs").all();
        }
        const hb = await env.DB.prepare("SELECT * FROM heartbeat WHERE id=1").first();
        const today = await env.DB.prepare("SELECT * FROM daily_stats WHERE lagos_date=?")
          .bind(lagosDate()).first();
        return json({ settings, pairs: pairs.results, heartbeat: hb, today: today || { pnl: 0, trades: 0, wins: 0 }, lagos_date: lagosDate() });
      }

      if (path === "/api/account/reset-demo-balance" && method === "POST") {
        return err("MT5 balance reset must be performed at the broker; no ledger or balance was changed",409);
      }

      if (path === "/api/settings" && method === "POST") {
        for (const [k, v] of Object.entries(body)) {
          if (k.toLowerCase().includes("token") || k.toLowerCase().includes("secret")) {
            return err("refusing to store secrets in D1", 400);
          }
          await env.DB.prepare(
            "INSERT INTO settings (key, value, updated_utc) VALUES (?,?,?) " +
            "ON CONFLICT(key) DO UPDATE SET value=excluded.value, updated_utc=excluded.updated_utc"
          ).bind(k, JSON.stringify(v), nowUTC()).run();
        }
        return json({ ok: true });
      }

      if (path === "/api/risk/overrides" && method === "GET") {
        const m = url.searchParams.get("mode") || "demo";
        const def = {
          take_profit: { enabled: false, unit: "money", value: null },
          stop_loss: { enabled: false, unit: "money", value: null },
          daily_profit_target: { enabled: false, unit: "money", value: null, close_open_on_hit: false },
          daily_loss_limit: { enabled: false, unit: "money", value: null, close_open_on_hit: false },
          trade_weekends: false,
        };
        const row = await env.DB.prepare("SELECT value FROM settings WHERE key=?").bind(`risk_overrides_${m}`).first();
        const overrides = row ? JSON.parse(row.value) : def;
        const statusRow = await env.DB.prepare("SELECT value FROM settings WHERE key=?").bind(`risk_status_${m}`).first();
        const risk_status = statusRow ? JSON.parse(statusRow.value) : { status: "normal", today_pnl: 0 };
        const testKeyRow = await env.DB.prepare("SELECT value FROM settings WHERE key='test_day_key'").first();
        const test_day_key = testKeyRow ? JSON.parse(testKeyRow.value) : null;
        return json({ ok: true, mode: m, overrides, risk_status, test_day_key, utc_now: nowUTC() });
      }

      if (path === "/api/risk/overrides" && method === "POST") {
        const m = body.mode || "demo";
        const overrides = body.overrides || {};
        await env.DB.prepare(
          "INSERT INTO settings (key, value, updated_utc) VALUES (?,?,?) " +
          "ON CONFLICT(key) DO UPDATE SET value=excluded.value, updated_utc=excluded.updated_utc"
        ).bind(`risk_overrides_${m}`, JSON.stringify(overrides), nowUTC()).run();
        return json({ ok: true, mode: m, overrides });
      }

      if (path === "/api/risk/clear-daily-limit" && method === "POST") {
        const m = body.mode || "demo";
        await env.DB.prepare(
          "INSERT INTO settings (key, value, updated_utc) VALUES (?,?,?) " +
          "ON CONFLICT(key) DO UPDATE SET value=excluded.value, updated_utc=excluded.updated_utc"
        ).bind(`risk_status_${m}`, JSON.stringify({ status: "normal", cleared_utc: nowUTC(), today_pnl: 0, reason: "cleared manually by owner" }), nowUTC()).run();
        return json({ ok: true, mode: m, status: "normal" });
      }

      if (path === "/api/test/shift-day-key" && method === "POST") {
        const dayKey = body.test_day_key ?? null;
        await env.DB.prepare(
          "INSERT INTO settings (key, value, updated_utc) VALUES (?,?,?) " +
          "ON CONFLICT(key) DO UPDATE SET value=excluded.value, updated_utc=excluded.updated_utc"
        ).bind("test_day_key", JSON.stringify(dayKey), nowUTC()).run();
        return json({ ok: true, test_day_key: dayKey });
      }

      if (path === "/api/settings/test-login-result" && method === "POST") {
        await env.DB.prepare(
          "INSERT INTO settings (key, value, updated_utc) VALUES (?,?,?) " +
          "ON CONFLICT(key) DO UPDATE SET value=excluded.value, updated_utc=excluded.updated_utc"
        ).bind("test_login_result", JSON.stringify(body), nowUTC()).run();
        return json({ ok: true });
      }

      if (path === "/api/settings/test-login-result" && method === "GET") {
        const row = await env.DB.prepare("SELECT value FROM settings WHERE key='test_login_result'").first();
        const result = row ? JSON.parse(row.value) : null;
        return json({ ok: true, result });
      }

      if (path === "/api/settings/mt5" && method === "GET") {
        const row = await env.DB.prepare("SELECT value FROM settings WHERE key='mt5_account_config'").first();
        const conf = row ? JSON.parse(row.value) : {
          demo_login: "41286446",
          demo_server: "Deriv-Demo",
          real_login: "10357278",
          real_server: "DerivSVG-Server",
          has_password: true
        };
        delete conf.password;
        return json({ ok: true, config: conf });
      }

      if (path === "/api/settings/mt5" && method === "POST") {
        const conf = {
          demo_login: String(body.demo_login || "41286446"),
          demo_server: String(body.demo_server || "Deriv-Demo"),
          real_login: String(body.real_login || "10357278"),
          real_server: String(body.real_server || "DerivSVG-Server"),
          has_password: true
        };
        await env.DB.prepare(
          "INSERT INTO settings (key, value, updated_utc) VALUES (?,?,?) " +
          "ON CONFLICT(key) DO UPDATE SET value=excluded.value, updated_utc=excluded.updated_utc"
        ).bind("mt5_account_config", JSON.stringify(conf), nowUTC()).run();
        return json({ ok: true, config: conf });
      }

      if (path === "/api/pairs/update" && method === "POST") {
        const allowed = ["enabled", "shadow_mode", "duration", "duration_unit", "min_stake", "max_stake", "stake_pct",
                         "daily_loss_cap", "daily_target", "max_consec_losses", "status", "pack_version", "verdict", "has_custom_code"];
        const sets = [], vals = [];
        for (const k of allowed) {
          if (k in body) { sets.push(`${k}=?`); vals.push(body[k]); }
        }
        if (!sets.length || !body.symbol) return err("nothing to update");
        if (body.min_stake !== undefined && body.min_stake < 0.35) return err("min_stake below 0.35");
        vals.push(nowUTC(), body.symbol);
        await env.DB.prepare(`UPDATE pairs SET ${sets.join(",")}, updated_utc=? WHERE symbol=?`).bind(...vals).run();
        return json({ ok: true });
      }

      if (path === "/api/pairs" && method === "GET") {
        const pairs = await env.DB.prepare("SELECT * FROM pairs").all();
        const packs = await env.DB.prepare(
          "SELECT symbol, version, status, verdict, has_custom_code, metrics, installed_utc FROM pair_packs ORDER BY version DESC"
        ).all();
        const models = await env.DB.prepare("SELECT * FROM models ORDER BY version DESC").all().catch(() => ({ results: [] }));
        const fwd = await env.DB.prepare("SELECT * FROM forward_metrics").all().catch(() => ({ results: [] }));
        return json({ pairs: pairs.results, packs: packs.results, models: models.results, forward: fwd.results });
      }

            if (path === "/api/settings/training-lock" && method === "POST") {
        const locked = Boolean(body.locked);
        const reason = String(body.reason || "");
        await env.DB.prepare(
          "INSERT INTO settings (key, value, updated_utc) VALUES (?,?,?) " +
          "ON CONFLICT(key) DO UPDATE SET value=excluded.value, updated_utc=excluded.updated_utc"
        ).bind("training_locked", JSON.stringify(locked), nowUTC()).run();
        await env.DB.prepare(
          "INSERT INTO settings (key, value, updated_utc) VALUES (?,?,?) " +
          "ON CONFLICT(key) DO UPDATE SET value=excluded.value, updated_utc=excluded.updated_utc"
        ).bind("training_lock_reason", JSON.stringify(reason), nowUTC()).run();
        return json({ ok: true });
      }

      if (path === "/api/logs" && method === "GET") {
        const level = url.searchParams.get("level");
        const lim = Math.min(200, parseInt(url.searchParams.get("limit") || "100"));
        const q = level
          ? env.DB.prepare("SELECT * FROM logs WHERE level=? ORDER BY id DESC LIMIT ?").bind(level, lim)
          : env.DB.prepare("SELECT * FROM logs ORDER BY id DESC LIMIT ?").bind(lim);
        const r = await q.all();
        return json({ logs: r.results.reverse() });
      }

      if (path === "/api/trades" && method === "GET") {
        try {
          const active=await env.DB.prepare("SELECT data FROM cfd_positions").all();
          const rows=await env.DB.prepare("SELECT position_id,SUM(net) net FROM cfd_deals GROUP BY position_id").all();
          const open=active.results.map(r=>JSON.parse(r.data));const openIds=new Set(open.map(p=>p.ticket));const trades=[];
          for(const p of open) {
            const own=await env.DB.prepare("SELECT * FROM cfd_ownership WHERE position_id=?").bind(p.ticket).first();
            trades.push({contract_id:p.ticket,pair:p.symbol,side:p.type,stake:p.volume,open_price:p.price_open,current_price:p.price_current,sl:p.sl,tp:p.tp,pnl:p.profit,open_utc:new Date(p.time*1000).toISOString(),close_utc:null,reason:own?.reason||p.reason||p.comment,model_id:own?.model_symbol||null,mode:"demo"});
          }
          for(const row of rows.results) {
            if(openIds.has(row.position_id))continue;
            const ds=await env.DB.prepare("SELECT data FROM cfd_deals WHERE position_id=? ORDER BY ticket").bind(row.position_id).all();const deals=ds.results.map(d=>JSON.parse(d.data));const entry=deals.find(d=>d.entry===0);const exit=deals.filter(d=>d.entry===1||d.entry===2).at(-1);
            if(!entry||!exit)continue;
            const own=await env.DB.prepare("SELECT * FROM cfd_ownership WHERE position_id=?").bind(row.position_id).first();
            trades.push({contract_id:row.position_id,pair:entry.symbol,side:entry.type===0?"BUY":"SELL",stake:entry.volume,open_price:entry.price,close_price:exit.price,open_utc:new Date(entry.time*1000).toISOString(),close_utc:new Date(exit.time*1000).toISOString(),pnl:row.net,result:row.net>0?"win":"loss",reason:own?.reason||entry.comment,model_id:own?.model_symbol||null,mode:"demo"});
          }
          return json({trades});
        } catch(e) { if(String(e).includes("no such table"))return json({trades:[]});throw e; }
      }

      if (path === "/api/news" && method === "GET") {
        const r = await env.DB.prepare(
          "SELECT * FROM news_events WHERE utc_time >= ? ORDER BY utc_time"
        ).bind(new Date(Date.now() - 86400e3 * 3).toISOString().slice(0, 10) + "T00:00:00Z").all();
        const rx = await env.DB.prepare(
          "SELECT * FROM news_reactions ORDER BY id DESC LIMIT 500"
        ).all().catch(() => ({ results: [] }));
        const cache = await env.DB.prepare("SELECT value FROM settings WHERE key='news_cache'").first();
        let newsMeta = null;
        if (cache) {
          try {
            const c = JSON.parse(cache.value);
            const ageH = (Date.now() - Date.parse(c.fetched_utc || 0)) / 3600e3;
            newsMeta = { fetched_utc: c.fetched_utc || null, stale: !(ageH < 2) };
          } catch (_) { newsMeta = { fetched_utc: null, stale: true }; }
        } else {
          newsMeta = { fetched_utc: null, stale: true };
        }
        return json({ events: r.results, reactions: rx.results || [], meta: newsMeta });
      }

      if (path === "/api/stats/daily" && method === "GET") {
        const r = await env.DB.prepare("SELECT * FROM daily_stats ORDER BY lagos_date DESC LIMIT 30").all();
        return json({ days: r.results });
      }

      // -------- live data index + tracked pairs (B1 single source of truth)
      if (path === "/api/data/playbook" && method === "GET") return serveRepoData(request,"data/playbook.json");
      if (path === "/api/data/index" && method === "GET") {
        if (url.searchParams.get("fresh")) _dataCache.delete("data/index.json");
        return serveRepoData(request, "data/index.json");
      }
      if (path === "/api/data/tracked-pairs" && method === "GET") {
        return serveRepoData(request, "data/tracked_pairs.json");
      }
      if (path === "/api/data/symbols" && method === "GET") {
        return serveRepoData(request, "data/symbols.json");
      }

      return err("not found", 404);
    } catch (e) {
      return err(String(e && e.message || e), 500);
    }
  },
};
