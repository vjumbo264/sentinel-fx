# SENTINEL-FX

Autonomous Deriv forex binary-trading bot with a mobile-first control site and a
pluggable, credential-free pair-training system.

## Plain-language summary
- **Control site (open on your phone):** https://sentinel-fx.pages.dev
  (Cloudflare Pages, auto-deploys on every push to `site/`).
- **Repo (public):** https://github.com/vjumbo264/sentinel-fx
- **Worker (API + D1 state):** https://sentinel-fx-worker.vjumbo264.workers.dev
- **First pair:** frxEURUSD pack v1 — verdict **fail** (trained on synthetic
  data purely as a pipeline proof; Deriv was unreachable from the training
  sandbox). Re-train with TRAIN_PROMPT.md on real data. It stays in SHADOW.

## Architecture
- **engine/** public pip package (single source of truth for indicators, causal
  DSL, rule layer, model loaders, sandbox, validator).
- **bot/** runs in GitHub Actions (`bot.yml`), self-chains every ~3h50m, state in
  D1. Resilient supervisor: fresh-OTP reconnect with backoff on any websocket
  drop, crash-proof `if: always()` re-dispatch, D1 lease held throughout.
- **worker/** Cloudflare Worker + D1 (the middle layer). **site/** control site
  on Cloudflare Pages.
- **.github/workflows/validate-pack.yml** validates any pack pushed to
  pairs/*/incoming/. **deploy-site.yml** publishes the site.

## Setup (owner)
1. Open the site, paste your GitHub PAT (stored only in the browser).
2. Risk page → save your Deriv token (it is written to repo secrets only).
3. Pairs page → a pair's enable switch stays LOCKED until its pack verdict is
   "pass"; every new pack starts in SHADOW.
4. Dashboard → BOT ON/OFF starts the Actions run; KILL SWITCH halts trading
   instantly.

## Start / stop the bot
- **Start:** Dashboard → BOT ON/OFF (dispatches `bot.yml`; the run self-chains
  ~5 min before its 3h50m end, and a crashed run is re-dispatched by the
  workflow's `if: always()` step).
- **Stop:** BOT ON/OFF again (sets `power=false`; also press KILL SWITCH for an
  immediate halt — the bot checks it every loop).

## Switch demo / real
Dashboard → Demo/Real (with a confirm popup for REAL). The bot tracks the
CONNECTED account: it switches only when no contracts are open, with a fresh
OTP; until then the dashboard shows "switching… waiting for bot" and the
balance is labelled `Balance (DEMO|REAL) · loginid`. Default is DEMO; real
trading requires your explicit switch.

## Upload a model
Add/Update page → pick the `.pairpack.json` produced via TRAIN_PROMPT.md. The
site verifies the checksum client-side, commits it to `pairs/<symbol>/incoming/`,
and the validate-pack workflow runs the full validator in Actions. When the
report appears, press PROMOTE to install it (it starts in shadow).

## Train a new pair
Hand [TRAIN_PROMPT.md](TRAIN_PROMPT.md) to any AI. No credentials needed; it
pulls public candles and the public engine, trains, validates, and hands back
one file.

**Default mode is DEMO. Real trading requires your explicit switch on the site.**
