// SENTINEL-FX Worker: middle layer between site (GitHub PAT auth) and bot (BOT_SHARED_SECRET).
// Secrets: BOT_SHARED_SECRET, GH_PAT (Worker secrets). Deriv token NEVER stored here.
export default {
  async fetch(request, env) {
    const url = new URL(request.url);
    if (request.method === "OPTIONS") return cors(new Response(null));
    const isBot = url.pathname.startsWith("/api/bot/") || ["/api/logs","/api/heartbeat","/api/run-lock/acquire","/api/run-lock/release","/api/news/upsert"].includes(url.pathname);
    const auth = request.headers.get("Authorization") || "";
    if (isBot) {
      if (auth !== `Bearer ${env.BOT_SHARED_SECRET}`) return json({error:"unauthorized"},401);
    } else {
      const ok = await verifyGitHubPat(auth.replace("Bearer ",""), env);
      if (!ok) return json({error:"bad or missing GitHub PAT"},401);
    }
    const q = (sql, ...b) => env.DB.prepare(sql).bind(...b);
    const route = url.pathname, m = request.method;

    if (route === "/api/settings" && m === "GET") return json(await kvAll(env));
    if (route === "/api/settings" && m === "POST") {
      const body = await request.json();
      for (const [k,v] of Object.entries(body))
        await q("INSERT INTO settings(key,value) VALUES(?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value", k, JSON.stringify(v)).run();
      return json({ok:true});
    }
    if (route === "/api/bot/settings") {
      const s = await kvAll(env);
      return json({kill_switch: s.kill_switch === true || s.kill_switch === "true",
                   mode: s.mode || "demo", ...s});
    }
    if (route === "/api/bot/pairs")
      return json((await env.DB.prepare("SELECT * FROM pairs").all()).results);
    if (route === "/api/logs" && m === "POST") {
      const b = await request.json();
      await q("INSERT INTO logs(ts,level,pair,message,data) VALUES(?,?,?,?,?)",
        new Date().toISOString(), b.level||"info", b.pair||null, b.message, JSON.stringify(b.data||{})).run();
      return json({ok:true});
    }
    if (route === "/api/logs" && m === "GET") {
      const level = url.searchParams.get("level"), limit = Math.min(+(url.searchParams.get("limit")||200), 500);
      const r = level
        ? await q("SELECT * FROM logs WHERE level=? ORDER BY id DESC LIMIT ?", level, limit).all()
        : await env.DB.prepare("SELECT * FROM logs ORDER BY id DESC LIMIT ?").bind(limit).all();
      return json(r.results);
    }
    if (route === "/api/heartbeat" && m === "POST") {
      const b = await request.json();
      await q("INSERT INTO heartbeat(owner,ts) VALUES(?,?) ON CONFLICT(owner) DO UPDATE SET ts=excluded.ts", b.owner, b.ts).run();
      return json({ok:true});
    }
    if (route === "/api/status") {
      const hb = (await env.DB.prepare("SELECT * FROM heartbeat ORDER BY ts DESC LIMIT 1").all()).results[0];
      const online = hb && (Date.now()/1000 - hb.ts) < 60;
      return json({online, last_heartbeat: hb ? hb.ts : null});
    }
    if (route === "/api/run-lock/acquire" && m === "POST") {
      const b = await request.json(), now = Math.floor(Date.now()/1000);
      const cur = (await env.DB.prepare("SELECT * FROM run_lock WHERE id=1").all()).results[0];
      const hb = (await env.DB.prepare("SELECT * FROM heartbeat WHERE owner=?").bind(cur?.owner||"").all()).results[0];
      const expired = !cur || cur.expires_at < now || !hb || (now - hb.ts) > (b.heartbeat_expiry_s||60);
      if (!expired) return json({ok:false, holder: cur.owner});
      await q("INSERT INTO run_lock(id,owner,expires_at) VALUES(1,?,?) ON CONFLICT(id) DO UPDATE SET owner=excluded.owner, expires_at=excluded.expires_at",
        b.owner, now + 4*3600).run();
      return json({ok:true});
    }
    if (route === "/api/run-lock/release" && m === "POST") {
      const b = await request.json();
      await q("DELETE FROM run_lock WHERE id=1 AND owner=?", b.owner).run();
      return json({ok:true});
    }
    if (route === "/api/daily-stats")
      return json((await env.DB.prepare("SELECT * FROM daily_stats WHERE lagos_date=?").bind(url.searchParams.get("date")).all()).results[0] || {pnl:0});
    if (route === "/api/news" && m === "GET")
      return json((await env.DB.prepare("SELECT * FROM news_events ORDER BY utc_time").all()).results);
    if (route === "/api/news/upsert" && m === "POST") {
      const b = await request.json();
      for (const e of b.events||[])
        await q("INSERT OR REPLACE INTO news_events(id,utc_time,currency,title,impact) VALUES(?,?,?,?,?)",
          `${e.currency}-${e.utc_time}-${(e.title||"").slice(0,20)}`, e.utc_time, e.currency, e.title, e.impact).run();
      return json({ok:true, n:(b.events||[]).length});
    }
    if (route === "/api/trades")
      return json((await env.DB.prepare("SELECT * FROM trades ORDER BY open_utc DESC LIMIT 300").all()).results);
    return json({error:"not found"}, 404);
  }
};
async function kvAll(env){
  const r = (await env.DB.prepare("SELECT key,value FROM settings").all()).results, o = {};
  for (const row of r) { try { o[row.key] = JSON.parse(row.value); } catch { o[row.key] = row.value; } }
  return o;
}
async function verifyGitHubPat(pat, env){
  if (!pat) return false;
  try {
    const r = await fetch("https://api.github.com/repos/vjumbo264/sentinel-fx",
      {headers:{Authorization:`Bearer ${pat}`,Accept:"application/vnd.github+json","User-Agent":"sentinel-fx-worker"}});
    return r.ok;
  } catch { return false; }
}
function json(o, s=200){ return cors(new Response(JSON.stringify(o), {status:s, headers:{"Content-Type":"application/json"}})); }
function cors(r){ r.headers.set("Access-Control-Allow-Origin","*"); r.headers.set("Access-Control-Allow-Headers","Authorization,Content-Type"); r.headers.set("Access-Control-Allow-Methods","GET,POST,OPTIONS"); return r; }
