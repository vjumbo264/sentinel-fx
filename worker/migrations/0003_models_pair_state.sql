-- BOT/FWD: model registry, forward metrics and per-pair runtime state
CREATE TABLE IF NOT EXISTS models (
  symbol TEXT NOT NULL,
  version INTEGER NOT NULL,
  release_tag TEXT,
  asset TEXT,
  sha256 TEXT,
  verdict TEXT,
  trained_through_utc TEXT,
  status TEXT NOT NULL DEFAULT 'staged',   -- staged|validated|rejected|active|retired
  metrics TEXT,                             -- json
  shadow_signals INTEGER NOT NULL DEFAULT 0,
  created_utc TEXT NOT NULL,
  PRIMARY KEY (symbol, version)
);

CREATE TABLE IF NOT EXISTS pair_state (
  symbol TEXT PRIMARY KEY,
  state TEXT NOT NULL,                      -- json
  updated_utc TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS forward_metrics (
  symbol TEXT NOT NULL,
  version INTEGER NOT NULL,
  computed_utc TEXT NOT NULL,
  metrics TEXT NOT NULL,                    -- json
  PRIMARY KEY (symbol, version)
);
