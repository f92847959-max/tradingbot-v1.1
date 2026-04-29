# Gold Trader

AI-assisted XAU/USD intraday trading system with a Python trading runtime, Capital.com broker integration, model training utilities, risk controls, a FastAPI API, and a Streamlit dashboard.

This project can place real trades when configured with live broker credentials. Start in demo mode, verify risk settings, and do not commit secrets.

## What It Does

- Fetches XAU/USD market data and technical indicators.
- Generates AI-backed trade signals with XGBoost and LightGBM.
- Applies strategy, multi-timeframe, and pre-trade risk checks.
- Supports automated or semi-automated trading modes.
- Exposes monitoring and control endpoints through FastAPI.
- Provides a Streamlit dashboard for account, trade, signal, and log views.
- Includes real-data training starters for Core-AI and Exit-AI models.

## Project Layout

```text
ai_engine/          Model loading, prediction, training, and saved artifacts
api/                FastAPI app, auth, dependencies, and routers
config/             Runtime settings and environment loading
dashboard/          Streamlit dashboard
database/           Database models, migrations, and persistence helpers
market_data/        Broker data access, indicators, and data providers
order_management/   Broker order execution and order state
portfolio/          Portfolio and position tracking
risk/               Pre-trade checks, sizing, and risk limits
scripts/            Training, data, and maintenance utilities
strategy/           Signal filters and strategy logic
tests/              Pytest test suite
trading/            Main lifecycle, trading loop, monitors, and signals
```

## Requirements

- Windows PowerShell
- Python 3.11 or newer
- Capital.com credentials for broker-backed runtime or real-data training
- PostgreSQL if you use the PostgreSQL-backed runtime paths

## Setup

From the repository root:

```powershell
cd "C:\Users\fuhhe\OneDrive\Desktop\ai\ai\tradingbot v1"
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
pip install -r requirements.txt
```

Optional development tools are declared in `pyproject.toml`:

```powershell
pip install -e ".[dev,dashboard]"
```

## Configuration

Settings are loaded by `config/settings.py` in this order:

1. `GOLD_ENV_PATH`
2. `C:\Users\<you>\secrets\ai-trading-gold\.env`
3. `.env` in the project root

Prefer the external secrets folder so credentials are not stored inside a OneDrive-synced project folder.

Example PowerShell session:

```powershell
$env:GOLD_ENV_PATH = "C:\Users\fuhhe\secrets\ai-trading-gold\.env"
```

Minimum runtime variables:

```dotenv
CAPITAL_EMAIL=your-email@example.com
CAPITAL_PASSWORD=your-password
CAPITAL_API_KEY=your-capital-api-key
CAPITAL_DEMO=true

POSTGRES_HOST=localhost
POSTGRES_PORT=5432
POSTGRES_DB=gold_trader
POSTGRES_USER=trader
POSTGRES_PASSWORD=change-me

API_KEY=change-this-local-api-key
API_AUTH_ENABLED=true
```

Optional WhatsApp notifications use:

```dotenv
TWILIO_ACCOUNT_SID=
TWILIO_AUTH_TOKEN=
TWILIO_FROM_NUMBER=
TWILIO_TO_NUMBER=
NOTIFICATIONS_ENABLED=false
```

## Run The Trading System

```powershell
.\.venv\Scripts\python.exe main.py
```

If `API_ENABLED=true`, the API is exposed on the configured host and port. Defaults:

- API: `http://127.0.0.1:8000`
- Docs: `http://127.0.0.1:8000/docs`
- Protected endpoints require the `X-API-Key` header when `API_AUTH_ENABLED=true`.

## Run The Dashboard

```powershell
streamlit run dashboard/app.py
```

## Train Models

Start real-data Core-AI training:

```powershell
.\.venv\Scripts\python.exe start_ai_training.py --target core
```

Train selected timeframes:

```powershell
.\.venv\Scripts\python.exe start_ai_training.py --target core --timeframes 5m,15m,1h
```

Train Core-AI plus Exit-AI when a real Exit-AI snapshot CSV exists:

```powershell
.\.venv\Scripts\python.exe start_ai_training.py --target all --exit-csv data/exit_ai_snapshots.csv
```

Training logs are written under `logs/training/`. Saved model artifacts are written under `ai_engine/saved_models/`.

## Validation

Syntax-check the main Python packages:

```powershell
python -m compileall config market_data ai_engine strategy risk order_management portfolio notifications monitoring api dashboard database shared trading
```

Run tests:

```powershell
pytest
```

Run Ruff if installed:

```powershell
ruff check .
```

## Security Notes

- Keep broker keys, API keys, Twilio tokens, and database passwords out of Git.
- Keep `CAPITAL_DEMO=true` until the full system behavior is verified.
- Review `MAX_RISK_PER_TRADE_PCT`, daily loss limits, trading hours, and `MAX_OPEN_POSITIONS` before enabling automated trading.
- Treat generated signals as decision support, not a profit guarantee.

## License

No license file is currently included. Add one before publishing or redistributing the project.
