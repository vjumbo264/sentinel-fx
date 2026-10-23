# FIX MISSION 5 PROGRESS

## Status Overview
- **Phase**: Initialization / Resume Protocol
- **Date**: 2026-10-23
- **Active Training**: EURUSD v1 chain actively training on GitHub Actions (run 39929904179 and checkpoint commits, 500,000+ steps completed, 62-dim observation).

## Done
- Initialized FIX MISSION 5 tracking in `BUILD_STATE.json` and `docs/FIX5_PROGRESS.md`.
- Pulled latest repo commits and inspected last 15 commits and workflow run history.
- Confirmed active EURUSD v1 training is running smoothly without interruption.

## Done
- **H1. Optional overrides (V1, V2 passed)**: Implemented four independent optional overrides (TP, SL, Daily Profit Target, Daily Loss Limit) in Risk page, Worker D1, Bot, and ExecutionAdapter. Live verified with headless Chromium at 375px (screenshots saved to docs/screenshots/). Verified next-day rollover and override precedence.

## Done
- **H2. Honest training ETA (V3 passed)**: Replaced erroneous static 4.75h multiplier with dynamic throughput measured from last 5 checkpoint timestamps (~3,959 steps/min -> 18.1 hours ETA for EURUSD v1, 0.01% diff from hand calculation). Shows rate, elapsed, finish time in local/WAT timezone, and queue total.

## Done
- **H3. Full 5,000,000-step training & best-checkpoint release (V4 passed)**: Removed plateau early-stopping so pairs train full 5M steps. Per-checkpoint validation logged in training_state.json and shown on Training page. Best-checkpoint selector releases peak validation checkpoint upon 5M completion provided it passes 1.5x cost stress holdout gates, otherwise marks 'no proven edge, not released'. Resumption preserved on active EURUSD v1 chain.

## Done
- **H4. Update MT5 credentials from Settings (V5 passed)**: Implemented MT5 account settings in UI, write-only password never returned or logged, libsodium sealed-box encryption to GitHub Actions secrets, test-login.yml workflow reporting broker status to Worker, zero-gap handover restart button. Purged all hardcoded fallback passwords from repo.

## Done
- **H5. No trading on weekends unless owner turns it on (V6 passed)**: Added `is_market_open` session checking in MT5Broker using broker symbol specifications. When `trade_weekends` is False (default), forex pairs are idle during market closure without spamming failed orders; Deriv synthetic volatility indices trade 24/7 unaffected. ExecutionAdapter and CFDSimulator reject orders on market closed sessions while preserving open positions with rollover/swap. Added toggle 'Trade on weekends (synthetic indices only trade 24/7)' in Risk and Settings pages. Passed tests/test_fix5_h5.py.

## In Progress
- **H6. The failed or cancelled live action root cause and fix**: Inspecting last 40 GitHub Actions workflow runs, identifying cancelled and failed live bot/training actions, reading exact log lines, fixing root cause, and dispatching green 10+ min live run on demo.

## Next
- **H7. Consistency & cleanup**: Enforce 62-dim observation across all components, retire old 47-dim models.
- **H8. Self-healing**: Cool-down retry progression (30m, 2h, 6h) for platform errors, watchdog for training.
- **H9. Manual training only**: Strip crons from train.yml, "Update training" button, verify training lock behavior.
- **H10. Weekly Deriv data append**: Weekly incremental candle ingestion, seam report, freeze HistData base.

## Problems / Blockers
- None currently. Autonomous execution underway.
