const https = require("https");
const fs = require("fs");

function fetchUrl(url, headers = {}) {
  return new Promise((resolve, reject) => {
    const u = new URL(url);
    const req = https.request({
      hostname: u.hostname,
      port: 443,
      path: u.pathname + u.search,
      method: "GET",
      headers: { "User-Agent": "Sentinel-FX-Verifier/1.0", ...headers }
    }, (res) => {
      let data = "";
      res.on("data", chunk => data += chunk);
      res.on("end", () => resolve({ status: res.statusCode, data, headers: res.headers }));
    });
    req.on("error", reject);
    req.setTimeout(12000, () => { req.abort(); reject(new Error("Timeout on " + url)); });
    req.end();
  });
}

async function runTests() {
  const token = process.env.GITHUB_PAT || "";
  const report = { timestamp: new Date().toISOString(), assets: {}, endpoints: {}, checks: {} };

  console.log("1. Verifying Deployed Static Assets on https://sentinel-fx.pages.dev...");
  const pagesAssets = [
    "/",
    "/styles/tokens.css",
    "/styles/components.css",
    "/js/app.js",
    "/js/version.js",
    "/js/pages/login.js",
    "/js/pages/home.js",
    "/js/pages/trades.js",
    "/js/pages/history.js",
    "/js/pages/chart.js",
    "/js/pages/models.js",
    "/js/pages/train.js",
    "/js/pages/upload.js",
    "/js/pages/risk.js",
    "/js/pages/settings.js",
    "/data/symbols.json",
    "/data/tracked_pairs.json",
    "/data/index.json"
  ];

  for (const path of pagesAssets) {
    const res = await fetchUrl("https://sentinel-fx.pages.dev" + path);
    report.assets[path] = { status: res.status, bytes: res.data.length };
    console.log(`  ${path.padEnd(26)} -> HTTP ${res.status} (${res.data.length} B)`);
    if (res.status !== 200) throw new Error(`Asset ${path} returned HTTP ${res.status}`);
  }

  console.log("\n2. Verifying Real Cloudflare Worker API & Live Auth...");
  // Valid token check
  const authGood = await fetchUrl("https://sentinel-fx-worker.vjumbo264.workers.dev/api/auth/check", { Authorization: `Bearer ${token}` });
  console.log(`  /api/auth/check [valid]    -> HTTP ${authGood.status}: ${authGood.data}`);
  report.endpoints["auth_valid"] = { status: authGood.status, ok: authGood.status === 200, response: JSON.parse(authGood.data) };

  // Invalid token check
  const authBad = await fetchUrl("https://sentinel-fx-worker.vjumbo264.workers.dev/api/auth/check", { Authorization: "Bearer bad_pat_invalid_123" });
  console.log(`  /api/auth/check [invalid]  -> HTTP ${authBad.status}: ${authBad.data}`);
  report.endpoints["auth_invalid"] = { status: authBad.status, ok: authBad.status === 401 };

  // Health
  const healthRes = await fetchUrl("https://sentinel-fx-worker.vjumbo264.workers.dev/api/health");
  console.log(`  /api/health                -> HTTP ${healthRes.status}: ${healthRes.data}`);
  report.endpoints["health"] = { status: healthRes.status, ok: healthRes.status === 200, response: JSON.parse(healthRes.data) };

  // State
  const stateRes = await fetchUrl("https://sentinel-fx-worker.vjumbo264.workers.dev/api/state", { Authorization: `Bearer ${token}` });
  console.log(`  /api/state                 -> HTTP ${stateRes.status} (${stateRes.data.length} B)`);
  report.endpoints["state"] = { status: stateRes.status, ok: stateRes.status === 200 };

  // Trades
  const tradesRes = await fetchUrl("https://sentinel-fx-worker.vjumbo264.workers.dev/api/trades", { Authorization: `Bearer ${token}` });
  console.log(`  /api/trades                -> HTTP ${tradesRes.status}: ${tradesRes.data}`);
  report.endpoints["trades"] = { status: tradesRes.status, ok: tradesRes.status === 200, response: JSON.parse(tradesRes.data) };

  // Session
  const sessionRes = await fetchUrl("https://sentinel-fx-worker.vjumbo264.workers.dev/api/session", { Authorization: `Bearer ${token}` });
  console.log(`  /api/session               -> HTTP ${sessionRes.status}: ${sessionRes.data}`);
  report.endpoints["session"] = { status: sessionRes.status, ok: sessionRes.status === 200, response: JSON.parse(sessionRes.data) };

  // Pairs
  const pairsRes = await fetchUrl("https://sentinel-fx-worker.vjumbo264.workers.dev/api/pairs", { Authorization: `Bearer ${token}` });
  console.log(`  /api/pairs                 -> HTTP ${pairsRes.status} (${pairsRes.data.length} B)`);
  report.endpoints["pairs"] = { status: pairsRes.status, ok: pairsRes.status === 200 };

  // News
  const newsRes = await fetchUrl("https://sentinel-fx-worker.vjumbo264.workers.dev/api/news", { Authorization: `Bearer ${token}` });
  console.log(`  /api/news                  -> HTTP ${newsRes.status} (${newsRes.data.length} B)`);
  report.endpoints["news"] = { status: newsRes.status, ok: newsRes.status === 200 };

  console.log("\n3. Verifying Zero Fake Data Across Files...");
  const fakeGrep = require("child_process").execSync(
    'grep -rn -E "1\\.08|525,600|v2\\.4\\.0|sample|mock|fake|demo-data|demoData|demoReviewMode" /app/applet/sentinel-fx/site || true',
    { encoding: "utf8" }
  );
  const relevantFake = fakeGrep.split("\n").filter(l => l.trim() && !l.includes("zero") && !l.includes("disclaimer") && !l.includes("Strict"));
  console.log("  Relevant fake lines found in site/:", relevantFake.length);
  report.checks["zero_fake_data"] = { ok: relevantFake.length === 0, count: relevantFake.length };

  console.log("\n4. Verifying Icon Sizing Contract in CSS...");
  const css = fs.readFileSync("/app/applet/sentinel-fx/site/styles/components.css", "utf8");
  const hasIconSystem = css.includes("EXPLICIT ICONOGRAPHY SYSTEM") && css.includes(".icon") && css.includes(".w-4");
  console.log("  Explicit icon system present in components.css:", hasIconSystem);
  report.checks["icon_system"] = { ok: hasIconSystem };

  console.log("\n5. Verifying Build ID in Deployed version.js...");
  const verRes = await fetchUrl("https://sentinel-fx.pages.dev/js/version.js");
  const hasBuildId = verRes.data.includes("build-");
  console.log("  Deployed version.js contains buildId:", hasBuildId);
  report.checks["deployed_build_id"] = { ok: hasBuildId, content: verRes.data.trim() };

  fs.writeFileSync("/app/applet/sentinel-fx/docs/ui/verification_report.json", JSON.stringify(report, null, 2));
  console.log("\nSaved verification report to docs/ui/verification_report.json");
}

runTests().catch(err => {
  console.error("Test execution error:", err);
  process.exit(1);
});
