"""Enhanced Utility functions and data fetching for the Gold Trader dashboard."""

import asyncio
import logging
import os
import sys
import pandas as pd
import datetime
import random
import threading
from concurrent.futures import TimeoutError as FutureTimeout
from typing import List

# Ensure project root is importable when this module is loaded from dashboard/ context.
_THIS_DIR = os.path.dirname(os.path.abspath(__file__))
_PROJECT_ROOT = os.path.dirname(_THIS_DIR)
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)

from database.connection import get_session
from database.repositories.trade_repo import TradeRepository
from database.repositories.signal_repo import SignalRepository
from market_data.data_provider import DataProvider
from market_data.broker_client import CapitalComClient

logger = logging.getLogger(__name__)

_runner_loop: asyncio.AbstractEventLoop | None = None
_runner_thread: threading.Thread | None = None
_runner_lock = threading.Lock()


def _runner_main(loop: asyncio.AbstractEventLoop) -> None:
    asyncio.set_event_loop(loop)
    loop.run_forever()


def _get_runner_loop() -> asyncio.AbstractEventLoop:
    global _runner_loop, _runner_thread
    with _runner_lock:
        if _runner_loop is None or _runner_thread is None or not _runner_thread.is_alive():
            _runner_loop = asyncio.new_event_loop()
            _runner_thread = threading.Thread(
                target=_runner_main,
                args=(_runner_loop,),
                daemon=True,
                name="dashboard-async-runner",
            )
            _runner_thread.start()
    return _runner_loop

def run_async(coro):
    """Run async code from Streamlit via a dedicated background event loop."""
    loop = _get_runner_loop()
    future = asyncio.run_coroutine_threadsafe(coro, loop)
    try:
        return future.result(timeout=45)
    except FutureTimeout:
        future.cancel()
        raise RuntimeError("Async operation timed out after 45s")


class DataBridge:
    """Bridge between the database/broker and the Streamlit UI."""

    def __init__(self):
        # Configuration for broker (read from .env)
        self.email = os.getenv("CAPITAL_EMAIL", "")
        self.password = os.getenv("CAPITAL_PASSWORD", "")
        self.api_key = os.getenv("CAPITAL_API_KEY", "")
        self.demo = os.getenv("CAPITAL_DEMO", "true").lower() == "true"

        self._broker = None
        self._data_provider = None
        self._data_status = {
            "trades": "db",
            "signals": "db",
            "candles": "broker",
            "risk": "db",
            "account": "broker",
        }
        self._data_errors: dict[str, str] = {}

    def get_data_status(self) -> dict[str, str]:
        return dict(self._data_status)

    def get_data_errors(self) -> dict[str, str]:
        return dict(self._data_errors)

    def _broker_credentials_ready(self) -> bool:
        values = (self.email.strip(), self.password.strip(), self.api_key.strip())
        if not all(values):
            return False
        return not (
            self.email.strip().endswith("@example.com")
            or self.password.strip().startswith("your-")
            or self.api_key.strip().startswith("your-")
        )

    async def get_broker(self) -> CapitalComClient:
        """Get or initialize broker client with connection check."""
        if not self._broker_credentials_ready():
            raise RuntimeError("Broker credentials missing or placeholder values in .env")
        if self._broker is None:
            self._broker = CapitalComClient(
                email=self.email,
                password=self.password,
                api_key=self.api_key,
                demo=self.demo,
            )
            await self._broker.authenticate()
        return self._broker

    async def get_data_provider(self) -> DataProvider:
        if self._data_provider is None:
            broker = await self.get_broker()
            self._data_provider = DataProvider(broker)
        return self._data_provider

    def _set_source(self, key: str, value: str) -> None:
        self._data_status[key] = value
        self._data_errors.pop(key, None)

    def _set_error(self, key: str, exc: Exception | str) -> None:
        self._data_errors[key] = str(exc)

    async def _fetch_broker_open_positions(self) -> pd.DataFrame:
        broker = await self.get_broker()
        positions = await broker.get_positions()
        if not positions:
            return pd.DataFrame()

        now_utc = datetime.datetime.now(datetime.timezone.utc)
        rows = []
        for idx, p in enumerate(positions, start=1):
            opened_at = pd.to_datetime(p.created_at, utc=True, errors="coerce")
            if pd.isna(opened_at):
                opened_at = now_utc

            rows.append({
                "ID": idx,
                "Deal ID": p.deal_id,
                "Direction": p.direction,
                "Lot Size": float(p.size),
                "Entry": float(p.open_level),
                "SL": float(p.stop_level) if p.stop_level is not None else None,
                "TP": float(p.limit_level) if p.limit_level is not None else None,
                "Exit": None,
                "P&L": float(p.profit),
                "Status": "OPEN",
                "Opened At": opened_at,
                "Closed At": None,
                "Reason": "Broker live position",
            })

        return pd.DataFrame(rows)

    @staticmethod
    def _timeframe_delta(timeframe: str) -> datetime.timedelta:
        mapping = {
            "1m": datetime.timedelta(minutes=1),
            "5m": datetime.timedelta(minutes=5),
            "15m": datetime.timedelta(minutes=15),
            "30m": datetime.timedelta(minutes=30),
            "1h": datetime.timedelta(hours=1),
            "4h": datetime.timedelta(hours=4),
            "1d": datetime.timedelta(days=1),
        }
        return mapping.get(timeframe, datetime.timedelta(minutes=5))

    def _synthetic_candles(self, timeframe: str, count: int) -> pd.DataFrame:
        if count <= 0:
            return pd.DataFrame()

        step = self._timeframe_delta(timeframe)
        end = datetime.datetime.now(datetime.timezone.utc).replace(second=0, microsecond=0)
        start = end - step * (count - 1)

        # Deterministic per hour to keep the chart visually stable across reruns.
        seed = int(end.timestamp() // 3600) + abs(hash(timeframe)) % 1000
        rng = random.Random(seed)
        price = 2300.0 + rng.uniform(-20.0, 20.0)

        rows = []
        for i in range(count):
            ts = start + step * i
            drift = rng.uniform(-0.25, 0.25)
            shock = rng.gauss(0.0, 1.2)
            close = max(1500.0, price + drift + shock)
            wick_high = abs(rng.gauss(0.6, 0.25))
            wick_low = abs(rng.gauss(0.6, 0.25))
            high = max(price, close) + wick_high
            low = min(price, close) - wick_low
            volume = max(1.0, rng.gauss(120.0, 35.0))
            rows.append({
                "timestamp": ts,
                "open": float(price),
                "high": float(high),
                "low": float(low),
                "close": float(close),
                "volume": float(volume),
            })
            price = close

        df = pd.DataFrame(rows).set_index("timestamp")
        try:
            from market_data.indicators import calculate_indicators
            df = calculate_indicators(df)
        except Exception as exc:
            logger.debug("Synthetic indicator calc skipped: %s", exc)
        return df

    async def fetch_recent_trades(self, limit: int = 50) -> pd.DataFrame:
        """Fetch recent trades with DB -> broker fallback."""
        try:
            async with get_session() as session:
                repo = TradeRepository(session)
                trades = await repo.get_history(days=30)
                if not trades:
                    self._set_source("trades", "db")
                    return pd.DataFrame()

                data = []
                for t in trades:
                    data.append({
                        "ID": t.id,
                        "Deal ID": t.deal_id,
                        "Direction": t.direction,
                        "Lot Size": float(t.lot_size),
                        "Entry": float(t.entry_price),
                        "SL": float(t.stop_loss) if t.stop_loss is not None else None,
                        "TP": float(t.take_profit) if t.take_profit is not None else None,
                        "Exit": float(t.exit_price) if t.exit_price else None,
                        "P&L": float(t.net_pnl) if t.net_pnl else 0.0,
                        "Status": t.status,
                        "Opened At": t.opened_at,
                        "Closed At": t.closed_at,
                        "Reason": t.close_reason or "-",
                    })
                self._set_source("trades", "db")
                return pd.DataFrame(data).head(limit)
        except Exception as e:
            self._set_error("trades", e)
            try:
                broker_df = await self._fetch_broker_open_positions()
                if not broker_df.empty:
                    self._set_source("trades", "broker_fallback")
                    return broker_df.head(limit)
            except Exception as broker_exc:
                self._set_error("trades", f"DB={e}; Broker={broker_exc}")
            self._data_status["trades"] = "unavailable"
            return pd.DataFrame()

    async def fetch_recent_signals(self, limit: int = 20) -> pd.DataFrame:
        """Fetch recent AI signals."""
        try:
            async with get_session() as session:
                from database.models import Signal
                from sqlalchemy import select
                stmt = select(Signal).order_by(Signal.timestamp.desc()).limit(limit)
                result = await session.execute(stmt)
                signals = result.scalars().all()

                if not signals:
                    self._set_source("signals", "db")
                    return pd.DataFrame()

                data = []
                for s in signals:
                    data.append({
                        "Timestamp": s.timestamp,
                        "Action": s.action,
                        "Confidence": f"{float(s.confidence):.1%}",
                        "Score": s.trade_score or 0,
                        "Price": f"{float(s.entry_price):.2f}" if s.entry_price else "-",
                        "Status": "Executed" if s.was_executed else f"Rejected: {s.rejection_reason or 'Risk'}",
                        "Reasoning": s.reasoning,
                    })
                self._set_source("signals", "db")
                return pd.DataFrame(data)
        except Exception as e:
            self._set_error("signals", e)
            self._data_status["signals"] = "unavailable"
            return pd.DataFrame()

    async def fetch_account_info(self):
        """Fetch live account information from the broker."""
        try:
            broker = await self.get_broker()
            account = await broker.get_account()
            self._set_source("account", "broker")
            return {
                "balance": float(account.balance),
                "equity": float(account.balance), # Simplified
                "available": float(account.available),
                "currency": account.currency,
            }
        except Exception as exc:
            self._set_error("account", exc)
            self._data_status["account"] = "unavailable"
            return {"balance": 0.0, "equity": 0.0, "available": 0.0, "currency": "USD"}

    async def fetch_candles(self, timeframe: str = "5m", count: int = 100) -> pd.DataFrame:
        """Fetch recent candles with broker -> synthetic fallback."""
        try:
            from market_data.indicators import calculate_indicators
            dp = await self.get_data_provider()
            df = await dp.get_candles_df(timeframe=timeframe, count=count)
            if not df.empty:
                df = calculate_indicators(df)
                self._set_source("candles", "broker")
                return df
            self._data_status["candles"] = "unavailable"
            return df
        except Exception as e:
            self._set_error("candles", e)
            fallback = self._synthetic_candles(timeframe=timeframe, count=count)
            if not fallback.empty:
                self._set_source("candles", "synthetic")
                return fallback
            self._data_status["candles"] = "unavailable"
            return pd.DataFrame()

    async def fetch_risk_status(self) -> dict:
        """Fetch current risk and kill switch status."""
        try:
            async with get_session() as session:
                from database.models import DailyRiskState
                from sqlalchemy import select
                
                today = datetime.date.today()
                stmt = select(DailyRiskState).where(DailyRiskState.date == today)
                result = await session.execute(stmt)
                state = result.scalar_one_or_none()
                
                if state:
                    self._set_source("risk", "db")
                    return {
                        "kill_switch": state.kill_switch_activated,
                        "drawdown": float(state.max_drawdown_pct or 0.0),
                        "daily_pnl": float(state.daily_pnl or 0.0),
                        "consecutive_losses": state.consecutive_losses,
                    }
                self._set_source("risk", "db")
                return {"kill_switch": False, "drawdown": 0.0, "daily_pnl": 0.0, "consecutive_losses": 0}
        except Exception as exc:
            self._set_error("risk", exc)
            self._data_status["risk"] = "unavailable"
            return {"kill_switch": False, "drawdown": 0.0, "daily_pnl": 0.0, "consecutive_losses": 0}

    def get_latest_logs(self, n: int = 50) -> List[str]:
        """Read the last N lines from the trading log file."""
        log_file = "logs/trading.log"
        if not os.path.exists(log_file):
            return ["Log file not found. Start main.py to generate logs."]
        
        try:
            with open(log_file, "r", encoding="utf-8") as f:
                lines = f.readlines()
                return lines[-n:]
        except Exception as e:
            return [f"Error reading log file: {e}"]

    async def trigger_kill_switch(self) -> bool:
        """Manually activate the kill switch in the database."""
        try:
            async with get_session() as session:
                from database.models import DailyRiskState
                from sqlalchemy import select
                
                today = datetime.date.today()
                stmt = select(DailyRiskState).where(DailyRiskState.date == today)
                result = await session.execute(stmt)
                state = result.scalar_one_or_none()
                
                if not state:
                    state = DailyRiskState(date=today, kill_switch_activated=True)
                    session.add(state)
                else:
                    state.kill_switch_activated = True
                
                await session.commit()
                return True
        except Exception as e:
            print(f"Error triggering kill switch: {e}")
            return False

    async def close_position(self, deal_id: str) -> bool:
        """Close a specific position."""
        try:
            broker = await self.get_broker()
            from order_management.order_manager import OrderManager
            orders = OrderManager(broker)
            # This relies on OrderManager having a close_trade method
            return await orders.close_trade(deal_id)
        except Exception as e:
            print(f"Error closing position: {e}")
            return False

    async def close(self):
        if self._broker:
            await self._broker.close()
            self._broker = None
            self._data_provider = None
