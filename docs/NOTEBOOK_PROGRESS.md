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

## End of session 1 (2026-10-11)
- **Done**: state section created; PAT verified (API+push); probe workflow bug fixed (bash -e kill, 60s timeout, freeserv mirror added).
- **In progress**: D attempt 2/5 dispatched — run pending; read its logs first next session.
- **Next exact step**: fetch logs of the attempt-2 probe run; then attempts 3-5 per BUILD_STATE.json next_step.
- **Not started**: T, S, A, R, N, P, W, E2E and tests T1-T11.

## Session 1 — D foundation PROVEN (2026-10-11 18:35 UTC)
- **Attempt 2 result (run 38163977306, SUCCESS)**: Dukascopy is reachable AND decodable from Actions
  runners. A real EURUSD hour (2026-09-09 10h) downloaded 15,147 bytes and LZMA-decoded to
  62,640 bytes = 3,132 valid tick records. Attempt-1's TCP timeout was transient filtering.
- **Real constraint**: throttling — 429s under rapid curl bursts, occasional 503. The pipeline stays
  serial with backoff; pacing needs increasing (pause ~1.5-2s, honor Retry-After).
- **freeserv mirror**: the /2.0/datafeed/ path form 404s; not needed since primary host works.
- **Next exact step**: tune fetch_dukascopy_bi5.py pacing, then run forex-history.yml for one real
  month of EURUSD as decode-at-scale proof, then extend to the full Deriv+Dukascopy pair list.

## Session 2 — started 2026-10-11, resuming at D
- Pacing fix committed: inter-request pause 0.25s -> 1.6s, Retry-After honored (up to 120s).
- Next exact step: watch the dispatched forex-history.yml run (EURUSD 2026-09 month), verify
  out/*.report.json artifact and the published release shard, then extend to the full pair matrix.
