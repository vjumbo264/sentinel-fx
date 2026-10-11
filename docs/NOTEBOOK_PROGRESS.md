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

## Session 2 — D tooling built
- dukascopy-backfill.yml: pair x month matrix (16 pairs, max-parallel 3, resumable cache).
- fetch_dukascopy_bi5.py hardened: Retry-After, 1.6s pacing, spread-profile-by-hour report,
  crossed-bid/ask count, real bid/ask O/H/L/C columns.
- indicator_lab.py + train_rl.py scaffolds added (T, R in progress); lab NaN-warmup bug fixed.
- Next: watch backfill + month runs, then full 16-pair backfill, then T parity test.

## Session 2 checkpoint (auto-save)
- Lab DSL length-mismatch fixed and verified (kept>0). Backfill dispatch hit 404 (workflow indexing lag) — retry is the exact next step in BUILD_STATE.json.

## Session 2 checkpoint
- Lab cost_vec off-by-one fixed. Backfill 38165565445 (EURUSD 2024, 12 months x3 parallel) RUNNING. forex-history 38164983264 FAILED - root-cause line being extracted. Exact next_step in BUILD_STATE.json.

## Session 2 — D root cause CONFIRMED
- forex-history failure = HTTP 503 storm from datafeed.dukascopy.com caused by SELF-INFLICTED parallelism (3 concurrent month jobs, rapid retries). Probe proved a single paced request decodes fine.
- FIX: backfill serialized (max-parallel 1), pause 2.5s, retries 10, base 4s. Lab off-by-one FIXED (kept=3, best=0.002219 verified).
- NEXT (exact, in BUILD_STATE.json): cancel throttled run, REDISPATCH serial backfill, then full 16-pair backfill, then item T parity test.

## Session 2 — end-of-turn checkpoint
- Serial backfill (38165717985) dispatched; lab green; state file holds the exact next command chain.

## Checkpoint: serial backfill healthy (1 running / 11 queued / 0 failed); next_step in BUILD_STATE.json.

## Session 3 — started 2026-10-11, resuming at D (Section 1b candle fix)
- Cancelled stale hourly-tick run 38165717985 per Section 1b instructions (hourly ticks 503-throttled at scale).
- Dispatched updated probe-dukascopy.yml to test 2-request/day prebuilt candle files (BID_candles_min_1.bi5, ASK_candles_min_1.bi5) across multiple dates and headers, testing LZMA decompress and struct unpacking.
- Next: read probe logs, verify candle decoder output, then update data pipeline to use candle files (or fallback route per section 1b).
