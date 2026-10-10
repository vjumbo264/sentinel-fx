# TRAIN A SENTINEL-FX PAIR — hand this whole file to any capable AI

You are training ONE forex pair for SENTINEL-FX. You need NO credentials: all market data
comes from Deriv's PUBLIC WebSocket, and the engine + validator come from the public repo.

## Inputs (the owner fills these in)
- PAIR_SYMBOL: `frxEURUSD`   <!-- owner edits -->
- PAYOUT_ASSUMPTION: 0.85    <!-- optional; the live bot re-checks the real payout anyway -->
- UPDATE_EXISTING: no        <!-- or: yes — fetch current pack from the public repo as parent -->

## Setup
```bash
pip install "git+https://github.com/vjumbo264/sentinel-fx#subdirectory=engine"
```
Read `docs/PAIRPACK_SPEC.md` in that repo (github.com/vjumbo264/sentinel-fx) and the
`SUPPORTED_OPS` list in `engine/sentinel_engine/dsl.py`.

## Steps
1. **Pull candles.** Public, no token: `wss://ws.derivws.com/websockets/v3?app_id=1089`,
   `ticks_history` with `style: "candles"`, `granularity: 60`, paginate backwards with
   `end`/`start` as far as Deriv allows. Report honestly how far back it really goes.
2. **Design features** with the engine library and DSL. The DSL is STRICTLY CAUSAL — no
   negative shifts, no centered windows, no whole-series stats. Use custom code ONLY if the
   DSL truly cannot express the logic, and justify it in `trainer.notes`.
3. **Train a model** for the +15 minute direction (binary up/down at horizon). Walk-forward
   validation on unseen data, no look-ahead. Break-even win rate = 1/(1+PAYOUT_ASSUMPTION)
   = ~0.5405 at 0.85. Export the model as `tree_json` or `logreg_json` (data-only; never pickle).
4. **Design the rule layer, news rules, session filter and risk profile** from the evidence
   (e.g. block when ranging with ADX<18; blackout ±N minutes around high-impact releases of
   either currency in the pair; stake_pct/daily caps conservative).
5. **Build the pack** per PAIRPACK_SPEC.md including embedded `tests` vectors (a slice of
   real candles + features/probs computed with the engine) and the canonical `checksum_sha256`.
6. **RUN THE VALIDATOR in full mode** and fix EVERY failure until it passes:
   `python -m sentinel_engine.validate <symbol>.pairpack.json --mode full`
   Never hand over a pack that has not passed.
7. **Honesty rule:** a failing backtest is labelled `"fail"`, never massaged. If you have no
   network or cannot compute, say so instead of inventing numbers.

## Deliverable back to the owner
- The single file `<symbol>.pairpack.json`
- A short plain-language summary: data range, OOS win rate vs break-even, verdict, risk
  profile, validator result, whether custom code is used.
The owner uploads it on the SENTINEL-FX site. Nothing else is needed.
