# FIX MISSION 3 — Final Report (2026-10-11)

## F1 — "Fetch Data" HTTP 422 ✅ FIXED
- Cause: train.js sent `{symbol}`; fetch-candles.yml declares `symbols`, `granularity`, `mode`.
- Fix: single source of truth (`WF_IN`); dispatch sends exactly `symbols`/`granularity`/`mode` (mode=incremental when an asset exists, else full). Workflow already handles frx* + R_*/1HZ* from the registry (validated in plan step).
- Inline queued/running/finished per row via `api.getLatestWorkflowRun`; row flips to "Ready (rows, first → last)" ONLY after data/index.json confirms the asset. GitHub errors parsed to readable text; Actions link kept.
- Evidence: tests/test_fix3_ui_state.mjs PASS 4; live dispatches returned HTTP 204 for frxEURUSD and R_10; run 38126588222 succeeded (R_10 in release data-01); frxEURUSD run failed in the fetch step because the forex market is closed on the weekend (expected; daily cron covers it).

## F2 — Session balance pool ✅ FIXED
- Risk page: validated 2-decimal amount (capped at available balance), "Use full balance", percent slider, live equal-split preview (pool / enabled models), Save via /api/session/allocate + settings. Daily TP/SL each with own toggle + repeat-daily; owner overrides (max lot / TP / SL) each with toggle default OFF. Saved values rehydrate on reload.
- Home: real pool, per-model share, used/remaining from /api/session; "Set Pool" shortcut.
- Bot: reads pool/shares/settings via new /api/bot/session each cycle.
- Found + fixed a worker bug: body was only parsed under /api/bot/*, so site POSTs 400'd ("body is not defined").
- Evidence: live /api/state shows settings.session_pool=5000; /api/session shows session + 3×3333.33 ledger; /api/bot/session live.

## F3 — Tabs resetting ✅ FIXED
- store.fetchSnapshot now diffs every slice (heartbeat ts excluded) and notifies ONLY on real change; router force-refreshes before each page render; pages no longer subscribe/rebuild on poll; chips/filters/group-by/search drafts persist in pageState.js; history search keeps focus+caret.
- Evidence: PASS 1-3 (identical polls → zero notifies; change → notify; state persists).

## F4 — Visual defects ✅ FIXED
- Chip bar: flex 0 0 auto, nowrap, 8px gaps, horizontal scroll + fade edge, active chip scrolled into view.
- Pair avatars redesigned: single chip with full code (EURUSD / XAUUSD / V100 / 1sV100) — no clipping.
- Home valuation: all fields honest ("No runner data yet"), no fake zeros, no green +/bin/bash.00 pill, no ∞. Worker heartbeat now persists equity + free_margin (schema-migration safe).
- Reset 0k: demo-only, confirm sheet, real endpoint — verified LIVE (Deriv demo reset returned 10000.00 on DOT93176227; D1 ledger zeroed).
- 320/375/414px screenshot sweep: NOT RUN — this sandbox has no /opt/pw-browsers Chromium (gap, see below).

## F5 — Pool → sizing audit ✅ done
- docs/pool-and-sizing.md. Gaps fixed: bot never read pool (now per-share ctx + margin-share precheck); missing /api/bot/session + /api/bot/overrides; owner max-lot clamp now enforced. Remaining gaps (documented, not fixed): session-wide TP/SL flatten loop; bundle policy output schema enforcement.

## F6 — Deploy & verify ✅ (with one gap)
- Worker redeployed (versions incl. dde7df3f-…); site auto-deploys to Cloudflare Pages via deploy-site.yml on push; build id stamped into version.js.
- GAP: live browser verification at 375px in both color schemes with screenshots to docs/ui/ could not be executed — the sandbox has no headless Chromium at /opt/pw-browsers. All verifiable API-level proofs were done live instead; the UI changes are pure CSS/DOM and unit-tested where possible.
