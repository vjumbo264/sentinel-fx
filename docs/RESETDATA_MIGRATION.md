# SENTINEL-FX CFD Data & Schema Migration Note (RESETDATA)

**Date:** 2026-10-10  
**Phase:** Binary Options (Rise/Fall) -> Autonomous MT5 CFD Migration  

## 1. Purged Legacy Assets & Releases
- Deleted all old Rise/Fall 60s candle assets from GitHub Releases (`data-01`: `R_100_60s.csv.gz`, `R_10_60s.csv.gz`, and legacy `index.json`).
- Deleted legacy Rise/Fall binary options model packs (`R_10_v2.sfxmodel.zip`) from `staging` and `models-01`.
- Cleaned legacy symbol references.

## 2. Preserved Assets & Foundations
- **News Archive:** Release `news-archive` (`news_archive.jsonl.gz`) preserved intact. Continues continuous economic calendar history across USD, EUR, GBP, JPY, and other major currency events.
- **Session & Compounding Ledger:** D1 tables `session`, `model_ledger`, `overrides`, `ledger_events` preserved.
- **Secrets & Credentials:** GitHub Actions secrets and Cloudflare tokens intact.

## 3. D1 Database Schema Updates for CFD
- **trades:** Transitioned from binary contracts (`contract_id`, `payout`, `stake`, `side: CALL/PUT`) to CFD executions (`ticket`, `symbol`, `side: BUY/SELL`, `volume`, `open_price`, `close_price`, `sl`, `tp`, `commission`, `swap`, `pnl`, `magic`, `model_id`, `reason`).
- **shadow_signals:** Updated with CFD entry/exit prices, volume, and SL/TP.
- **positions:** New real-time table tracking open broker positions with live SL/TP and profit.
- **quotes:** Real-time rolling quote log capturing live bid, ask, spread, and swap for accurate cost simulation.
