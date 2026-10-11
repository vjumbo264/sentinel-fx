# Notebook Mission Progress (plain words; mirrors BUILD_STATE.json "notebook")

## Session 1 — started 2026-10-11
**Resuming at: D (Dukascopy data hub).**

### Done
- Session started; state file "notebook" section created (all items todo). Verified prior state:
  site login/UI/Risk done, MT5 demo login works on Actions, real demo orders on Volatility 10 exist
  (retcode 10009), but CFD lifecycle report still "pending" overall; frxEURUSD history is only the
  ~100k-row MT5 fallback, not Dukascopy years; no RL trainer / indicator lab / notebook / Gradio UI exist.

### In progress
- D: Dukascopy data hub — proving runner reachability first.

### Next
- Probe Dukascopy from Actions (dispatch workflow, read logs); harden tools/fetch_dukascopy_bi5.py.

### Problems
- None new yet.
