# Phase 8: Wirtschaftskalender-Integration - Research

**Researched:** 2026-03-26
**Domain:** Economic Calendar API, Trading Signal Veto Logic, FastAPI Background Scheduler, SQLAlchemy ORM
**Confidence:** HIGH (stack verified against existing codebase; API findings verified against official docs)

---

## Project Constraints (from CLAUDE.md)

### Mandatory directives from CLAUDE.md
- **Python 3.12** — backend .venv uses Python 3.12.10 (verified)
- **FastAPI 0.115.6** — existing version pinned in requirements.txt
- **SQLAlchemy 2.0.36 async** — all DB access via `AsyncSession` + `async_sessionmaker`
- **Alembic 1.14.1** — schema migrations (alembic dir exists but currently empty — needs init)
- **httpx 0.27.2** — already installed; use for external API calls
- **structlog** — all logging via `structlog.get_logger()`
- **Deutsche UI, englischer Code** — German user-facing text, English variable names
- **Farben NUR via CSS Variables** — frontend only
- **Icons NUR lucide-react** — frontend only
- **try/catch um API Calls** — all external calls wrapped
- **KEINE Platzhalter/TODOs** — implement fully, no stubs
- **Type hints** — Python type hints everywhere
- **Pydantic schemas** — all request/response objects use Pydantic

---

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|------------------|
| ECAL-01 | Wirtschaftskalender-Daten abrufen (NFP, FOMC, CPI, etc.) | Finnhub free API + httpx async; JBlanked als Fallback |
| ECAL-02 | Events nach Impact klassifizieren (High/Medium/Low) | Finnhub `impact` field; eigene Keyword-Whitelist als Sicherheitsnetz |
| ECAL-03 | Veto-Logik in signal_service.py: Trading-Pause bei High-Impact Events | Pre-check pattern: `is_blackout_now()` vor Signal-Generierung |
| ECAL-04 | Historische Events in DB speichern fuer Backtesting | Neue `EconomicEventDB` Tabelle; Alembic Migration |
</phase_requirements>

---

## Summary

Phase 8 muss einen wirtschaftlichen Ereignisschutz in das bestehende TradeForge-Backend einbauen. Das System soll automatisch Handelssignale blockieren, wenn bekannte Hochvolatilitaets-Ereignisse (NFP, FOMC, CPI) innerhalb eines konfigurierbaren Zeitfensters bevorstehen oder gerade stattgefunden haben.

Der beste kostenlose Datenlieferant ist **Finnhub** (offizielle Python-Library, freie API-Keys, kein Scraping, `impact`-Feld direkt in der Antwort). Als Fallback dient **JBlanked** (ForexFactory-Quelle, keine Registration, 1 Request/Tag kostenlos). Beide werden ueber `httpx.AsyncClient` abgerufen. Ein `APScheduler AsyncIOScheduler` triggert stundlich einen Cache-Refresh in Redis.

Die Veto-Logik wird als einzelne `async def is_blackout_window(db: AsyncSession) -> tuple[bool, str]` Funktion in `app/services/economic_calendar_service.py` implementiert, die `generate_signal()` in `signal_service.py` als Pre-Check aufruft. Die DB-Tabelle `economic_events` nimmt historische und geplante Events auf und ermoeglicht spaeteres Backtesting nach Ereignistyp.

**Primary recommendation:** Finnhub als Primaerquelle (60 req/min free tier, `calendar_economic()` method, impact-Klassifikation eingebaut), Redis-Cache mit 1h TTL, APScheduler fuer automatischen Refresh, Alembic Migration fuer neue Tabelle.

---

## Standard Stack

### Core
| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| finnhub-python | 2.4.27 | Wirtschaftskalender-Daten von Finnhub API | Offizielle Library, freier Tier, `impact` field eingebaut |
| apscheduler | 3.11.2 | Periodischer Hintergrund-Fetch | Einzige AsyncIOScheduler-Library mit FastAPI lifespan-Integration |
| httpx | 0.27.2 | HTTP-Client fuer Fallback-APIs | Bereits im Projekt; async-native |
| redis | 5.2.1 | Caching der naechsten Events (1h TTL) | Bereits im Projekt; verhindert Rate-Limit-Hits |

### Supporting
| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| tenacity | latest | Retry mit exponential backoff | Wenn Finnhub 429 oder Timeout |
| alembic | 1.14.1 | DB-Migration fuer neue Tabelle | Phase 8 fuegt `economic_events` Tabelle hinzu |

### Alternatives Considered
| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| Finnhub | JBlanked (forexfactory.com) | JBlanked kostenlos aber nur 1 req/Tag; gut als Fallback |
| Finnhub | market-calendar-tool (scraped) | Scraping-Risiko: Blockierung, ToS-Verletzung, instabil |
| Finnhub | investpy | Gilt als deprecated, nicht mehr gewartet |
| APScheduler | FastAPI BackgroundTasks | BackgroundTasks laufen nicht zeitgesteuert — nur bei Requests |
| Redis Cache | In-Memory Dict | Redis bereits vorhanden; In-Memory verliert Daten bei Restart |

**Installation:**
```bash
pip install finnhub-python==2.4.27 apscheduler==3.11.2 tenacity
```

**Version verification (ausgefuehrt am 2026-03-26):**
```
finnhub-python: 2.4.27 (aktuell)
apscheduler:    3.11.2 (aktuell, release 2025-12-22)
tenacity:       bereits auf PyPI verfuegbar, Version nicht gepinnt
```

---

## Architecture Patterns

### Recommended Project Structure
```
apps/backend/app/
├── services/
│   ├── economic_calendar_service.py   # NEU: Fetch + Cache + Veto-Logik
│   └── signal_service.py              # CHANGE: Veto Pre-Check einbauen
├── models/
│   ├── db/
│   │   └── economic_event.py          # NEU: EconomicEventDB Tabelle
│   └── schemas/
│       └── economic_event.py          # NEU: Pydantic Schemas
├── api/v1/
│   └── economic_calendar.py           # NEU: REST Endpunkte
└── main.py                            # CHANGE: APScheduler starten
alembic/
├── alembic.ini                        # NEU: Alembic muss erst initialisiert werden
├── env.py
└── versions/
    └── 001_add_economic_events.py     # NEU: Migration
```

### Pattern 1: Veto Pre-Check in Signal Generation
**What:** `generate_signal()` fragt vor jeder KI-Anfrage `is_blackout_window()` ab. Wenn ein High-Impact Event in -30/+60 Minuten liegt, wird HOLD zurueckgegeben statt Kosten fuer LLM zu verursachen.

**When to use:** Immer wenn `generate_signal()` aufgerufen wird (manuell oder geplant).

**Example:**
```python
# Source: Verifikation gegen bestehende signal_service.py Struktur
async def generate_signal(db: AsyncSession, symbol: str = "GC=F", timeframe: str = "1h") -> AISignalDB | None:
    # ECAL-03: Veto-Logik
    blackout, reason = await is_blackout_window(db)
    if blackout:
        log.info("signal_blocked_by_calendar", reason=reason)
        signal = AISignalDB(
            id=str(uuid.uuid4()),
            symbol=symbol,
            timeframe=timeframe,
            signal="HOLD",
            confidence=0.0,
            reasoning=f"[Kalender-Schutz] {reason}",
            entry_price=0.0,
            stop_loss=0.0,
            take_profit=[],
            ...
        )
        db.add(signal)
        await db.commit()
        return signal
    # ... bestehende KI-Signal-Logik
```

### Pattern 2: Economic Calendar Service mit Redis-Cache
**What:** Finnhub wird maximal 1x pro Stunde abgefragt. Ergebnis wird in Redis gecacht. `is_blackout_window()` prueft nur den Cache, nicht direkt die API.

**When to use:** Immer — vermeidet Rate-Limit-Hits (Finnhub: 60 req/min) und Latenz.

**Example:**
```python
# Source: Finnhub API Docs + redis 5.2.1 Docs
CACHE_KEY = "ecal:upcoming_high"
CACHE_TTL_SECONDS = 3600  # 1 Stunde

async def fetch_and_cache_events() -> None:
    """Wird stundlich von APScheduler aufgerufen."""
    import finnhub
    client = finnhub.Client(api_key=settings.finnhub_api_key)
    today = datetime.utcnow().date()
    tomorrow = today + timedelta(days=1)
    data = client.calendar_economic(str(today), str(tomorrow))
    high_events = [
        e for e in data.get("economicCalendar", [])
        if e.get("impact", "").lower() == "high"
        and e.get("country") == "US"
    ]
    redis_client.setex(CACHE_KEY, CACHE_TTL_SECONDS, json.dumps(high_events))

async def is_blackout_window(db: AsyncSession) -> tuple[bool, str]:
    """Gibt (True, Grund) zurueck wenn Trading pausiert werden soll."""
    raw = redis_client.get(CACHE_KEY)
    if not raw:
        return False, ""
    events = json.loads(raw)
    now = datetime.utcnow()
    for event in events:
        event_time = datetime.fromisoformat(event["time"])
        delta_minutes = (event_time - now).total_seconds() / 60
        if -60 <= delta_minutes <= 30:  # 60min nach Event, 30min davor
            return True, f"{event['event']} in {delta_minutes:.0f} min"
    return False, ""
```

### Pattern 3: APScheduler Integration in FastAPI Lifespan
**What:** APScheduler `AsyncIOScheduler` laeuft im gleichen Event-Loop wie FastAPI. Stundlicher Cron-Job refresht den Event-Cache.

**When to use:** Immer fuer zeitgesteuerte Hintergrundaufgaben in FastAPI.

**Example:**
```python
# Source: APScheduler 3.11.2 Docs + FastAPI Lifespan Pattern
from apscheduler.schedulers.asyncio import AsyncIOScheduler

scheduler = AsyncIOScheduler()

@asynccontextmanager
async def lifespan(app: FastAPI):
    scheduler.add_job(fetch_and_cache_events, "interval", hours=1)
    scheduler.start()
    await fetch_and_cache_events()  # Initial-Fetch beim Start
    yield
    scheduler.shutdown()
```

### Pattern 4: Finnhub API-Aufruf mit Fallback
**What:** Finnhub via `finnhub-python` als Primaerquelle. Bei Fehler (Netzwerk, 429, API-Key fehlt) Fallback auf JBlanked.

**When to use:** Im `fetch_and_cache_events()` Job.

**Example:**
```python
# Source: Finnhub Python Library README, JBlanked API Docs
async def _fetch_from_finnhub(from_date: str, to_date: str) -> list[dict]:
    import finnhub
    client = finnhub.Client(api_key=settings.finnhub_api_key)
    result = client.calendar_economic(from_date, to_date)
    return [
        e for e in result.get("economicCalendar", [])
        if e.get("impact", "").lower() == "high" and e.get("country") == "US"
    ]

async def _fetch_from_jblanked_fallback() -> list[dict]:
    """JBlanked: kostenlos, 1 req/Tag, ForexFactory-Quelle."""
    async with httpx.AsyncClient(timeout=10) as client:
        r = await client.get(
            "https://www.jblanked.com/news/api/forex-factory/calendar/today/",
            params={"impact": "High", "currency": "USD"}
        )
        r.raise_for_status()
        return r.json()
```

### Anti-Patterns to Avoid
- **Direktes Scraping von ForexFactory:** ToS-Verletzung, blockierbar, wartungsaufwaendig
- **API-Aufruf bei jedem Signal:** Rate-Limit-Treffer, Latenz (Cache verwenden)
- **Blocking-HTTP in async Context:** `requests` statt `httpx.AsyncClient` oder Finnhub sync in async-Funktion — blockiert Event-Loop
- **Kein Fallback:** Wenn Finnhub faellt, wird gesamter Schutz deaktiviert
- **Blackout-Fenster zu eng:** Nur 5 Minuten vor Event reicht nicht — Gold bewegt sich 15-30 Minuten vor NFP
- **Impact-Check nur auf Eventname:** Finnhub gibt `impact` direkt zurueck — nicht manuell parsen
- **APScheduler 4.x statt 3.x:** APScheduler 4.0 hat Breaking Changes — `AsyncIOScheduler` ist in 3.x

---

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Periodischer Background-Job | Eigene asyncio.create_task Schleife | APScheduler | Cron-Syntax, Fehlerbehandlung, Shutdown-Hook |
| HTTP Retry | Manuelles try/except + sleep | tenacity `@retry` | Exponential backoff, jitter, async-kompatibel |
| Wirtschaftskalender-Parsing | Regex auf investing.com HTML | finnhub-python | Offizielles SDK, strukturierte Antwort |
| Event-Cache | Eigene Python dict mit TTL | Redis `setex()` | Bereits vorhanden, persistiert Restarts |
| DB-Schema-Migration | `Base.metadata.create_all()` | Alembic `alembic revision --autogenerate` | Produktionssicher, tracked Aenderungen |

**Key insight:** Wirtschaftskalender-Daten sind haeufig aenderbar — Zeiten verschieben sich, Events werden hinzugefuegt. Ein dedizierter API-Provider mit Impact-Klassifikation spart alle Edge-Case-Behandlung.

---

## DB Schema for Historical Events

### EconomicEventDB Tabelle (neue SQLAlchemy Model)
```python
# Source: Analyse bestehender Modelle (market_data.py, signal.py als Vorlage)
class EconomicEventDB(Base):
    __tablename__ = "economic_events"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    event_name: Mapped[str] = mapped_column(String(200), nullable=False)
    country: Mapped[str] = mapped_column(String(10), nullable=False, default="US")
    impact: Mapped[str] = mapped_column(String(10), nullable=False)  # "high", "medium", "low"
    event_time: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    actual: Mapped[float | None] = mapped_column(Float, nullable=True)
    estimate: Mapped[float | None] = mapped_column(Float, nullable=True)
    previous: Mapped[float | None] = mapped_column(Float, nullable=True)
    unit: Mapped[str | None] = mapped_column(String(50), nullable=True)
    source: Mapped[str] = mapped_column(String(50), default="finnhub")
    caused_blackout: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow)

    __table_args__ = (
        Index("ix_economic_events_time_impact", "event_time", "impact"),
        Index("ix_economic_events_name_time", "event_name", "event_time", unique=True),
    )
```

### Alembic Migration Workflow (Alembic ist noch nicht initialisiert)
```bash
# Im backend-Verzeichnis:
cd apps/backend
alembic init alembic
# alembic.ini und env.py anpassen (target_metadata = Base.metadata)
# Neues Model importieren in env.py
alembic revision --autogenerate -m "add_economic_events"
alembic upgrade head
```

**Wichtig:** Das `alembic/` Verzeichnis existiert, aber `alembic.ini` und `alembic/env.py` fehlen. Diese muessen als Teil von Wave 0 erstellt werden.

---

## Impact Classification Logic

### Finnhub Impact Field Values
Finnhub gibt `impact` direkt als String zurueck. Beobachtete Werte (MEDIUM confidence — aus API-Doku):
- `"high"` — NFP, FOMC Rate Decision, CPI
- `"medium"` — PPI, Retail Sales, Trade Balance
- `"low"` — sonstige Indikatoren

### Keyword-Whitelist als Sicherheitsnetz (falls impact-Feld fehlt)
```python
HIGH_IMPACT_KEYWORDS = {
    "non-farm", "nfp", "fomc", "federal funds", "cpi", "consumer price",
    "interest rate decision", "gdp", "unemployment rate"
}

def classify_impact(event_name: str, api_impact: str | None) -> str:
    """Fallback-Klassifikation wenn API impact fehlt."""
    if api_impact:
        return api_impact.lower()
    lower = event_name.lower()
    if any(kw in lower for kw in HIGH_IMPACT_KEYWORDS):
        return "high"
    return "medium"
```

### Blackout-Fenster fuer Gold (XAU/USD)
Gold reagiert stark auf US-Events. Empfohlene Fenster basierend auf Marktdaten:

| Event-Typ | Vor dem Event | Nach dem Event | Begruendung |
|-----------|---------------|----------------|-------------|
| NFP | 30 min | 60 min | Erste Reaktion +/- $30; Reversal nach 20-40 min haeufig |
| FOMC Rate Decision | 30 min | 90 min | Haelt laenger an; Statement und Pressekonferenz |
| CPI | 15 min | 60 min | Schnell verarbeitet, aber oft zweite Welle |
| Sonstiges High | 15 min | 30 min | Standard-Schutzfenster |

Quellen: Vantage Markets "News Trading Gold" Guide, FXNX "Gold News Trading Guide" (MEDIUM confidence — Branchenstandard, nicht offiziell)

---

## REST API Endpunkte (neue in Phase 8)

```
GET  /api/v1/economic-calendar/upcoming     # Naechste 24h Events (aus Redis-Cache)
GET  /api/v1/economic-calendar/blackout     # Ist Trading gerade blockiert?
GET  /api/v1/economic-calendar/history      # Historische Events aus DB
POST /api/v1/economic-calendar/refresh      # Manueller Cache-Refresh
```

---

## Common Pitfalls

### Pitfall 1: Finnhub-Key im Free Tier — Economic Calendar Zugang
**What goes wrong:** Nicht alle Finnhub-Endpunkte sind im Free Tier verfuegbar. Der Economic Calendar war in einigen Reports als "Basic"-Tier eingestuft.
**Why it happens:** Finnhub-Preisseite nennt Economic Data als Add-on.
**How to avoid:** Beim Start via `client.calendar_economic(today, today)` testen und Response pruefen. Bei 403 oder leerem Ergebnis sofort auf JBlanked-Fallback switchen.
**Warning signs:** Leeres `economicCalendar` Array trotz bekannter Events.

### Pitfall 2: APScheduler 4.x Breaking Changes
**What goes wrong:** `from apscheduler.schedulers.asyncio import AsyncIOScheduler` existiert in APScheduler 4.0 nicht mehr.
**Why it happens:** APScheduler 4.x wurde komplett umgeschrieben.
**How to avoid:** `pip install apscheduler==3.11.2` explizit pinnen (aktuellste 3.x-Version).
**Warning signs:** `ImportError: cannot import name 'AsyncIOScheduler'`

### Pitfall 3: Blocking Finnhub Client in async Context
**What goes wrong:** `finnhub.Client.calendar_economic()` ist synchron — im async-Kontext blockiert es den Event-Loop.
**Why it happens:** Offizielle Library hat keinen async-Client.
**How to avoid:** In `asyncio.get_event_loop().run_in_executor(None, sync_func)` wrappen ODER eigenen httpx-Call direkt gegen `https://finnhub.io/api/v1/calendar/economic`.
**Warning signs:** Uvicorn Worker haengt waehrend Fetch.

### Pitfall 4: Alembic nicht initialisiert
**What goes wrong:** `alembic revision --autogenerate` schlaegt fehl weil `alembic.ini` und `env.py` fehlen.
**Why it happens:** Das `alembic/` Verzeichnis wurde angelegt, aber nie mit `alembic init` begruendet.
**How to avoid:** Wave 0 muss `alembic init alembic`, `env.py` Konfiguration, und `target_metadata` Setup enthalten.
**Warning signs:** `Error: No config file 'alembic.ini' found, or file has no '[alembic]' section`

### Pitfall 5: Zeitzone-Mismatch bei Event-Zeiten
**What goes wrong:** Finnhub gibt Event-Zeiten als UTC an; lokale Auswertung ohne `timezone=True` fuehrt zu falschen Blackout-Fenstern.
**Why it happens:** NFP erscheint um 08:30 ET (13:30 UTC) — ohne Timezone-Handling kann Blackout-Fenster falsch berechnet werden.
**How to avoid:** Alle `DateTime` Spalten mit `timezone=True`; alle Vergleiche in UTC via `datetime.utcnow()` oder `datetime.now(timezone.utc)`.

### Pitfall 6: Redis nicht verfuegbar beim Start
**What goes wrong:** Initial-Fetch beim Lifespan-Start schlaegt fehl wenn Redis nicht laeuft.
**Why it happens:** Docker-Compose Startorder nicht garantiert.
**How to avoid:** `try/except` um Redis-Writes; Fallback auf In-Memory-Cache wenn Redis unavailable. Kein hard crash.

---

## Code Examples

### Finnhub Direct HTTP Call (async, umgeht blocking Library)
```python
# Source: Finnhub API Docs https://finnhub.io/docs/api/economic-calendar
async def fetch_finnhub_economic_calendar(
    from_date: str, to_date: str, api_key: str
) -> list[dict]:
    url = "https://finnhub.io/api/v1/calendar/economic"
    async with httpx.AsyncClient(timeout=10.0) as client:
        response = await client.get(
            url,
            params={"from": from_date, "to": to_date, "token": api_key}
        )
        response.raise_for_status()
        data = response.json()
        return data.get("economicCalendar", [])
```

### APScheduler + FastAPI Lifespan Integration
```python
# Source: APScheduler 3.11.2 Docs; FastAPI lifespan pattern
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from contextlib import asynccontextmanager

scheduler = AsyncIOScheduler(timezone="UTC")

@asynccontextmanager
async def lifespan(app: FastAPI):
    scheduler.add_job(
        fetch_and_cache_events,
        "interval",
        hours=1,
        id="ecal_refresh",
        replace_existing=True
    )
    scheduler.start()
    try:
        await fetch_and_cache_events()
    except Exception as e:
        log.warning("ecal_initial_fetch_failed", error=str(e))
    yield
    scheduler.shutdown(wait=False)
```

### Redis Cache Write/Read Pattern (matching existing redis.py)
```python
# Source: Verifikation gegen app/db/redis.py
import json
from datetime import timedelta

async def cache_events(events: list[dict]) -> None:
    redis_client.setex(
        "ecal:upcoming_high",
        int(timedelta(hours=1).total_seconds()),
        json.dumps(events, default=str)
    )

async def get_cached_events() -> list[dict]:
    raw = redis_client.get("ecal:upcoming_high")
    if not raw:
        return []
    return json.loads(raw)
```

### Alembic env.py Target Metadata Setup
```python
# Source: Alembic Docs + Verifikation gegen bestehende Modell-Struktur
# In alembic/env.py
from app.models.db import *  # alle Modelle importieren
from app.db.base import Base
target_metadata = Base.metadata
```

---

## Environment Availability

| Dependency | Required By | Available | Version | Fallback |
|------------|------------|-----------|---------|----------|
| Python 3.12 | Backend .venv | ✓ | 3.12.10 | — |
| httpx | API Calls | ✓ | 0.27.2 | — |
| redis | Caching | ✓ | 5.2.1 | In-Memory dict (degraded) |
| alembic | DB Migration | ✓ | 1.14.1 | — (aber nicht initialisiert) |
| finnhub-python | Primaer-Datenquelle | ✗ | — | httpx direkter GET; JBlanked Fallback |
| apscheduler | Background Scheduler | ✗ | — | Kein direkter Ersatz — muss installiert werden |
| tenacity | Retry Logic | ✗ | — | Manuelles try/except (vereinfacht) |
| Finnhub API Key | ECAL-01 | ✗ | — | JBlanked (kein Key, aber 1 req/Tag) |
| PostgreSQL | DB | ✓ | laut docker-compose | — |

**Missing dependencies with no fallback:**
- `apscheduler` — muss via `pip install apscheduler==3.11.2` installiert und in requirements.txt ergaenzt werden
- `finnhub-python` — muss via `pip install finnhub-python==2.4.27` installiert werden
- `alembic.ini` + `env.py` — muss manuell initialisiert werden (Alembic-Verzeichnis vorhanden, aber leer)

**Missing dependencies with fallback:**
- Finnhub API Key: JBlanked API als Fallback (kein Key, aber nur 1 req/Tag — nur fuer Demo/Test geeignet)
- Redis nicht erreichbar: Graceful degradation auf In-Memory-Liste (kein Schutz bei Restart)

---

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| investpy (investing.com scraping) | Finnhub offizielle API | 2022-2023 | investpy nicht mehr gewartet |
| APScheduler 2.x/3.x global instance | APScheduler 3.x + lifespan context | 2022 | Sauberes Shutdown |
| ForexFactory XML Scraping | REST APIs mit impact-Feld | 2020+ | Keine ToS-Risiken |
| `Base.metadata.create_all()` in dev | Alembic Migrationen | SQLAlchemy 2.0 | Produktionssicher |

**Deprecated/outdated:**
- `investpy.get_economic_calendar()`: Keine Wartung mehr; letzter Commit 2022; scraping von investing.com blockiert regelmaessig
- APScheduler 4.x: Breaking changes; `AsyncIOScheduler` wurde umbenannt — Version 3.11.2 verwenden
- `requests` library fuer async-Kontext: Blockiert asyncio Event-Loop

---

## Open Questions

1. **Finnhub Free Tier — Economic Calendar Zugang**
   - What we know: Finnhub bietet einen Free Tier; Economic Calendar Endpunkt existiert; die Preisseite listet "Economic Data" als Add-on.
   - What's unclear: Ob der Free Tier (mit API Key) Zugang zum economic calendar hat ohne Bezahlplan.
   - Recommendation: Wave 0 muss API-Key-Test einschliessen; bei 403 direkt auf JBlanked oder direkten Finnhub-HTTP-Endpoint umschalten.

2. **Alembic Initialisierung ohne bestehende Migrations-History**
   - What we know: Das `alembic/` Verzeichnis existiert aber ist leer (kein `alembic.ini`, kein `env.py`). Alle bestehenden Tabellen wurden ohne Alembic erstellt (wahrscheinlich `create_all`).
   - What's unclear: Ob eine erste Baseline-Migration fuer bestehende Tabellen erstellt werden muss.
   - Recommendation: `alembic stamp head` nach `create_all` um bestehenden Stand als Baseline zu markieren, dann additive Migration fuer `economic_events`.

3. **FOMC Blackout-Fenster: Pressekonferenz beruecksichtigen**
   - What we know: FOMC Rate Decision und FOMC Press Conference sind separate Events, ca. 30 min auseinander.
   - What's unclear: Ob beide Events als ein kombiniertes Blackout gelten sollen (insgesamt ~2h).
   - Recommendation: Beide Events getrennt erfassen; kombinierte Blackout-Dauer 90 Minuten nach erster Entscheidung.

---

## Validation Architecture

> nyquist_validation: nicht explizit auf false gesetzt — Abschnitt wird eingeschlossen.

### Test Framework
| Property | Value |
|----------|-------|
| Framework | pytest + pytest-asyncio |
| Config file | Wave 0 muss `pytest.ini` oder `pyproject.toml [tool.pytest]` erstellen |
| Quick run command | `pytest apps/backend/tests/test_economic_calendar.py -x` |
| Full suite command | `pytest apps/backend/tests/ -x` |

### Phase Requirements -> Test Map
| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|-------------|
| ECAL-01 | Fetch liefert Events mit impact-Feld | unit (mocked httpx) | `pytest tests/test_economic_calendar.py::test_fetch_returns_events -x` | Wave 0 |
| ECAL-02 | High-Impact Events werden korrekt gefiltert | unit | `pytest tests/test_economic_calendar.py::test_impact_classification -x` | Wave 0 |
| ECAL-03 | Signal wird HOLD wenn Blackout aktiv | unit | `pytest tests/test_signal_veto.py::test_blackout_blocks_signal -x` | Wave 0 |
| ECAL-04 | Events werden in DB gespeichert | integration | `pytest tests/test_economic_calendar.py::test_event_persisted_to_db -x` | Wave 0 |

### Wave 0 Gaps
- [ ] `apps/backend/tests/test_economic_calendar.py` — covers ECAL-01, ECAL-02, ECAL-04
- [ ] `apps/backend/tests/test_signal_veto.py` — covers ECAL-03
- [ ] `apps/backend/tests/conftest.py` — async db session fixture, redis mock
- [ ] Framework install: `pip install pytest pytest-asyncio pytest-mock`
- [ ] `alembic.ini` + `alembic/env.py` — Alembic-Initialisierung (Wave 0 Infra)

---

## Sources

### Primary (HIGH confidence)
- Finnhub Python Library (GitHub: Finnhub-Stock-API/finnhub-python) — calendar_economic() Methode, Response-Schema
- APScheduler 3.11.2 (PyPI) — aktuelle Version, AsyncIOScheduler, FastAPI Lifespan-Pattern
- TradeForge CLAUDE.md (lokal) — Pflicht-Stack, Coding-Konventionen
- TradeForge requirements.txt (lokal) — tatsaechlich installierte Package-Versionen
- TradeForge signal_service.py (lokal) — bestehende Signal-Pipeline als Integrations-Zielstruktur

### Secondary (MEDIUM confidence)
- JBlanked Calendar API Docs (jblanked.com) — Endpoints, Impact-Filter, Pricing verifiziert via WebFetch
- Vantage Markets / FXNX "News Trading Gold" — Empfohlene Blackout-Fenster fuer NFP/FOMC/CPI
- dev.to/marc_piatkowski — Forex Calendar Pro API, Blackout-Pattern fuer Trading-Bots

### Tertiary (LOW confidence)
- Finnhub Free Tier Economic Calendar Zugang — nicht offiziell bestaetigt ob Free Tier Zugang hat; nur als "basic" erwaehnt

---

## Metadata

**Confidence breakdown:**
- Standard Stack: HIGH — alle Libraries gegen PyPI-Index verifiziert; Versionen geprueft
- Architecture: HIGH — direkt von bestehender Codebase (signal_service.py, models/db/) abgeleitet
- API-Zugaenglichkeit Finnhub Free Tier: LOW — nicht eindeutig aus Preisseite; muss beim Start getestet werden
- Pitfalls: HIGH — direkt aus Codebase-Analyse + Docs

**Research date:** 2026-03-26
**Valid until:** 2026-04-25 (stabile Libraries; Finnhub API-Verfuegbarkeit kann sich aendern)
