# Notebook Mission Progress (plain words; mirrors BUILD_STATE.json "notebook")

## Session 1 — started 2026-10-11
**Resuming at: D (Dukascopy data hub).**

### Done
- Session started; state file "notebook" section created (all items todo). Verified prior state:
  site login/UI/Risk done, MT5 demo login works on Actions, real demo orders on Volatility 10 exist
  (retcode 10009), but CFD lifecycle report still "pending" overall; frxEURUSD history is only the
  ~100k-row MT5 fallback, not Dukascopy years; no RL trainer / indicator lab / notebook / Gradio UI exist.

### In progress
- D: probe attempt 1 FAILED — datafeed.dukascopy.com TCP-unreachable from Actions runner
  (curl 28 timeout, run 38163818415). Probe workflow bug found: first curl failure kills the job.

### Next
- Fix probe workflow (|| true, 60s timeout, add freeserv.dukascopy.com mirror), redispatch = attempt 2/5.

### Problems
- None new yet.
