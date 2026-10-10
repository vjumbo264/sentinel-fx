CREATE TABLE IF NOT EXISTS settings (key TEXT PRIMARY KEY, value TEXT);
CREATE TABLE IF NOT EXISTS pairs (symbol TEXT PRIMARY KEY, enabled INTEGER DEFAULT 0,
  shadow_mode INTEGER DEFAULT 1, status TEXT DEFAULT 'locked', min_stake REAL DEFAULT 0.35,
  max_stake REAL DEFAULT 5.0, stake_pct REAL, pack_version INTEGER DEFAULT 0);
CREATE TABLE IF NOT EXISTS pair_packs (symbol TEXT, version INTEGER, sha256 TEXT,
  status TEXT CHECK(status IN ('incoming','validating','validated','rejected','active','retired')),
  has_custom_code INTEGER DEFAULT 0, verdict TEXT, metrics TEXT, validation_report TEXT,
  installed_utc TEXT, PRIMARY KEY (symbol, version));
CREATE TABLE IF NOT EXISTS trades (contract_id TEXT PRIMARY KEY, pair TEXT, side TEXT,
  stake REAL, payout REAL, open_utc TEXT, close_utc TEXT, result TEXT, pnl REAL,
  mode TEXT, model_prob REAL, news_flag TEXT, reason TEXT);
CREATE TABLE IF NOT EXISTS shadow_signals (id INTEGER PRIMARY KEY AUTOINCREMENT, pair TEXT,
  side TEXT, prob REAL, open_utc TEXT, close_utc TEXT, virtual_result TEXT, virtual_pnl REAL);
CREATE TABLE IF NOT EXISTS logs (id INTEGER PRIMARY KEY AUTOINCREMENT, ts TEXT, level TEXT,
  pair TEXT, message TEXT, data TEXT);
CREATE TABLE IF NOT EXISTS news_events (id TEXT PRIMARY KEY, utc_time INTEGER, currency TEXT,
  title TEXT, impact TEXT, forecast TEXT, previous TEXT, affected_pairs TEXT);
CREATE TABLE IF NOT EXISTS news_reactions (event_key TEXT, pair TEXT, move_pips_5m REAL,
  move_pips_15m REAL, PRIMARY KEY (event_key, pair));
CREATE TABLE IF NOT EXISTS daily_stats (lagos_date TEXT PRIMARY KEY, pnl REAL DEFAULT 0,
  trades INTEGER DEFAULT 0, wins INTEGER DEFAULT 0);
CREATE TABLE IF NOT EXISTS heartbeat (owner TEXT PRIMARY KEY, ts INTEGER);
CREATE TABLE IF NOT EXISTS run_lock (id INTEGER PRIMARY KEY CHECK(id=1), owner TEXT, expires_at INTEGER);
