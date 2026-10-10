-- SENTINEL-FX D1 schema

CREATE TABLE IF NOT EXISTS settings (
  key TEXT PRIMARY KEY,
  value TEXT NOT NULL,
  updated_utc TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS pairs (
  symbol TEXT PRIMARY KEY,
  enabled INTEGER NOT NULL DEFAULT 0,
  shadow_mode INTEGER NOT NULL DEFAULT 1,
  status TEXT NOT NULL DEFAULT 'locked',
  min_stake REAL NOT NULL DEFAULT 0.35,
  max_stake REAL NOT NULL DEFAULT 10.0,
  stake_pct REAL NOT NULL DEFAULT 0.01,
  daily_loss_cap REAL,
  daily_target REAL,
  max_consec_losses INTEGER NOT NULL DEFAULT 3,
  pack_version INTEGER NOT NULL DEFAULT 0,
  verdict TEXT,
  has_custom_code INTEGER NOT NULL DEFAULT 0,
  updated_utc TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS pair_packs (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  symbol TEXT NOT NULL,
  version INTEGER NOT NULL,
  sha256 TEXT,
  status TEXT NOT NULL,              -- incoming|validating|validated|rejected|active|retired
  has_custom_code INTEGER NOT NULL DEFAULT 0,
  verdict TEXT,
  metrics TEXT,                       -- json
  validation_report TEXT,             -- json
  installed_utc TEXT,
  created_utc TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS trades (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  contract_id TEXT UNIQUE,
  pair TEXT NOT NULL,
  side TEXT NOT NULL,
  stake REAL NOT NULL,
  payout REAL,
  open_utc TEXT,
  close_utc TEXT,
  result TEXT,
  pnl REAL DEFAULT 0,
  mode TEXT NOT NULL DEFAULT 'demo',
  model_prob REAL,
  news_flag TEXT,
  reason TEXT
);
CREATE INDEX IF NOT EXISTS idx_trades_pair ON trades(pair, open_utc);

CREATE TABLE IF NOT EXISTS shadow_signals (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  pair TEXT NOT NULL,
  side TEXT NOT NULL,
  stake REAL,
  open_utc TEXT NOT NULL,
  close_utc TEXT,
  entry_price REAL,
  exit_price REAL,
  result TEXT,
  pnl REAL DEFAULT 0,
  model_prob REAL,
  reason TEXT
);
CREATE INDEX IF NOT EXISTS idx_shadow_pair ON shadow_signals(pair, open_utc);

CREATE TABLE IF NOT EXISTS logs (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  ts TEXT NOT NULL,
  level TEXT NOT NULL,
  pair TEXT,
  message TEXT NOT NULL,
  data TEXT
);
CREATE INDEX IF NOT EXISTS idx_logs_ts ON logs(ts DESC);

CREATE TABLE IF NOT EXISTS news_events (
  id TEXT PRIMARY KEY,
  utc_time TEXT NOT NULL,
  currency TEXT NOT NULL,
  title TEXT NOT NULL,
  impact TEXT,
  forecast TEXT,
  previous TEXT,
  affected_pairs TEXT                  -- json array
);
CREATE INDEX IF NOT EXISTS idx_news_time ON news_events(utc_time);

CREATE TABLE IF NOT EXISTS news_reactions (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  event_key TEXT NOT NULL,
  pair TEXT NOT NULL,
  move_5m REAL,
  move_15m REAL,
  recorded_utc TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS daily_stats (
  lagos_date TEXT NOT NULL,
  pnl REAL NOT NULL DEFAULT 0,
  trades INTEGER NOT NULL DEFAULT 0,
  wins INTEGER NOT NULL DEFAULT 0,
  PRIMARY KEY (lagos_date)
);

CREATE TABLE IF NOT EXISTS heartbeat (
  id INTEGER PRIMARY KEY CHECK (id = 1),
  ts TEXT NOT NULL,
  mode TEXT,
  balance REAL,
  note TEXT
);

CREATE TABLE IF NOT EXISTS run_lock (
  id INTEGER PRIMARY KEY CHECK (id = 1),
  owner TEXT,
  lease_until TEXT,
  updated_utc TEXT
);
