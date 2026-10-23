# SENTINEL-FX OVERHAUL — Build specification

Security-redacted copy of Victor's build request. Credential values intentionally omitted, including from git history. Original supplied credential names: GITHUB_PAT, CLOUDFLARE_API_TOKEN, CLOUDFLARE_ACCOUNT_ID. Store credentials only as Actions/Cloudflare secrets; BUILD_STATE records names only.

## Role, autonomy, repository
Build vjumbo264/sentinel-fx autonomously in Q1–Q5 order. Read BUILD_STATE.json first and resume the first incomplete overhaul item. Never redo verified completed work. Finish and verify each item before the next, committing and pushing every meaningful unit. Log assumptions, decisions, and blockers. Ask Victor only when required credentials block all remaining progress. All execution is GitHub Actions and Cloudflare; Victor uses Android/Termux and must not need a local machine. No Colab.

## Architecture and invariant contracts
Policy → engine/sentinel_engine/execution_adapter.py → broker (native MT5 live, SimulationBroker for training). The trained policy never touches MT5 and never sees prices/lots/retcodes. Import the existing build_observation(), vectorize(), ExecutionAdapter, SimulationBroker, and policy_schema.py. Observation is EXACTLY 47 floats (4 timeframes × 8 plus 15 scalar features). Do not add/change features. Actions: hold, open, add, reduce, reverse, move_stop, close, normalized risk_fraction and stop_distance in ATR units. Adapter owns prices, risk sizing, server-side SL, stop clamping, volume rounding, and margin checks. Preserve Worker API shapes, D1 schema, and .sfxmodel.zip format.

Existing secrets must retain names: MT5_DEMO_LOGIN (fallback 41286446), MT5_PASSWORD (required; no fallback), MT5_DEMO_SERVER (fallback Deriv-Demo), GH_CHAIN_PAT, BOT_SHARED_SECRET, DERIV_BEARER_TOKEN, DERIV_APP_ID. Report explicitly whether MT5_PASSWORD is set or missing.

Current bot is Ubuntu/Wine/rpyc/mt5linux with 235 minute timeout and 13800 second wall; replace production runner with Windows/native MT5. Existing tools/trade_test.py exercises order_check, open, modify stop, partial/full close, history and D1 reconciliation, with 10018 market-closed marked pending. EURUSD has 1,537,204 historical rows in four annual data-01 assets; preserve and skip that completed bulk import. Target pairs: EURUSD, GBPUSD, USDJPY, USDCHF, AUDUSD, USDCAD, NZDUSD, EURGBP, EURJPY, GBPJPY, AUDJPY, EURAUD, GBPAUD.

## State and commits
First commit: add overhaul.queue to existing BUILD_STATE.json and save this security-redacted prompt. Each queue entry has id, title, status pending/doing/done, notes. Overhaul records pairs_target, last_updated, notes, decisions, known_issues. Update and commit after every item. Never mark done without verification. At 4h45m checkpoint/push and self-dispatch before absolute 5h job exit.

## Q1 — 5-hour wall and self-dispatch
bot/main.py: WALL default 17100 (4h45 dispatch), HARD_STOP default 18000, keep handoff mechanics. bot.yml: timeout-minutes 300, BOT_WALL_SECONDS 17100, BOT_HANDOFF_LEAD_S 300. All long-running fetch/histdata/train workflows use timeout 300 and clean resumable handoff at 4h45.
Acceptance: bot timeout 300, WALL 17100, other long workflow timeouts updated.

## Q2 — Native Windows MT5 and acceptance
bot.yml runs-on windows-latest. Remove Linux-stack steps. Install native MetaTrader5, pandas, numpy, requests, lightgbm and ./engine (and dependencies needed by the bot). Download https://download.mql5.com/cdn/web/deriv.com.limited/mt5/derivmt5setup.exe and install /auto, wait 20s. Find terminal64.exe in Program Files or Program Files (x86); launch, wait 45s. Preserve credentials under exact existing secret names. Conditional broker import supports native Windows; no production Wine/rpyc/mt5linux.
Create workflow_dispatch-only .github/workflows/mt5-acceptance.yml on windows-latest, timeout 60, plus tools/mt5_acceptance.py. Run seven steps in order:
1. MT5Broker.connect('demo'); balance > 0; account mode demo.
2. All 13 symbols have specs and positive bid ticks.
3. EURUSD M1 count 100 returns at least 50 candles.
4. order_check minimum volume BUY with SL bid−0.0020 and TP ask+0.0040, rounded to digits, magic 999001, comment sfx:acceptance. Retcode 0 or 10018 only (closed pending).
5. Existing trade_test.lifecycle on EURUSD, pending on market-closed, otherwise all lifecycle/D1 checks pass.
6. Shared build_observation on actual candles, equity/pool 10000, no positions; vectorize shape (47,), no NaNs.
7. ExecutionAdapter hold smoke test, pool equity/free margin 10000, volatility ATR; status filled.
Write full honest results docs/mt5_windows_acceptance.json, commit and upload artifact even on failure. Initial report must not invent live passing evidence. BUILD_STATE note: Victor must trigger mt5-acceptance workflow manually after merge to confirm Windows MT5 login.
Acceptance: Windows workflow, acceptance workflow and all seven test steps exist; results JSON committed.

## Q3 — HistData, release overflow, incremental Deriv
Create tools/release_utils.py upload_asset_with_overflow(gh_token, repo, pair, filename, data_bytes, size_limit_mb=1800): paginate releases matching data-{pair.lower()}-NN, sort shard numbers, sum assets, advance when full (also avoid upload crossing limit), upload, return tag. Record pair shard_releases in data/index.json. Avoid losing existing data-01 references.
Create tools/fetch_histdata_bulk.py with histdata package. Download M1 year-by-year from 2000 through current year. Skip completed pairs/years using index (existing EURUSD completed). Annual {PAIR}_{YEAR}.csv.gz contains epoch, bid_open, bid_high, bid_low, bid_close, ask_open, ask_high, ask_low, ask_close. HistData bid-only ask synthesized using symbols registry spread if present else 1.5 × point; disclose cost assumption. Pace all requests ≥2s and honor HTTP 429 Retry-After. Upload and update index and commit/push each successful year. At 17100 seconds commit/push, dispatch histdata-bulk.yml with original pairs, exit 0. Missing history must not be fabricated or falsely marked complete.
Create histdata-bulk.yml workflow_dispatch input pairs default all 13, ubuntu-latest timeout 300, resumable self-chain.
Update tools/fetch_candles.py: read last_epoch before requests, only fetch/request new epoch > last_epoch; scheduled daily Deriv path is incremental only. Preserve old historical shards during append.
Acceptance: helper/fetch script syntactically valid, EURUSD skipped by index on rerun, workflow exists, incremental lower-bound check present.

## Q4 — Resumable per-pair PPO
Create training_state.json: queue all 13; active_pair EURUSD; active_version 1; total_steps_done 0; total_steps_target 5000000; last_checkpoint_utc null; last_checkpoint_steps 0; pairs_done []; pairs_pending all 13; retrain_cycle 1; next_retrain_after_utc null; updated_utc null. Preserve existing checkpoints if found. After cycle complete schedule next cycle 30 days ahead, requeue all, increment cycle.
Create tools/train_env.py Gymnasium SentinelScalpEnv using shared SimulationBroker/build_observation/vectorize/ExecutionAdapter, observation Box ±inf (47,) float64, action Discrete(5). 0 hold; 1 long/2 short risk .01 stop 1.5 ATR; 3 close oldest current ticket or hold if absent; 4 move stop to breakeven or hold if absent. Reward log(curr_equity/max(prev_equity,1e-9)) + (-0.00005*bars_held when positioned) + (-.001 for close/BE without a pre-action position). No future leakage. Reset randomized bar ≥60 history; terminate at data end or equity <10% initial. Advance M1, intrabar, shared observation, adapter execute, reward. Model costs via broker and disclose unknown commission/slippage assumptions; preserve live training inference semantics.
Create tools/train_agent.py: read state, advance completed active pair, download indexed annual release history, load actual specs, resume latest training-checkpoints pair/version checkpoint, PPO CPU, checkpoint every 50000 steps with state commit/push. At 17100 seconds upload resumable checkpoint and push state then dispatch train.yml and exit. Export on target 5M or 10 checkpoint intervals with mean episode reward improvement <.001. PPO MlpPolicy learning_rate=3e-4, n_steps=2048, batch_size=64, n_epochs=10, gamma=.99, gae_lambda=.95, clip_range=.2, device cpu. Export ONNX opset17 input obs shape 1×47, output action_logits; ensure actual logits rather than sampled action/value tuple. Bundle per TRAIN_PROMPT.md and actual engine schema with manifest.json, policy.json, risk_brain.json, training_report.json, ONNX and required parity/adapter tests. Run python -m sentinel_engine.check before publishing to models releases/models/index.json. Do not claim profitability solely from convergence.
Create train.yml workflow_dispatch mode start|resume and daily 02:00 UTC, ubuntu-latest timeout300, PAT secret, Python3.11, CPU torch/SB3, onnx/onnxruntime/numpy/pandas/requests/engine. Prevent concurrent writers; checkpoint upload/state must remain consistent across job boundaries.
--smoke-test: train 1000 PPO steps on synthetic bars, no upload/network; update state with separately labeled smoke-test evidence without counting synthetic steps as real pair training. Acceptance: files exist, smoke passes, state updated.

## Q5 — Training dashboard
Worker GET /api/training/state fetches https://raw.githubusercontent.com/vjumbo264/sentinel-fx/main/training_state.json with cacheTtl60; 503 on upstream failure. No changes to existing API shapes.
site/js/pages/training.js uses api.js real endpoint, polls every30 seconds. Show active pair/status, actual total/target progress bar, full queue icons ✅ done / 🔄 active / ⏳ pending, checkpoint time, retrain cycle, honest loading/empty/error. Add Training nav and route. Stop polling on unmount. No fake data or unrelated UI redesign.
Acceptance: endpoint returns repo state, actual API page renders, navigation works.

## Definition of done
All five overhaul.queue items verified done. Final response: queue statuses, explicit MT5_PASSWORD set/missing, actual train smoke result, actual API/page success, and outstanding human action (manually trigger MT5 acceptance after merge). Do not touch unrelated UI polish. Never commit credential values.
