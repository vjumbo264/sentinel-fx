# SENTINEL-FX

Autonomous Deriv forex binary-trading bot with a mobile-first control site and a
pluggable, credential-free pair-training system.

## Plain-language summary
- **Control site (open on your phone):** https://vjumbo264.github.io/sentinel-fx/site/
  (GitHub Pages; Cloudflare token lacked Pages scope, so GitHub Pages is the host.)
- **Repo (public):** https://github.com/vjumbo264/sentinel-fx
- **Worker (API + D1 state):** https://sentinel-fx-worker.vjumbo264.workers.dev
- **First pair:** frxEURUSD pack v1 — walk-forward win rate
  **')**
  vs break-even **54.05%** → verdict **fail**.
  NOTE: trained on synthetic data (Deriv public WS was unreachable from the training
  sandbox) purely to prove the pipeline. Re-train with TRAIN_PROMPT.md for real data.

## Architecture
- **engine/** public pip package (single source of truth for indicators, causal DSL,
  rule layer, model loaders, sandbox, validator).
- **bot/** runs in GitHub Actions (`bot.yml`), self-chains every ~3h50m, state in D1.
- **worker/** Cloudflare Worker + D1 (the middle layer). **site/** control site.
- **.github/workflows/validate-pack.yml** validates any pack pushed to pairs/*/incoming/.

## Setup (owner)
1. Open the site, paste your GitHub PAT (stored only in the browser).
2. Risk page → save your Deriv token (it is written to repo secrets only).
3. Pairs page → a pair's enable switch stays LOCKED until its pack verdict is "pass".
4. Dashboard → BOT ON/OFF starts the Actions run; KILL SWITCH halts trading instantly.
5. Add/Update page → upload a `.pairpack.json` produced via TRAIN_PROMPT.md.

## Train a new pair
Hand [TRAIN_PROMPT.md](TRAIN_PROMPT.md) to any AI. No credentials needed; it pulls
public candles and the public engine, trains, validates, and hands back one file.

**Default mode is DEMO. Real trading requires your explicit switch on the site.**
