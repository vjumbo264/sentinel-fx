# SENTINEL-FX

A Deriv forex binary-trading bot (15-minute CALL/PUT contracts on `frx*` pairs) with a
mobile-first Cloudflare control site and a **pluggable pair-training system**: any AI can
train a currency pair using only public data and the public engine, producing a single
`<symbol>.pairpack.json` file that the owner uploads on the site. Packs are validated
(schema, causality/no-leakage, reproducibility, sandboxed execution, backtest consistency)
before they can ever trade.

## Architecture

- **engine/** — `sentinel_engine`, a pip-installable Python package. Single source of truth
  for indicators, the strictly-causal feature DSL, the rule layer, model loaders
  (lightgbm_text / tree_json / logreg_json — never pickle), the sandboxed custom-code
  runner (empty env, no network, resource limits, fail-closed) and the decision pipeline.
  The SAME code is used by training AIs, the validator and the live bot.
- **bot/** — the live bot, running in GitHub Actions (`bot.yml`). ~3h50m self-chaining runs,
  state in D1 (never on the runner), lease + heartbeat, crash reconciliation by contract_id.
  **Default mode is DEMO.** Real trading requires an explicit owner switch on the site.
- **worker/** — Cloudflare Worker + D1: the middle layer between site and bot.
- **site/** — Cloudflare Pages control site (mobile-first, dark theme): dashboard, live
  charts, pairs/upload/rollback, risk, news, logger, trade history.
- **tools/validate_pack.py** — the pack validator (fast and full modes).
- **docs/PAIRPACK_SPEC.md** — the pack format. **TRAIN_PROMPT.md** — the credential-free
  prompt to hand any AI to train a new pair.

## Setup (owner)

1. Repo secrets (Settings → Secrets and variables → Actions):
   `GH_PAT`, `DERIV_BEARER_TOKEN`, `DERIV_APP_ID`, `BOT_SHARED_SECRET`, `WORKER_URL`.
2. Cloudflare: create the D1 database, deploy the Worker (`worker/`), set Worker secrets
   (`BOT_SHARED_SECRET`, `GH_PAT`), deploy the site (`site/`) to Pages.
3. Open the site on your phone, paste your GitHub PAT (stored only in browser
   localStorage), then save the Deriv token via the Settings page — it is written to the
   repo secret with libsodium sealed-box encryption and never stored in D1 or shown again.
4. Add pairs via the **Add / Update Pair** page. A pair's enable switch stays locked until
   its pack verdict is `pass` AND full validation passed.

## Risk controls

Kill switch; demo/real toggle (default demo); stake = balance × stake_pct clamped to
[min_stake, max_stake], min 0.35, rounded to 2dp; daily loss cap / profit target (manual or
auto from balance, reset at midnight Africa/Lagos); overall goal; per-pair risk from the
pack with owner overrides; news-aware gating; shadow mode for unproven packs; **no
martingale by default**.

## Honest expectations

Always-on bots on GitHub Actions free tiers may be flagged by GitHub's acceptable-use
policy — the self-chaining design includes backoff and the README documents a fallback
(external cron hitting `workflow_dispatch`). A pack that fails its out-of-sample backtest
is labelled `fail` and stays locked; that is the system working as intended.
