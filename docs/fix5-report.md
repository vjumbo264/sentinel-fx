# Fix5 acceptance report — INCOMPLETE

This mission is not complete. FAIL includes acceptance not yet demonstrated; it does not mean every implemented feature is broken. No owner-side blocker has been established. The required final fresh V1–V12 suite has not been run.

## Test results

| Test | Result | Evidence / remaining acceptance |
|---|---|---|
| V1 | FAIL — not rerun | No fresh 375px save/toggle/reload browser evidence. Existing screenshots are inherited, not new acceptance. |
| V2 | FAIL — unproved | Real demo synthetic OFF/ON stops, daily halt and day reset still need broker evidence; inherited tests are mocked. |
| V3 | FAIL — unproved | Chain is running again and one new checkpoint is in history. Displayed-versus-hand ETA and fresh measuring-state browser checks remain. Do not infer current throughput from the old 12.5-minute rate. |
| V4 | FAIL — partial progress | **Resume now proved:** actual [950000-producing run](https://github.com/vjumbo264/sentinel-fx/actions/runs/39992955869) and [patched active resume](https://github.com/vjumbo264/sentinel-fx/actions/runs/39997388327); embedded purged validation score -50.414696, verdict no_edge. Best-release short real CPU/gates acceptance still missing, so V4 is NOT passing. |
| V5 | FAIL — unproved | Wrong/correct-password real login flow is not completed. Do not use native Windows again; the previous IPC failure is already established. Supplied secrets have no matches in the scoped current scan. |
| V6 | FAIL — unproved | Real closed-session forex and synthetic behavior plus simulator acceptance remain. |
| V7 | PASS — retained prior evidence | [39986703235](https://github.com/vjumbo264/sentinel-fx/actions/runs/39986703235): green demo run, 59 heartbeats, elapsed 2–657s. Not rerun here, as instructed not to re-prove it; this is not the final fresh suite. |
| V8 | FAIL — unfinished | Actual bot/training API cancellation/recovery/adoption proof is not done. Prior watchdog remains staged and disabled; atomic Worker routes are absent. |
| V9 | FAIL — partial progress | Both train.yml crons removed. Live site now states manual-only starts and correctly says training does not pause trading. Owner update request queue, Update all, new-version warm-start integration and real update proof remain unfinished. |
| V10 | FAIL — not started | Weekly Deriv append, seam verification, immutable-base cleanup and real append run remain. H10 has not been skipped ahead of H9. |
| V11 | FAIL — integration unfinished | Existing pure retry/classification tests are not live recovery evidence. No scheduled recovery activation or real circuit-breaker acceptance yet. |
| V12 | FAIL — full suite not rerun | Six current local regressions PASS, including real sfx rejection of a 47-input model and forged metadata. This does not substitute for the full fresh live suite. |

## H0 completed: genuine checkpoint progression, not a mock

Original failure [39929904179](https://github.com/vjumbo264/sentinel-fx/actions/runs/39929904179) reached evaluation and raised at `sentinel_engine/observation.py`, `causal_market`, original line27:

```text
if atr<=0 or not math.isfinite(atr):raise ValueError('invalid volatility')
ValueError: invalid volatility
```

Replayed the original function on immutable release candles with the actual EURUSD_v1_s900000.zip. A flat fourteen-bar EURUSD window ending at epoch1626388800 reproduces the exception; USDCHF has the same issue at epoch1790548200. The inherited shared-observation floor already handles finite flat windows; that behavior was verified rather than falsely claimed as newly added. All13 pairs were probed using real release candles and actual checkpoint inference, returning finite62-dimensional observations.

New per-checkpoint evaluation uses three deterministic1024-bar validation windows, a2400-bar purge and2400-bar warmup. Invalid windows are logged/skipped, and skipped/error evaluations cannot become the best checkpoint. Insufficient data never borrows the locked holdout. Coverage is explicitly sampled validation, not the whole validation fold. Two local invalid-window regressions pass. Actual900000-checkpoint CPU validation on real2025 candles also passes evaluator execution with a poisoned, unread locked holdout; its profitability verdict is no_edge.

Actual run39992955869 trained from900000 to950000 and uploaded EURUSD_v1_s950000.zip. Its evaluation completed, but post-upload digest verification hit:

```text
urllib3.exceptions.ReadTimeoutError: HTTPSConnectionPool(host='release-assets.githubusercontent.com', port=443): Read timed out. (read timeout=180)
```

That run failed; it is not represented as green. Bounded retries now cover safe GitHub read/CAS transport timeouts and connection resets, without blindly repeating asset-creation POSTs. Restore now recovers an uploaded-but-unindexed archive's digest, steps, validation history and best metadata idempotently.

Patched run39997388327 restored the actual950000-step archive and committed remote status=training with last_error cleared. Recorded digest: `b52f8d5a5bf88870706168aae264b0702d4109ababf59e9ea652083a7d9e1c29`. The target remains5000000, version remains1, and no model was released or enabled. At the final verification the writer was in progress; do not cancel it or dispatch a duplicate.

Evidence: `docs/evidence/h0_original_failure.txt`, `h0_real_pair_probes.json`, `h0_real_validation_cpu.json`, `h0_actions950000.json`, and `h0_resumed_state.json`.

## H9 partial changes and exact next work

Removed both daily and Saturday schedules from `.github/workflows/train.yml`; single-writer concurrency and cancel-in-progress=false are unchanged. The current Worker training-lock endpoint only writes training_locked/training_lock_reason to D1. Current bot/main.py does not read that flag; it is not a live-trading interlock. Its use as a real duplicate-start guard still needs request integration.

Corrected false UI statements about pausing the bot and scheduled Saturday retraining. [Site deployment39998311804](https://github.com/vjumbo264/sentinel-fx/actions/runs/39998311804) is green. Actual deployed training.js HTTP200 contains the corrected text. No design/layout changes were made. This source-level live verification is not a rendered browser screenshot.

`tools/training_requests.py` is explicitly STAGED and unused. Do not activate it as-is. Finish Worker-authenticated durable owner request submission, single-writer request consumption, per-pair Update training and Update all; remove current invalid extra workflow inputs; implement native checkpoint provenance, isolated version counters, per-cycle frozen data bounds and no automatic new cycles. Preserve existing active_version until a new candidate passes and is selected through the owner enable flow. Current registry is empty, so no live update from a released model was proved.

## Failed bot action: retained established root cause

Original bot39983309547 failed before native MT5 IPC became ready:

```text
2026-10-23T16:05:47.8206445Z 2026-10-23 16:05:47,819 [WARNING] sentinel.broker: initialize attempt 3 returned False (last_err: (-10005, 'IPC timeout'))
2026-10-23T16:05:53.8227685Z AssertionError: demo login failed
```

The known-green Linux runtime remains in place. Older resource-import and inline IndentationError failures are documented in FIX5_PROGRESS.md. No new native-Windows test or speculative duplicate bot was started.

## Final safety and verification scope

Mode remains demo; no credentials were modified, no model was enabled, and no trading tests were performed on real. No active training run was cancelled or reset. Current exact-value scan:215 tracked files, two failure-log excerpts, live state API and deployed training.js; zero supplied PAT/password/Cloudflare-token matches. This is NOT a scan of every historical git object/log. Evidence is `docs/evidence/fix5_resume_final_checks.json`.

The specified /opt/pw-browsers/chromium binary is absent in this environment. No playwright install was run and no missing browser proof is claimed. This environment limitation is not labelled an owner-side blocker.

## Resume order and owner blockers

H0 is verified. Resume H9 at the exact BUILD_STATE.json fix5.next_step; then H10, H8, H1–H5 and the full V1–V12 suite from scratch. Existing H6/H7 evidence is preserved. No owner-side blocker has been established and no owner input is requested. This is an incomplete handover at the session limit, not a completed mission.
