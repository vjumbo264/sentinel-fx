# TRAIN_PROMPT v2 — train a per-pair SENTINEL-FX model (committee design)

You are a stateless AI asked to train (or update) a trading model for one
SENTINEL-FX pair. You need NO credentials for training; the owner may append a
PUBLISH ACCESS block at the end (only then you also publish).

Inputs: PAIR_SYMBOLS (e.g. frxEURUSD), optional PAYOUT_ASSUMPTION (default
0.85; break-even = 1/(1+payout) = 0.5405), and per pair "new" or "update
existing v<N>".

## Facts you must respect
- Deriv forex (frx*) binaries: 15-minute minimum duration floor.
- Deriv synthetic indices (Volatility Indices R_10/25/50/75/100 and 1-second variants 1HZ10V/25V/50V/75V/100V/150V/250V/300V):
  Trade 24/7/365 with NO weekend gaps. Flexible durations from 5 seconds and up (e.g. 5s, 15s, 30s, 60s, 1m, 2m, 5m, etc.).
  Target horizon is dynamic: horizon_bars = max(1, round(duration_sec / candle_granularity_sec)).
  Store "duration" and "duration_unit" in decision.json and manifest.json.
- Demo vs Real: Shadow mode is removed. Any model can be traded live in DEMO mode so the owner can test it on Deriv demo account. Real mode is strictly guarded for models that passed full validation.
- Honesty: a failing backtest is verdict "fail", never massaged. If you lack
  network or compute for a proper run, SAY SO — never invent numbers, never
  call synthetic data real.

## Steps
1. GET DATA. Read https://raw.githubusercontent.com/vjumbo264/sentinel-fx/main/data/index.json
   for the pair's release tag + asset URL + sha256; download the candles
   (epoch,open,high,low,close, 1-minute) and verify the sha256. If the pair is
   still refreshing, poll every 30-60 s (up to ~20 min). Fall back to Deriv's
   public websocket (wss://ws.derivws.com/websockets/v3?app_id=1089,
   ticks_history style=candles granularity 60 count 5000, paginate backwards
   with end=oldest-1). News archive:
   https://github.com/vjumbo264/sentinel-fx/releases/download/news-archive/news_archive.jsonl.gz
2. INSTALL the engine: pip install "git+https://github.com/vjumbo264/sentinel-fx#subdirectory=engine"
   and read docs/TRAINING.md (toolkit, simulator, bundle builder, validator).
3. UNDERSTAND THE PAIR like a trader studying an instrument: how higher
   timeframes relate to the next 15 minutes, volatility by hour/weekday,
   trend vs mean reversion at 15m (autocorrelation, variance ratios, Hurst),
   reactions around levels, weekend gaps, volatility regimes, news behavior
   (from the archive), latency/slippage sensitivity.
4. DESIGN THE TRADER'S MIND (see engine docs, task M2): a committee — several
   analyst models (e.g. higher-timeframe trend/structure, entry-timeframe
   momentum/volatility, levels, regime/seasonality, news) each outputting
   {direction probability, strength, flags}, a router deciding which analysts
   matter per regime, and a head trader combining the opinions into
   trade/skip + side + calibrated p_win + stake fraction. Every analyst and
   indicator must EARN its place in ablation; keep it as simple as the
   evidence allows. Analysts train out-of-fold (purged walk-forward, embargo
   >= 15m + longest lookback); lock the final hold-out FIRST and evaluate it
   ONCE; log every variant tried. Confidence must be CALIBRATED (reliability
   on hold-out) — never hard-code "agreement = confidence".
5. TWO-STAGE NEWS: stage A price model on the full history; stage B news
   layer trained only where news coverage exists (< 200 relevant high-impact
   events => conservative GUARD mode, learned=false, clearly labeled).
6. EXPORT to DATA formats only (ONNX preferred; LightGBM text; XGBoost JSON —
   NO pickle/joblib/torch.save, no custom ONNX ops, no external data), with a
   parity test (native vs ONNX vs engine, tolerances, embedded test vectors).
7. BUILD the bundle with the toolkit: <symbol>_v<N>.sfxmodel.zip containing
   manifest.json (schema_version 2, sha256+size of every file),
   analysis_plan.json, model files, preprocess.json, decision.json, risk.json,
   news_layer.json, training_report.json (data files used, coverage,
   trained_through_utc, hold-out window, variants_tried, purged walk-forward
   metrics, hold-out metrics with Wilson 95% interval, payout sensitivity
   -5/+5, breakdowns by weekday/hour/regime/news-state, plain-language
   description of what it learned and its weaknesses, verdict pass|fail),
   tests/ parity vectors.
8. RUN THE VALIDATOR in full mode:
   python -m sentinel_engine.validate <symbol>_v<N>.sfxmodel.zip --mode full
   Fix every failure and re-run until it passes OR report an honest fail.
9. DELIVER:
   - File route (no credential): hand back the .sfxmodel.zip plus a
     plain-language summary (data range, what the model learned, hold-out win
     rate vs break-even with interval, drawdown, payout sensitivity, news
     mode, verdict, weaknesses). The owner uploads it on the site.
   - Publish route (PUBLISH ACCESS block present): run
     python tools/publish_model.py <bundle> --symbol <S> --version <N>
     --token <PAT>  and report the validator result and final status.
10. OPTIONAL news backfill (only if you can browse): collect older
    economic-calendar events with provenance (source URL, retrieval date,
    confidence), normalize to the archive schema (source="browsed:<domain>"),
    save as news_backfill_<date>.jsonl.gz and publish via the same route.
    Never invent events; respect site terms; skip silently if you cannot.
