# SENTINEL-FX — FULL OVERHAUL BUILD PROMPT
**Repo:** `vjumbo264/sentinel-fx`
**Site:** https://sentinel-fx.pages.dev
**Worker:** https://sentinel-fx-worker.vjumbo264.workers.dev
**D1 ID:** `5e272a6b-ad11-4bd6-bd61-70569c9f74f6`

---

## STEP 0: CREDENTIALS (read first, do this before anything else)

```
GITHUB_PAT = [CONFIGURED_IN_GITHUB_SECRETS]
CLOUDFLARE_API_TOKEN = [CONFIGURED_IN_SECRETS]
CLOUDFLARE_ACCOUNT_ID = 1695bfc7422ac8004179e99f3cdd60c1
WORKER_URL            = https://sentinel-fx-worker.vjumbo264.workers.dev
```

Use these to push to the repo and deploy. Store them as GitHub Actions / Cloudflare secrets.
Never commit them, never write values into BUILD_STATE.json (names only).
If any value is still a placeholder, do all work that does not need it first,
then ask for it in a single short message at the end only if nothing else can proceed.

---

## ROLE AND AUTONOMY

You are the builder. You have full autonomy over all implementation decisions.
Deliver working code, push every file change to `vjumbo264/sentinel-fx`, and let
GitHub Actions + Cloudflare do the rest. Never stop to ask Victor for
clarification, confirmation, or choices — pick the most sensible default, record
it in BUILD_STATE.json `decisions`, and keep going. The only time you stop is if
a required secret is missing and nothing else can proceed. Do everything else
first, then ask once at the end.

Commit and push after every file or small unit of work. Never leave work
uncommitted while starting something new. Each push must leave the repo in a
state the next AI can understand from BUILD_STATE.json alone.

---

## PROJECT BACKGROUND

SENTINEL-FX is an autonomous Deriv MT5 CFD forex trading system run by Victor
(MOTIONSALT), a solo developer based in Nigeria working entirely from Android /
Termux. The system trains RL (PPO) models per forex pair on real historical M1
data and executes them live via a GitHub Actions Windows bot.

**Current state when this prompt was written:**
- Bot workflow (`bot.yml`) runs on `windows-latest` ✅ — correct, MT5 requires Windows
- Training workflow (`train.yml`) runs on `ubuntu-latest` ✅ — correct for PyTorch CPU
- EURUSD data present (5 years, 1.5M rows) ✅
- AUDUSD data present (3 years, 1.1M rows) ✅
- Synthetics (R_10, R_25, R_50, R_75, R_100, 1HZ variants) present and auto-updating daily ✅
- 11 forex pairs have NO data: GBPUSD, USDJPY, USDCHF, USDCAD, NZDUSD, EURGBP, EURJPY, GBPJPY, AUDJPY, EURAUD, GBPAUD
- No trained models exist yet
- Current observation vector is 47 dimensions — this schema is being replaced entirely
- The site is laggy, bloated, and full of stale flows — it is being completely trashed and rebuilt
- No training interlock exists in the bot — this is being added
- The old zip-upload / validate-pack / promote flow is removed entirely — training is fully automated

---

## WHAT THIS PROMPT BUILDS — FIVE QUEUED ITEMS

Work through these in order. Finish each completely before starting the next.
Never skim. Every item gets full, proper work verified against its acceptance
criteria before being marked done in BUILD_STATE.json.

---

## ITEM F1 — Fetch missing forex pair data

**What:** Run `histdata-bulk.yml` for the 11 pairs that have no data.

**Missing pairs:**
`GBPUSD, USDJPY, USDCHF, USDCAD, NZDUSD, EURGBP, EURJPY, GBPJPY, AUDJPY, EURAUD, GBPAUD`

**How:** Dispatch the existing `histdata-bulk.yml` workflow via the GitHub API
with those 11 pairs as the `pairs` input. The workflow fetches HistData M1
history and commits results to `data/index.json` + uploads to release assets.

**Acceptance:**
- All 11 pairs appear in `data/index.json` with `rows > 0`
- Each has a release asset URL and SHA256 in the index
- `data/index.json` committed to main
- If a pair fails (HistData unavailable for that symbol), log it in
  BUILD_STATE.json `known_issues` and continue — do not block everything else

**Important:** Dispatch and monitor the workflow. If it hits the 5h wall and
self-chains (the workflow has wall-dispatch logic), wait for the chain to
complete. Record run URLs in BUILD_STATE.json as evidence.

---

## ITEM F2 — Training engine overhaul (observation + reward + actions)

**What:** Replace the current thin 47-dimension observation and weak reward with
a professional-grade scalper observation. This is the most important item.
Any model trained on the old 47-dim schema is incompatible and worthless —
the new schema replaces it entirely. No backward compatibility needed.

### 2A. New observation — `engine/sentinel_engine/observation.py`

Add these features to `causal_market()` and `build_observation()`. All must be
causally safe — computed only from completed bars available at inference time.

**Per-timeframe additions (M1 and H1 only for new features — M5/M15 keep existing):**

RSI(14):
```
delta = close.diff()
gain = delta.clip(lower=0).ewm(com=13, adjust=False).mean()
loss = (-delta.clip(upper=0)).ewm(com=13, adjust=False).mean()
rs = gain / loss.replace(0, 1e-9)
rsi = 100 - (100 / (1 + rs))
rsi_normalized = (rsi.iloc[-1] - 50) / 50   # range approx [-1, 1]
```

Bollinger band position (20-period, 2 std):
```
sma20 = close.rolling(20).mean()
std20 = close.rolling(20).std()
upper = sma20 + 2 * std20
lower = sma20 - 2 * std20
band_width = upper - lower
bb_position = (close - lower) / band_width.replace(0, 1e-9)   # 0=lower, 1=upper
bb_position_normalized = bb_position.iloc[-1].clip(0, 1) * 2 - 1  # map to [-1, 1]
```

Bollinger squeeze (on M1 only):
```
# Squeeze = current band width < 80th percentile of band width over last 100 bars
current_width = float((upper - lower).iloc[-1])
hist_width = (upper - lower).tail(100)
squeeze = 1.0 if current_width < float(hist_width.quantile(0.2)) else 0.0
```

EMA cross (M1 and M5):
```
ema9 = close.ewm(span=9, adjust=False).mean()
ema21 = close.ewm(span=21, adjust=False).mean()
ema_cross = float((ema9.iloc[-1] - ema21.iloc[-1]) / atr)  # normalized by ATR
```

ATR regime (M1 only):
```
atr_series = tr.ewm(span=14, adjust=False).mean()
atr_20_mean = float(atr_series.tail(20).mean())
atr_regime = 1.0 if atr > atr_20_mean else 0.0   # 1=expanding, 0=contracting
volatility_percentile = float((atr_series < atr).tail(100).mean())  # 0-1
```

Candle body ratio (M1 only — last completed bar):
```
body = abs(last.close - last.open)
wick = (last.high - last.low)
body_ratio = float(body / max(wick, atr * 0.01))   # 0=doji, 1=full body
# Direction of body: positive = bullish, negative = bearish
body_direction = float(np.sign(last.close - last.open)) * body_ratio
```

RSI divergence flag (M1 only):
```
# Price making new high but RSI not = bearish divergence (-1)
# Price making new low but RSI not = bullish divergence (+1)
# No divergence = 0
price_high_5 = close.tail(5).max() == close.iloc[-1]
rsi_high_5 = rsi.tail(5).max() == rsi.iloc[-1]
price_low_5 = close.tail(5).min() == close.iloc[-1]
rsi_low_5 = rsi.tail(5).min() == rsi.iloc[-1]
divergence = 0.0
if price_high_5 and not rsi_high_5: divergence = -1.0   # bearish
if price_low_5 and not rsi_low_5: divergence = 1.0      # bullish
```

Consecutive same-direction bars (M1, last 5 bars):
```
directions = np.sign(close.diff().tail(5))
consecutive = 0
last_dir = directions.iloc[-1]
for d in reversed(directions.values):
    if d == last_dir and d != 0: consecutive += 1
    else: break
consecutive_normalized = float(consecutive * last_dir) / 5.0  # range [-1, 1]
```

Session high/low distance (M1, current session = last 8 hours):
```
session_bars = df[df['epoch'] >= (asof - 8*3600)]
session_high = float(session_bars['high'].max())
session_low = float(session_bars['low'].min())
dist_from_high = float((session_high - last.close) / atr)
dist_from_low = float((last.close - session_low) / atr)
```

Spread spike flag:
```
current_spread = tick['ask'] - tick['bid']
# Use spread_profile_by_utc_hour from data/index.json if available
# Fall back to specs typical_spread_pts * specs point
typical_spread = specs.get('typical_spread_pts', 1.5) * specs.get('point', 0.00001)
spread_spike = 1.0 if current_spread > 2.5 * typical_spread else 0.0
```

**New fields added to the `market` dict per timeframe (M1 and H1):**
`rsi`, `bb_position`, `ema_cross`

**New fields added to `market['M1']` only:**
`bb_squeeze`, `atr_regime`, `volatility_percentile`, `body_direction`, `rsi_divergence`, `consecutive_bars`

**New top-level fields in the observation (not per-timeframe):**
`session_dist_high`, `session_dist_low`, `spread_spike`

**Update `vectorize()` to include all new fields.** New vector size will be
approximately 65–70 dimensions. The exact count does not matter — whatever
is produced becomes the new locked schema. Update `observation_space` in
`train_env.py` to match exactly.

**Update `VERSION` in `policy_schema.py` to `'sentinel.policy.v2'`** so any
old 47-dim bundle is immediately rejected by the engine.

### 2B. New action space — `tools/train_env.py`

Replace the 5-action catalog with this 8-action catalog:

```python
ACTION_CATALOG = [
    [{'type': 'hold',      'reason': 'agent_hold'}],
    [{'type': 'open', 'side': 'long',  'risk_fraction': 0.01, 'stop_distance': 1.5, 'reason': 'agent_long_full'}],
    [{'type': 'open', 'side': 'long',  'risk_fraction': 0.005,'stop_distance': 1.5, 'reason': 'agent_long_half'}],
    [{'type': 'open', 'side': 'short', 'risk_fraction': 0.01, 'stop_distance': 1.5, 'reason': 'agent_short_full'}],
    [{'type': 'open', 'side': 'short', 'risk_fraction': 0.005,'stop_distance': 1.5, 'reason': 'agent_short_half'}],
    [{'type': 'close',     'position_ref': 'oldest', 'reason': 'agent_close'}],
    [{'type': 'move_stop', 'position_ref': 'oldest', 'to_breakeven': True,  'reason': 'agent_be'}],
    [{'type': 'move_stop', 'position_ref': 'oldest', 'trail': 0.8,          'reason': 'agent_trail'}],
]
```

Update `action_space = gym.spaces.Discrete(8)`.

Update `_action_to_dict()` to handle all 8 indices correctly.
Actions 5/6/7 (close/be/trail) on no-position → convert to hold + invalid
penalty in reward, do not crash.

### 2C. New reward function — `tools/train_env.py`

Replace `_reward()` with this composite reward. This shapes the agent into a
conservative, consistent scalper — smooth equity growth, not volatile swings:

```python
def _reward(self, prev_equity, curr_equity, action_idx, had_position=None):
    # 1. Core: log equity growth after costs
    pnl = np.log(max(curr_equity, 1e-9) / max(prev_equity, 1e-9))

    # 2. Drawdown penalty — exponential, not linear
    # Penalises deep drawdowns sharply; small drawdowns lightly
    dd = max(0.0, 1.0 - curr_equity / self.peak)
    drawdown_penalty = -0.001 * (np.exp(5.0 * dd) - 1.0)

    # 3. Hold cost — penalises sitting in a trade too long (scalper should be quick)
    # Cost increases with bars held: gentle for first 15 bars, steeper after
    hold_cost = 0.0
    if self._position:
        bars = self._bars_held
        hold_cost = -(0.00003 * bars + 0.00001 * max(0, bars - 15) ** 2)

    # 4. Invalid action penalty
    invalid = -0.002 if action_idx in (5, 6, 7) and not had_position else 0.0

    # 5. Profitable exit bonus — reward taking a good exit
    exit_bonus = 0.0
    if action_idx == 5 and had_position:  # close action
        closed = self.broker.closed
        if closed:
            last_trade = closed[-1]
            if last_trade.get('net_pnl', 0) > 0:
                exit_bonus = 0.001  # small bonus for profitable close

    # 6. Spread spike penalty — penalises opening during high spread
    spread_spike = getattr(self, '_last_spread_spike', 0.0)
    if action_idx in (1, 2, 3, 4) and spread_spike:  # opening actions
        spread_penalty = -0.001
    else:
        spread_penalty = 0.0

    # 7. Consistency bonus — running Sharpe-like term
    # Reward if this step's PnL is above the rolling mean (smooth returns)
    if len(self._recent_pnl) >= 10:
        mean_pnl = np.mean(self._recent_pnl[-20:])
        consistency = 0.0002 if pnl > mean_pnl else 0.0
    else:
        consistency = 0.0

    self._recent_pnl.append(pnl)

    return float(pnl + drawdown_penalty + hold_cost + invalid + exit_bonus + spread_penalty + consistency)
```

In `reset()`: add `self._recent_pnl = []` and `self._last_spread_spike = 0.0`.

In `step()`: update `self._last_spread_spike` from the observation's
`spread_spike` field before computing reward.

### 2D. Walk-forward evaluation — `tools/train_agent.py`

Replace the current simple train/holdout split in `load_data()` with proper
walk-forward. After training completes but before `publish()`, run this:

```python
def walk_forward_eval(model, full_data, specs, pair):
    """
    Split: 70% train (already used), 15% validation, 15% holdout (locked).
    Walk-forward: evaluate on validation fold only.
    Returns verdict: 'pass' or 'no_edge', plus metrics.
    """
    n = len(full_data)
    val_start = int(n * 0.70)
    holdout_start = int(n * 0.85)

    val_data = full_data.iloc[val_start:holdout_start].reset_index(drop=True)
    holdout_data = full_data.iloc[holdout_start:].reset_index(drop=True)

    if len(val_data) < 500:
        return {'verdict': 'insufficient_data', 'val_rows': len(val_data)}

    val_env = SentinelScalpEnv(val_data, specs, pair)
    obs, _ = val_env.reset(options={'start_bar': 60})
    equity_curve = [val_env.initial_balance]
    done = False
    while not done:
        action, _ = model.predict(obs, deterministic=True)
        obs, reward, terminated, truncated, info = val_env.step(int(action))
        equity_curve.append(info['equity'])
        done = terminated or truncated

    equity_curve = np.array(equity_curve)
    returns = np.diff(np.log(np.maximum(equity_curve, 1e-9)))

    final_equity = float(equity_curve[-1])
    total_return = float((final_equity - val_env.initial_balance) / val_env.initial_balance)
    max_dd = float(np.max(np.maximum.accumulate(equity_curve) - equity_curve) / np.maximum.accumulate(equity_curve).max())
    sharpe = float(np.mean(returns) / (np.std(returns) + 1e-9) * np.sqrt(252 * 1440))  # annualized M1 Sharpe
    trade_count = len(val_env.broker.closed)
    win_rate = float(np.mean([1 if t['net_pnl'] > 0 else 0 for t in val_env.broker.closed])) if trade_count > 0 else 0.0

    # Verdict: positive return AND Sharpe > 0.3 AND max drawdown < 30%
    verdict = 'pass' if (total_return > 0 and sharpe > 0.3 and max_dd < 0.30 and trade_count >= 10) else 'no_edge'

    return {
        'verdict': verdict,
        'val_rows': len(val_data),
        'holdout_rows': len(holdout_data),
        'final_equity': final_equity,
        'total_return_pct': round(total_return * 100, 2),
        'max_drawdown_pct': round(max_dd * 100, 2),
        'sharpe_annualized': round(sharpe, 3),
        'trade_count': trade_count,
        'win_rate_pct': round(win_rate * 100, 1),
        'cost_paid': val_env.broker.cost_paid,
    }
```

Call `walk_forward_eval()` in `publish()` before uploading the bundle. Pass
the result into `training_report.json` inside the bundle. Set
`models/index.json` entry `verdict` to either `'pass'` or `'no_edge'`.

A `no_edge` model is still published — Victor can review the metrics and
decide whether to enable it. The bot will not auto-enable a `no_edge` model
but Victor can manually enable it from the site.

### 2E. Acceptance criteria for F2:

- `engine/sentinel_engine/observation.py` produces a finite vector of the new
  size (will be ~65–70 dims); exact size doesn't matter but must be consistent
- `policy_schema.py` VERSION = `'sentinel.policy.v2'`
- `train_env.py` observation_space shape matches new vector size exactly
- Smoke test passes: `python tools/train_agent.py --smoke-test`
- All existing tests pass: `pytest tests/ -x -q` (expect 2 pre-existing
  reconnect-test failures on baseline — those are known and acceptable)
- Walk-forward eval runs on synthetic data in smoke test (skip network upload)

---

## ITEM F3 — Training interlock (bot pauses during training)

**What:** When training is scheduled, the bot must stop opening new trades
immediately. Open trades close naturally. Bot idles. Training runs. Bot resumes.

### 3A. Worker — `worker/src/index.js`

Add one new site-authenticated endpoint:

```
POST /api/settings/training-lock
Body: { "locked": true|false, "reason": "string" }
```

This writes `training_locked` (bool) and `training_lock_reason` (string) to
the D1 `settings` table. Use the same upsert pattern as other settings writes.
Return `{ ok: true }`.

Also: remove these dead endpoints that no longer exist in the architecture:
- `POST /api/upload/staging-asset`
- `POST /api/packs/register`
- `POST /api/packs/status`
- `POST /api/packs/promote`

These were the old zip-upload flow. Remove them cleanly. Do not leave stubs.

Deploy worker after changes: push to `worker/src/index.js` → `deploy-worker.yml` auto-deploys.

### 3B. Bot — `bot/main.py`

At the top of the main loop (after fetching session/settings), add:

```python
training_locked = bool(settings.get('training_locked', False))
if training_locked:
    log.info('Training lock active — bot idle, not opening new trades')
    # Still post heartbeat so site knows bot is alive but paused
    http_worker('POST', '/api/bot/heartbeat', {
        'mode': 'demo',
        'balance': acct['balance'],
        'equity': acct['equity'],
        'free_margin': acct['margin_free'],
        'loginid': str(acct['login'])[:2] + '***',
        'currency': acct['currency'],
        'note': 'training_locked — idle'
    })
    # Do NOT self-chain into a new bot run while training is locked
    # (training workflow will clear the lock when done; bot resumes via schedule or manual dispatch)
    time.sleep(60)
    continue
```

The bot still holds its lease and posts heartbeat — it just skips all trade
execution. When training clears the lock, the bot's next loop iteration
resumes normally.

Also: remove the `if mode != 'demo'` hard stop that blocks real mode.
Replace with a proper mode check that reads from settings, not a hard-coded
ValueError. Victor controls mode from the site.

### 3C. Training workflow — `.github/workflows/train.yml`

Add two steps to the training job:

**Before training starts** (after checkout/setup):
```yaml
- name: Set training lock
  env:
    WORKER_URL: ${{ secrets.WORKER_URL }}
    BOT_SHARED_SECRET: ${{ secrets.BOT_SHARED_SECRET }}
    GH_CHAIN_PAT: ${{ secrets.GH_CHAIN_PAT }}
  run: |
    # Use the PAT to call the site-auth endpoint
    curl -sS -X POST "$WORKER_URL/api/settings/training-lock" \
      -H "Authorization: Bearer $GH_CHAIN_PAT" \
      -H "Content-Type: application/json" \
      -d '{"locked":true,"reason":"train.yml active"}' \
      && echo "Training lock set"
```

**After training finishes** (with `if: always()` so it runs even on failure):
```yaml
- name: Clear training lock
  if: always()
  env:
    WORKER_URL: ${{ secrets.WORKER_URL }}
    GH_CHAIN_PAT: ${{ secrets.GH_CHAIN_PAT }}
  run: |
    curl -sS -X POST "$WORKER_URL/api/settings/training-lock" \
      -H "Authorization: Bearer $GH_CHAIN_PAT" \
      -H "Content-Type: application/json" \
      -d '{"locked":false,"reason":""}' \
      && echo "Training lock cleared"
```

### 3D. Weekend retrain schedule

Add Saturday 2am UTC cron to `train.yml`:
```yaml
schedule:
  - cron: '0 2 * * *'    # daily (existing)
  - cron: '0 2 * * 6'    # Saturday retrain (new — weekend, forex closed)
```

Acceptance: Worker deployed with new endpoint. `curl POST /api/settings/training-lock` returns `{ok:true}`. Bot main.py has training_locked check before trade execution. train.yml has lock/unlock steps.

---

## ITEM F4 — Complete site rebuild

**What:** Delete everything in `site/js/` and `site/styles/`. Write a brand-new,
fast, minimal site from scratch. No legacy code survives.

The site is a single `site/index.html` with all CSS inline in `<style>` and
all JS in `<script type="module">` tags split into logical modules under
`site/js/`. No build step. No bundler. No framework. Pure vanilla JS ES modules.

**Files to delete** (do not keep any of these):
```
site/js/app.js
site/js/api.js
site/js/store.js
site/js/router.js
site/js/theme.js
site/js/ui.js
site/js/icons.js
site/js/version.js
site/js/pageState.js
site/js/pages/home.js
site/js/pages/trades.js
site/js/pages/chart.js
site/js/pages/models.js
site/js/pages/history.js
site/js/pages/login.js
site/js/pages/risk.js
site/js/pages/settings.js
site/js/pages/training.js
site/js/pages/upload.js
site/styles/tokens.css
site/styles/components.css
site/styles/fix3.css
```

Delete by replacing with the new files described below. Do not try to patch
or update any old file — start fresh.

---

### Site architecture: what gets built

**4 pages:** Dashboard (`#dash`), Training (`#training`), History (`#history`), Settings (`#settings`)

**No:** chart page, upload page, separate trades page, more drawer, separate risk page

**Navigation:**
- Mobile: bottom bar with 4 tabs
- Desktop: left rail with 4 links

---

### 4A. Design system — `site/index.html` inline `<style>`

Professional dark-first terminal aesthetic. Clean, fast, no excess.

Color tokens (CSS variables on `:root`):
```css
:root {
  --bg:          #080c14;
  --bg-card:     #0f1520;
  --bg-input:    #151d2e;
  --border:      #1e2d45;
  --text:        #e8edf5;
  --text-2:      #8a9bb5;
  --text-3:      #4a5c75;
  --accent:      #3b82f6;
  --accent-dim:  #1e3a5f;
  --profit:      #22c55e;
  --loss:        #ef4444;
  --warning:     #f59e0b;
  --radius:      8px;
  --radius-lg:   14px;
}
[data-theme="light"] {
  --bg:       #f0f4f8;
  --bg-card:  #ffffff;
  --bg-input: #e8edf5;
  --border:   #d0d9e8;
  --text:     #0f1520;
  --text-2:   #4a5c75;
  --text-3:   #8a9bb5;
}
```

Typography: use `system-ui, -apple-system, sans-serif` — no Google Fonts import.
Numbers: `font-variant-numeric: tabular-nums`.

Base rules:
```css
* { box-sizing: border-box; margin: 0; padding: 0; }
body {
  background: var(--bg);
  color: var(--text);
  font-family: system-ui, -apple-system, sans-serif;
  font-size: 14px;
  line-height: 1.5;
  min-height: 100dvh;
}
```

Cards:
```css
.card {
  background: var(--bg-card);
  border: 1px solid var(--border);
  border-radius: var(--radius-lg);
  padding: 16px;
}
```

Buttons:
```css
.btn {
  display: inline-flex; align-items: center; justify-content: center;
  gap: 6px; padding: 8px 16px; border-radius: var(--radius);
  font-size: 13px; font-weight: 600; cursor: pointer; border: none;
  min-height: 40px; min-width: 40px;
  transition: opacity 0.15s;
}
.btn:disabled { opacity: 0.4; cursor: not-allowed; }
.btn-primary  { background: var(--accent); color: #fff; }
.btn-danger   { background: var(--loss); color: #fff; }
.btn-ghost    { background: transparent; color: var(--text-2); border: 1px solid var(--border); }
.btn-sm       { padding: 6px 12px; font-size: 12px; min-height: 32px; }
```

Layout — mobile-first with desktop rail:
```css
.shell {
  display: grid;
  grid-template-rows: 52px 1fr 60px;
  grid-template-areas: "topbar" "main" "bottomnav";
  min-height: 100dvh;
}
@media (min-width: 1024px) {
  .shell {
    grid-template-columns: 220px 1fr;
    grid-template-rows: 1fr;
    grid-template-areas: "rail main";
  }
  .bottom-nav { display: none; }
  .top-bar    { display: none; }
}
```

Status dot:
```css
.dot { width: 8px; height: 8px; border-radius: 50%; display: inline-block; }
.dot-live   { background: var(--profit); box-shadow: 0 0 6px var(--profit); }
.dot-paused { background: var(--text-3); }
.dot-train  { background: var(--warning); animation: pulse 1.5s infinite; }
@keyframes pulse { 0%,100%{opacity:1} 50%{opacity:0.4} }
```

Training lock banner:
```css
.train-banner {
  background: var(--warning); color: #000;
  text-align: center; padding: 8px 16px;
  font-size: 12px; font-weight: 700; letter-spacing: 0.04em;
  display: none;
}
.train-banner.visible { display: block; }
```

---

### 4B. HTML structure — `site/index.html`

```html
<!doctype html>
<html lang="en" data-theme="dark">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width,initial-scale=1,viewport-fit=cover">
  <title>SENTINEL-FX</title>
  <meta name="theme-color" content="#080c14">
  <style>/* ALL CSS inline here — full design system */</style>
  <script>
    try {
      var t = localStorage.getItem('sfx_theme');
      if (t) document.documentElement.setAttribute('data-theme', t);
    } catch(_) {}
  </script>
</head>
<body>
  <div class="shell">
    <!-- Mobile top bar -->
    <header class="top-bar" style="grid-area:topbar; ...">
      <span style="font-weight:700; font-size:15px;">SENTINEL-FX</span>
      <div id="top-status"></div>
    </header>

    <!-- Desktop rail -->
    <aside class="rail" style="grid-area:rail; ...">
      <div style="padding:20px 16px; font-weight:800; font-size:16px; color:var(--accent);">SENTINEL-FX</div>
      <nav id="rail-nav"><!-- links injected by JS --></nav>
      <div style="margin-top:auto; padding:16px; font-size:11px; color:var(--text-3);">
        <div id="rail-clock"></div>
        <div style="margin-top:4px;">MOTIONSALT</div>
      </div>
    </aside>

    <!-- Main content -->
    <main id="view" style="grid-area:main; overflow-y:auto; padding:16px;"></main>

    <!-- Mobile bottom nav -->
    <nav class="bottom-nav" style="grid-area:bottomnav; ...">
      <button class="tab" data-page="dash">Dashboard</button>
      <button class="tab" data-page="training">Training</button>
      <button class="tab" data-page="history">History</button>
      <button class="tab" data-page="settings">Settings</button>
    </nav>
  </div>

  <!-- Training lock banner (shown above main when active) -->
  <div id="train-banner" class="train-banner">
    ⚠ TRAINING IN PROGRESS — Bot paused, no new trades until training completes
  </div>

  <!-- Toast container -->
  <div id="toasts" style="position:fixed;bottom:80px;right:16px;z-index:100;display:flex;flex-direction:column;gap:8px;"></div>

  <script type="module" src="./js/app.js"></script>
</body>
</html>
```

---

### 4C. JavaScript modules

**`site/js/api.js`** — clean API client, no polling baked in:
```javascript
const WORKER = 'https://sentinel-fx-worker.vjumbo264.workers.dev';

function getToken() {
  try { return localStorage.getItem('sfx_pat') || ''; } catch(_) { return ''; }
}

async function req(method, path, body) {
  const token = getToken();
  const opts = {
    method,
    headers: {
      'Authorization': `Bearer ${token}`,
      'Content-Type': 'application/json',
    }
  };
  if (body !== undefined) opts.body = JSON.stringify(body);
  const r = await fetch(WORKER + path, opts);
  if (r.status === 401) throw Object.assign(new Error('unauthorized'), { status: 401 });
  const data = await r.json().catch(() => ({}));
  if (!r.ok) throw new Error(data.error || `HTTP ${r.status}`);
  return data;
}

export const api = {
  get:  (path)       => req('GET',  path),
  post: (path, body) => req('POST', path, body),

  getState:       () => api.get('/api/state'),
  getTraining:    () => api.get('/api/training/state'),
  getTrades:      () => api.get('/api/trades'),
  getPairs:       () => api.get('/api/pairs'),
  getSession:     () => api.get('/api/session'),
  getHealth:      () => api.get('/api/health'),
  saveSettings:   (d) => api.post('/api/settings', d),
  setTrainLock:   (locked, reason) => api.post('/api/settings/training-lock', { locked, reason }),
  dispatchWorkflow: (workflow, inputs) => {
    const token = getToken();
    return fetch(`https://api.github.com/repos/vjumbo264/sentinel-fx/actions/workflows/${workflow}/dispatches`, {
      method: 'POST',
      headers: {
        'Authorization': `Bearer ${token}`,
        'Accept': 'application/vnd.github+json',
        'Content-Type': 'application/json',
      },
      body: JSON.stringify({ ref: 'main', inputs: inputs || {} }),
    }).then(r => {
      if (r.status === 204) return { ok: true };
      return r.json().then(d => { throw new Error(d.message || `GitHub API ${r.status}`); });
    });
  },
};
```

**`site/js/router.js`** — hash router, dead simple:
```javascript
const routes = {};
let current = null;
let pollTimer = null;

export function register(page, mountFn) { routes[page] = mountFn; }

export function navigate(page) {
  window.location.hash = '#' + page;
}

export function stopPoll() {
  if (pollTimer) { clearInterval(pollTimer); pollTimer = null; }
}

export function startPoll(fn, intervalMs) {
  stopPoll();
  pollTimer = setInterval(fn, intervalMs);
}

export function handleRoute() {
  const page = (window.location.hash.slice(1) || 'dash');
  stopPoll();
  if (routes[page]) {
    current = page;
    routes[page]();
  } else {
    navigate('dash');
  }
  // Update nav active state
  document.querySelectorAll('.tab, .rail-link').forEach(el => {
    el.classList.toggle('active', el.dataset.page === page);
  });
}

window.addEventListener('hashchange', handleRoute);
```

**`site/js/toast.js`** — minimal toast:
```javascript
export function toast(msg, type = 'info') {
  const el = document.createElement('div');
  el.style.cssText = `
    background: var(--bg-card); border: 1px solid var(--border);
    color: var(--text); padding: 10px 14px; border-radius: var(--radius);
    font-size: 13px; font-weight: 500; max-width: 280px;
    border-left: 3px solid ${type === 'error' ? 'var(--loss)' : type === 'success' ? 'var(--profit)' : 'var(--accent)'};
  `;
  el.textContent = msg;
  const container = document.getElementById('toasts');
  container.appendChild(el);
  setTimeout(() => el.remove(), 3500);
}
```

**`site/js/app.js`** — bootstrap only:
```javascript
import { register, handleRoute, navigate } from './router.js';
import { dashPage }     from './pages/dash.js';
import { trainingPage } from './pages/training.js';
import { historyPage }  from './pages/history.js';
import { settingsPage } from './pages/settings.js';
import { loginPage }    from './pages/login.js';
import { api }          from './api.js';

// Nav setup
function buildNav() {
  const pages = [
    { id: 'dash',     label: 'Dashboard' },
    { id: 'training', label: 'Training'  },
    { id: 'history',  label: 'History'   },
    { id: 'settings', label: 'Settings'  },
  ];
  // Rail
  const rail = document.getElementById('rail-nav');
  if (rail) rail.innerHTML = pages.map(p =>
    `<a href="#${p.id}" class="rail-link" data-page="${p.id}">${p.label}</a>`
  ).join('');
  // Bottom tabs
  document.querySelectorAll('.tab').forEach(btn => {
    btn.addEventListener('click', () => navigate(btn.dataset.page));
  });
}

// Training lock banner
async function refreshBanner() {
  try {
    const state = await api.getState();
    const locked = state?.settings?.training_locked;
    document.getElementById('train-banner').classList.toggle('visible', !!locked);
  } catch(_) {}
}

// Clock
function startClock() {
  const el = document.getElementById('rail-clock');
  if (!el) return;
  setInterval(() => {
    const now = new Date(Date.now() + 60 * 60 * 1000); // UTC+1 Lagos
    el.textContent = now.toUTCString().slice(17, 25) + ' WAT';
  }, 1000);
}

// Auth gate
function isAuth() {
  try { return !!localStorage.getItem('sfx_pat'); } catch(_) { return false; }
}

register('login',    loginPage);
register('dash',     () => isAuth() ? dashPage()     : navigate('login'));
register('training', () => isAuth() ? trainingPage() : navigate('login'));
register('history',  () => isAuth() ? historyPage()  : navigate('login'));
register('settings', settingsPage);

window.addEventListener('DOMContentLoaded', () => {
  buildNav();
  startClock();
  refreshBanner();
  setInterval(refreshBanner, 30000); // recheck banner every 30s
  handleRoute();
});
```

---

### 4D. Pages

**`site/js/pages/login.js`**

Simple PAT entry. Validate against `/api/auth/check`. On success, store in
`localStorage` as `sfx_pat` and navigate to `#dash`.

Show: title, description of what the PAT is used for, input field, Connect button,
error message on failure.

---

**`site/js/pages/dash.js`** — Dashboard

Fetches on mount: `api.getState()`, `api.getSession()`, `api.getTrades()`.

Renders:

**Balance card** (top, prominent):
- Equity value (large font, monospaced)
- Balance, free margin, today's P&L (profit=green, loss=red)
- Mode pill: DEMO | REAL — click to switch (confirm sheet for REAL)
- Runner status dot + label ("Bot running" / "Bot idle" / "Training — bot paused")

**Bot controls:**
- BOT ON/OFF button — dispatches `bot.yml` when ON, sets `power=false` setting when OFF
- Kill switch button (red, confirm required) — POSTs `{ halt: true }` to `/api/settings`
- Disabled and locked if `training_locked = true` (show "Training in progress" tooltip)

**Session pool card:**
- "Set Session Balance" — input field + save button → `POST /api/session/allocate`
- Global stop-loss (% of pool) + global take-profit (% of pool) → `POST /api/settings`
- Shows current pool amount and per-model allocation if session exists

**Active models table:**
- Columns: Pair | Capital | Status | Enable toggle
- Status: "Trading" / "Idle" / "No model" / "Disabled"
- Enable toggle → `POST /api/session/override` with pause/resume
- Empty state: "No trained models yet — go to Training to train your first pair"

**Open positions table** (inline, below models):
- Columns: Pair | Side | Lots | Open price | Current | P&L | Stop
- Empty state: "No open positions"
- Fetched from `/api/trades` (filter: `close_utc IS NULL`)

**Polling:** if bot is running (heartbeat < 2 min old), poll `/api/state` every 15s.
If bot idle or training locked, no polling — just the mount fetch.
Use `startPoll` / `stopPoll` from router. Stop poll when leaving page.

---

**`site/js/pages/training.js`** — Training

Fetches on mount: `api.getTraining()`, `api.get('/api/data/index')`.

State from `training_state.json` (via `/api/training/state`):
```
{
  active_pair, status, total_steps_done, total_steps_target,
  pairs_done, pairs_pending, queue
}
```

State from `data/index.json` (via `/api/data/index`):
tells which pairs have data ready.

Renders:

**Status header:**
- If `status === 'training'`: show active pair, progress bar (steps_done / steps_target),
  ETA (estimate based on 50k steps per ~4h45m Actions run)
- If `training_locked` from settings: show "Training queued / running — bot paused"
- If idle: "No training in progress"

**Pairs grid** — all 13 forex pairs in a grid:
```
EURUSD  GBPUSD  USDJPY  USDCHF  AUDUSD
USDCAD  NZDUSD  EURGBP  EURJPY  GBPJPY
AUDJPY  EURAUD  GBPAUD
```

Plus synthetics section below:
```
R_10  R_25  R_50  R_75  R_100
```

Per pair card shows:
- Pair name
- Data status chip: "Ready ✓" (green) | "No data ✗" (red)
- Training status chip: "Trained" (green) | "Training..." (amber pulse) | "Queued" (blue) | "Untrained" (grey) | "No edge" (yellow)
- Last trained date (if available from `models/index.json`)
- Walk-forward result (if available): total return %, Sharpe, verdict

**Schedule Training button:**
- Checkbox per pair (only enabled if data is ready)
- "Schedule Training" button → on click:
  1. `api.setTrainLock(true, 'user_scheduled')` via worker
  2. Dispatch `histdata-bulk.yml` for any selected pairs without data (fetch data first)
  3. Dispatch `train.yml` with `mode: resume`
  4. Show success toast "Training scheduled — bot will pause when next trade closes"

**Polling:** if `status === 'training'`, poll `/api/training/state` every 30s.
Stop poll on page leave.

---

**`site/js/pages/history.js`** — Trade History

Fetches on mount: `api.getTrades()` (filter closed: `close_utc IS NOT NULL`).

Renders:

**Summary row:**
- Total trades, Win rate %, Net P&L, Profit factor

**Filter controls:**
- Pair selector (dropdown from unique pairs in history)
- Date range (from/to date inputs)
- Outcome filter: All | Win | Loss

**Trades table:**
- Columns: Date | Pair | Side | P&L | Result | Duration
- Sorted newest first
- Paginated at 50 rows

**CSV export button** — generates and downloads client-side.

No polling. Static on mount.

---

**`site/js/pages/settings.js`** — Settings

Renders:

**GitHub PAT section:**
- Current status: Connected ✓ / Not connected
- Input to update PAT, Test Connection button → `api.get('/api/auth/check')`
- Disconnect button (clears localStorage, navigates to login)

**Theme toggle:** Dark / Light

**Risk / Auth:**
- MT5 credentials display (masked — show demo login, server)
- Reset demo balance button → `POST /api/account/reset-demo-balance`

**System info:**
- Worker health: `GET /api/health` → latency, UTC time
- Bot status: last heartbeat time
- Training status: current pair and steps if active

No polling. Refresh button for health check.

---

## ITEM F5 — Start EURUSD training

**What:** Dispatch the first real training run on EURUSD immediately after F2 and F4 are complete.

1. Set training lock: `POST /api/settings/training-lock { "locked": true, "reason": "initial_eurusd_training" }`
2. Dispatch `train.yml` via GitHub API with `{ "mode": "start" }`
3. Confirm the workflow shows as running in GitHub Actions
4. Record the run URL in BUILD_STATE.json

Note: EURUSD has 5 years of data (frxEURUSD in data/index.json). Training will
self-chain across multiple 4h45m runs until 5M steps are complete or plateau
is detected. Victor can monitor progress on the Training page.

Acceptance: run URL in BUILD_STATE.json, `/api/training/state` shows
`status: 'training'`, `active_pair: 'EURUSD'`.
