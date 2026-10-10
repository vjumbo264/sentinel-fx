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

    try {
      // -------- public health
      if (path === "/api/health") {
        return json({ ok: true, service: "sentinel-fx-worker", utc: nowUTC() });
      }

      // -------- site auth probe
      if (path === "/api/auth/check" && method === "GET") {
        const a = await verifySiteAuth(request);
        return a ? json({ ok: true, repo: GITHUB_REPO }) : err("unauthorized", 401);
      }

      // ============================ BOT ENDPOINTS ============================
      if (path.startsWith("/api/bot/")) {
        if (!verifyBotAuth(request, env)) return err("unauthorized", 401);
        const body = method === "GET" ? {} : await request.json().catch(() => ({}));

        if (path === "/api/bot/state" && method === "GET") {
          const settings = {};
          const rs = await env.DB.prepare("SELECT key, value FROM settings").all();
          for (const r of rs.results) settings[r.key] = JSON.parse(r.value);
          const pairs = await env.DB.prepare("SELECT * FROM pairs").all();
          const hb = await env.DB.prepare("SELECT * FROM heartbeat WHERE id=1").first();
          return json({ settings, pairs: pairs.results, heartbeat: hb, lagos_date: lagosDate() });
        }

        if (path === "/api/bot/heartbeat" && method === "POST") {
          // FIX-B: also persist the CONNECTED account identity when supplied
          const cur = await env.DB.prepare("SELECT loginid, currency FROM heartbeat WHERE id=1").first();
          const loginid = body.loginid !== undefined ? body.loginid : (cur ? cur.loginid : null);
          const currency = body.currency !== undefined ? body.currency : (cur ? cur.currency : null);
          await env.DB.prepare(
            "INSERT INTO heartbeat (id, ts, mode, balance, note, loginid, currency) VALUES (1,?,?,?,?,?,?) " +
            "ON CONFLICT(id) DO UPDATE SET ts=excluded.ts, mode=excluded.mode, balance=excluded.balance, " +
            "note=excluded.note, loginid=excluded.loginid, currency=excluded.currency"
          ).bind(nowUTC(), body.mode || null, body.balance ?? null, body.note || null, loginid, currency).run();
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

        if (path === "/api/bot/log" && method === "POST") {
          await logLine(env, body.level || "info", body.pair, body.message || "", body.data);
          return json({ ok: true });
        }

        if (path === "/api/bot/lock" && method === "POST") {
          // acquire lease if free or expired
          const cur = await env.DB.prepare("SELECT * FROM run_lock WHERE id=1").first();
          const now = new Date();
          if (cur && cur.lease_until && new Date(cur.lease_until) > now && cur.owner !== body.owner) {
            return json({ acquired: false, owner: cur.owner, lease_until: cur.lease_until });
          }
          const lease = new Date(now.getTime() + 60 * 1000).toISOString();
          await env.DB.prepare(
            "INSERT INTO run_lock (id, owner, lease_until, updated_utc) VALUES (1,?,?,?) " +
            "ON CONFLICT(id) DO UPDATE SET owner=excluded.owner, lease_until=excluded.lease_until, updated_utc=excluded.updated_utc"
          ).bind(body.owner || "bot", lease, nowUTC()).run();
          return json({ acquired: true, lease_until: lease });
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

        if (path === "/api/bot/shadow" && method === "POST") {
          await env.DB.prepare(
            `INSERT INTO shadow_signals (pair, side, stake, open_utc, entry_price, model_prob, reason)
             VALUES (?,?,?,?,?,?,?)`
          ).bind(body.pair, body.side, body.stake ?? null, nowUTC(),
                 body.entry_price ?? null, body.model_prob ?? null, body.reason || null).run();
          return json({ ok: true });
        }

        if (path === "/api/bot/shadow/settle" && method === "POST") {
          await env.DB.prepare(
            "UPDATE shadow_signals SET close_utc=?, exit_price=?, result=?, pnl=? WHERE id=?"
          ).bind(nowUTC(), body.exit_price ?? null, body.result, body.pnl ?? 0, body.id).run();
          return json({ ok: true });
        }

        if (path === "/api/bot/shadow/open" && method === "GET") {
          const pair = url.searchParams.get("pair");
          const r = await env.DB.prepare(
            "SELECT * FROM shadow_signals WHERE pair=? AND close_utc IS NULL"
          ).bind(pair).all();
          return json({ open: r.results });
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

        return err("not found", 404);
      }

      // ============================ SITE ENDPOINTS ===========================
      const site = await verifySiteAuth(request);
      if (!site) return err("unauthorized", 401);

      if (path === "/api/state" && method === "GET") {
        const settings = {};
        const rs = await env.DB.prepare("SELECT key, value FROM settings").all();
        for (const r of rs.results) settings[r.key] = JSON.parse(r.value);
        const pairs = await env.DB.prepare("SELECT * FROM pairs").all();
        const hb = await env.DB.prepare("SELECT * FROM heartbeat WHERE id=1").first();
        const today = await env.DB.prepare("SELECT * FROM daily_stats WHERE lagos_date=?")
          .bind(lagosDate()).first();
        return json({ settings, pairs: pairs.results, heartbeat: hb, today: today || { pnl: 0, trades: 0, wins: 0 }, lagos_date: lagosDate() });
      }

      if (path === "/api/settings" && method === "POST") {
        const body = await request.json();
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

      if (path === "/api/pairs/update" && method === "POST") {
        const body = await request.json();
        const allowed = ["enabled", "shadow_mode", "min_stake", "max_stake", "stake_pct",
                         "daily_loss_cap", "daily_target", "max_consec_losses", "status"];
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

      if (path === "/api/packs/register" && method === "POST") {
        const body = await request.json();
        await env.DB.prepare(
          "INSERT INTO pair_packs (symbol, version, sha256, status, has_custom_code, verdict, metrics, created_utc) VALUES (?,?,?,?,?,?,?,?)"
        ).bind(body.symbol, body.version, body.sha256 || null, body.status || "incoming",
               body.has_custom_code ? 1 : 0, body.verdict || null,
               body.metrics ? JSON.stringify(body.metrics) : null, nowUTC()).run();
        return json({ ok: true });
      }

      if (path === "/api/packs/status" && method === "POST") {
        // called by validate-pack workflow OR by the site polling step
        const body = await request.json();
        await env.DB.prepare(
          "UPDATE pair_packs SET status=?, verdict=?, validation_report=? WHERE symbol=? AND version=?"
        ).bind(body.status, body.verdict || null,
               body.validation_report ? JSON.stringify(body.validation_report) : null,
               body.symbol, body.version).run();
        return json({ ok: true });
      }

      if (path === "/api/packs/promote" && method === "POST") {
        const body = await request.json();
        // mark all previous packs retired, this one active; upsert pair row
        await env.DB.prepare("UPDATE pair_packs SET status='retired' WHERE symbol=? AND status='active'")
          .bind(body.symbol).run();
        await env.DB.prepare("UPDATE pair_packs SET status='active', installed_utc=? WHERE symbol=? AND version=?")
          .bind(nowUTC(), body.symbol, body.version).run();
        const existing = await env.DB.prepare("SELECT * FROM pairs WHERE symbol=?").bind(body.symbol).first();
        const p = body.pack || {};
        if (existing) {
          await env.DB.prepare(
            "UPDATE pairs SET pack_version=?, verdict=?, has_custom_code=?, updated_utc=? WHERE symbol=?"
          ).bind(body.version, p.verdict || null, p.has_custom_code ? 1 : 0, nowUTC(), body.symbol).run();
        } else {
          await env.DB.prepare(
            `INSERT INTO pairs (symbol, enabled, shadow_mode, status, min_stake, max_stake, stake_pct,
                                max_consec_losses, pack_version, verdict, has_custom_code, updated_utc)
             VALUES (?,?,?,?,?,?,?,?,?,?,?,?)`
          ).bind(body.symbol, 0, p.has_custom_code ? 1 : 0, "installed",
                 Math.max(0.35, p.min_stake || 0.35), p.max_stake || 10,
                 p.stake_pct || 0.01, p.max_consec_losses || 3,
                 body.version, p.verdict || null, p.has_custom_code ? 1 : 0, nowUTC()).run();
        }
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
        const r = await env.DB.prepare("SELECT * FROM trades ORDER BY id DESC LIMIT 200").all();
        return json({ trades: r.results });
      }

      if (path === "/api/news" && method === "GET") {
        const r = await env.DB.prepare(
          "SELECT * FROM news_events WHERE utc_time >= ? ORDER BY utc_time"
        ).bind(nowUTC().slice(0, 10) + "T00:00:00Z").all();
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
        return json({ events: r.results, meta: newsMeta });
      }

      if (path === "/api/stats/daily" && method === "GET") {
        const r = await env.DB.prepare("SELECT * FROM daily_stats ORDER BY lagos_date DESC LIMIT 30").all();
        return json({ days: r.results });
      }

      return err("not found", 404);
    } catch (e) {
      return err(String(e && e.message || e), 500);
    }
  },
};
