# SENTINEL-FX Training Playbook v1
Policy schema: `sentinel.policy.v1`. Bundle archive schema: 2.

## 1. Mission, objective and honesty
Grow the balance assigned to one instrument while protecting it from deep losses. The objective is risk-adjusted **log equity growth after every cost**, not win rate, trade count, or an attractive in-sample curve. A truthful conclusion of no demonstrable edge, with a policy that trades rarely or stays out, is a valid and often superior outcome. Synthetics exist here only to prove plumbing; they are not a market-edge project. Never manufacture fills, candles, volume, news, screenshots, returns, or broker evidence. Never trade a real-money account while training or verifying this delivery. Only the owner can separately authorize real deployment.

Use a starting research objective such as mean daily log return minus penalties for return variance, maximum drawdown, CVaR and excessive margin. Optimize on development folds, not the final holdout. Compare against cash and a simple cost-aware baseline. Reward penalties must expose catastrophic-tail and martingale behavior rather than making it look profitable through frequent small wins. Show ruin/stop-out sensitivity and scenario gaps explicitly. A high win rate with rare ruin is unacceptable.

## 2. The policy is not an MT5 program
The trained policy consumes data and returns an arbitrary list of normalized trading intentions. It never imports MT5, receives terminal handles, learns tickets as numbers, selects lots, or emits absolute broker stop prices. Broker translation is exclusively `sentinel_engine.execution_adapter.ExecutionAdapter`, shared by the live bot and simulator. A failed order appears on the next observation as a plain rejection result. Execution safety remains outside the learned model.

The plan is a declarative acyclic graph of causal feature groups, optional analyst models, routers, calibration/news nodes and exactly one learned `policy` node. A policy node requires a model filename, `schema_version`, and an `action_catalog` containing lists of actions. ONNX or LightGBM scores select an action-list catalogue entry using deterministic argmax. Catalogue entries may use the symbolic position reference `oldest`, resolved to the oldest owned position at inference. Expand the action catalogue to represent adaptive risk, stop distance, management and confluence; do not substitute a hard-coded constant policy. A continuous actor may be represented by independently learned heads and a versioned deterministic decoder only after decoder parity is added to the engine.

## 3. Versioned contract
Read the installed `policy-v1.schema.json`, Python dataclasses in `policy_schema.py`, `observation.py` and `execution_adapter.py` before training. Use the implementation pinned in the copied prompt, not a guessed interface.

Observation contains:
* `schema_version`, per-timeframe causal `market` features, `costs`, UTC `session` features and as-known `news` state;
* own `equity`, `drawdown`, `pool_share`, own normalized `positions`, normalized `recent_results`, and `last_action_result`;
* position references are opaque strings, with direction, size fraction of equity, entry distance in volatility units, profit in risk units, age in minutes, and stop/target distances. Never feed broker prices or numeric ticket magnitude into a learned feature;
* costs include spread in ATR units, swap, commission and an availability mask. Unknown commissions/news are unknown, not evidence of zero cost or zero risk.

Every step returns `{"schema_version":"sentinel.policy.v1","actions":[...]}`. Any number of actions is allowed. Every action has a short, truthful `reason`:
* `hold`;
* `open` with `side: long|short`, `risk_fraction` in (0,1], optional positive `stop_distance` in ATR units, and `targets:[{distance,fraction}]`; fractions total at most one;
* `add` with `position_ref` and incremental `risk_fraction`;
* `reduce` with `position_ref` and `fraction` in (0,1];
* `reverse` or `close` with `position_ref`;
* `move_stop` with `position_ref` and exactly one of positive `new_stop_distance`, `to_breakeven:true`, or positive `trail` in ATR units.

ActionResult has `status: filled|partial|rejected`, `reason`, optional fill `price` and `size`, `clamped` values and opaque returned `tickets`. Rejection reasons are margin, broker_limit, market_closed, owner_override, invalid. The adapter always attaches a protective stop when a stop distance is missing and records this clamp. This is not permission to train without understanding downside.

## 4. Sizing, risk and the session pool
Use the model's own pool share and compounded equity, never the whole account. Consider calibrated cost-adjusted edge, uncertainty, volatility, drawdown, correlated exposure, losing-run evidence and available margin. Fractional Kelly and volatility targeting are starting hypotheses, not guarantees. Fit shrinkage/calibration out of fold. Reduce risk as evidence weakens or losses deepen; scale up only with independently proven confluence. Never double simply because the previous position lost. Assess risk over all concurrent positions and scenarios, not each order in isolation.

The adapter converts equity times risk fraction to monetary loss at the stop using broker tick value/tick size or native profit calculation. It rounds **down** to volume step, rejects sizes below minimum, obeys broker max/stops/freeze/filling rules, and checks free margin and the model's share. Targets can split hedging positions where minimum size permits. Owner exposure/take-profit/stop-loss overrides are optional and default off. Mandatory server-side stops are not optional. Gap loss can exceed the stop budget: include it in stress tests and the report. No artificial two-position cap or arbitrary holding-time limit belongs in the policy.

## 5. Read the market like a professional
Start with completed M1 candles and causally resample M5/M15/H1/H4/D1 only after their close. Do not use a developing higher-timeframe candle as if closed. Maintain a per-instrument checklist: trend/range structure, key swing/session levels and ranges, distance to liquidity/round-number levels, momentum and exhaustion, volatility expansion/contraction, session overlap, weekday, spread, regime, and uncertainty. Document each feature's causal availability and warmup.

Build independent analyst hypotheses (trend, momentum/volatility, levels/ranges, regime/session, event risk). Out-of-fold analyst predictions must be generated without cross-fold information leakage. Agreement is not automatically independent confirmation: test correlations and disagreement. Keep relative tick volume only if it improves unseen results and Deriv MT5 tick volume correlates with the training-source volume on an overlapping period. Tick counts are not exchange volume. Turn it off for synthetics. Do not fabricate volume when a source has no volume field.

## 6. Trade management is part of the policy
Train entry and management jointly or in validated stages: stay out, long/short, split entries, additional independent positions, scale-in, partial exits, several targets, early adverse cuts, hold, reversal, break-even and trailing. Actions must account for existing exposure and available equity, not reset sizing after every trade. Never remove a server stop during a modification. Minimum-size partial exits may be rejected; the next policy step should observe and respond to that result. Do not force opens simply to obtain a pretty trade count. A special demo execution test must be clearly separated from profitability research.

## 7. Architecture contest and staged compute
A: simple committee of cost-aware analyst models plus learned policy. B: raw multi-timeframe candle network with causal encoders. C: hybrid encoder plus analyst committee plus learned policy, trained in the shared simulator on risk-adjusted log growth. Start A with a small, interpretable model. Use C/B only when they beat the simpler candidate by a predeclared meaningful margin on unseen development folds, accounting for uncertainty, latency and parameter search. Greater complexity is not a benefit by itself.

Stages: instrument/data audit; simplest baseline; causal supervised representation/edge training; calibrated out-of-fold committee; simulator action-value/actor training; management and sizing; walk-forward contest; finalists only on locked holdout; passive forward evaluation; data-only export and parity. Fit scalers on training segments only. If reinforcement learning is used, randomize realistic costs and initial allocations, use recurrent state without future information, and distinguish simulated episodes from live proof. Begin with CPU, 4 threads, a fixed seed, bounded memory and a measured short pilot. Record actual compute and request owner permission before using an external paid service. Do not build heavy synthetic machinery.

## 8. Evaluation, counted looks and selection bias
Lock the final holdout before tuning. Development uses purged walk-forward with embargo longer than label overlap and typical maximum holding horizon. All preprocessing, calibration and analyst predictions are fold-local. Report fold results after costs, growth, equity drawdown, worst day, margin, cost paid, holding times, trade counts and win rate as information only. Use block bootstrap on daily returns with dependence-preserving blocks; insufficient data means no CI, not zero uncertainty. Show weekday/hour/regime/news breakdowns and flag unsupported coverage.

Run cost sensitivity at spread x1/x1.5/x2, commissions, swap, slippage, gaps and margin/stop-out stress. Ablate each analyst, timeframe, tick-volume, news layer and management component. Report the simpler baseline, every counted finalist holdout look, candidate/search budget and selection process. A disappointing holdout cannot be silently reassigned to development and replaced. FWD is passive forward evaluation on data after trained_through, never unauthorized real trades. Do not claim profitability from sfx check: it verifies code and bundle health only.

## 9. Two-stage news, as known live
Stage one trains price analysts across the full reliable candle history. Stage two trains a news layer only where archive coverage exists; otherwise use an explicitly conservative guard and a missing-data mask. Map events to the pair's currencies. Upcoming/recent events can expose schedule, impact, forecast and previous values as they were recorded. Actual/reaction data can be shown only after its publication and after the reaction horizon elapsed. Never retroactively replace historical forecasts with revised values. Validate archive recorded timestamps before using them. Evaluate changes in spread and volatility, pre-event stand-down, post-event reaction and disagreement. If coverage is too short to establish benefit, retain the simpler price model plus conservative guard.

## 10. Simulator parity and known limitations
Use `CFDSimulator` with real candles, actual specs, explicit costs and the same adapter; fills occur only after the completed input bar. Require modeled bid/ask, spread, commission, swap, slippage, margin, stop-out, multiple positions, partial exits and gaps. If both SL and TP hit in one bar, the stop wins; stop gap fills use the worse open, not the unattainable stop price. Never manufacture intrabar ticks from OHLC to inflate an edge.

Inspect `cost_assumptions` and unsupported report fields in the pinned implementation. An unknown commission or unavailable news/regime breakdown is not a passed evaluation requirement. Add the missing validated measurement/feature/report before making a quality claim. Broker bid-only fallback candles do not imply actual historical ask OHLC: use recorded spread with explicit approximation/stress. Close all simulated exposure at evaluation end and account for costs. No real execution is necessary for training.

## 11. Safe formats, engine commands and delivery
Install the **exact commit** from the copied prompt in a clean environment. Run `sfx guide`. `sfx init SYMBOL --dir export` creates metadata, not a trained policy. Keep training scripts/data/research outside `export`; its ZIP may contain only JSON, ONNX or LightGBM text model data. No pickle/joblib, executable Python/JS/shell/native code, custom ONNX operators/functions, external-data ONNX tensors, path traversal or network hooks.

Export analysis_plan.json, policy.json, trained model files, preprocessing/risk/news metadata, training_report.json, manifest.json, `tests/vectors.json` and `tests/adapter.json`. Embedded vectors contain full real causal observations and trainer expected outputs; include unseen inputs, flat state, own positions, missing news, rejections and invalid-output fixtures. Adapter vectors include actual specs/ticks/equity/volatility and expected conversions. Keep missing-file, wrong-hash, pickled-model, custom-op, external-data, bad-plan, NaN, parity-mismatch and syntax-error rejection fixtures; add invalid actions, oversized risk and missing-stop protective handling.

Commands:
```
sfx build export SYMBOL_v1.sfxmodel.zip
sfx check SYMBOL_v1.sfxmodel.zip
sfx sim SYMBOL_v1.sfxmodel.zip --candles SYMBOL.csv.gz --specs symbol-specs.json --balance 1000 --out simulation-report.json
```
Use an explicit correct broker specification file, never guessed defaults. If the owner separately supplied a publishing credential, keep it in GITHUB_TOKEN environment, never in source/logs or command-line arguments, then `sfx publish SYMBOL_v1.sfxmodel.zip --symbol SYMBOL --version 1`. Wait for the public publish workflow's actual checker result and disabled installation. Without a credential, build the .sfxmodel.zip and tell the owner to download it and upload via the site. The AI must never enable real-money trading.

## 12. Resumability, stop conditions and final report
Maintain PROGRESS.md outside the bundle, with reproducible commands, data/checksums, pinned engine SHA, split boundaries, candidates, measured results, rejected hypotheses, counted holdout looks, errors/root causes, remaining experiments and next exact command. Save small checkpoints/data-only intermediate models, seeds and costs. Iterate until evidence is genuinely good; diagnose failure rather than immediately abandoning. Exhaust reasonable simpler architectures, sizing, calibration, management, cost realism and ablations before declaring no edge. Do not optimize forever on one holdout or promise that more compute guarantees profitability.

Final report: instrument/data source and limitations; rows/first/last/checksums; pinned engine and policy version; feature causality and news coverage; architecture contest and compute; split/purge/embargo/holdout look count; all cost-aware growth/drawdown/worst-day/margin/holding/cost metrics and CIs; stress/ablations/breakdowns; reasons the selected candidate beats cash/baseline or the honest no-edge verdict; sfx check output and bundle checksum; delivery/download path; passive forward plan. Clearly separate pure logic tests, replay evidence and actual demo broker execution. Never claim a live pass from a simulator or from green workflow status alone.
