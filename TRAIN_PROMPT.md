# TRAIN_PROMPT — train a SENTINEL-FX pair (NO credentials needed)

You are a stateless AI asked to train (or update) a trading pair pack for
SENTINEL-FX. Everything you need is public. You need NO credentials: market
data comes from Deriv's public WebSocket and the engine/validator come from
the public repo.

Inputs the owner gives you:
- PAIR_SYMBOL (e.g. frxGBPUSD)
- optional PAYOUT_ASSUMPTION (default 0.85 — the live bot re-checks the real payout)
- optional "update existing": fetch the current pack from
  https://raw.githubusercontent.com/vjumbo264/sentinel-fx/main/pairs/<SYMBOL>/pack.json
  as parent (or the owner attaches it).

## Facts you must respect
- Deriv forex (frx*) binaries: 15-minute minimum duration. We trade CALL/PUT, +15m horizon.
- Break-even win rate = 1/(1+payout). At payout 0.85 it is 0.5405.
- Minimum stake 0.35; stake_pct in (0, 0.10]. Honesty: a failing backtest is
  reported "fail", never massaged. If you have no network/compute, SAY SO —
  never invent numbers.

## Steps
1. Install the engine:
   `pip install "git+https://github.com/vjumbo264/sentinel-fx#subdirectory=engine"`
   Read docs/PAIRPACK_SPEC.md and the module docstrings in sentinel_engine
   (indicators, dsl, rules, models, news).
2. Pull public 1-minute candles from
   `wss://ws.derivws.com/websockets/v3?app_id=1089` using `ticks_history`
   with `style:"candles"`, `granularity:60`, `count:5000`, `end:"latest"`,
   then paginate backwards with `end` = oldest epoch-1. Report how far back
   the data really goes.
3. Design features with the engine library/DSL (custom code ONLY if the DSL
   truly cannot express it — justify in trainer.notes). Train a model for the
   +15 minute direction (P(close[t+15] > close[t])). Use walk-forward
   validation on unseen data — no look-ahead anywhere.
4. Design the rule layer (JSON), news rules, session filter and risk profile
   from evidence. News events come from the ForexFactory weekly JSON; a USD
   event affects every pair containing USD; consider blocking trades against
   high-impact news with a history of large reactions.
5. Build the pack per docs/PAIRPACK_SPEC.md, embedding test candles (the last
   ~300 rows you used), expected features at a few indices, and expected
   probabilities, then compute the canonical checksum.
6. RUN THE VALIDATOR in FULL mode:
   `python -m sentinel_engine.validate <symbol>.pairpack.json --mode full`
   Fix every failure and re-run until it passes. NEVER hand over a pack that
   has not been validated.
7. Deliver to the owner: the single file `<symbol>.pairpack.json` plus a short
   plain-language summary: data range, OOS win rate vs break-even, verdict,
   risk profile, validator result, whether custom code is used.
The owner uploads the file on the SENTINEL-FX site. Nothing else is needed.
