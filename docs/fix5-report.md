# Fix5 acceptance report — INCOMPLETE

This is a partial completion report, **not** a claim that Fix Mission 5 passed. FAIL below means the acceptance test is either known failing or has not been demonstrated; the reason distinguishes them. No owner-side blocker has been established. Unfinished engineering/testing is not labelled blocked.

## Test results

| Test | Result | Evidence / missing requirement |
|---|---|---|
| V1 | FAIL — not freshly verified | Existing375px screenshots retained, but fresh save/toggle/reload browser suite not rerun. |
| V2 | FAIL — evidence incomplete | Inherited test uses mock broker, not actual demo synthetic trades; actual ON/OFF levels and day reset not proved. |
| V3 | FAIL — evidence incomplete | Live original chain stopped; current state has no checkpoint_history. No fresh live displayed/hand ETA comparison. |
| V4 | FAIL | Original EURUSD run failed with invalid volatility.900,000-step checkpoint preserved; no fresh new-evaluation resume/best-release short CPU acceptance. |
| V5 | FAIL | Real native correct-password test failed IPC timeout: [39985636231](https://github.com/vjumbo264/sentinel-fx/actions/runs/39985636231). All five correct secrets restored. No secret matches in scoped audit; password absent from API. Wrong/correct broker acceptance still missing. |
| V6 | FAIL — evidence incomplete | No fresh actual closed-session broker/synthetic proof; inherited evidence is mocked. |
| V7 | PASS | [39986703235](https://github.com/vjumbo264/sentinel-fx/actions/runs/39986703235): green, 59 actual demo heartbeats, elapsed 2–657s; Worker snapshots in docs/evidence/h6_heartbeat.json; no FAIL CLOSED or assertion; no cancellation. |
| V8 | FAIL — not completed | No actual bot/training cancellation/recovery/adoption demonstration. Watcher is staged, explicitly disabled pending atomic Worker routes. |
| V9 | FAIL — not completed | Both train.yml cron entries still remain. Update-training semantics and safe training-lock integration not implemented/verified in this session. |
| V10 | FAIL — not completed | Weekly authenticated Deriv append/seam run and schedule cleanup have not been implemented or verified in this session. |
| V11 | FAIL — integration incomplete | Six pure recovery decision regressions pass, including 30m/2h/6h and code halt after 3; actual recovery integration/cancellation evidence missing. |
| V12 | FAIL — full suite not rerun | 12 local authored regressions pass; actual ONNX 47 input rejected by real sfx CLI (exit1, expected62), forged metadata rejected, 62 shape accepted. These do not substitute for the required full fresh live suite. |

## Changes actually delivered
- H6: restored the known-green Linux MT5 runtime after two native Windows verification runs still failed IPC; preserved READY handover, per-run concurrency, lease and 4h backup cron. Bounded chain=false acceptance exits normally after its requested wall time. Workflow account mode cannot silently change to real. Added explicit login-report User-Agent after a real probe proved Cloudflare1010/HTTP403 for default urllib andHTTP200 for the explicit agent.
- H7: centralized 62-dimensional observation contract; actual policy ONNX shape and metadata checked before inference; sfx/bot/shared simulation reject retired inputs; added authenticated model registry endpoint and retired label using existing UI styling; exporter/registry carry compatibility metadata; operational documentation added.
- H8 partial: bounded transport retry helper and recovery/watchdog logic plus pure decision tests are committed. **Not wired to any schedule.** Missing atomic Worker record/claim routes and real recovery acceptance; explicit activation guard prevents premature use.

## Actual failed-action root cause
Latest original failed bot run [39983309547](https://github.com/vjumbo264/sentinel-fx/actions/runs/39983309547) failed before establishing native MT5 IPC:
```text
2026-10-23T16:05:47.8206445Z 2026-10-23 16:05:47,819 [WARNING] sentinel.broker: initialize attempt 3 returned False (last_err: (-10005, 'IPC timeout'))
2026-10-23T16:05:53.8227685Z AssertionError: demo login failed
```
Full exact original lines and all 40 audited run URLs are in FIX5_PROGRESS.md. Separate older failures were the Windows-incompatible `resource` import and inline safety-dispatch `IndentationError: unexpected indent`. No evidence supports blaming owner cancellation or concurrency cancellation for these runs. The corrective green demo run is39986703235, not an old pre-fix success.

## Training/account integrity
- Original [EURUSD run39929904179](https://github.com/vjumbo264/sentinel-fx/actions/runs/39929904179) was already completed/failure, not actively running when this session inspected it. It failed during evaluation with `ValueError: invalid volatility`.
- training_state.json is unchanged from starting commitc43649f: EURUSD v1,900,000 steps, durable asset EURUSD_v1_s900000.zip, recorded digest preserved. Training was not reset, cancelled or restarted by this session. It is **not currently resumed**.
- Final mode remains **demo**. The bounded verification ended normally; no model was enabled, so V7 proves actual broker connectivity/supervision, not trading or adoption.
- Scoped exact-value scan found zero supplied PAT/password/Cloudflare-token matches in 205 tracked files, 96 retrieved Actions log files and four live API responses. This is not an audit of every historical git object or every unavailable log. Correct credential secrets restored; API password absent.

## Resume order
Unsupported inherited H1–H5 PASS claims have been reopened, with prior evidence retained. Resume H1 actual live/demo acceptance, then H2–H5. H6/H7 have fresh evidence. Complete staged H8 and H9, then H10, then the entire V1–V12 suite from scratch. Do not mark passing from pure/mock tests for broker/Worker/Actions/site requirements.

## Owner-side blockers
None established. No owner action is requested; the mission is unfinished, not owner-blocked.
