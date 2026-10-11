# SENTINEL-FX UI API Map & Data Source Audit

Audited against `worker/src/index.js`, `bot/main.py`, `bot/mt5_broker.py`, `data/`, and the live Worker (`https://sentinel-fx-worker.vjumbo264.workers.dev`).

---

## 1. Authentication & Security
- **Mechanism**: Bearer token via `Authorization: Bearer <GITHUB_PAT>`.
- **Validation Endpoint**: `GET /api/auth/check`
  - **Success Response**: `{ ok: true, repo: "vjumbo264/sentinel-fx" }`
  - **Failure Response (401)**: `{ error: "unauthorized" }`
- **Storage**: In-memory and `localStorage.getItem("sentinel_pat")` wrapped in `try/catch`. Never logged, never printed, never displayed in cleartext.
- **Handling**: Any API 401/403 clears the active session and routes directly to the Login screen with an explicit error notification.

---

## 2. Page-by-Page Data Sources

### Page: Login (`#/login`)
| UI Element | Source Endpoint / Contract | Fallback / Empty State |
|---|---|---|
| PAT Token Input | User input | Masked password input |
| Auth Probe Result | `GET /api/auth/check` | "GitHub PAT validated with push permissions" / "Invalid or unauthorized PAT" |

### Page: Home / Dashboard (`#/dash`)
| UI Element | Source Endpoint / Field | Empty / Missing State |
|---|---|---|
| Account Balance | `GET /api/state` -> `heartbeat.balance` | If `null`, display `—` with "Awaiting runner update" (no fabricated $10,000.00) |
| Equity | Calculated: `balance + open_positions_pnl` | If balance is null, display `—` |
| Margin & Free Margin | Calculated from active open contracts | If 0 positions, display `0.00` and `—` |
| Today's P/L | `GET /api/state` -> `today.pnl` | `0.00` |
| Today's Trades & Wins | `GET /api/state` -> `today.trades`, `today.wins` | `0 trades` |
| Mode Pill | `GET /api/state` -> `settings.mode` or `heartbeat.mode` | Defaults to `demo` |
| Runner Status | `GET /api/state` -> `heartbeat.ts` (active if within 120s) | "Offline" or "Standby" |
| Runner Heartbeat Note | `GET /api/state` -> `heartbeat.note`, `loginid`, `currency` | Hidden if no heartbeat |
| Runner Handover Timer | Calculated from heartbeat ts (< 3h50m window) | Hidden if offline |
| Economic News Radar | `GET /api/news` -> `events` array | "No upcoming economic events in next 24h" |
| Quick Actions | `POST /api/account/reset-demo-balance` | Dispatched via shared sfxBusy helper |

### Page: Active Trades (`#/trades`)
| UI Element | Source Endpoint / Field | Empty / Missing State |
|---|---|---|
| Open Positions Desk | `GET /api/trades` filtered by `close_utc IS NULL` | "No open positions. The bot is currently flat." |
| Ticket / Symbol | `t.contract_id`, `t.pair` | — |
| Side & Lots | `t.side`, `t.stake` (volume) | — |
| Entry & Current Price | `t.open_price`, live candle close | — |
| SL / TP | `t.sl`, `t.tp` | "None" |
| Live P/L | `t.pnl` (or calculated from tick) | `0.00` |
| Strategy Reason | `t.reason` | "Automated execution" |
| Position Actions | Close / Close Half / Move SL to Break-Even | Action sheet modal with confirmation |

### Page: Trade History (`#/history`)
| UI Element | Source Endpoint / Field | Empty / Missing State |
|---|---|---|
| Closed Trade Journal | `GET /api/trades` filtered by `close_utc IS NOT NULL` | "No closed trades recorded in the database yet." |
| Summary Header | Computed strictly from real rows: Total, Net PnL, Win Rate %, Profit Factor | All zeros if 0 rows |
| Outcome Filters | Client-side filter (All, Wins, Losses) | — |
| CSV Export | Client-side export of displayed rows | Disabled if 0 rows |

### Page: Candlestick Chart (`#/chart`)
| UI Element | Source Endpoint / Field | Empty / Missing State |
|---|---|---|
| Candlesticks | `GET /api/candles?symbol=...&granularity=...&count=300` | 10s timeout, status line: Loading / Live / Market closed / Error with Retry |
| Pair List | Populated from `data/tracked_pairs.json` & `GET /api/state` | Dynamic select dropdown |
| Timeframes | `60` (M1), `300` (M5), `900` (M15), `3600` (H1), `86400` (D1) | Active chip |
| Open Trade Overlays | Positions from `store.positions` matching symbol | Horizontal lines on chart canvas |

### Page: Trained Models (`#/models`)
| UI Element | Source Endpoint / Field | Empty / Missing State |
|---|---|---|
| Installed Models | `GET /api/pairs` -> `models` & `packs` | "No models installed. Train or upload a model to deploy it." |
| Forward Eval Metrics | `GET /api/pairs` -> `forward` | "Pending forward-eval run" |
| Enable/Disable Toggle | `POST /api/pairs/update` | Confirmation modal |

### Page: Train Models (`#/train`)
| UI Element | Source Endpoint / Field | Empty / Missing State |
|---|---|---|
| Pair Selector | `data/tracked_pairs.json` & `data/symbols.json` | Dynamic list |
| Data Ready Status | `data/index.json` confirmation | "Data not downloaded: run candle fetch workflow" |
| Prompt Playbook | Generated from `TRAIN_PROMPT.md` specs | Disabled or warning until data confirmed |

### Page: Upload Bundle (`#/upload`)
| UI Element | Source Endpoint / Field | Empty / Missing State |
|---|---|---|
| Drag & Drop Area | Client file picker (`.sfxmodel.zip`) | File dropzone |
| Validation Report | Client-side zip inspection + manifest verify | Plain language status |
| Upload Action | `POST /api/upload/staging-asset?name=...` | Staging release asset |

### Page: Risk & Auth (`#/risk`)
| UI Element | Source Endpoint / Field | Empty / Missing State |
|---|---|---|
| Session Balance Pool | `GET /api/session` -> `session`, `ledger` | "No active compounding session" |
| Equal-Split Preview | Computed from active models & pool balance | — |
| Owner Overrides | `GET /api/session` -> `overrides` | Default OFF |
| Emergency Kill Switch | `POST /api/settings` `{ kill: true }` | Confirmation sheet |
| Real / Demo Switch | `POST /api/settings` `{ mode: 'real'|'demo' }` | Mandatory safety confirmation modal |

### Page: Settings (`#/settings`)
| UI Element | Source Endpoint / Field | Empty / Missing State |
|---|---|---|
| Theme Switcher | Local preference (`sentinel_theme`): Auto / Light / Dark | Auto (prefers-color-scheme) |
| Timezone | Display: Lagos (WAT, UTC+1) | Static display with live clock |
| API Diagnostics | `GET /api/health` -> latency ms + status | "Online / Offline" |
| Build Information | Stamped git commit hash / build ID | Real build ID |
| Logout Action | Clears token and reloads to `#/login` | — |

---

## 3. Data Gaps Identified & Transparent Handlers
1. **Runner Balance when offline**: The MT5 runner posts `balance` only while actively connected. When the runner is idle or between jobs, `heartbeat.balance` is `null`.
   - *Handler*: Display honest `—` with subtitle "Awaiting runner update".
2. **Candles endpoint connection**: `/api/candles` depends on outbound Deriv WebSocket upgrade in Cloudflare Workers. If Deriv returns closed market or socket failure, the endpoint returns HTTP 502 with `{ error, market_closed }`.
   - *Handler*: Display honest status banner with exact error message and an interactive "Retry" button. Never hang or fake candles.
3. **Empty Models Table**: Currently `models/index.json` and D1 `models` table have 0 rows.
   - *Handler*: Display honest empty card explaining that no models have been deployed yet.
