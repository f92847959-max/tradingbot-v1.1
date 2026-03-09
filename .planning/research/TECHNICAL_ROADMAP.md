# Technische Verbesserungsroadmap für Goldbot2

**Priorität:** Stellen Sie sicher, dass die "MUST-FIX" Punkte vor der Produktionsnutzung adressiert werden.

---

## 1. SICHERHEITS-FIXES (KRITISCH)

### 1.1 API Key Management

**Problem:** Keys werden geloggt und im RAM gespeichert

**Lösung:**
```python
# config/secrets.py (NEU)
import os
from functools import lru_cache

@lru_cache(maxsize=1)
def get_api_key() -> str:
    """Load API key from secure source."""
    # Option 1: AWS Secrets Manager
    try:
        import boto3
        client = boto3.client("secretsmanager")
        secret = client.get_secret_value(SecretId="goldbot/api-key")
        return secret["SecretString"]
    except Exception:
        pass
    
    # Option 2: Environment (nur für local dev)
    key = os.getenv("API_KEY", None)
    if not key:
        raise RuntimeError(
            "API_KEY nicht gesetzt. "
            "Für Produktion: AWS Secrets Manager nutzen. "
            "Für local dev: export API_KEY=$(python -c 'import secrets; "
            "print(secrets.token_urlsafe(32))')"
        )
    return key

# api/auth.py (UPDATED)
async def verify_api_key(request: Request) -> str:
    api_key = request.headers.get("X-API-Key")
    if not api_key:
        raise HTTPException(status_code=401, detail="Missing X-API-Key header")
    
    expected = get_api_key()
    if not secrets.compare_digest(api_key, expected):
        # ❌ NICHT loggen — das ist ein Angrissindikator
        await audit_log("api_auth_failed", ip=request.client.host)
        raise HTTPException(status_code=401, detail="Invalid API key")
    
    return api_key
```

### 1.2 Broker-Credentials verschlüsseln

**Problem:** Capital.com Passwörter im .env im Plaintext

**Lösung:**
```bash
# Setup: Secrets Manager
aws secretsmanager create-secret \
  --name goldbot/broker-credentials \
  --secret-string '{
    "email": "your@email.com",
    "password": "encrypted_pass",
    "api_key": "xyz123"
  }'

# config/settings.py (UPDATED)
from functools import lru_cache

@lru_cache(maxsize=1)
def get_broker_credentials():
    """Load from AWS Secrets Manager, not .env"""
    import boto3
    client = boto3.client("secretsmanager")
    secret = client.get_secret_value(SecretId="goldbot/broker-credentials")
    import json
    return json.loads(secret["SecretString"])

class Settings(BaseSettings):
    @property
    def capital_email(self) -> str:
        creds = get_broker_credentials()
        return creds["email"]
    
    # Similar for password and api_key
```

### 1.3 CORS einschränken

**api/app.py (UPDATED)**
```python
import os

ALLOWED_ORIGINS = os.getenv("CORS_ORIGINS", "").split(",")
if not ALLOWED_ORIGINS or ALLOWED_ORIGINS == [""]:
    logger.warning("CORS_ORIGINS not set — restricting to localhost")
    ALLOWED_ORIGINS = ["http://127.0.0.1:8000"]

app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_credentials=False,  # ← Wichtig: Keine Cookies!
    allow_methods=["GET", "POST"],  # ← Nur notwendig
    allow_headers=["Authorization", "Content-Type"],
)
```

### 1.4 Webhook-Signatur validieren (WhatsApp Confirmations)

**api/routers/webhook.py (NEW SECTION)**
```python
import hmac
import hashlib

WEBHOOK_SECRET = os.getenv("WEBHOOK_SECRET")

def verify_webhook_signature(body: bytes, signature: str) -> bool:
    """Verify Twilio webhook signature."""
    expected = hmac.new(
        WEBHOOK_SECRET.encode(),
        body,
        hashlib.sha1
    ).digest()
    expected_b64 = base64.b64encode(expected).decode()
    return hmac.compare_digest(signature, expected_b64)

@app.post("/webhook/confirmation")
async def handle_confirmation(
    request: Request,
    body: dict
):
    # Verify signature from X-Twilio-Signature header
    signature = request.headers.get("X-Twilio-Signature", "")
    if not verify_webhook_signature(await request.body(), signature):
        logger.warning("Invalid webhook signature from %s", request.client.host)
        raise HTTPException(status_code=403, detail="Invalid signature")
    
    # Process confirmation...
```

---

## 2. FEHLERBEHANDLUNG-FIXES

### 2.1 Exception Classification schärfen

**trading/trading_loop.py (REFACTORED)**
```python
async def _trading_loop(self: TradingSystem) -> None:
    """Main trading loop with improved error handling."""
    while self._running:
        try:
            await self._trading_tick()
            self._consecutive_errors = 0
        except asyncio.CancelledError:
            logger.info("Trading loop cancelled")
            raise
        except (BrokerError, DataError, PredictionError) as e:
            # RETRYABLE errors
            self._consecutive_errors += 1
            category = classify_error(e)
            
            if category == ErrorCategory.TEMPORARY:
                backoff = min(
                    self.settings.trading_interval_seconds * (2 ** self._consecutive_errors),
                    300  # Max 5 minutes
                )
                logger.warning(f"Temporary error (retry in {backoff}s): {e}")
                await asyncio.sleep(backoff)
            
            elif category == ErrorCategory.PERMANENT:
                logger.critical(f"Permanent error — stopping: {e}")
                self._running = False
                await self.notifications.notify_error("Permanent error", str(e))
        
        except Exception as e:
            # UNEXPECTED errors — don't kill-switch!
            self._unexpected_errors += 1
            logger.exception("UNEXPECTED ERROR: %s (count: %d)", e, self._unexpected_errors)
            
            # Send to monitoring team (not auto kill-switch)
            await self.alerts.send_to_ops(
                level="CRITICAL",
                title="Unexpected Error in Trading Loop",
                details=str(e),
                traceback=traceback.format_exc()
            )
            
            if self._unexpected_errors >= 3:
                logger.critical("3 unexpected errors — deactivating bot for manual review")
                self._running = False
```

### 2.2 Retry-Wrapper für alle I/O

**shared/retry.py (NEW)**
```python
import functools
import asyncio
from typing import Awaitable, TypeVar

T = TypeVar("T")

async def retry_async(
    coro_func,
    max_retries: int = 3,
    backoff_base: float = 2.0,
    max_backoff: float = 60.0,
) -> T:
    """Generic async retry with exponential backoff."""
    for attempt in range(max_retries):
        try:
            return await coro_func()
        except (asyncio.TimeoutError, ConnectionError) as e:
            if attempt == max_retries - 1:
                raise
            backoff = min(backoff_base ** attempt, max_backoff)
            logger.warning(f"Attempt {attempt + 1} failed, retrying in {backoff}s: {e}")
            await asyncio.sleep(backoff)

# Usage:
result = await retry_async(
    lambda: self.broker.get_account(),
    max_retries=3
)
```

---

## 3. TESTING-GRUNDSTRUKTUR

### 3.1 Unit-Test Setup

**tests/conftest.py (NEW)**
```python
import pytest
import asyncio
from unittest.mock import AsyncMock, MagicMock
from config.settings import Settings

@pytest.fixture
async def settings():
    return Settings(
        capital_email="test@test.com",
        capital_password="test",
        capital_api_key="test",
        max_daily_loss_pct=5.0,
        max_open_positions=3,
        min_trade_score=60,
    )

@pytest.fixture
def mock_broker():
    return AsyncMock(name="broker")

@pytest.fixture
def mock_db():
    return AsyncMock(name="db")
```

### 3.2 RiskManager Tests

**tests/test_risk_manager.py (NEW)**
```python
import pytest
from risk.risk_manager import RiskManager, RiskApproval

@pytest.mark.asyncio
async def test_approve_trade_basic_pass():
    """Test a simple trade approval."""
    rm = RiskManager(
        max_daily_loss_pct=5.0,
        max_open_positions=3,
    )
    
    # Set up initial state
    rm.set_initial_equity(10000.0)
    
    # Request approval
    result = await rm.approve_trade(
        direction="BUY",
        entry_price=2050.0,
        stop_loss=2045.0,
        current_equity=10000.0,
        available_margin=5000.0,
        open_positions=0,
        trades_today=5,
        consecutive_losses=0,
        current_spread=0.5,
        has_open_same_direction=False,
    )
    
    assert result.approved is True
    assert result.lot_size > 0.01

@pytest.mark.asyncio  
async def test_approve_trade_kill_switch_active():
    """Test rejection when kill switch is active."""
    rm = RiskManager(kill_switch_drawdown_pct=20.0)
    rm.kill_switch.activate("Manual test")
    
    result = await rm.approve_trade(
        direction="BUY",
        entry_price=2050.0,
        stop_loss=2045.0,
        current_equity=8000.0,  # 20% drawdown
        available_margin=5000.0,
        open_positions=0,
        trades_today=5,
        consecutive_losses=0,
        current_spread=0.5,
        has_open_same_direction=False,
    )
    
    assert result.approved is False
    assert "kill switch" in result.reason.lower()
```

### 3.3 OrderExecutor Mocking

**tests/test_order_executor.py (NEW)**
```python
import pytest
from unittest.mock import AsyncMock
from order_management.order_executor import OrderExecutor

@pytest.mark.asyncio
async def test_execute_order_success(mock_broker):
    """Test successful order execution."""
    executor = OrderExecutor(broker_client=mock_broker)
    
    # Mock broker response
    mock_broker.open_deal.return_value = {
        "dealId": "12345",
        "status": "OPEN",
        "entry": 2050.0,
    }
    
    result = await executor.execute_buy(
        entry_price=2050.0,
        stop_loss=2045.0,
        take_profit=2060.0,
        lot_size=1.0,
    )
    
    assert result["dealId"] == "12345"
    mock_broker.open_deal.assert_called_once()

@pytest.mark.asyncio
async def test_execute_order_broker_error_retriable(mock_broker):
    """Test retry on temporary broker error."""
    from market_data.broker_client import BrokerConnectionError
    
    executor = OrderExecutor(broker_client=mock_broker)
    
    # First call fails, second succeeds
    mock_broker.open_deal.side_effect = [
        BrokerConnectionError("Network timeout"),
        {"dealId": "12346", "status": "OPEN"},
    ]
    
    result = await executor.execute_with_retry(
        entry_price=2050.0,
        stop_loss=2045.0,
        take_profit=2060.0,
        lot_size=1.0,
        max_retries=2,
    )
    
    assert result["dealId"] == "12346"
    assert mock_broker.open_deal.call_count == 2
```

---

## 4. OBSERVABILITY-FRAMEWORK

### 4.1 Strukturiertes Logging

**shared/logger.py (NEW)**
```python
import structlog
import logging

# Konfiguriere strukturelles Logging
structlog.configure(
    processors=[
        structlog.stdlib.filter_by_level,
        structlog.stdlib.add_logger_name,
        structlog.stdlib.add_log_level,
        structlog.stdlib.PositionalArgumentsFormatter(),
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.processors.StackInfoRenderer(),
        structlog.processors.format_exc_info,
        structlog.processors.UnicodeDecoder(),
        structlog.processors.JSONRenderer(),
    ],
    context_class=dict,
    logger_factory=structlog.stdlib.LoggerFactory(),
    cache_logger_on_first_use=True,
)

# Usage statt print()
log = structlog.get_logger()

# Trade approval
log.info(
    "trade_approved",
    direction="BUY",
    entry_price=2050.0,
    lot_size=1.0,
    risk_pct=2.0,
    confidence=0.85,
)
```

### 4.2 Prometheus Metriken

**shared/metrics.py (NEW)**
```python
from prometheus_client import Counter, Histogram, Gauge
import time

# Counters
trades_opened = Counter(
    'trades_opened_total',
    'Total number of trades opened',
    ['direction', 'strategy']
)

trades_closed = Counter(
    'trades_closed_total',
    'Total trades closed',
    ['reason']  # 'tp', 'sl', 'manual', etc
)

pnl_total = Counter(
    'pnl_cumulative',
    'Cumulative P&L',
    ['pair']
)

# Histograms
trade_duration = Histogram(
    'trade_duration_seconds',
    'Time from open to close'
)

signal_generation_time = Histogram(
    'signal_generation_seconds',
    'Time to generate AI signal'
)

# Gauges
equity = Gauge('equity_current', 'Current account equity')
drawdown_pct = Gauge('drawdown_percent', 'Current drawdown %')
open_positions = Gauge('open_positions', 'Number of open positions')

# Usage
trades_opened.labels(direction="BUY", strategy="ml_ensemble").inc()
with signal_generation_time.time():
    signal = await self.ai.predict(df)
```

---

## 5. CONTAINERIZATION

### 5.1 Dockerfile

**Dockerfile (NEW)**
```dockerfile
FROM python:3.11-slim

WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y \
    gcc \
    postgresql-client \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements
COPY requirements.txt .
RUN pip install -r requirements.txt

# Copy code
COPY . .

# Health check
HEALTHCHECK --interval=30s --timeout=10s --retries=3 \
    CMD curl -f http://localhost:8000/health || exit 1

# Run
CMD ["python", "main.py"]
```

### 5.2 docker-compose.yml

**docker-compose.yml (NEW)**
```yaml
version: '3.8'

services:
  postgres:
    image: postgres:15
    environment:
      POSTGRES_USER: trader
      POSTGRES_PASSWORD: ${POSTGRES_PASSWORD}
      POSTGRES_DB: gold_trader
    ports:
      - "5432:5432"
    volumes:
      - postgres_data:/var/lib/postgresql/data

  goldbot:
    build: .
    depends_on:
      - postgres
    environment:
      POSTGRES_HOST: postgres
      POSTGRES_PASSWORD: ${POSTGRES_PASSWORD}
      API_KEY: ${API_KEY}
      CAPITAL_EMAIL: ${CAPITAL_EMAIL}
      CAPITAL_PASSWORD: ${CAPITAL_PASSWORD}
      CAPITAL_API_KEY: ${CAPITAL_API_KEY}
      LOG_LEVEL: INFO
    ports:
      - "8000:8000"
    restart: unless-stopped

  prometheus:
    image: prom/prometheus:latest
    volumes:
      - ./monitoring/prometheus.yml:/etc/prometheus/prometheus.yml
    ports:
      - "9090:9090"

volumes:
  postgres_data:
```

---

## 6. BACKTESTING-INTEGRATION

### 6.1 Backtester Klasse

**ai_engine/backtester.py (NEW)**
```python
import pandas as pd
from dataclasses import dataclass, field
from typing import List

@dataclass
class BacktestResult:
    total_trades: int = 0
    winning_trades: int = 0
    losing_trades: int = 0
    total_pnl: float = 0.0
    max_drawdown: float = 0.0
    sharpe_ratio: float = 0.0
    win_rate: float = 0.0
    avg_win: float = 0.0
    avg_loss: float = 0.0
    profit_factor: float = 0.0
    trade_log: List[dict] = field(default_factory=list)

class Backtester:
    def __init__(self, initial_capital: float = 10000.0):
        self.initial_capital = initial_capital
        self.capital = initial_capital
        self.peak_capital = initial_capital
        self.trades = []
    
    async def run_backtest(
        self,
        df: pd.DataFrame,
        predictor,  # AIPredictor instance
        start_date: str,
        end_date: str,
    ) -> BacktestResult:
        """Run backtest on historical data."""
        # Filter date range
        df = df[(df.index >= start_date) & (df.index <= end_date)]
        
        for i in range(len(df) - 1):
            row = df.iloc[i]
            next_row = df.iloc[i + 1]
            
            # Generate signal
            signal = await predictor.predict_on_row(row)
            if signal["action"] == "HOLD":
                continue
            
            # Simulate trade
            entry_price = next_row["open"]
            sl = signal["stop_loss"]
            tp = signal["take_profit"]
            
            # Determine exit
            high = next_row["high"]
            low = next_row["low"]
            
            if signal["action"] == "BUY":
                if high >= tp:
                    exit_price = tp
                elif low <= sl:
                    exit_price = sl
                else:
                    exit_price = next_row["close"]
            else:  # SELL
                if low <= tp:
                    exit_price = tp
                elif high >= sl:
                    exit_price = sl
                else:
                    exit_price = next_row["close"]
            
            # Calculate P&L
            pnl = (exit_price - entry_price) * 1.0  # 1 lot = 1 oz
            self.capital += pnl
            self.peak_capital = max(self.peak_capital, self.capital)
            
            self.trades.append({
                "entry": entry_price,
                "exit": exit_price,
                "pnl": pnl,
                "direction": signal["action"],
            })
        
        return self._calculate_stats()
```

---

## 7. DEPLOYMENT-PRÜFLISTE

- [ ] API-Key Sicherheit hardened
- [ ] Broker-Credentials in Secrets Manager
- [ ] CORS restricted
- [ ] Webhooks signiert
- [ ] Exception Handling überarbeitet
- [ ] Unit-Tests (minimum 50% Coverage)
- [ ] Strukturelles Logging aktiv
- [ ] Prometheus-Metriken integriert
- [ ] Dockerfile & docker-compose erstellt
- [ ] Backtesting-Ergebnisse dokumentiert (Sharpe, Max DD, Win Rate)
- [ ] 3-6 Monate Paper-Trading durchlaufen
- [ ] 24/7 Monitoring & Alerting konfiguriert
- [ ] Disaster-Recovery Plan erstellt
- [ ] Performance-Test unter Last bestanden
- [ ] Security Audit durchgeführt

---

## 🎯 ZEITSCHÄTZUNG

| Modul | Aufwand | Priorität |
|-------|---------|-----------|
| Sicherheits-Fixes | 1-2 Wochen | 🔴 KRITISCH |
| Error Handling | 1 Woche | 🟡 HOCH |
| Unit-Tests | 2-3 Wochen | 🟡 HOCH |
| Observability | 1 Woche | 🟡 MITTEL |
| Containerization | 3-5 Tage | 🟡 MITTEL |
| Backtesting | 2 Wochen | 🟡 MITTEL |

**Gesamtaufwand für "production-ready":** ~4-6 Wochen (1 Dev)
