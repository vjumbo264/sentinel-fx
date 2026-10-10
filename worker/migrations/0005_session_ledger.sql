-- SESSION: per-model bankroll ledger + owner overrides
CREATE TABLE IF NOT EXISTS session (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  started_utc TEXT NOT NULL,
  mode TEXT NOT NULL DEFAULT 'demo',
  starting_balance REAL NOT NULL DEFAULT 0,
  note TEXT
);
CREATE TABLE IF NOT EXISTS model_ledger (
  symbol TEXT PRIMARY KEY,
  allocated REAL NOT NULL DEFAULT 0,
  balance REAL NOT NULL DEFAULT 0,
  active INTEGER NOT NULL DEFAULT 1,
  updated_utc TEXT
);
CREATE TABLE IF NOT EXISTS overrides (
  symbol TEXT PRIMARY KEY,
  action TEXT NOT NULL,
  updated_utc TEXT
);
CREATE TABLE IF NOT EXISTS ledger_events (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  ts TEXT NOT NULL,
  symbol TEXT,
  kind TEXT NOT NULL,
  amount REAL NOT NULL DEFAULT 0,
  note TEXT
);
CREATE INDEX IF NOT EXISTS idx_ledger_events_symbol ON ledger_events(symbol, ts);
