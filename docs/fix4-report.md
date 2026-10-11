# FIX4 Report — 2026-10-11

## What was broken
1. bot.yml never installed/started the MT5 stack -> `No module named 'MetaTrader5'`, runs #227-239 all failed (E1).
2. Every order_check/order_send returned retcode=None: RPyC eval namespace never had MetaTrader5 imported (E2). No order was ever placed; mt5-spike.md's "DONE" was false.
3. fetch-candles crashed publishing empty forex assets; no Dukascopy implementation existed (E3).

## What is now proven (with run URLs)
- MT5 stack starts + logs into Deriv-Demo on Actions: https://github.com/vjumbo264/sentinel-fx/actions/runs/38129230441 — "Logged in successfully", Account USD 10007.18, Leverage 1:1000, Trade Allowed True. Stack extracted as reusable composite action .github/actions/mt5-stack used by bot.yml + trade-test.yml.
- Synthetic candle data (R_10) from Deriv: https://github.com/vjumbo264/sentinel-fx/actions/runs/38128792662 — 525798 rows, 2025-10-11→2026-10-11, sha256-verified, atomic swap guards, index.json updated.
- Anti-spam backoff + 3-failure circuit breaker in bot.yml crash-proof chain.
- Root-cause fix committed for the retcode=None bug (remote import MetaTrader5); time-offset sanity (±14h, 30m rounding) already in get_server_time_offset_hours.

## Pending / blocked
- Real order execution proof (G2): trade-test re-dispatched after the fix; check newest run of workflow `trade-test`.
- 10-min live bot heartbeat in Worker /api/state (G1 tail): bot re-dispatched.
- Dukascopy forex fetch on Actions: `gh workflow run fetch-candles -f symbols=frxEURUSD -f granularity=60 -f mode=incremental`.
- HANDOFF second-terminal lease test, SESSION pool live read: unverified.

## Exact commands to finish
- gh workflow run trade-test.yml -R vjumbo264/sentinel-fx
- gh workflow run bot.yml -f mode=demo -R vjumbo264/sentinel-fx
- gh workflow run fetch-candles.yml -f symbols=frxEURUSD -f granularity=60 -f mode=incremental -R vjumbo264/sentinel-fx
