# Pair Pack Specification (schema_version 1)

A pack is ONE JSON file `<symbol>.pairpack.json`. It holds data AND optional code as
embedded, hashed strings. Target size < ~20MB (gzip+base64 blobs). Extendable, backward
compatible: unknown top-level fields are ignored by older engines.

| field | notes |
|---|---|
| `schema_version` | integer, currently 1 |
| `symbol` | `^frx[A-Z]{6}$`, e.g. `frxEURUSD` |
| `pack_version` / `parent_version` | integer, increases per update / previous version or null |
| `min_engine_version` | semver; engine must be >= this |
| `features.dsl` | causal JSON expression graph (see engine `SUPPORTED_OPS`) |
| `features.custom_modules` | `[{name, sha256, code_b64gz}]`; `code_b64gz` = base64(gzip(python source)) |
| `model` | `type`: `lightgbm_text` / `tree_json` / `logreg_json` (never pickle); `encoding`: `utf8` or `base64-gzip`; `input_features` must match feature names |
| `rules` | rule tree: `{"tree": {"if": {field, op, value}, "then": {...}, "else": {...}}}`; leaf = `{action: allow|block|adjust_confidence, reason, delta?}` |
| `decision` | `horizon_min: 15`, `payout_assumed` (default 0.85; live payout re-checked), `margin`, `cooldown_min` |
| `risk` | `stake_pct`, `max_stake_suggested`, `daily_loss_pct`, `daily_target_pct`, `max_consecutive_losses`, `loss_cooldown_min` |
| `sessions.allowed_utc_hours` | list of UTC hours 0-23, empty = all |
| `news_rules` | `block_if_against`, `against_extra_margin`, `blackout_minutes_before/after`, `reaction_threshold_pips` |
| `backtest` | walk-forward results; `verdict` pass requires OOS win rate > break-even `1/(1+payout)` by margin and >= 100 OOS trades |
| `tests` | embedded `candles_b64gz`, `check_indices`, `expected_features`, `expected_probs`, `tolerance` — used by validator checks 4-6 |
| `checksum_sha256` | sha256 of canonical JSON (sorted keys, `(",", ":")` separators, UTF-8) with this field removed |

Verdict honesty: a failing backtest is `fail`, never massaged. The validator exits
non-zero on any failed check.
