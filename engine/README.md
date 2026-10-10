# sentinel_engine

Public calculation engine for SENTINEL-FX pair packs.

```bash
pip install "git+https://github.com/vjumbo264/sentinel-fx#subdirectory=engine"
```

- `sentinel_engine.indicators` — SMA/EMA/WMA/RSI/MACD/Bollinger/ATR/Stochastic/ADX/CCI/Williams %R/ROC/Keltner/Donchian/Ichimoku/pivots/candle patterns/rolling stats/sessions/multi-TF resample. All strictly causal. No volume.
- `sentinel_engine.dsl` — causal JSON feature graph (`compute_features`). Negative shifts and non-rolling stats are rejected.
- `sentinel_engine.rules` — JSON rule tree evaluated after the model (`evaluate` → allow/block/adjust + reasons).
- `sentinel_engine.models` — data-only loaders: `lightgbm_text`, `tree_json`, `logreg_json`. Never pickle.
- `sentinel_engine.sandbox` — empty-env, network-isolated subprocess runner for pack custom code. Fail closed.
- `sentinel_engine.news` — ForexFactory weekly calendar helpers and news features.
- `sentinel_engine.pack` — pack loading, canonical sha256 checksum, full decision pipeline.
- `sentinel_engine.validate` — the pack validator (`python -m sentinel_engine.validate <file>`).

Engine versioning is semantic; DSL ops are append-only. Packs declare `min_engine_version`.
