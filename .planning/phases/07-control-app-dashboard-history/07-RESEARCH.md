# Phase 7: Control App - Dashboard & History - Research

**Researched:** 2026-03-06  
**Domain:** Control App dashboard/history UX, trade-history filtering, model-performance exposure, and real-time UI notifications  
**Confidence:** MEDIUM

<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Decisions
### 1) Density, Rhythm, and Block Sizing
- Activity Feed and Error View should use adaptive heights by viewport (not fixed short/long).
- Status + KPI must be presented as one horizontal strip with scroll-snap, Apple-like cleanliness.
- Vertical rhythm should be airy: 16px spacing between major blocks.
- Dashboard should focus on live data; action controls should not be in dashboard main flow (actions stay in risk/settings contexts).

### 2) Visual Direction
- Primary style direction: Minimal Dark.
- Visual feel: very clean, glassy, futuristic (calm, not noisy).
- Color system: monochrome-first palette with restrained accents.
- Motion style: expressive (allowed up to ~500ms where appropriate), still controlled.

### 3) Action Hierarchy and Critical Interactions
- Primary action emphasis: both `START_BOT` and `RESUME_TRADING`.
- Critical actions should use subdued warning red with pulse feedback (not aggressive permanent red blocks).
- Double-click requirement hint should be compact (mini label), not a large text block.
- Confirm interaction for critical actions: 1s timer ring + second click required.

### 4) Chart and Log Readability
- Default chart layer combination: EMA + VWAP.
- Event markers: small and color-coded by status (minimal footprint, still distinguishable).
- Logs: grouped and compact; timestamps smaller and visually de-emphasized.
- JSON details in logs/errors: accordion behavior with smooth ~300ms expansion.

### 5) Motion and System Feedback (Added Requirement)
- Status transition (`STOPPED -> RUNNING`): color fade + subtle pulse-in on status badge.
- Heartbeat indicator: small pulse every 3s to show system activity.
- Latency badges: subtle green glow on healthy values; warning wobble on degraded values.
- Chart layers (EMA/VWAP/RSI): fade/slide-in when toggled (~200ms target behavior).
- New event markers: soft drop-in effect.
- Replay mode: animated moving cursor over timeline.
- New log entries: slide-down + short highlight flash.
- Guard-blocked feedback: short shake to indicate blocked command.
- Buttons: hover-lift with soft shadow; critical hover pulse for danger awareness.
- Navigation: animated active-tab underline; short fade-through between sections/tabs.
- Theme switch (light/dark): smooth cross-fade (~300ms).

### Claude's Discretion
- Exact easing curves, duration fine-tuning per component, and per-device motion reduction behavior.
- Exact monochrome token values and accent intensity to preserve contrast and readability.
- Final breakpoint thresholds for adaptive panel heights.
- Whether some optional “wow” animations are enabled by default or gated behind a setting.

### Deferred Ideas (OUT OF SCOPE)
- Large startup Lottie cinematic sequence is optional and should be treated as non-blocking polish unless explicitly prioritized in planning.
- Additional “wow-only” effects (e.g., stronger risk wave / position flourish variants) should not displace core readability and history/dashboard usability.
</user_constraints>

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|-----------------|
| CTRL-04 | User can view trade history with filtering | Add validated server-side filters (date range, direction, P&L bounds), return paged/sorted history, and bind filter UI controls to query params. |
| CTRL-05 | User can view model performance metrics | Expose normalized model metrics endpoint from model metadata/version files and render per-model, per-version accuracy/profit-factor cards/table. |
| CTRL-06 | Real-time updates via WebSocket | Add `/ws/trades` event stream and implement frontend snapshot+stream merge with reconnect/dedupe + in-app trade toasts. |
</phase_requirements>

## Summary

Phase 7 should be planned as an API + UI slice, not just frontend polish. The UI decisions are already locked in CONTEXT.md; the planning risk is data contract design. Today, the frontend refreshes every 250ms and fetches multiple endpoints in parallel. That gives "near real-time" visuals, but it does not satisfy CTRL-06 and creates avoidable request load.

Primary technical gap for CTRL-04/05/06 is missing backend contracts: no filter-rich trade-history API, no dedicated model-performance API, and no websocket stream for trade events. Trades are available in `trades` table and model metrics are available in `ai_engine/saved_models` metadata, but they are not exposed in a planner-friendly API shape.

**Primary recommendation:** Plan Phase 7 around three backend contracts first (`/orders/history` filters, `/models/performance`, `/ws/trades`) and then wire new dashboard/history panels to those contracts with snapshot + stream state handling.

## Standard Stack

### Core

| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| React | 18.3.1 | UI rendering and state composition | Already in use; idiomatic hooks-based integration for streams and UI updates. |
| TypeScript | 5.9.3 | Typed frontend contracts | Prevents schema drift between API payloads and UI models. |
| FastAPI | >=0.115.0 | REST + WebSocket endpoints | Native query validation + websocket support in same service boundary. |
| SQLAlchemy (async) | >=2.0.36 | Trade-history querying | Existing repository pattern already uses it; safe composable filtering. |
| Browser WebSocket API | Standard | Real-time client channel | Native, no extra dependency; aligns with FastAPI websocket endpoint. |
| Recharts | 2.15.4 | Existing chart/event marker rendering | Already used by current dashboard (`ChartPanel`). |

### Supporting

| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| Pydantic v2 | >=2.10.0 | Query/response DTO validation | Define strict filter and metric response models for Phase 7 APIs. |
| FastAPI TestClient | current | API + websocket tests | Verify endpoint behavior and stream payloads in control-app style tests. |
| Existing CSS token system | current | Minimal-dark + motion implementation | Keep current design language and apply locked CONTEXT decisions. |

### Alternatives Considered

| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| Polling-only updates | WebSocket events + REST snapshot | WebSocket adds server state management but satisfies CTRL-06 and lowers request churn. |
| Client-only filtering on full history payload | Server-side query filters | Server-side scales better and simplifies deterministic filtering behavior. |
| Extending duplicate control-app backend only | Extending main `api/` service | Main API aligns with CTRL-01 architecture goal; duplicate backend increases divergence risk. |

**Installation:**
```bash
# Baseline phase implementation needs no new package installs.
```

## Architecture Patterns

### Recommended Project Structure

```text
api/
|-- routers/
|   |-- trades.py                 # extend /history filtering
|   |-- model_performance.py      # new model metrics endpoint
|   `-- realtime.py               # new websocket endpoint(s)
|-- schemas/
|   |-- trades.py                 # filter/query + response DTOs
|   `-- model_performance.py      # metrics DTOs
|-- events/
|   `-- trade_events.py           # in-process broadcaster for opened/closed events

goldbot-control-app/frontend/src/
|-- api/client.ts                 # add history + model metrics + ws client
|-- hooks/useTradeStream.ts       # snapshot+stream merge
|-- components/TradeHistoryTable.tsx
|-- components/ModelPerformancePanel.tsx
`-- components/TradeNotificationStack.tsx
```

### Pattern 1: Query-Model Driven History Filters
**What:** Use a typed query model to validate filter inputs once, then convert to SQLAlchemy conditions.  
**When to use:** CTRL-04 filtering by date, direction, and P&L.  
**Example:**
```python
# Source patterns: FastAPI query-param models + SQLAlchemy where chaining
class TradeHistoryFilters(BaseModel):
    date_from: datetime | None = None
    date_to: datetime | None = None
    direction: Literal["BUY", "SELL"] | None = None
    pnl_min: float | None = None
    pnl_max: float | None = None
    limit: int = 200

conditions = []
if filters.date_from:
    conditions.append(Trade.opened_at >= filters.date_from)
if filters.date_to:
    conditions.append(Trade.opened_at <= filters.date_to)
if filters.direction:
    conditions.append(Trade.direction == filters.direction)
if filters.pnl_min is not None:
    conditions.append(Trade.net_pnl >= filters.pnl_min)
if filters.pnl_max is not None:
    conditions.append(Trade.net_pnl <= filters.pnl_max)

stmt = select(Trade).where(*conditions).order_by(Trade.opened_at.desc()).limit(filters.limit)
```

### Pattern 2: REST Snapshot + WebSocket Delta
**What:** Load initial data via REST, then apply websocket events incrementally.  
**When to use:** CTRL-06 and notification freshness without full refresh loops.  
**Example:**
```python
# Source pattern: FastAPI websocket connection manager
@app.websocket("/api/v1/ws/trades")
async def trades_ws(websocket: WebSocket):
    await manager.connect(websocket)
    try:
        while True:
            await websocket.receive_text()  # optional heartbeat client ping
    except WebSocketDisconnect:
        manager.disconnect(websocket)
```

### Pattern 3: Frontend External-Connection Hook with Cleanup
**What:** Open/close websocket inside `useEffect`, merge events into local state, and dedupe by `event_id` / `deal_id + status + timestamp`.  
**When to use:** Trade-notification UI + live history updates.  
**Example:**
```typescript
useEffect(() => {
  const ws = new WebSocket(wsUrl);
  ws.onmessage = (ev) => {
    const event = JSON.parse(ev.data) as TradeEvent;
    applyTradeEvent(event);
    pushToast(event.type === "trade_closed" ? "success" : "info", event.message);
  };
  return () => ws.close();
}, [wsUrl, applyTradeEvent, pushToast]);
```

### Pattern 4: Model Metrics Adapter (Versioned + Legacy)
**What:** Normalize metrics from `production.json -> version.json` when present, fallback to `model_metadata.json`.  
**When to use:** CTRL-05 while Phase 2 versioning rollout may be incomplete in runtime data.  
**Example:**
```python
def load_model_metrics(saved_models_dir: Path) -> list[ModelPerf]:
    # 1) try production pointer + version.json
    # 2) fallback to model_metadata.json
    # 3) emit normalized shape: model_name, accuracy, profit_factor, trained_at, version_dir
```

### Anti-Patterns to Avoid
- **Full-dashboard 250ms hard polling:** high request volume and still no true event stream semantics.
- **Filtering only in frontend after large fetches:** poor scalability and inconsistent date/P&L interpretation.
- **Adding new action-control blocks to dashboard flow:** conflicts with locked phase decisions.
- **Using duplicate backend as long-term source of truth:** conflicts with CTRL-01 architecture direction.

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Real-time transport protocol | Custom TCP/event protocol | FastAPI websocket endpoints + browser WebSocket API | Stable, standard tooling and testable behavior. |
| Filter parsing/validation | Manual query-string parsing in route bodies | FastAPI query models + Pydantic validation | Clear API contracts and fewer edge-case bugs. |
| Dynamic SQL strings | String-concatenated SQL conditions | SQLAlchemy expression building | Safer and easier to evolve with new filters. |
| Model-metrics shape guessing in UI | Ad-hoc parsing in React components | Backend normalization endpoint DTO | Keeps frontend simple and consistent across metadata formats. |

**Key insight:** Most Phase 7 risk is contract drift, not rendering code. Centralize contract shaping in backend.

## Common Pitfalls

### Pitfall 1: Treating Polling as "WebSocket Enough"
**What goes wrong:** UI appears live but does not satisfy CTRL-06 and scales poorly.  
**Why it happens:** Existing hook polls every 250ms and already feels real-time.  
**How to avoid:** Keep polling only as fallback; implement websocket stream for trade events.  
**Warning signs:** 20+ req/s per client, duplicate row flashes, delayed notification ordering.

### Pitfall 2: History Filter Ambiguity (Time + P&L)
**What goes wrong:** Date and P&L filters disagree between backend/frontend interpretations.  
**Why it happens:** Mixed timezone handling and frontend-only filter logic.  
**How to avoid:** Define filter semantics in API contract (UTC ISO timestamps, inclusive/exclusive rules, `None` P&L handling).  
**Warning signs:** Trade count changes when only browser locale changes.

### Pitfall 3: No Single Source for Model Metrics
**What goes wrong:** UI shows stale or partial metrics.  
**Why it happens:** Runtime may have legacy `model_metadata.json` while versioned files are phase-dependent.  
**How to avoid:** Implement backend adapter with explicit fallback chain and response flags (`source=version_json|legacy_metadata`).  
**Warning signs:** empty metrics despite trained models present on disk.

### Pitfall 4: WebSocket Lifecycle Leaks
**What goes wrong:** duplicate notifications and memory growth from orphaned connections.  
**Why it happens:** missing disconnect cleanup and reconnect dedupe.  
**How to avoid:** connection manager + `WebSocketDisconnect` handling + client dedupe keys.  
**Warning signs:** same trade event appears multiple times after reconnect.

### Pitfall 5: Scope Creep into New Product Modules
**What goes wrong:** planning drifts into new modules (mobile app, cinematic intro, extra wow features).  
**Why it happens:** Phase 7 is visual and invites polish expansion.  
**How to avoid:** enforce CONTEXT deferred-ideas boundary and ship core CTRL-04/05/06 first.  
**Warning signs:** plan items that do not map to requirement IDs.

## Code Examples

Verified patterns from official sources and current code style:

### FastAPI Query Model for Filtered Endpoint
```python
from typing import Annotated, Literal
from fastapi import Query
from pydantic import BaseModel, Field

class HistoryQuery(BaseModel):
    direction: Literal["BUY", "SELL"] | None = None
    pnl_min: float | None = None
    pnl_max: float | None = None
    limit: int = Field(200, ge=1, le=1000)

@router.get("/history")
async def history(q: Annotated[HistoryQuery, Query()]):
    ...
```

### FastAPI WebSocket Manager Pattern
```python
class ConnectionManager:
    def __init__(self):
        self.active_connections: list[WebSocket] = []

    async def connect(self, websocket: WebSocket):
        await websocket.accept()
        self.active_connections.append(websocket)

    def disconnect(self, websocket: WebSocket):
        self.active_connections.remove(websocket)

    async def broadcast(self, message: str):
        for c in list(self.active_connections):
            await c.send_text(message)
```

### React `useEffect` Connection Lifecycle
```typescript
useEffect(() => {
  const conn = createConnection(serverUrl, roomId);
  conn.connect();
  return () => conn.disconnect();
}, [serverUrl, roomId]);
```

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| Fast, full polling refresh loop | REST snapshot + websocket deltas | Current standard pattern | Lower load, better event freshness, explicit realtime semantics. |
| Single flat metadata payload assumptions | Version-aware metrics with fallback | After model versioning adoption | Reliable model performance display across runtime states. |
| UI-only filtering | Backend-validated query filters + indexed DB conditions | Current API best practice | Deterministic filtering and easier test coverage. |

**Deprecated/outdated:**
- Fixed high-frequency polling as primary realtime mechanism for trade notifications.
- Growing feature scope beyond CONTEXT locked decisions and requirement IDs.

## Open Questions

1. **Phase 6 dependency status (`CTRL-01/02/03`)**
   - What we know: Current control app still has its own backend on port 8060.
   - What's unclear: Whether Phase 7 should extend main `api/` directly or temporary control-app backend.
   - Recommendation: Decide this in planning Wave 0; prefer main API path to avoid duplicate-contract debt.

2. **Model metrics source of truth**
   - What we know: `model_metadata.json` exists; versioned `production.json` may not always exist at runtime.
   - What's unclear: Required depth (latest only vs per-version history table).
   - Recommendation: Ship latest + optional recent versions if `v*/version.json` present.

3. **Notification scope**
   - What we know: Requirement asks for real-time trade notifications in UI.
   - What's unclear: in-app toasts only vs browser/system notifications.
   - Recommendation: Commit to in-app toasts in this phase; defer system notifications unless explicitly requested.

## Sources

### Primary (HIGH confidence)
- Local context and requirements:
  - `.planning/phases/07-control-app-dashboard-history/07-CONTEXT.md`
  - `.planning/REQUIREMENTS.md`
  - `.planning/STATE.md`
- Local implementation references:
  - `goldbot-control-app/frontend/src/hooks/useDashboardData.ts` (current polling behavior)
  - `goldbot-control-app/frontend/src/api/client.ts` (current API contracts)
  - `api/routers/trades.py` + `database/repositories/trade_repo.py` (trade data/query surface)
  - `ai_engine/training/model_versioning.py` + `tests/test_model_versioning.py` (model metadata/version format)
- Official docs:
  - FastAPI WebSockets: https://fastapi.tiangolo.com/advanced/websockets/
  - FastAPI query parameter models: https://fastapi.tiangolo.com/tutorial/query-param-models/
  - FastAPI testing websockets: https://fastapi.tiangolo.com/advanced/testing-websockets/
  - SQLAlchemy where/select patterns: https://docs.sqlalchemy.org/en/20/core/operators.html
  - React `useEffect` external sync pattern: https://react.dev/reference/react/useEffect
  - MDN WebSocket API reference: https://developer.mozilla.org/en-US/docs/Web/API/WebSocket

### Secondary (MEDIUM confidence)
- Existing control-app docs (`docs/API.md`, `docs/STRUCTURE.md`, `ops/app.env.example`) for current runtime assumptions and path conventions.

### Tertiary (LOW confidence)
- None.

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH - Versions and tooling confirmed from local package metadata and current code.
- Architecture: MEDIUM - Depends on unresolved Phase 6 backend-unification state.
- Pitfalls: HIGH - Directly observed in current polling, contract, and data-source layout.

**Research date:** 2026-03-06  
**Valid until:** 2026-04-05
