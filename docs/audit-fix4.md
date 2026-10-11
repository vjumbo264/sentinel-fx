# SENTINEL-FX — FIX4 Honesty Audit (docs/audit-fix4.md)
Date: 2026-10-11 UTC. All statuses verified against live GitHub Actions logs.

| Step | Claimed | Actually verified | Evidence | Remaining gap |
|---|---|---|---|---|
| SPIKE | done | PARTIAL — login & symbols proven; ALL order ops retcode=None, 0 deals | run 38129230441 log: `NameError: MetaTrader5 is not defined` on every order_send/order_check | re-run spike after eval-namespace fix |
| RESETDATA | done | plausible (index reset history) | data/index.json history | — |
| SYMBOLS | done | plausible | data/symbols.json | — |
| DATA | done | Synthetics PROVEN; forex NOT | run 38128792662 R_10 525798 rows OK | Dukascopy frxEURUSD run pending |
| MT5LAYER | done | UNVERIFIED — unit tests are mocks | tests/test_mt5_broker.py (mocks) | real bridge order proof (G2) |
| HANDOFF | done | UNVERIFIED on Actions | docs/handoff_test_report.json only | second-terminal lease test pending |
| BUYTEST | done | FAILED — retcode=None both symbols | docs/cfd_trade_test_report.json (run 38129230441) | re-run after fix |
| SIM | done | engine-local, plausible | tests/test_cfd_sim.py | — |
| MODEL | done | engine-local, plausible | fixtures + validate tests | — |
| PUBLISH | done | unverified this pass | — | dispatch publish-model |
| TRAINUI | done | unverified this pass | — | site check |
| SESSION | done | UNVERIFIED bot reads pool live | — | live bot run |
| BOT | done | FAILED (E1 originally); stack login now proven, loop not yet | run 38129230441 stack OK | 10-min heartbeat run pending |
| SITE | done | unverified this pass | — | — |
| NEWS | done | engine-local tests pass | tests/test_news.py | — |
| TRAINPROMPT | done | doc exists | TRAIN_PROMPT.md | — |
| PROVE | done | REVOKED — no real order ever placed | mt5-spike.md shows retcode None / deal 0 / 0 history deals | full re-proof pending |

Root cause fixed in fix4: RPyC `conn.eval("MetaTrader5.order_send(...)")` needed a remote
`import MetaTrader5` first; without it every order returned retcode=None. Fixed in
bot/mt5_broker.py and tools/mt5_spike.py.
