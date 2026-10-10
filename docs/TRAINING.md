# docs/TRAINING.md — SENTINEL-FX training toolkit (MODEL task M5)

Install:
```bash
pip install "git+https://github.com/vjumbo264/sentinel-fx#subdirectory=engine"
```
The SAME engine package is used by the training AI, the validator, the
simulator and the live bot — so training and live behavior are identical by
construction (train/serve skew rule R5).

## Modules
| module | purpose |
|---|---|
| `sentinel_engine.dsl` | versioned, strictly-causal feature library (indicators, multi-timeframe) |
| `sentinel_engine.bundle` | `.sfxmodel.zip` (schema v2) loader + static verifier (data-only gate) |
| `sentinel_engine.plan` | analysis_plan.json evaluator (feature groups -> router -> analysts -> head -> calibrator -> decision) |
| `sentinel_engine.sim` | replay a bundle over history exactly as the live bot would |
| `sentinel_engine.news` | calendar fetch (Aurelia-style), archive helpers (`news_as_known_at`, `upcoming`, `recent`, `reaction_stats`) |
| `sentinel_engine.validate` | fast/full validator |

## Workflow
1. Build datasets with purged walk-forward splits (embargo >= horizon +
   longest lookback) and a LOCKED final hold-out chosen first.
2. Train analysts out-of-fold; train the head on the analysts' out-of-fold
   opinions; calibrate p_win on the hold-out (reliability table).
3. Export models to DATA formats only (ONNX / LightGBM text / XGBoost JSON)
   and build the bundle (see TRAIN_PROMPT.md step 7).
4. Replay with `sim.replay(...)` and check the honesty gates (hold-out trades
   >= 300, Wilson lower bound > break-even, positive edge at payout -3).
5. Run `python -m sentinel_engine.validate <bundle> --mode full`.

## Honesty
A failing result is labeled `fail`, never massaged. `No edge -> verdict fail,
stays in shadow` is a valid, expected outcome.
