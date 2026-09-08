# Deriv Terminal — Django Analysis Platform

Analysis-only trading dashboard for Deriv markets: live advanced charts +
an analysis window that scans **every** Deriv market with the ML ensemble
ported from `bot.py`, and tracks the resulting signals as **paper
positions**. Nothing in this project places a real order — there is no
broker execution code anywhere.

## What's ported from bot.py / email_alerts.py

| Original | Here |
|---|---|
| `DerivAPI` class | `analysis/services/deriv_client.py` (`DerivFeed`, multi-symbol, persistent) |
| `AVAILABLE_MARKETS`, `format_deriv_symbol`, `get_market_type` | `markets/catalog.py` |
| `add_technical_indicators`, `calculate_rsi/macd/bollinger/atr/stochastic` | `analysis/services/indicators.py` |
| `build_pipeline`, `build_tf_model`, `train_model` | `analysis/services/ml_engine.py` — extended to the full RF+GB+AdaBoost+XGBoost+LightGBM+LogReg+SVC+MLP ensemble blended with the Keras NN, trained **per market** |
| `generate_trade_signals`, `calculate_scalp_opportunity`, `get_market_thresholds`, `get_entry_type`, `get_risk_level` | `analysis/services/signal_engine.py` |
| `safe_position_size_for_balance`, `MAX_POSITIONS`, TradeManager's SL/TP-hit close logic | `positions/services/position_manager.py` — writes `PaperPosition` rows instead of MT5 orders |
| `email_alerts.py` | `alerts/email_alerts.py` — same cooldown logic, credentials now come from `.env` instead of being hardcoded |

MT5-specific code (`initialize_mt5`, `execute_mt5_trade`, the tkinter
`MarketSelector`, MetaTrader5-dependent risk constants) was **not**
ported — this project only ever reads market data from Deriv's own
WebSocket API and never touches a broker.

## ⚠️ Before you do anything else

The uploaded `bot.py` and `email_alerts.py` had a live MT5 password and a
Gmail app password hardcoded in plaintext. **Rotate both** (change the MT5
password, revoke/regenerate the Gmail app password) — treat the old ones
as compromised since they were in a plaintext file. This project reads
all credentials from `.env`, which is git-ignored.

## Setup

```bash
cp .env.example .env        # fill in EMAIL_* / ALERT_CONTACT_EMAIL if you want alerts
python -m venv venv && source venv/bin/activate
pip install -r requirements.txt
python manage.py migrate
python manage.py createsuperuser   # optional, for /admin/
```

**Also install and run Redis** — required for live signals to actually
reach the browser (see "Why live signals go dead" below):

```bash
sudo apt install redis-server
sudo systemctl enable --now redis-server
# REDIS_URL=redis://127.0.0.1:6379/0 is already the default in .env.example
```

## Running (two processes, same pattern as the DRIVETHRU systemd services)

**1. Web/ASGI server** (dashboard + websocket push to the analysis window):

```bash
daphne -b 0.0.0.0 -p 8000 deriv_platform.asgi:application
```

**2. Analysis + paper-trading loop** (the actual "bot" — connects to Deriv,
runs the ML ensemble across every market, opens/closes paper positions):

```bash
python manage.py run_analysis
```

Open `http://<host>:8000/` — the left pane is the live chart (browser
connects directly to Deriv's WebSocket API, so charting works even if
`run_analysis` isn't running), the right pane is the analysis window and
paper positions, both pushed live over `ws/analysis/`.

### systemd (matches your `kfc` host setup)

```ini
# /etc/systemd/system/deriv-web.service
[Unit]
Description=Deriv Terminal web
After=network.target

[Service]
User=admin
WorkingDirectory=/home/admin/derivplatform
EnvironmentFile=/home/admin/derivplatform/.env
ExecStart=/home/admin/derivplatform/venv/bin/daphne -b 0.0.0.0 -p 8000 deriv_platform.asgi:application
Restart=always

[Install]
WantedBy=multi-user.target
```

```ini
# /etc/systemd/system/deriv-analysis.service
[Unit]
Description=Deriv Terminal analysis loop
After=network.target

[Service]
User=admin
WorkingDirectory=/home/admin/derivplatform
EnvironmentFile=/home/admin/derivplatform/.env
ExecStart=/home/admin/derivplatform/venv/bin/python manage.py run_analysis
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
```

## Chart engine — TradingView Advanced Charting Library

The dashboard and AI Chart pages now run on the licensed **TradingView
Advanced Charting Library** instead of the open-source `lightweight-charts`
CDN build.

- Vendor bundle lives at `static/charting_library/` and is **not** committed
  (see `.gitignore`) — it's ~14MB of licensed code. To set it up on a new
  checkout: unzip your TradingView `charting_library` package and copy
  `charts.js`, `charting_library.standalone.js`, `themed.css`,
  `sprite-*.smartcharts.svg`, `bundles/`, `static/`, and `assets/` into
  `static/charting_library/`.
- `static/js/tv_datafeed.js` — a hand-written `DerivDatafeed` implementing
  the library's `IDatafeedChartApi` (the older `getBars(..., rangeStartDate,
  rangeEndDate, ..., isFirstCall)` signature this package ships) directly
  against Deriv's public `ticks_history`/`ohlc`/`forget` WebSocket calls.
  One shared `DerivSocket` multiplexes history requests and live bar
  subscriptions per `listenerGuid`.
- `static/js/chart.js` — mounts `new TradingView.widget({...})` and keeps
  the exact same `window.initDerivChart(opts)` contract the old
  Lightweight-Charts version exposed, so `index.html`/`ai_chart.html` only
  needed their `<script>` includes swapped, nothing else.
- The old Lightweight-Charts implementation is kept at
  `static/js/chart.lightweight.js.bak` (unused, not wired into any
  template) in case you ever want to fall back to it.
- Candle colors and chart chrome are overridden to match the site palette
  (`--accent`/`--sell` → `#26a69a`/`#ef5350`) via the widget's `overrides`
  option, and the symbol picker in `.symbol-bar` still drives the chart
  (`select.value` → `activeChart().setSymbol(...)`) — the library's own
  header symbol search is disabled to avoid having two pickers.
- Resolution switching (1m/5m/15m/30m/1h/4h/1D) now genuinely works and
  maps to Deriv `granularity` values in `tv_datafeed.js` — a real upgrade
  over the old hardcoded 60s candles.

## Why live signals go dead

`run_analysis` and `daphne` are **two separate OS processes** (see systemd
units above). The browser's `ws/analysis/` connection is served by
`daphne`; signals are computed and broadcast from `run_analysis`. Those
two processes only share state through the Django channel layer — and
`InMemoryChannelLayer` (the old default) only exists inside a single
process. So `run_analysis` was generating signals, saving them to the DB
correctly, and calling `broadcast()`... into a channel layer that
`daphne`'s process could never see. Nothing was actually broken in the
signal engine itself; the pipe between the two processes was a no-op.

Fixed by switching `CHANNEL_LAYERS` to `channels_redis.core.RedisChannelLayer`
when `REDIS_URL` is set (see Setup above) — Redis is shared across both
processes, so broadcasts from `run_analysis` now reach every browser
connected via `daphne`. If `REDIS_URL` is left blank the app still boots
(falls back to in-memory) but logs a loud `RuntimeWarning` at startup,
since that configuration silently drops all live updates.

## Known limitations / things to tune before relying on this

- **Paper position sizing math assumes forex-style pricing** (`contract_size
  = 100000`, price ~1.x). For synthetic/volatility indices (prices in the
  hundreds/thousands) this can push the minimum lot size to risk far more
  than intended — this mirrors a real gap in the original
  `safe_position_size_for_balance`, not a new bug. Worth tightening
  `positions/services/position_manager.py`'s contract-size assumption
  per market type before trusting the P/L numbers.
- **Per-market model training** happens on first scan and then every
  `MODEL_RETRAIN_HOURS` (default 6) — the first full pass across ~30
  markets will be slow (each market trains its own RF/GB/AdaBoost/XGB/
  LightGBM/SVC/MLP ensemble + Keras NN). Consider lowering
  `ANALYSIS_INTERVAL_SECONDS` expectations for that first cycle.
- **Deriv's free `app_id=1089`** is rate-limited. Register your own app_id
  at api.deriv.com if you see frequent `error` messages in the logs once
  you're polling ~30 markets continuously.
