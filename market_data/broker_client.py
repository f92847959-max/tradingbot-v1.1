"""Capital.com REST + WebSocket client for Gold (XAU/USD) trading."""

import asyncio
import json
import logging
import time
from collections import deque
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Callable

import aiohttp
import websockets

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Data Models
# ---------------------------------------------------------------------------

@dataclass
class AccountInfo:
    account_id: str
    balance: float
    deposit: float
    profit_loss: float
    available: float
    currency: str = "EUR"


@dataclass
class CandleData:
    timestamp: datetime
    open: float
    high: float
    low: float
    close: float
    volume: float = 0.0


@dataclass
class Position:
    deal_id: str
    direction: str  # BUY or SELL
    size: float
    open_level: float
    current_level: float
    stop_level: float | None = None
    limit_level: float | None = None
    profit: float = 0.0
    currency: str = "EUR"
    created_at: str = ""


@dataclass
class OrderResult:
    deal_reference: str
    deal_id: str
    status: str  # ACCEPTED, REJECTED
    reason: str = ""
    level: float = 0.0
    affected_deals: list = field(default_factory=list)


# ---------------------------------------------------------------------------
# Rate Limiter
# ---------------------------------------------------------------------------

class RateLimiter:
    """Enforce max N requests per second."""

    def __init__(self, max_per_second: int = 10) -> None:
        self.max_per_second = max_per_second
        self._timestamps: list[float] = []
        self._lock = asyncio.Lock()

    async def acquire(self) -> None:
        async with self._lock:
            now = time.monotonic()
            # Filter & snapshot once — no re-read between checks
            active = [t for t in self._timestamps if now - t < 1.0]
            self._timestamps = active

            if len(active) >= self.max_per_second:
                wait = 1.0 - (now - active[0])
                if wait > 0:
                    await asyncio.sleep(wait)

            self._timestamps.append(time.monotonic())


# ---------------------------------------------------------------------------
# Exceptions — re-exported from shared for backward compatibility
# ---------------------------------------------------------------------------

from shared.exceptions import BrokerError, BrokerAuthError as AuthenticationError  # noqa: E402


class OrderRejectedError(BrokerError):
    def __init__(self, reason: str, deal_reference: str = ""):
        self.reason = reason
        self.deal_reference = deal_reference
        super().__init__(f"Order rejected: {reason}")


class RateLimitError(BrokerError):
    pass


# ---------------------------------------------------------------------------
# Circuit Breaker
# ---------------------------------------------------------------------------

class CircuitBreakerState(Enum):
    CLOSED = "CLOSED"
    OPEN = "OPEN"
    HALF_OPEN = "HALF_OPEN"


@dataclass
class CircuitBreaker:
    """Protects against cascading failures by tracking broker errors."""

    error_threshold: int = 5
    window_seconds: float = 120
    recovery_seconds: float = 60

    def __post_init__(self) -> None:
        self.state: CircuitBreakerState = CircuitBreakerState.CLOSED
        self._errors: deque[float] = deque(maxlen=20)
        self._opened_at: float = 0.0

    def record_failure(self) -> None:
        """Record a failure timestamp; trip to OPEN if threshold exceeded."""
        now = time.monotonic()
        self._errors.append(now)
        cutoff = now - self.window_seconds
        errors_in_window = sum(1 for t in self._errors if t >= cutoff)
        if errors_in_window >= self.error_threshold:
            self.state = CircuitBreakerState.OPEN
            self._opened_at = now
            logger.critical(
                "Circuit breaker OPEN — %d errors in %ds window",
                errors_in_window,
                self.window_seconds,
            )

    def record_success(self) -> None:
        """On success in HALF_OPEN state, close the circuit."""
        if self.state == CircuitBreakerState.HALF_OPEN:
            self.state = CircuitBreakerState.CLOSED
            self._errors.clear()
            logger.info("Circuit breaker CLOSED — broker recovered")

    def allow_request(self) -> bool:
        """Decide whether a request is allowed through."""
        if self.state == CircuitBreakerState.CLOSED:
            return True
        if self.state == CircuitBreakerState.OPEN:
            if time.monotonic() - self._opened_at >= self.recovery_seconds:
                self.state = CircuitBreakerState.HALF_OPEN
                logger.info("Circuit breaker HALF_OPEN — allowing probe request")
                return True
            return False
        # HALF_OPEN — allow one probe
        return True

    @property
    def is_healthy(self) -> bool:
        return self.state != CircuitBreakerState.OPEN


# ---------------------------------------------------------------------------
# Capital.com Client
# ---------------------------------------------------------------------------

DEMO_URL = "https://demo-api-capital.backend-capital.com"
LIVE_URL = "https://api-capital.backend-capital.com"
WS_URL = "wss://api-streaming-capital.backend-capital.com/connect"

GOLD_EPIC = "GOLD"

TIMEFRAME_MAP = {
    "1m": "MINUTE",
    "5m": "MINUTE_5",
    "15m": "MINUTE_15",
    "30m": "MINUTE_30",
    "1h": "HOUR",
    "4h": "HOUR_4",
    "1d": "DAY",
}


class CapitalComClient:
    """Client for Capital.com REST API and WebSocket streaming."""

    def __init__(
        self,
        email: str,
        password: str,
        api_key: str,
        demo: bool = True,
        max_requests_per_second: int = 10,
    ) -> None:
        self.email = email
        self.password = password
        self.api_key = api_key
        self.base_url = DEMO_URL if demo else LIVE_URL
        self.demo = demo

        self._cst: str | None = None
        self._security_token: str | None = None
        self._session: aiohttp.ClientSession | None = None
        self._rate_limiter = RateLimiter(max_requests_per_second)
        self._ws: Any = None
        self._ws_task: asyncio.Task | None = None
        self._circuit_breaker = CircuitBreaker()

    @property
    def is_healthy(self) -> bool:
        """Whether the broker circuit breaker considers the connection healthy."""
        return self._circuit_breaker.is_healthy

    # -- Session Management -------------------------------------------------

    async def _ensure_session(self) -> aiohttp.ClientSession:
        if self._session is None or self._session.closed:
            self._session = aiohttp.ClientSession(
                timeout=aiohttp.ClientTimeout(total=30),
            )
        return self._session

    def _auth_headers(self) -> dict[str, str]:
        headers = {"X-CAP-API-KEY": self.api_key, "Content-Type": "application/json"}
        if self._cst:
            headers["CST"] = self._cst
        if self._security_token:
            headers["X-SECURITY-TOKEN"] = self._security_token
        return headers

    async def authenticate(self) -> None:
        """Login and obtain CST + security token."""
        session = await self._ensure_session()
        await self._rate_limiter.acquire()

        async with session.post(
            f"{self.base_url}/api/v1/session",
            json={"identifier": self.email, "password": self.password},
            headers={"X-CAP-API-KEY": self.api_key, "Content-Type": "application/json"},
        ) as resp:
            if resp.status != 200:
                body = await resp.text()
                raise AuthenticationError(f"Login failed ({resp.status}): {body}")

            self._cst = resp.headers.get("CST")
            self._security_token = resp.headers.get("X-SECURITY-TOKEN")

            if not self._cst or not self._security_token:
                raise AuthenticationError("Missing CST or security token in response")

            logger.info("Authenticated with Capital.com (%s)", "DEMO" if self.demo else "LIVE")

    async def _request(
        self, method: str, path: str, json_data: dict | None = None
    ) -> dict:
        """Make authenticated API request with rate limiting."""
        if not self._circuit_breaker.allow_request():
            raise BrokerError("Circuit breaker OPEN — broker unavailable")

        if not self._cst:
            await self.authenticate()

        session = await self._ensure_session()
        await self._rate_limiter.acquire()

        url = f"{self.base_url}{path}"
        async with session.request(
            method, url, json=json_data, headers=self._auth_headers()
        ) as resp:
            if resp.status == 401:
                # Token expired — re-auth and retry once
                logger.warning("Token expired, re-authenticating...")
                await self.authenticate()
                async with session.request(
                    method, url, json=json_data, headers=self._auth_headers()
                ) as retry_resp:
                    if retry_resp.status >= 400:
                        body = await retry_resp.text()
                        self._circuit_breaker.record_failure()
                        raise BrokerError(f"API error {retry_resp.status}: {body}")
                    self._circuit_breaker.record_success()
                    return await retry_resp.json()

            if resp.status >= 400:
                body = await resp.text()
                self._circuit_breaker.record_failure()
                raise BrokerError(f"API error {resp.status} on {method} {path}: {body}")

            self._circuit_breaker.record_success()
            if resp.status == 204:
                return {}
            return await resp.json()

    # -- Account ------------------------------------------------------------

    async def get_account(self) -> AccountInfo:
        data = await self._request("GET", "/api/v1/accounts")
        acc = data["accounts"][0]
        return AccountInfo(
            account_id=acc["accountId"],
            balance=float(acc["balance"]["balance"]),
            deposit=float(acc["balance"]["deposit"]),
            profit_loss=float(acc["balance"]["profitLoss"]),
            available=float(acc["balance"]["available"]),
            currency=acc.get("currency", "EUR"),
        )

    # -- Market Data --------------------------------------------------------

    async def get_candles(
        self,
        timeframe: str = "5m",
        count: int = 200,
        epic: str = GOLD_EPIC,
    ) -> list[CandleData]:
        """Fetch historical candles for Gold."""
        resolution = TIMEFRAME_MAP.get(timeframe, timeframe)
        data = await self._request(
            "GET",
            f"/api/v1/prices/{epic}?resolution={resolution}&max={count}",
        )

        candles = []
        for p in data.get("prices", []):
            snapshot_time = p.get("snapshotTime")
            if not snapshot_time:
                logger.warning("Skipping candle with missing snapshotTime")
                continue
            try:
                ts = datetime.fromisoformat(snapshot_time.replace("Z", "+00:00"))
            except (ValueError, AttributeError) as e:
                logger.warning("Skipping candle with invalid snapshotTime %r: %s", snapshot_time, e)
                continue

            open_price = p.get("openPrice", {}) or {}
            high_price = p.get("highPrice", {}) or {}
            low_price = p.get("lowPrice", {}) or {}
            close_price = p.get("closePrice", {}) or {}

            open_bid = open_price.get("bid")
            open_ask = open_price.get("ask")
            high_bid = high_price.get("bid")
            low_bid = low_price.get("bid")
            close_bid = close_price.get("bid")

            if close_bid is None or high_bid is None or low_bid is None or open_bid is None:
                logger.warning(
                    "Skipping candle at %s: missing OHLC fields (o=%s h=%s l=%s c=%s)",
                    snapshot_time, open_bid, high_bid, low_bid, close_bid,
                )
                continue

            try:
                if open_ask is not None:
                    o = (float(open_bid) + float(open_ask)) / 2
                else:
                    o = float(open_bid)
                high_v = float(high_bid)
                low_v = float(low_bid)
                c = float(close_bid)
                v = float(p.get("lastTradedVolume", 0) or 0)
            except (TypeError, ValueError) as e:
                logger.warning("Skipping candle at %s: invalid numeric value (%s)", snapshot_time, e)
                continue

            candles.append(CandleData(timestamp=ts, open=o, high=high_v, low=low_v, close=c, volume=v))

        return candles

    async def get_candles_paginated(
        self,
        timeframe: str = "5m",
        total_count: int = 5000,
        epic: str = GOLD_EPIC,
    ) -> list[CandleData]:
        """Fetch more than 1000 candles by paginating backwards in time.

        Capital.com limits each request to max=1000 and enforces date-range
        limits per resolution. This method uses small time windows (max 500
        candles worth) to stay within API limits, then stitches results.
        """
        from datetime import timedelta

        # Capital.com enforces date-range limits per resolution.
        # Use conservative batch sizes (in candle count) that stay within limits.
        tf_seconds = {
            "1m": 60, "5m": 300, "15m": 900, "30m": 1800,
            "1h": 3600, "4h": 14400, "1d": 86400,
        }
        # Max candles per batch to stay within API date-range limits
        tf_batch_size = {
            "1m": 200, "5m": 500, "15m": 500, "30m": 500,
            "1h": 500, "4h": 500, "1d": 500,
        }
        step = tf_seconds.get(timeframe, 300)
        batch_size = tf_batch_size.get(timeframe, 500)

        all_candles: list[CandleData] = []
        to_dt = datetime.utcnow()

        remaining = total_count
        max_iterations = 30  # safety cap (5000/200 = 25 for 1m)

        for iteration in range(max_iterations):
            if remaining <= 0:
                break

            batch = min(remaining, batch_size)
            from_dt = to_dt - timedelta(seconds=step * batch)

            from_str = from_dt.strftime("%Y-%m-%dT%H:%M:%S")
            to_str = to_dt.strftime("%Y-%m-%dT%H:%M:%S")

            try:
                data = await self._request(
                    "GET",
                    f"/api/v1/prices/{epic}?resolution={TIMEFRAME_MAP.get(timeframe, timeframe)}"
                    f"&from={from_str}&to={to_str}&max={batch}",
                )
            except BrokerError as e:
                logger.warning(
                    "Paginated fetch batch %d failed (%s to %s): %s",
                    iteration + 1, from_str, to_str, e,
                )
                # Try halving batch size once on date-range error
                if "daterange" in str(e).lower() and batch > 100:
                    batch_size = batch_size // 2
                    logger.info("Reducing batch size to %d and retrying", batch_size)
                    continue
                break

            prices = data.get("prices", [])
            if not prices:
                break

            batch_candles: list[CandleData] = []
            for p in prices:
                snapshot_time = p.get("snapshotTime")
                if not snapshot_time:
                    continue
                try:
                    ts = datetime.fromisoformat(snapshot_time.replace("Z", "+00:00"))
                except (ValueError, AttributeError):
                    continue

                open_price = p.get("openPrice", {}) or {}
                high_price = p.get("highPrice", {}) or {}
                low_price = p.get("lowPrice", {}) or {}
                close_price = p.get("closePrice", {}) or {}

                open_bid = open_price.get("bid")
                open_ask = open_price.get("ask")
                high_bid = high_price.get("bid")
                low_bid = low_price.get("bid")
                close_bid = close_price.get("bid")

                if any(v is None for v in (open_bid, high_bid, low_bid, close_bid)):
                    continue

                try:
                    if open_ask is not None:
                        o = (float(open_bid) + float(open_ask)) / 2
                    else:
                        o = float(open_bid)
                    batch_candles.append(CandleData(
                        timestamp=ts,
                        open=o,
                        high=float(high_bid),
                        low=float(low_bid),
                        close=float(close_bid),
                        volume=float(p.get("lastTradedVolume", 0) or 0),
                    ))
                except (TypeError, ValueError):
                    continue

            if not batch_candles:
                break

            all_candles = batch_candles + all_candles  # prepend (older first)
            remaining -= len(batch_candles)

            # Move window back: next batch ends where this one started
            earliest = min(c.timestamp for c in batch_candles)
            to_dt = earliest.replace(tzinfo=None) - timedelta(seconds=1)

            # Only stop if API returned zero useful candles two batches in a row
            # (weekends/holidays cause sparse batches that shouldn't stop pagination)

        logger.info(
            "Paginated fetch: got %d/%d candles for %s",
            len(all_candles), total_count, timeframe,
        )
        return all_candles

    async def get_current_price(self, epic: str = GOLD_EPIC) -> dict:
        """Get current bid/ask for Gold.

        The REST API only exposes candle data, so we estimate
        bid/ask from the last 1-minute candle:
          bid  = close
          ask  = close + estimated spread
        The spread is estimated as 20% of the candle's range
        with a minimum of 0.30 (typical Gold CFD spread).
        """
        candles = await self.get_candles(timeframe="1m", count=1, epic=epic)
        if not candles:
            raise BrokerError("No price data available")
        last = candles[-1]
        candle_range = last.high - last.low
        estimated_spread = max(0.30, candle_range * 0.2)
        return {
            "bid": last.close,
            "ask": last.close + estimated_spread,
            "timestamp": last.timestamp.isoformat(),
        }

    # -- Positions ----------------------------------------------------------

    async def get_positions(self) -> list[Position]:
        data = await self._request("GET", "/api/v1/positions")
        positions = []
        for p in data.get("positions", []):
            pos = p["position"]
            market = p.get("market", {})
            positions.append(Position(
                deal_id=pos["dealId"],
                direction=pos["direction"],
                size=float(pos["size"]),
                open_level=float(pos["level"]),
                current_level=float(market.get("bid", pos["level"])),
                stop_level=float(pos["stopLevel"]) if pos.get("stopLevel") else None,
                limit_level=float(pos["limitLevel"]) if pos.get("limitLevel") else None,
                profit=float(pos.get("profit", 0)),
                currency=pos.get("currency", "EUR"),
                created_at=pos.get("createdDateUTC", ""),
            ))
        return positions

    async def open_position(
        self,
        direction: str,
        size: float,
        stop_level: float | None = None,
        limit_level: float | None = None,
        epic: str = GOLD_EPIC,
    ) -> OrderResult:
        """Open a new position (market order)."""
        payload: dict[str, Any] = {
            "epic": epic,
            "direction": direction,
            "size": size,
        }
        if stop_level is not None:
            payload["stopLevel"] = stop_level
        if limit_level is not None:
            payload["limitLevel"] = limit_level

        data = await self._request("POST", "/api/v1/positions", payload)
        deal_ref = data.get("dealReference", "")

        # Get confirmation
        confirm = await self._get_confirmation(deal_ref)
        return confirm

    async def close_position(self, deal_id: str) -> OrderResult:
        """Close an existing position."""
        data = await self._request("DELETE", f"/api/v1/positions/{deal_id}")
        deal_ref = data.get("dealReference", "")
        return await self._get_confirmation(deal_ref)

    async def modify_position(
        self,
        deal_id: str,
        stop_level: float | None = None,
        limit_level: float | None = None,
    ) -> OrderResult:
        """Modify stop/limit on existing position."""
        payload: dict[str, Any] = {}
        if stop_level is not None:
            payload["stopLevel"] = stop_level
        if limit_level is not None:
            payload["limitLevel"] = limit_level

        data = await self._request("PUT", f"/api/v1/positions/{deal_id}", payload)
        deal_ref = data.get("dealReference", "")
        return await self._get_confirmation(deal_ref)

    async def close_all_positions(self) -> list[OrderResult]:
        """Close all open positions (kill switch)."""
        positions = await self.get_positions()
        results = []
        for pos in positions:
            try:
                result = await self.close_position(pos.deal_id)
                results.append(result)
            except BrokerError as e:
                logger.error("Failed to close position %s: %s", pos.deal_id, e)
        return results

    async def _get_confirmation(self, deal_reference: str) -> OrderResult:
        """Poll for deal confirmation."""
        for attempt in range(5):
            await asyncio.sleep(0.5)
            try:
                data = await self._request(
                    "GET", f"/api/v1/confirms/{deal_reference}"
                )
                return OrderResult(
                    deal_reference=deal_reference,
                    deal_id=data.get("dealId", ""),
                    status=data.get("dealStatus", "UNKNOWN"),
                    reason=data.get("reason", ""),
                    level=float(data.get("level", 0)),
                    affected_deals=data.get("affectedDeals", []),
                )
            except BrokerError:
                if attempt == 4:
                    raise
                continue

        raise BrokerError(f"Confirmation timeout for {deal_reference}")

    # -- WebSocket Streaming ------------------------------------------------

    async def start_price_stream(
        self,
        callback: Callable[[dict], Any],
        epic: str = GOLD_EPIC,
    ) -> None:
        """Connect to WebSocket and stream live Gold prices."""
        if not self._cst:
            await self.authenticate()

        ws_retries = 0
        max_ws_retries = 20

        while True:
            if ws_retries >= max_ws_retries:
                logger.critical(
                    "WebSocket: max retries (%d) reached — stopping price stream",
                    max_ws_retries,
                )
                return

            try:
                async with websockets.connect(WS_URL) as ws:
                    self._ws = ws
                    ws_retries = 0  # Reset on successful connect
                    logger.info("WebSocket connected")

                    # Subscribe to Gold market data
                    subscribe_payload = {
                        "destination": "marketData.subscribe",
                        "correlationId": "1",
                        "cst": self._cst,
                        "securityToken": self._security_token,
                        "payload": {"epics": [epic]},
                    }
                    subscribe_msg = json.dumps(subscribe_payload)
                    # Mask tokens before any debug-level logging
                    if logger.isEnabledFor(logging.DEBUG):
                        masked = {**subscribe_payload, "cst": "***", "securityToken": "***"}
                        logger.debug("Sending subscribe message: %s", masked)
                    await ws.send(subscribe_msg)

                    async for message in ws:
                        try:
                            data = json.loads(message)
                            if data.get("destination") == "quote":
                                await callback(data.get("payload", {}))
                        except json.JSONDecodeError:
                            logger.warning("Invalid WebSocket message: %s", message[:100])

            except (websockets.ConnectionClosed, ConnectionError) as e:
                ws_retries += 1
                backoff = min(5 * 2 ** min(ws_retries - 1, 4), 120)
                logger.warning(
                    "WebSocket disconnected: %s. Retry %d/%d in %ds...",
                    e, ws_retries, max_ws_retries, backoff,
                )
                await asyncio.sleep(backoff)
                # Re-authenticate before reconnecting (tokens may be stale)
                try:
                    await self.authenticate()
                except AuthenticationError:
                    logger.error("Re-auth failed, will retry on next cycle")
            except Exception as e:
                ws_retries += 1
                backoff = min(5 * 2 ** min(ws_retries - 1, 4), 120)
                logger.warning(
                    "WebSocket error: %s. Retry %d/%d in %ds...",
                    e, ws_retries, max_ws_retries, backoff,
                )
                await asyncio.sleep(backoff)
                try:
                    await self.authenticate()
                except AuthenticationError:
                    logger.error("Re-auth failed, will retry on next cycle")
            finally:
                # Avoid stale references — the context manager has closed ws
                self._ws = None

    async def stop_price_stream(self) -> None:
        if self._ws:
            await self._ws.close()
            self._ws = None

    # -- History ------------------------------------------------------------

    async def get_transaction_history(
        self, max_results: int = 50
    ) -> list[dict]:
        data = await self._request(
            "GET",
            f"/api/v1/history/transactions?maxSpanInSeconds=604800&pageSize={max_results}",
        )
        return data.get("transactions", [])

    # -- Cleanup ------------------------------------------------------------

    async def close(self) -> None:
        await self.stop_price_stream()
        if self._session and not self._session.closed:
            await self._session.close()
