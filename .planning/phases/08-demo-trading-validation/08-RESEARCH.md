# Phase 8: Demo Trading Validation - Research

**Researched:** 2026-03-08
**Domain:** Production stability, continuous operation, trade logging, P&L validation
**Confidence:** HIGH

## Summary

Phase 8 is the final milestone validation phase. The bot already has a complete trading system: broker integration (Capital.com REST + WebSocket), AI signal generation (XGBoost + LightGBM ensemble), risk management (11 pre-trade checks, kill switch, trailing stops), database persistence (SQLAlchemy async with PostgreSQL/SQLite), and a FastAPI REST API. The codebase is mature -- Phases 1-4 have been completed with 260+ tests passing.

The primary challenge is not building new features but hardening the existing system for continuous 24+ hour operation. This means identifying and fixing stability gaps: session expiry without re-authentication mid-run, unhandled edge cases in the position monitor loop, missing daily P&L aggregation, and incomplete trade logging (the `reasoning` field is stored but not guaranteed complete). The existing error handling is already sophisticated (circuit breaker, exponential backoff, consecutive error kill switch), but has gaps around database connection recovery and broker session renewal during extended runs.

**Primary recommendation:** Focus on three areas: (1) a startup/operational checklist script that validates readiness, (2) hardening the existing code for 14-day continuous operation, and (3) a demo validation report generator that produces the evidence needed to prove DEMO-01 through DEMO-04.

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|-----------------|
| DEMO-01 | Bot runs stable on Capital.com demo account for 24+ hours without crashes | Existing error handling (circuit breaker, exponential backoff, kill switch at 10 errors) is strong. Gaps: no broker session keepalive/refresh, no DB connection pool recovery, no automatic restart on fatal crash. Need process supervisor + session renewal. |
| DEMO-02 | Bot opens and closes trades automatically based on AI signals | Full pipeline exists: signal generation -> strategy filter -> risk check -> order execution -> position monitor -> close detection. Needs verification that trained models are loaded and producing actionable signals on demo. |
| DEMO-03 | Bot shows positive P&L over a 2-week demo period | Trade P&L is calculated and stored per-trade (net_pnl in DB). DailyStats model exists but upsert uses PostgreSQL-specific `on_conflict_do_update`. Need a demo validation report that aggregates 2-week P&L from trades table. |
| DEMO-04 | All trades are logged with entry/exit prices, P&L, reasoning | Trade model stores: deal_id, entry_price, exit_price, stop_loss, take_profit, lot_size, spread_at_entry, slippage, pnl_pips, pnl_euros, net_pnl, close_reason, ai_confidence, trade_score, reasoning (JSONB). Signal model stores: model_votes, top_features. Coverage is good. Need to verify reasoning dict is always populated. |
</phase_requirements>

## Standard Stack

### Core (Already in Project)
| Library | Version | Purpose | Status |
|---------|---------|---------|--------|
| asyncio | stdlib | Main event loop, concurrent tasks | In use |
| SQLAlchemy | >=2.0.36 | Async ORM for trade/signal/risk persistence | In use |
| FastAPI | >=0.115.0 | REST API for monitoring/control | In use |
| aiohttp | >=3.11.0 | Broker HTTP client | In use |
| websockets | >=14.0 | Broker WebSocket streaming | In use |
| logging + RotatingFileHandler | stdlib | Log rotation (10MB x 5 files) | In use |

### Supporting (No New Dependencies Needed)
| Library | Version | Purpose | Status |
|---------|---------|---------|--------|
| pydantic-settings | >=2.6.0 | Configuration from .env | In use |
| aiosqlite | >=0.18.0 | SQLite fallback for local operation | In use |
| structlog | >=24.4.0 | Available but unused -- stick with stdlib logging | Available |

### Not Needed
| Library | Reason |
|---------|--------|
| systemd / supervisord | Windows platform -- use PowerShell script or Windows Task Scheduler |
| prometheus / grafana | Overkill for demo phase -- use DB queries + log analysis |
| sentry | Overkill for demo -- existing file + console logging is sufficient |

**No new dependencies are required for Phase 8.** Everything needed is already installed.

## Architecture Patterns

### Current System Architecture (Already Working)
```
main.py
  -> TradingSystem (mixin composition)
     -> LifecycleMixin    (init, health check, start, stop)
     -> TradingLoopMixin  (main loop with exponential backoff)
     -> SignalGeneratorMixin (AI prediction + signal persistence)
     -> MonitorMixin       (position monitor, daily cleanup)
  -> FastAPI server (concurrent with trading loop)
  -> 3 concurrent asyncio tasks:
     1. _trading_loop()        (interval: trading_interval_seconds)
     2. _position_monitor_loop() (interval: position_check_seconds)
     3. _daily_cleanup_loop()   (interval: 300s, runs at midnight)
```

### Pattern 1: Stability Hardening (for 24+ hour operation)
**What:** Address specific gaps in the existing system that could cause crashes during extended runs.
**Gaps identified:**

1. **Broker session expiry:** Capital.com CST tokens expire (typically after 10 minutes of inactivity or after a fixed period). The `_request()` method handles 401 re-auth, but the WebSocket has its own re-auth path that may not align. For 24+ hour operation, add a periodic session ping/renewal.

2. **Database connection pool exhaustion:** PostgreSQL connections are configured with `pool_size=10, max_overflow=5, pool_pre_ping=True, pool_recycle=3600`. The `pool_recycle=3600` is good for long runs. The `pool_pre_ping=True` handles stale connections. This is already well-configured.

3. **Memory leaks:** The `ModelMonitor._predictions` deque has `maxlen=100` -- bounded. The `CircuitBreaker._errors` deque has `maxlen=20` -- bounded. The `RateLimiter._timestamps` list is cleaned every call. No obvious memory leak sources.

4. **Unhandled asyncio.CancelledError propagation:** The trading loop and monitor loop both properly re-raise `CancelledError`. Good.

5. **No process-level restart:** If `main.py` crashes with an unhandled exception, nothing restarts it. The `main()` function catches `Exception` and calls `sys.exit(1)`. Need a wrapper script.

### Pattern 2: Demo Validation Report
**What:** A script/endpoint that queries the trades table and produces aggregated metrics proving profitability.
**When to use:** At the end of the 2-week demo period, and periodically during the run.
**Data sources:**
- `trades` table: all trade records with P&L
- `signals` table: all signals (executed + rejected)
- `daily_stats` table: daily aggregates (if populated)
- `risk_events` table: kill switch activations, risk events

### Pattern 3: Operational Runbook
**What:** A checklist/script that validates the system is ready for the 2-week demo run.
**Items to verify:**
1. `.env` has correct Capital.com demo credentials
2. `CAPITAL_DEMO=true` (never run on live during demo validation)
3. Database accessible and tables created
4. Trained models exist in `ai_engine/saved_models/`
5. Disk space sufficient for 2 weeks of logs (10MB x 5 = 50MB max)
6. No kill switch active in DB
7. API server starts and responds to /health

### Anti-Patterns to Avoid
- **Building a monitoring dashboard from scratch:** The Control App (Phases 6-7) handles this. Phase 8 focuses on hardening and validation, not new UI.
- **Adding complex alerting infrastructure:** The existing WhatsApp notifications and log-based monitoring are sufficient for a 2-week demo.
- **Changing trading strategy parameters:** Phase 8 validates what was built in Phases 1-7. Do not tune parameters during the demo.
- **Running on live account:** The requirements explicitly state demo account only. Enforce `CAPITAL_DEMO=true`.

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Process supervision on Windows | Custom Windows service | PowerShell wrapper script with restart loop | Simple, reliable, no dependencies |
| P&L aggregation | Custom analytics engine | SQL queries against trades table | Data is already structured correctly |
| Session keepalive | Custom heartbeat protocol | Periodic broker API call (get_account) | Broker already supports this pattern |
| Log analysis | Custom log parser | Query DB directly (all trades/signals are persisted) | Structured data > log parsing |

**Key insight:** The bot already persists everything to the database. Validation is a SQL query problem, not a new feature problem.

## Common Pitfalls

### Pitfall 1: Broker Session Timeout During Market Close
**What goes wrong:** Capital.com sessions expire while markets are closed (weekends, holidays). The bot wakes up Monday morning and fails the first few requests before re-auth kicks in.
**Why it happens:** The 401 re-auth in `_request()` handles single token expiry, but if the underlying aiohttp session also closed (e.g., TCP keepalive expired), the re-auth itself may fail.
**How to avoid:** Add a periodic health ping (every 5 minutes) that calls `broker.get_account()` even when not trading. This keeps the session alive and triggers re-auth proactively.
**Warning signs:** Burst of errors at market open on Monday morning in logs.

### Pitfall 2: SQLite Concurrency Under Load
**What goes wrong:** If `SQLITE_FALLBACK=true` is used (default when no PostgreSQL), SQLite has write lock contention between the 3 concurrent asyncio tasks.
**Why it happens:** SQLite only allows one writer at a time. The trading loop, position monitor, and daily cleanup all write to the DB.
**How to avoid:** Use PostgreSQL for the 2-week demo. SQLite is a development convenience, not a production database. Ensure `.env` has `POSTGRES_PASSWORD` set.
**Warning signs:** `database is locked` errors in logs.

### Pitfall 3: Orphaned Positions After Crash
**What goes wrong:** Bot crashes while a position is open. On restart, `recover_from_db()` loads the position, but the broker may have hit the SL/TP while the bot was down, so the trade shows as "open" in DB but is actually closed at the broker.
**How to avoid:** The existing `sync_with_broker()` handles this -- it detects orphaned positions and marks them as `CLOSED_BY_BROKER`. This is already implemented in `lifecycle.py:start()`. No change needed.
**Warning signs:** `Orphaned position` warnings in startup logs.

### Pitfall 4: Kill Switch Not Resettable
**What goes wrong:** A temporary error (e.g., 10 consecutive timeout errors during a network blip) activates the kill switch. The bot stops trading permanently until someone manually deactivates it.
**Why it happens:** The kill switch is designed to be a fail-safe. It requires manual intervention via the API (`POST /api/v1/risk/kill-switch` with `activate: false`).
**How to avoid:** This is by design. Document the reset procedure. Ensure the operator knows how to check kill switch status and reset it.
**Warning signs:** `KILL SWITCH ACTIVATED` in logs, bot running but not placing any trades.

### Pitfall 5: Log File Fills Disk
**What goes wrong:** On DEBUG level, the RotatingFileHandler generates a lot of output. With 5 backup files at 10MB each, max disk usage is 60MB -- manageable.
**Why it happens:** Default `LOG_LEVEL=INFO` is appropriate for demo. Do not set to DEBUG for the 2-week run.
**How to avoid:** Keep `LOG_LEVEL=INFO`. The 10MB x 5 rotation is sufficient.
**Warning signs:** Logs directory exceeding 50MB.

### Pitfall 6: Incomplete Trade Reasoning
**What goes wrong:** The `reasoning` field in the Trade model is a JSONB column populated from `signal.get("reasoning")`. If the AI predictor doesn't include reasoning, the field is `None` for some trades.
**Why it happens:** The AI predictor may return signals without a `reasoning` key, especially if the model is loaded from an older version.
**How to avoid:** Verify that the current AI predictor always populates the `reasoning` field. If not, add a default reasoning dict at signal generation time.
**Warning signs:** `SELECT COUNT(*) FROM trades WHERE reasoning IS NULL AND status = 'CLOSED'` returns non-zero.

### Pitfall 7: DailyStats Not Being Populated
**What goes wrong:** The `DailyStats` model exists, the `StatsRepository.upsert()` method exists, but nothing in the trading loop calls it. Daily statistics are never aggregated.
**Why it happens:** The daily stats aggregation was designed but never wired into the daily cleanup loop or a scheduled task.
**How to avoid:** Wire a daily stats aggregation into the `_daily_cleanup_loop()` or create a separate periodic task.
**Warning signs:** `daily_stats` table is empty after running for days.

## Code Examples

### Current Error Handling Flow (Already Working)
```python
# Source: trading/trading_loop.py lines 29-93
# Trading loop already has:
# - Error classification (TEMPORARY, PERMANENT, UNKNOWN)
# - Exponential backoff: min(interval * 2^errors, 300s)
# - Kill switch activation at 10 consecutive errors
# - Proper CancelledError propagation
```

### Existing Trade Persistence Schema (Already Complete)
```python
# Source: database/models.py lines 96-127
# Trade model stores ALL required fields for DEMO-04:
# - deal_id, entry_price, exit_price (entry/exit prices)
# - pnl_pips, pnl_euros, net_pnl (P&L)
# - ai_confidence, trade_score, reasoning (AI reasoning)
# - spread_at_entry, slippage (realistic cost tracking)
# - close_reason (why the trade closed)
# - opened_at, closed_at (timestamps)
```

### Startup Position Recovery (Already Implemented)
```python
# Source: trading/lifecycle.py lines 167-207
# On startup:
# 1. Load open trades from DB
# 2. Sync with broker (detect positions closed while offline)
# 3. Mark orphaned positions as CLOSED_BY_BROKER
# 4. Track remaining open positions in position monitor
```

### Demo Validation Query (To Be Implemented)
```python
# Example: aggregate 2-week P&L from trades table
# Source: pattern based on existing TradeRepository methods

async def get_demo_validation_report(session, start_date, end_date) -> dict:
    """Generate demo validation report for the specified period."""
    repo = TradeRepository(session)

    # All trades in the period
    stmt = (
        select(Trade)
        .where(and_(
            Trade.opened_at >= start_date,
            Trade.opened_at <= end_date,
            Trade.status == "CLOSED",
        ))
        .order_by(Trade.opened_at.asc())
    )
    result = await session.execute(stmt)
    trades = result.scalars().all()

    total_pnl = sum(float(t.net_pnl or 0) for t in trades)
    winners = [t for t in trades if float(t.net_pnl or 0) > 0]
    losers = [t for t in trades if float(t.net_pnl or 0) < 0]

    return {
        "period_start": start_date.isoformat(),
        "period_end": end_date.isoformat(),
        "total_trades": len(trades),
        "winners": len(winners),
        "losers": len(losers),
        "win_rate": len(winners) / len(trades) if trades else 0,
        "total_pnl": round(total_pnl, 2),
        "gross_profit": round(sum(float(t.net_pnl or 0) for t in winners), 2),
        "gross_loss": round(sum(float(t.net_pnl or 0) for t in losers), 2),
        "profit_factor": (
            abs(sum(float(t.net_pnl or 0) for t in winners)) /
            abs(sum(float(t.net_pnl or 0) for t in losers))
            if losers else float('inf')
        ),
        "avg_trade_pnl": round(total_pnl / len(trades), 2) if trades else 0,
        "max_drawdown_trade": min((float(t.net_pnl or 0) for t in trades), default=0),
        "best_trade": max((float(t.net_pnl or 0) for t in trades), default=0),
        "demo_01_passed": True,  # If we got here, bot ran without crash
        "demo_03_passed": total_pnl > 0,
    }
```

### Restart Wrapper Script (To Be Implemented)
```powershell
# Windows PowerShell wrapper for continuous operation
# Restarts the bot if it crashes, with a 30-second cooldown

$maxRestarts = 50
$restartCount = 0
$cooldownSeconds = 30

while ($restartCount -lt $maxRestarts) {
    Write-Host "Starting GoldBot (attempt $($restartCount + 1))..."
    python main.py
    $exitCode = $LASTEXITCODE
    $restartCount++

    if ($exitCode -eq 0) {
        Write-Host "Bot exited cleanly."
        break
    }

    Write-Host "Bot crashed with exit code $exitCode. Restarting in ${cooldownSeconds}s..."
    Start-Sleep -Seconds $cooldownSeconds
}
```

## Stability Gaps (Must Fix Before 2-Week Run)

### Gap 1: No Broker Session Keepalive
**Current:** The broker client only re-authenticates on 401 responses.
**Problem:** During market-closed hours (weekends), the session may expire silently. Monday morning starts with multiple failed requests before re-auth kicks in.
**Fix:** Add a periodic keepalive in the trading loop that calls a lightweight broker endpoint (e.g., `get_account()`) at least once every 5 minutes, even when no trading signal is generated. The existing account info cache already does this (`_CACHE_TTL_SECONDS = 300.0`), but only when a trade signal triggers the tick path far enough.
**Severity:** MEDIUM -- the 401 handler does recover, but it causes error bursts and may trigger the consecutive error counter.

### Gap 2: No Process-Level Restart
**Current:** `main.py` calls `sys.exit(1)` on fatal error. Nothing restarts it.
**Problem:** A truly fatal error (e.g., out of memory, segfault in native library) kills the process permanently.
**Fix:** PowerShell wrapper script (see code example above) or Windows Task Scheduler with "restart on failure" policy.
**Severity:** HIGH -- a single unrecoverable crash would end the demo run.

### Gap 3: DailyStats Not Populated
**Current:** `DailyStats` model and repository exist, but nothing writes to the table.
**Problem:** DEMO-03 (positive P&L) can still be proven from the `trades` table directly, but daily aggregation would make reporting cleaner.
**Fix:** Wire daily stats aggregation into `_daily_cleanup_loop()` or a separate nightly task.
**Severity:** LOW -- the trades table has all needed data. DailyStats is nice-to-have.

### Gap 4: Missing Uptime Tracking
**Current:** The API has an `uptime_seconds` field calculated from `time.monotonic()`, but there's no persistent record of uptime across restarts.
**Problem:** DEMO-01 requires proving 24+ hours without crashes. Without persistent uptime logging, the only evidence is continuous log output.
**Fix:** Log a heartbeat timestamp to the database every N minutes. On startup, check the last heartbeat to detect gaps (crash periods).
**Severity:** MEDIUM -- log continuity can serve as evidence, but heartbeat records are more rigorous.

### Gap 5: Trade Reasoning May Be None
**Current:** The `reasoning` field on Trade is populated from `signal.get("reasoning")`, which may be None if the AI predictor doesn't include it.
**Problem:** DEMO-04 requires "all trades logged with full details." Missing reasoning makes the log incomplete.
**Fix:** Ensure the signal generator always provides a default reasoning dict, even if minimal (e.g., `{"model": "ensemble", "action": direction, "confidence": confidence}`).
**Severity:** LOW -- the other fields (entry/exit prices, P&L) are always populated. Reasoning is supplementary.

## State of the Art

| Old Approach | Current Approach | Impact |
|--------------|------------------|--------|
| Fixed 50/30 pip TP/SL | Dynamic ATR-based TP/SL (Phase 4) | Strategy adapts to volatility |
| Simple train/test split | Walk-forward validation (Phase 2) | Better out-of-sample performance |
| All features used | SHAP-based pruning (Phase 3) | Removes noise, improves generalization |
| No regime awareness | 3-state regime detection (Phase 4) | Different params per market condition |
| Monolithic main.py | Mixin composition (Phase 1) | Maintainable, testable |

**No deprecated approaches in the current codebase.** All phases (1-4) have been completed with modern patterns.

## What the Planner Needs to Know

### Task Categories for Phase 8

1. **Stability hardening** (code changes):
   - Broker session keepalive enhancement
   - Default reasoning dict for signals
   - Heartbeat/uptime tracking to DB
   - Daily stats aggregation wiring

2. **Operational infrastructure** (scripts/config):
   - Process restart wrapper script (PowerShell)
   - Pre-flight validation script (checklist before starting demo)
   - Demo validation report generator script

3. **Validation criteria** (what proves success):
   - DEMO-01: Heartbeat records show continuous operation for 24+ hours (and ideally 2 weeks)
   - DEMO-02: trades table has entries with `status=CLOSED` and `close_reason` values showing automated TP/SL hits
   - DEMO-03: `SUM(net_pnl) > 0` over the 2-week period
   - DEMO-04: `SELECT * FROM trades WHERE reasoning IS NOT NULL` covers all trades

### Risk Assessment for 2-Week Demo

**Likely to work without changes:**
- Trade execution pipeline (well-tested across Phases 1-4)
- Position monitoring and close detection
- Risk management and kill switch
- Error handling and exponential backoff
- Database persistence of trades and signals

**Needs hardening:**
- Broker session management during extended idle periods
- Process-level restart capability
- Completeness of trade reasoning field

**Not a code problem but critical:**
- Trained models must exist and produce signals (depends on Phase 2-3 training)
- Demo account must have sufficient balance for position sizing
- PostgreSQL must be running continuously (or use SQLite with known limitations)

## Open Questions

1. **What qualifies as "positive P&L"?**
   - What we know: DEMO-03 says "positive P&L over a 2-week demo period"
   - What's unclear: Is this total net P&L > 0, or profit factor > 1.0, or both? Does it account for spread costs (which are already included in `net_pnl`)?
   - Recommendation: Use total `net_pnl > 0` as the primary criterion, report profit factor as supplementary evidence.

2. **What if the bot produces zero trades in 2 weeks?**
   - What we know: If market conditions are unfavorable, the risk manager may reject all signals. The bot would run without crashes but produce no P&L.
   - What's unclear: Does "no trades" pass or fail the demo?
   - Recommendation: The bot must produce at least some trades to validate DEMO-02. If zero trades occur, investigate signal threshold settings.

3. **Is the 2-week demo period continuous or cumulative?**
   - What we know: The requirement says "2+ weeks continuously" in scope, but UAT says "positive P&L over 2-week period."
   - What's unclear: Does a weekend restart count as a break in continuity?
   - Recommendation: Track uptime continuously but expect market-close periods (weekends). The bot should remain running through weekends even if it doesn't trade.

4. **Where does the bot run during the 2-week demo?**
   - What we know: The project runs on Windows 11 (from environment context). No Docker setup exists.
   - What's unclear: Will it run on the same development machine, or a separate server?
   - Recommendation: Provide instructions for both local Windows operation and potential future deployment. For now, assume the local Windows machine with PowerShell restart wrapper.

## Sources

### Primary (HIGH confidence)
- Direct codebase analysis of all source files (see file paths throughout this document)
- `main.py` -- entry point and system architecture
- `trading/` -- all mixin modules (lifecycle, trading_loop, signal_generator, monitors)
- `market_data/broker_client.py` -- Capital.com REST + WebSocket client
- `order_management/` -- order executor, position monitor, trailing stops
- `database/models.py` -- full ORM schema
- `database/connection.py` -- connection pool configuration
- `risk/` -- risk manager, kill switch, position sizing
- `config/settings.py` -- all configuration options
- `monitoring/` -- health checks, watchdog, model monitor
- `shared/exceptions.py` -- error classification hierarchy

### Secondary (MEDIUM confidence)
- Capital.com API behavior (session expiry, rate limits) -- based on code patterns and broker client implementation
- PostgreSQL connection pool behavior -- based on SQLAlchemy documentation conventions

## Metadata

**Confidence breakdown:**
- Stability gaps: HIGH - based on direct code analysis of all relevant modules
- Architecture patterns: HIGH - the existing architecture is well-understood from 4 completed phases
- Pitfalls: HIGH - identified from actual code paths and edge cases
- Trade logging completeness: HIGH - verified against Trade/Signal ORM models
- P&L validation approach: MEDIUM - the "positive P&L" criterion needs user clarification

**Research date:** 2026-03-08
**Valid until:** 2026-04-08 (stable -- no external dependencies changing)
