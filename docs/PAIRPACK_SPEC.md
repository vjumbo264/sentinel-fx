# Pair Pack Specification (schema_version 1)

ONE JSON file: `<symbol>.pairpack.json`. Holds data AND code as embedded, hashed strings.
Extendable but backward compatible. Size target: < ~20 MB (gzip blobs).

```json
{
  "schema_version": 1,
  "symbol": "frxEURUSD",
  "pack_version": 1,
  "parent_version": null,
  "created_utc": "ISO8601Z",
  "min_engine_version": "1.0.0",
  "trainer": {"ai": "", "notes": ""},
  "data": {"granularity_s": 60, "from_utc": "", "to_utc": "", "candles": 0},
  "features": {"dsl": [], "custom_modules": [{"name": "", "sha256": "", "code_b64gz": "", "params": {}}]},
  "model": {"type": "lightgbm_text|tree_json|logreg_json", "encoding": "utf8|base64-gzip", "blob": "", "input_features": [], "output": "prob_up"},
  "rules": {},
  "decision": {"horizon_min": 15, "payout_assumed": 0.85, "margin": 0.0, "cooldown_min": 0},
  "risk": {"stake_pct": 0.0, "max_stake_suggested": 0.0, "daily_loss_pct": 0.0, "daily_target_pct": 0.0, "max_consecutive_losses": 0, "loss_cooldown_min": 0},
  "sessions": {"allowed_utc_hours": []},
  "news_rules": {},
  "backtest": {"method": "walk_forward", "folds": 0, "oos_trades": 0, "win_rate": 0.0, "break_even_win_rate": 0.0, "edge": 0.0, "max_drawdown_pct": 0.0, "verdict": "pass|fail", "notes": ""},
  "tests": {"candles_b64gz": "", "check_indices": [], "expected_features": {}, "expected_probs": [], "tolerance": 1e-6},
  "checksum_sha256": ""
}
```

## Hard rules
- `symbol` matches `^frx[A-Z]{6}$`. `horizon_min` is 15 (Deriv forex minimum).
- `break_even_win_rate` MUST equal `1/(1+payout_assumed)`.
- `verdict` is "pass" ONLY if OOS win rate > break-even + `decision.margin`,
  `oos_trades` >= 60, `max_drawdown_pct` <= 50. Honesty: failing = "fail".
- Model is data-only: lightgbm_text | tree_json | logreg_json. NEVER pickle.
- DSL is strictly causal; custom modules: deterministic, no I/O, whitelisted
  imports (numpy, pandas, math, scipy.signal/stats), per-module sha256 of the
  decoded source, <= 64 KB each, executed only in the engine sandbox.
- `checksum_sha256` = sha256 of the canonical JSON (sorted keys, compact
  separators, UTF-8) of the whole pack with the checksum field removed.
- `tests.candles_b64gz`: gzip+base64 of a JSON list of candles
  `{epoch, open, high, low, close}` (>= 120 rows). `check_indices` list row
  indices; `expected_features` maps `{"<idx>": {"<feature>": value}}`;
  `expected_probs[i]` is P(up) at `check_indices[i]`. Tolerance default 1e-6.
- Engine versioning is semantic; DSL ops are append-only.

## Validation
`python -m sentinel_engine.validate <file> --mode fast|full`
Fast: schema/size/checksum/static/backtest consistency. Full adds causality
(truncation test), reproducibility vs embedded vectors, determinism, sandbox
run for custom code (fail closed if isolation unavailable), latency, sanity.
