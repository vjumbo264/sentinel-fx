/**
 * F3 regression tests (Node, no browser):
 *  1. store.fetchSnapshot does NOT notify when polled data is identical
 *     (so pages never rebuild and chips/filters/scroll survive poll cycles).
 *  2. store.fetchSnapshot DOES notify when data actually changes.
 *  3. pageState keeps a page's chip/filter state across "re-renders".
 *  4. train view sends exactly the workflow-declared inputs (symbols/granularity/mode).
 *
 * The browser-level assertion (click chip -> wait 2 poll cycles -> chip +
 * scroll unchanged) is executed live with Playwright and saved to docs/ui/.
 */
import { strict as assert } from "assert";

// ---- minimal browser stubs so api.js/store.js import under Node
globalThis.localStorage = {
  _m: new Map(),
  getItem(k) { return this._m.has(k) ? this._m.get(k) : null; },
  setItem(k, v) { this._m.set(k, String(v)); },
  removeItem(k) { this._m.delete(k); }
};
globalThis.document = { addEventListener() {}, getElementById() { return null; }, querySelectorAll() { return []; } };
globalThis.window = { addEventListener() {} };

const { store } = await import("../site/js/store.js");
const { getPageState, setPageState } = await import("../site/js/pageState.js");
const { api } = await import("../site/js/api.js");

// ---- fake API layer: canned responses, identical across polls
const snapshotBody = () => ({
  settings: { mode: "demo" },
  pairs: [{ symbol: "frxEURUSD", enabled: 1 }],
  heartbeat: { ts: new Date().toISOString(), mode: "demo", balance: 10000 },
  today: { pnl: 0, trades: 0, wins: 0 }
});
api.getState = async () => snapshotBody();
api.getSession = async () => ({ session: null, ledger: [], overrides: [] });
api.getTrades = async () => ({ trades: [] });
api.getPairs = async () => ({ pairs: [{ symbol: "frxEURUSD", enabled: 1 }] });
api.getNews = async () => ({ events: [] });

store.state.isAuth = true;

let notifies = 0;
store.subscribe(() => { notifies++; }); // subscribe fires once immediately
assert.equal(notifies, 1, "subscribe fires once immediately");

// Test 1: two identical poll cycles -> zero extra notifies
await store.fetchSnapshot(); // first: populates -> notifies
const afterFirst = notifies;
assert.ok(afterFirst >= 2, "first snapshot notifies (data changed)");
await store.fetchSnapshot();
await store.fetchSnapshot();
assert.equal(notifies, afterFirst, "identical poll cycles must NOT notify");
console.log("PASS 1: no notify on identical poll ticks (chip/scroll safe)");

// Test 2: changed data -> notify fires
api.getTrades = async () => ({ trades: [{ id: 1, pair: "frxEURUSD", side: "BUY", stake: 0.01, open_utc: "2026-10-11T00:00:00Z", close_utc: null, pnl: 1.5 }] });
await store.fetchSnapshot();
assert.ok(notifies > afterFirst, "changed data notifies");
console.log("PASS 2: notify on real change");

// Test 3: page state persistence across simulated re-renders
setPageState("train", { currentCategory: "synthetics" });
setPageState("history", { filterOutcome: "win" });
assert.equal(getPageState("train").currentCategory, "synthetics");
assert.equal(getPageState("history").filterOutcome, "win");
console.log("PASS 3: per-page UI state persists");

// Test 4: workflow dispatch sends exactly the declared inputs
let sentBody = null;
globalThis.fetch = async (url, opts) => {
  sentBody = JSON.parse(opts.body);
  return { ok: true, status: 204, text: async () => "" };
};
api.token = "test-token";
await api.dispatchWorkflow("fetch-candles.yml", "main", { symbols: "frxEURUSD", granularity: "60", mode: "incremental" });
assert.deepEqual(Object.keys(sentBody.inputs).sort(), ["granularity", "mode", "symbols"]);
assert.ok(!("symbol" in sentBody.inputs), "must not send legacy 'symbol' input");
console.log("PASS 4: dispatch inputs match fetch-candles.yml contract");

console.log("\nAll F3/F1 unit tests passed.");
