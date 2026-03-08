# Phase 6: Control App -- Core Interface - Research

**Researched:** 2026-03-08
**Domain:** React frontend unification with bot FastAPI backend, WebSocket real-time transport, start/stop control
**Confidence:** HIGH

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|-----------------|
| CTRL-01 | React Control App connects to bot API (not duplicate backend) | Rewrite `client.ts` to call main bot API at port 8000, remove control app backend dependency, map existing UI contracts to bot API schemas |
| CTRL-02 | User can start/stop bot from web interface | Add `/api/v1/system/start` endpoint to main bot API (only `/system/stop` exists today), wire QuickActionsPanel to new unified API |
| CTRL-03 | User can see live bot status (running/stopped, current positions, P&L) | Combine `/status`, `/orders/positions`, `/orders/summary` into dashboard polling; add WebSocket `/ws/status` for push updates |
</phase_requirements>

## Summary

Phase 6 is an integration/unification phase, not a greenfield build. The control app frontend already exists with a polished UI (dashboard, KPI cards, action buttons, chart panel, activity feed, error panel, sidebar navigation, theming, login gate). The backend also exists as a separate FastAPI service (`goldbot-control-app/backend/`) running on port 8060 with its own SQLite database, its own auth (`X-Control-Token`), and a `GoldBotAdapter` that is a stub -- it tracks state in-memory and does not actually call the real trading system.

The main bot already has a fully functional FastAPI API (`api/`) running on port 8000 with real endpoints: `/api/v1/health`, `/api/v1/status`, `/api/v1/orders/positions`, `/api/v1/orders/summary`, `/api/v1/orders/history`, `/api/v1/market/price`, `/api/v1/market/candles`, `/api/v1/market/signal`, `/api/v1/market/model-info`, `/api/v1/system/stop`, `/api/v1/risk/kill-switch`, `/api/v1/risk/status`. Auth uses `X-API-Key` header.

The core work is: (1) rewrite `frontend/src/api/client.ts` to call the main bot API instead of the control app backend, (2) add missing endpoints to the main bot API (notably `/system/start` and a unified status payload matching what the frontend expects), (3) add a WebSocket endpoint to the main bot API for real-time push updates, and (4) update shared type contracts to align with the main bot API schemas.

**Primary recommendation:** Do NOT rewrite the frontend UI components. Instead, create an API adapter layer in `client.ts` that maps main bot API responses to existing frontend type contracts. Add 2-3 new endpoints to the main bot API. Add a single `/ws/status` WebSocket endpoint for real-time status push. The control app backend (`goldbot-control-app/backend/`) becomes dead code after this phase.

## Standard Stack

### Core
| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| FastAPI | >=0.115.0 | Bot API server (REST + WebSocket) | Already in use in `api/app.py`; native WebSocket support built-in |
| React | 18.3.1 | Frontend UI | Already in use; no change needed |
| TypeScript | 5.6.3 | Frontend type safety | Already in use; no change needed |
| Vite | 5.4.10 | Frontend build tool | Already in use; no change needed |
| Browser WebSocket API | Standard | Real-time client connection | Native, no extra dependency needed |
| uvicorn[standard] | >=0.32.0 | ASGI server with WebSocket support | Already in requirements.txt |
| websockets | >=14.0 | Python WebSocket library (uvicorn dependency) | Already in requirements.txt |

### Supporting
| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| Pydantic v2 | >=2.10.0 | API schema validation | Already used for all API schemas |
| asyncio | stdlib | WebSocket broadcast loop | For periodic status push to connected clients |

### Alternatives Considered
| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| Browser WebSocket | socket.io-client | Adds 40KB+ dependency, overkill for single-channel status push |
| Polling (current) | WebSocket only | Current 250ms polling works but wastes bandwidth; WebSocket is better for push |
| SSE (Server-Sent Events) | WebSocket | SSE is simpler but unidirectional; WebSocket allows future command sending |

## Architecture Patterns

### Current Architecture (Problem)
```
Frontend (React, port 5173)
    |
    v
Control App Backend (FastAPI, port 8060)  <-- DUPLICATE, stub adapter
    |
    v (reads SQLite directly, in-memory state)
GoldBotAdapter (in-memory fake state)

Main Bot (FastAPI, port 8000)  <-- REAL, connected to TradingSystem
    |
    v
TradingSystem -> Broker, DB, AI
```

### Target Architecture (Solution)
```
Frontend (React, port 5173)
    |
    +---> Main Bot REST API (port 8000, /api/v1/*)
    |
    +---> Main Bot WebSocket (port 8000, /ws/status)
    |
    v
TradingSystem -> Broker, DB, AI
```

### Recommended Changes by File

**Main Bot API -- New/Modified Files:**
```
api/
  app.py              # Add WebSocket route, update CORS for WS
  routers/
    system.py          # Add POST /system/start endpoint
    websocket.py       # NEW: WebSocket endpoint /ws/status
  schemas/
    system.py          # Add BotControlResponse schema
    websocket.py       # NEW: WebSocket message schemas
```

**Frontend -- Modified Files:**
```
goldbot-control-app/frontend/src/
  api/
    client.ts          # REWRITE: point to main bot API, map responses
  hooks/
    useWebSocket.ts    # NEW: WebSocket connection hook
    useDashboardData.ts # MODIFY: use WebSocket for status, REST for initial load
  types/
    api.ts             # NEW: main bot API response types (or update shared/types.ts)
```

**Dead Code (mark/remove):**
```
goldbot-control-app/backend/     # Entire directory becomes unused
goldbot-control-app/integration/ # GoldBotAdapter no longer needed
goldbot-control-app/database/    # Control app SQLite no longer needed
```

### Pattern 1: WebSocket Status Broadcast
**What:** Server-side periodic broadcast of system status to all connected WebSocket clients.
**When to use:** For CTRL-03 live status display.
**Example:**
```python
# api/routers/websocket.py
import asyncio
import json
import logging
from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from api.dependencies import get_trading_system, get_start_time

logger = logging.getLogger(__name__)
router = APIRouter()

class ConnectionManager:
    def __init__(self):
        self.active_connections: list[WebSocket] = []

    async def connect(self, websocket: WebSocket):
        await websocket.accept()
        self.active_connections.append(websocket)

    def disconnect(self, websocket: WebSocket):
        self.active_connections.remove(websocket)

    async def broadcast(self, message: dict):
        dead = []
        for connection in self.active_connections:
            try:
                await connection.send_json(message)
            except Exception:
                dead.append(connection)
        for conn in dead:
            self.active_connections.remove(conn)

manager = ConnectionManager()

@router.websocket("/ws/status")
async def websocket_status(websocket: WebSocket):
    await manager.connect(websocket)
    try:
        while True:
            # Send status every 2 seconds
            try:
                system = get_trading_system()
                status = {
                    "type": "status",
                    "trading_active": system._running,
                    "open_positions": system.orders.get_open_count(),
                    "kill_switch_active": system.risk.kill_switch.is_active,
                    # ... more fields
                }
                await websocket.send_json(status)
            except Exception as e:
                await websocket.send_json({"type": "error", "message": str(e)})
            await asyncio.sleep(2)
    except WebSocketDisconnect:
        manager.disconnect(websocket)
```

### Pattern 2: Frontend API Adapter (Response Mapping)
**What:** Map main bot API responses to existing frontend type contracts to avoid rewriting UI components.
**When to use:** For CTRL-01 unification.
**Example:**
```typescript
// Map main bot /status response to existing BotStatusResponse type
interface MainBotStatus {
  trading_active: boolean;
  mode: string;
  kill_switch_active: boolean;
  open_positions: number;
  uptime_seconds: number;
  components: Array<{ name: string; status: string; detail: string }>;
}

function mapToControlStatus(botStatus: MainBotStatus): BotStatusResponse {
  return {
    state: botStatus.trading_active ? "RUNNING" : "STOPPED",
    uptime_sec: Math.round(botStatus.uptime_seconds),
    last_heartbeat: new Date().toISOString(),
    active_strategy: "xau-usd-intraday-v1",
    open_positions: botStatus.open_positions,
    risk_state: botStatus.kill_switch_active ? "kill_switch" : "normal",
    last_error: null,
  };
}
```

### Pattern 3: Start Endpoint Design
**What:** The main bot API has `/system/stop` but NO `/system/start`. Starting requires careful design because the trading loop runs as the main process.
**When to use:** For CTRL-02 start/stop controls.
**Key insight:** The bot starts via `system.start()` which runs `asyncio.gather(_trading_loop, _position_monitor_loop, _daily_cleanup_loop)`. Stopping sets `_running = False`. Restarting means re-running those coroutines.
```python
# api/routers/system.py -- add start endpoint
@router.post("/system/start")
async def start_system(system=Depends(get_trading_system)) -> dict:
    """Start/resume the trading system."""
    if system._running:
        return {"success": False, "message": "Trading system already running"}

    # Re-run the background loops
    system._running = True
    import asyncio
    asyncio.create_task(system._trading_loop())
    asyncio.create_task(system._position_monitor_loop())
    asyncio.create_task(system._daily_cleanup_loop())
    return {"success": True, "message": "Trading system start requested"}
```

### Anti-Patterns to Avoid
- **Starting a new TradingSystem instance:** The system is already initialized. Start/stop should toggle `_running` and manage loop tasks, NOT create new instances.
- **Keeping the control app backend alive:** Do not try to proxy through the control app backend. Kill the intermediary entirely.
- **Polling faster than 1s via REST:** The current 250ms poll interval is excessive. Use WebSocket for sub-second updates and reduce REST polling to 5-10s for fallback.
- **Mixing auth schemes:** The main bot uses `X-API-Key`; the control app uses `X-Control-Token`. Standardize on `X-API-Key` and update the frontend.

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| WebSocket transport | Custom TCP socket protocol | FastAPI `@app.websocket()` | Built-in ASGI WebSocket support, handles upgrade, ping/pong, close frames |
| WebSocket reconnection | Manual retry loops in JS | Simple `useWebSocket` hook with exponential backoff | 30 lines of code, handles all edge cases |
| Response type mapping | Rewrite all UI components | Adapter functions in client.ts | Frontend has 12 components that work; just map the data shape |
| CORS for WebSocket | Separate CORS config | FastAPI CORS middleware already handles WS origins | Same middleware works for both HTTP and WS |
| Auth for WebSocket | Session/cookie auth | Pass API key as query param on WS connect | Simple, stateless, matches existing REST auth pattern |

**Key insight:** The UI is already built and works. The only change needed is the data source. Treat this as a plumbing/integration phase, not a UI rewrite.

## Common Pitfalls

### Pitfall 1: Breaking the Frontend by Changing Type Contracts
**What goes wrong:** Changing `BotStatusResponse`, `BotMetricsResponse`, `CommandRequest` types to match the main bot API breaks all 12 UI components that depend on them.
**Why it happens:** The temptation to "clean up" types to match the real API.
**How to avoid:** Keep existing frontend types as-is. Write adapter/mapper functions in `client.ts` that convert main bot API responses to existing types. The UI components never need to know the data source changed.
**Warning signs:** TypeScript compilation errors across multiple components.

### Pitfall 2: WebSocket Connection Lifecycle on Windows
**What goes wrong:** WebSocket connections silently fail or hang on Windows due to event loop differences.
**Why it happens:** `asyncio.get_event_loop()` behaves differently on Windows; `ProactorEventLoop` is default and has WebSocket quirks.
**How to avoid:** uvicorn with `loop="none"` (already configured in `main.py`) lets uvicorn manage the loop. Test WebSocket on Windows explicitly.
**Warning signs:** WebSocket connects but never receives messages, or disconnects silently after 30s.

### Pitfall 3: Start/Stop Race Conditions
**What goes wrong:** Calling start while loops are still shutting down, or calling stop twice, causes duplicate tasks or errors.
**Why it happens:** `_running = False` doesn't immediately stop the loop (it finishes the current sleep/tick first). Starting again creates duplicate loop tasks.
**How to avoid:** Track loop tasks as `asyncio.Task` objects. Check if they're done before starting new ones. Use a state machine (STOPPED/STARTING/RUNNING/STOPPING) instead of a boolean.
**Warning signs:** Duplicate trades, log messages appearing twice, "coroutine already awaited" errors.

### Pitfall 4: CORS Configuration for WebSocket
**What goes wrong:** WebSocket connections fail with no error message (browsers don't show CORS errors for WS).
**Why it happens:** CORS middleware only applies to HTTP; WebSocket origin checking must be done manually in the WebSocket endpoint or trusted.
**How to avoid:** FastAPI CORS middleware handles the initial HTTP upgrade request. Ensure `http://127.0.0.1:5173` is in `allow_origins`. For WS-specific origin checking, validate in the WebSocket accept handler.
**Warning signs:** WebSocket connection immediately closes with no error in browser console.

### Pitfall 5: Control App Backend SQLite Locking
**What goes wrong:** If control app backend is not fully removed, it may hold locks on SQLite files that conflict with the main bot.
**Why it happens:** Two separate Python processes accessing the same SQLite file.
**How to avoid:** Completely stop and remove the control app backend process. The main bot uses PostgreSQL (or aiosqlite for its own DB), not the control app's SQLite.
**Warning signs:** "database is locked" errors.

### Pitfall 6: Missing `/system/start` Semantics
**What goes wrong:** The frontend sends START_BOT command but there's no endpoint to receive it on the main bot API.
**Why it happens:** The main bot was designed to start from the command line (`python main.py`), not via API. The control app backend faked it with in-memory state.
**How to avoid:** Implement a real start endpoint that re-launches the trading loop coroutines. Design it as idempotent (calling start when already running is a no-op, not an error).
**Warning signs:** 404 errors on start command, or start succeeds but bot doesn't actually trade.

## Code Examples

### Example 1: Rewritten client.ts (Core Pattern)
```typescript
// New API base points to main bot
const API_BASE = import.meta.env.VITE_API_BASE ?? "http://127.0.0.1:8000/api/v1";
const TOKEN_KEY = "control_api_token";

// Auth header changes from X-Control-Token to X-API-Key
async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const token = getApiToken();
  const response = await fetch(`${API_BASE}${path}`, {
    headers: {
      "Content-Type": "application/json",
      "X-API-Key": token,  // Changed from X-Control-Token
    },
    ...init,
  });
  if (!response.ok) {
    const body = await response.text();
    throw new Error(explainApiError(response.status, response.statusText, body));
  }
  return (await response.json()) as T;
}

// Map main bot status to frontend BotStatusResponse
export async function fetchStatus(): Promise<BotStatusResponse> {
  const raw = await request<SystemStatusResponse>("/status");
  return {
    state: raw.trading_active ? "RUNNING" : "STOPPED",
    uptime_sec: Math.round(raw.uptime_seconds),
    last_heartbeat: new Date().toISOString(),
    active_strategy: "xau-usd-intraday-v1",
    open_positions: raw.open_positions,
    risk_state: raw.kill_switch_active ? "kill_switch" : "normal",
    last_error: null,
  };
}
```

### Example 2: WebSocket Hook
```typescript
// hooks/useWebSocket.ts
export function useWebSocket(url: string, onMessage: (data: unknown) => void) {
  const wsRef = useRef<WebSocket | null>(null);
  const retriesRef = useRef(0);

  useEffect(() => {
    function connect() {
      const ws = new WebSocket(url);
      wsRef.current = ws;

      ws.onopen = () => { retriesRef.current = 0; };
      ws.onmessage = (event) => {
        try { onMessage(JSON.parse(event.data)); } catch {}
      };
      ws.onclose = () => {
        const delay = Math.min(1000 * Math.pow(2, retriesRef.current), 30000);
        retriesRef.current++;
        setTimeout(connect, delay);
      };
    }
    connect();
    return () => { wsRef.current?.close(); };
  }, [url, onMessage]);
}
```

### Example 3: Command Mapping (Start/Stop)
```typescript
// Map control app command types to main bot API endpoints
export async function postCommand(payload: CommandRequest): Promise<CommandResponse> {
  const { command_type } = payload;

  if (command_type === "START_BOT" || command_type === "RESUME_TRADING") {
    const result = await request<{ success: boolean; message: string }>("/system/start", {
      method: "POST",
    });
    return {
      accepted: result.success,
      command_id: payload.command_id,
      command_type: payload.command_type,
      status: result.success ? "success" : "failed",
      message: result.message,
      executed_at: new Date().toISOString(),
    };
  }

  if (command_type === "STOP_BOT") {
    const result = await request<{ success: boolean; message: string }>("/system/stop", {
      method: "POST",
    });
    return { /* similar mapping */ };
  }

  if (command_type === "EMERGENCY_STOP") {
    // Activate kill switch + stop
    await request<unknown>("/risk/kill-switch", {
      method: "POST",
      body: JSON.stringify({ activate: true, reason: "emergency_stop_from_ui" }),
    });
    const result = await request<{ success: boolean; message: string }>("/system/stop", {
      method: "POST",
    });
    return { /* similar mapping */ };
  }

  throw new Error(`Unsupported command type: ${command_type}`);
}
```

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| Separate control app backend (port 8060) | Direct connection to bot API (port 8000) | Phase 6 | Eliminates duplicate, stub-only backend |
| 250ms REST polling | WebSocket push + fallback REST polling (5-10s) | Phase 6 | Reduces request load by ~50x, true real-time |
| In-memory fake state (GoldBotAdapter) | Real TradingSystem state via API | Phase 6 | Actual bot control instead of state simulation |
| X-Control-Token auth | X-API-Key auth (same as bot API) | Phase 6 | Single auth mechanism |

**Deprecated/outdated after this phase:**
- `goldbot-control-app/backend/` -- entire directory (separate FastAPI server)
- `goldbot-control-app/integration/goldbot_adapter.py` -- stub adapter
- `goldbot-control-app/database/` -- control app SQLite database
- `goldbot-control-app/shared/contracts.py` -- Python contracts (only TS types remain relevant)

## Open Questions

1. **Start semantics when broker is not authenticated**
   - What we know: `system.start()` calls `_health_check()` which authenticates the broker. A lightweight restart (just re-enabling loops) skips this.
   - What's unclear: Should `/system/start` re-authenticate with the broker, or assume the session is still valid?
   - Recommendation: If `_running` was previously True (i.e., was stopped via API), skip full init. If the system was never started (cold start via API), that's out of scope -- require `python main.py` for initial boot.

2. **PAUSE_TRADING vs STOP_BOT semantics**
   - What we know: The frontend has both commands. The main bot only has stop (which sets `_running = False`). There's no pause concept.
   - What's unclear: Should PAUSE stop opening new trades but keep monitoring existing positions?
   - Recommendation: Map PAUSE to a new `_paused` flag that skips signal generation in the trading tick but continues position monitoring. Map RESUME to clearing that flag. STOP stops all loops.

3. **Metrics endpoint mapping**
   - What we know: The frontend expects `BotMetricsResponse` with `orders_today`, `successful_commands_24h`, `failed_commands_24h`, `api_latency_ms`, `db_latency_ms`. The main bot API does not have this exact endpoint.
   - What's unclear: Whether to add a dedicated metrics endpoint to the main bot API or synthesize it from existing endpoints.
   - Recommendation: Add a lightweight `/api/v1/metrics` endpoint that queries the trade repo for today's count and returns hardcoded latency values (measure actual latency in middleware). Command success/failure counts are not tracked in the main bot -- return 0 or omit.

## API Endpoint Mapping

This table maps what the frontend currently calls (control app backend) to what exists in the main bot API.

| Frontend Call | Control Backend Endpoint | Main Bot Equivalent | Gap |
|---------------|-------------------------|---------------------|-----|
| `fetchStatus()` | `GET /bot/status` | `GET /status` | Response shape differs; needs adapter |
| `fetchMetrics()` | `GET /bot/metrics` | None | **NEW: `GET /metrics`** |
| `postCommand(START_BOT)` | `POST /bot/commands` | None | **NEW: `POST /system/start`** |
| `postCommand(STOP_BOT)` | `POST /bot/commands` | `POST /system/stop` | Exists; needs response mapping |
| `postCommand(EMERGENCY_STOP)` | `POST /bot/commands` | `POST /risk/kill-switch` + `POST /system/stop` | Composed from 2 calls |
| `postCommand(PAUSE_TRADING)` | `POST /bot/commands` | None | **NEW: `POST /system/pause`** |
| `postCommand(RESUME_TRADING)` | `POST /bot/commands` | None | **NEW: `POST /system/resume`** (or same as start) |
| `postCommand(RELOAD_CONFIG)` | `POST /bot/commands` | None | **NEW: `POST /system/reload-config`** (or defer) |
| `fetchActions()` | `GET /logs/actions` | None | Defer to Phase 7; return empty array for now |
| `fetchErrors()` | `GET /logs/errors` | None | Defer to Phase 7; return empty array for now |
| `fetchSettings()` | `GET /settings` | None | Defer to Phase 7; return defaults |
| `fetchTradeChartPoints()` | `GET /trades/chart` | `GET /orders/history` + `GET /orders/positions` | Adapt from existing endpoints |
| (new) WebSocket | None | None | **NEW: `WS /ws/status`** |

## Sources

### Primary (HIGH confidence)
- **Project source code** -- `api/app.py`, `api/routers/system.py`, `api/routers/trades.py`, `api/routers/market.py` (main bot API)
- **Project source code** -- `goldbot-control-app/backend/app/` (control app backend)
- **Project source code** -- `goldbot-control-app/frontend/src/` (React frontend)
- **Project source code** -- `main.py`, `trading/lifecycle.py`, `trading/trading_loop.py` (bot startup/lifecycle)
- **Project source code** -- `config/settings.py` (bot configuration, API port/host)
- **Project source code** -- `requirements.txt` (FastAPI >=0.115.0, websockets >=14.0, uvicorn[standard] >=0.32.0)

### Secondary (MEDIUM confidence)
- FastAPI WebSocket documentation -- native `@app.websocket()` decorator, built into FastAPI
- Phase 7 research (`07-RESEARCH.md`) -- confirms WebSocket approach for CTRL-06

### Tertiary (LOW confidence)
- None -- all findings verified from project source code

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH -- all libraries already in use, versions confirmed from package.json and requirements.txt
- Architecture: HIGH -- full codebase review of both APIs and frontend completed
- Pitfalls: HIGH -- identified from actual code patterns (auth mismatch, missing endpoints, race conditions)
- API mapping: HIGH -- every frontend call traced to source, every main bot endpoint catalogued

**Research date:** 2026-03-08
**Valid until:** indefinite (project-specific findings, not library-version dependent)
