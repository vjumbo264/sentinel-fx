# TRAIN_PROMPT v3 — Train a per-pair SENTINEL-FX MT5 CFD Model

You are a stateless AI tasked with training (or updating) an autonomous trading model for one SENTINEL-FX pair. You need NO credentials for training. The owner may optionally append a PUBLISH ACCESS block at the end (only then do you also publish).

Inputs: `PAIR_SYMBOL` (e.g. `EURUSD`, `GBPUSD`, `USDJPY`, `Volatility 10 Index`), target specs from `data/symbols.json`, and whether this is a new model or an update to `v<N>`.

---

## 1. THE VISION & SINGLE PURPOSE
**THE SINGLE PURPOSE OF EVERY MODEL IS TO GROW THE BALANCE IT IS GIVEN.**
Not to maximize win rate or trade frequency. If no edge exists, the model stands down (`HOLD` / `STAY_OUT`).

The model behaves like a professional CFD trader:
- **Multiple Timeframes:** Entry timeframe (e.g., M1/M5) informed by higher timeframe structure (M15, H1, H4, D1).
- **Indicators chosen for that specific pair:** Trend, momentum, volatility (ATR/Bollinger), support/resistance levels, order flow confluence.
- **News Confluence:** Economic calendar awareness (high-impact events, rate decisions, NFP, CPI) from `news_archive.jsonl.gz`.
- **Full Execution Liberty:** The model may open and monitor several concurrent positions, scale in and out, place multiple take profits, trail stops, move stops to break-even, cut trades early, or stand down.
- **STRICT SAFETY RULE:** Every position opened by the bot MUST carry a server-side Stop Loss (the model chooses where; `sl > 0` or `sl_dist_points > 0`) so capital protection NEVER depends on a runner being alive.

---

## 2. FACTS & SYSTEM CONSTRAINTS
- **Platform:** MetaTrader 5 (MT5) CFD via Python broker layer (`bot/mt5_broker.py`).
- **Account Margin Mode:** Retail Hedging (`ACCOUNT_MARGIN_MODE_RETAIL_HEDGING`) allowing concurrent long and short positions per symbol.
- **Owner Overrides:** Outside the model, the owner may set max total exposure, daily TP/SL, or repeat daily. Default is OFF.
- **Honesty Clause:** A failing backtest is verdict "fail", never massaged. If you lack data or compute for a proper run, state so honestly — never invent backtest numbers.

---

## 3. PLAYBOOK WORKFLOW

### Step 1: Get Historical Data & Symbols Registry
1. Read `data/symbols.json` for exact symbol specs: `digits`, `point`, `contract_size`, `volume_min`, `volume_step`, `stops_level`, `swap_long`, `swap_short`.
2. Read `data/index.json` or download historical 1-minute OHLCV candles:
   `https://raw.githubusercontent.com/vjumbo264/sentinel-fx/main/data/index.json`
3. Download the news archive:
   `https://github.com/vjumbo264/sentinel-fx/releases/download/news-archive/news_archive.jsonl.gz`

### Step 2: Install Engine & Read Documentation
```bash
pip install "git+https://github.com/vjumbo264/sentinel-fx#subdirectory=engine"
```
Read `docs/` for bundle specification and simulator documentation.

### Step 3: Design the Trader's Mind (Hybrid Committee)
- **Feature Pipeline:** Multi-timeframe trend indicators, volatility regimes (ATR, realized volatility), session clocks (London, NY, Tokyo), and news proximity.
- **Committee of Analysts:**
  - Structural / Trend Analyst
  - Momentum & Key Levels Analyst
  - Volatility & Regime Analyst
  - News Impact & Risk Analyst
- **Risk Brain & Sizing:** Calculates position volume scaled to account equity, ATR volatility, and confluence confidence, clamped to `volume_min` and `volume_step`.
- **Position Manager:** Evaluates ongoing positions on each bar to adjust trailing stop, move to break-even, scale out, or hold.

### Step 4: Export to Data Formats (Zero-Exploration)
- Permitted formats: ONNX (`.onnx`), LightGBM text (`.txt`), XGBoost JSON (`.json`), declarative JSON (`analysis_plan.json`, `policy.json`, `risk_brain.json`, `manifest.json`).
- **STRICT PROHIBITION:** NO Python pickle (`.pkl`), joblib, or PyTorch serialized weights.

### Step 5: Bundle Assembly
Assemble `<symbol>_v<N>.sfxmodel.zip` containing:
- `manifest.json` (schema_version 2, sha256 + size of every enclosed file)
- `analysis_plan.json` (declarative execution DAG)
- `policy.json` or `decision.json` (decision mapping logic)
- `risk_brain.json` (sizing, mandatory SL logic, trailing stops)
- `news_layer.json` (currency news filters)
- `training_report.json` (data coverage, train/validation/holdout split, compounding growth multiple, max drawdown, 95% block-bootstrap growth CI, cost sensitivity)

### Step 6: Verify and Validate
Run the health and contract checker:
```bash
python3 -m sentinel_engine.check <bundle>.sfxmodel.zip
```
Run the compounding balance simulator:
```bash
python3 -m sentinel_engine.sim <bundle>.sfxmodel.zip
```
Ensure all checks pass with zero fatal problems.

### Step 7: Delivery
- **Manual Route:** Provide the `.sfxmodel.zip` along with the plain-language executive summary for upload via the web dashboard.
- **Publish Route (if PAT provided):** Run:
  ```bash
  python3 tools/publish_model.py <bundle>.sfxmodel.zip --symbol <SYMBOL> --version <VERSION> --token <PAT>
  ```
