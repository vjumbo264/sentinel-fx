# SENTINEL-FX

Autonomous Deriv forex binary-trading bot with a mobile-first Cloudflare control site and a
pluggable, credential-free pair-training system.

- **Repo (public):** this repo — engine, bot, worker, site, validator, docs.
- **Engine:** `pip install "git+https://github.com/vjumbo264/sentinel-fx#subdirectory=engine"`
- **Train a pair:** hand [TRAIN_PROMPT.md](TRAIN_PROMPT.md) to any AI. No credentials needed.
- **Pack spec:** [docs/PAIRPACK_SPEC.md](docs/PAIRPACK_SPEC.md)
- **Architecture:** GitHub Actions runs the bot; Cloudflare Worker + D1 is the state/API layer;
  Cloudflare Pages hosts the control site.

> Build in progress — see BUILD_STATE.json. Setup instructions will be finalized when the build completes.
> Default account mode is DEMO. Real trading requires an explicit owner switch on the site.
