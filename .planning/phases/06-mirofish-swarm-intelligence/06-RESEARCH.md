# Phase 6: MiroFish Swarm Intelligence Integration - Research

**Researched:** 2026-03-24
**Domain:** Multi-agent swarm simulation (MiroFish + OASIS + Zep Cloud + OpenAI API)
**Confidence:** HIGH (architecture verified via official sources and live GitHub inspection)

---

<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Decisions
- **D-01:** 10 agents, all focused on economics/macro — NO technical analysis (ML ensemble covers that)
- **D-02:** Agents discuss sequentially — each reacts to what previous agents said (multi-round simulation)
- **D-03:** Discussion runs until consensus is reached (not fixed number of rounds)
- **D-05:** Agents discuss in German
- **D-06:** MiroFish has **veto power** — can block a trade signal if swarm disagrees, but cannot initiate trades on its own
- **D-07:** MiroFish is a **secondary signal** (Nebensignal) — ML ensemble remains dominant (70-80%)
- **D-08:** If MiroFish agrees with ML signal — trade proceeds normally
- **D-09:** If MiroFish vetoes — trade is blocked, logged with reason
- **D-10:** MiroFish runs **in parallel** with ML ensemble but on a **less frequent schedule** (e.g., every 5 minutes)
- **D-11:** Results are **cached** — when ML ensemble produces a signal, the latest MiroFish assessment is used for veto check
- **D-16:** If MiroFish unavailable — **trade without it** — ML ensemble continues normally
- **D-17:** **One warning notification** when MiroFish goes offline, no repeated warnings per tick
- **D-18:** Graceful degradation — bot never stops trading because MiroFish is down

### CRITICAL LLM OVERRIDE
CONTEXT.md D-12 to D-15 specified Ollama. ROADMAP.md (updated 2026-03-09) and REQUIREMENTS.md (MIRO-03, MIRO-06) override this:
- **Use OpenAI API with gpt-4o-mini** (not Ollama — Ollama models too small for MiroFish)
- **MIRO-03:** LLM via OpenAI API (gpt-4o-mini), .env configured with LLM_API_KEY + ZEP_API_KEY + LLM_MODEL_NAME
- **MIRO-06:** API cost limiter limits simulations per day (token budget for gpt-4o-mini)
- ROADMAP.md explicitly states: "Ollama gemma3:1b zu klein fuer MiroFish"
- ROADMAP/REQUIREMENTS are authoritative over CONTEXT.md for LLM choice

### Claude's Discretion
- Specific 10 agent role names and personas
- MiroFish cache TTL (how long a simulation result stays valid)
- Simulation timeout thresholds
- How veto decision is logged and displayed
- MiroFish Flask backend startup integration

### Deferred Ideas (OUT OF SCOPE)
None — discussion stayed within phase scope
</user_constraints>

---

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|------------------|
| MIRO-01 | MiroFish kloned, uv-Deps installiert, Flask-Backend laeuft auf localhost:5001 (Windows 11, Python 3.12, kein Docker) | uv auto-downloads Python 3.11 for MiroFish venv; `uv sync` inside `mirofish/backend/` creates isolated .venv; `python run.py` starts Flask on :5001 |
| MIRO-02 | Zep Cloud verbunden (Free Tier), Knowledge Graph erstellt Gold-Markt-Ontologie aus Seed-Daten | Zep Cloud SDK 3.18.0; graph built via POST /api/graph/ontology/generate + POST /api/graph/build; seed data = Markdown/TXT files |
| MIRO-03 | LLM via OpenAI API (gpt-4o-mini), .env konfiguriert mit LLM_API_KEY + ZEP_API_KEY + LLM_MODEL_NAME | MiroFish Config defaults to gpt-4o-mini; LLM_BASE_URL=https://api.openai.com/v1; validated on startup |
| MIRO-04 | Gold-Agenten (Trader, Analysten, Zentralbanker) simulieren XAUUSD-Szenarien, Ergebnis als Prediction-Score | Agent profiles auto-generated from Zep graph entities; `platform=parallel` for max agent interaction; result extracted from report markdown |
| MIRO-05 | mirofish_client.py integriert Swarm-Score in signal_generator.py neben XGBoost/LightGBM Ensemble | Async httpx client; veto check after `_ai_predictor.predict()` at line 41-45 of signal_generator.py; cached result from background task |
| MIRO-06 | API-Kosten-Limiter begrenzt Simulationen pro Tag (Token-Budget fuer gpt-4o-mini) | Counter in JSON file; max_simulations_per_day and token_budget settings; checked before each simulation trigger |
</phase_requirements>

---

## Summary

MiroFish (github.com/666ghj/MiroFish) is a Flask-based multi-agent social simulation engine powered by the CAMEL-AI OASIS framework. It creates a "digital world" from seed documents, builds a Zep Cloud knowledge graph, generates agent personas, runs a multi-round social simulation via OASIS, and produces a prediction report via a ReACT-based report agent.

**Critical Python version conflict:** MiroFish's `camel-oasis==0.2.5` dependency requires Python `<3.12`. The host project runs Python 3.12.10. The solution is standard: `uv sync` inside `mirofish/backend/` creates an isolated Python 3.11 virtual environment automatically (uv auto-downloads Python 3.11 if not present). The host project and MiroFish run in completely separate Python environments. No conflict.

**Integration architecture:** MiroFish runs as a separate Flask subprocess on port 5001. The trading bot communicates with it exclusively via HTTP REST API using the existing `httpx` library (already in requirements.txt at version 0.28.1). A background `asyncio.Task` triggers periodic simulations (every ~5 minutes), caches the latest swarm score, and the `_generate_signal()` method performs a veto check against the cached result before returning a signal. This means the 60-180 second simulation latency never blocks the trading loop.

**Primary recommendation:** Clone MiroFish to `mirofish/`, run `uv sync` inside `mirofish/backend/` to get an isolated Python 3.11 env, build an async httpx client in `ai_engine/mirofish_client.py`, and add veto logic after line 44 in `trading/signal_generator.py`. Keep `mirofish_enabled: bool = False` as the default in settings so the bot trades normally when MiroFish is not configured.

---

## Standard Stack

### Core
| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| MiroFish | latest (git clone) | Multi-agent simulation engine | The specific system being integrated per MIRO-01 |
| camel-oasis | 0.2.5 (MiroFish pins) | OASIS social simulation framework inside MiroFish | MiroFish hard-pins this version; runs in isolated Python 3.11 venv |
| camel-ai | 0.2.78 (MiroFish pins) | Agent orchestration framework | Required by camel-oasis |
| zep-cloud | 3.13.0 (MiroFish pins) | Knowledge graph memory for agents | Required by MiroFish; Zep Cloud free tier covers this |
| flask | >=3.0.0 (MiroFish internal) | MiroFish backend API server | MiroFish uses it internally; never installed in host project |
| openai | >=1.0.0 (MiroFish internal) | LLM calls inside MiroFish | MiroFish uses OpenAI-compatible SDK |
| httpx | 0.28.1 (already in host project) | Async HTTP client for MiroFish REST API calls | Already in project requirements.txt; preferred async HTTP client |
| uv | 0.10.2 (already installed) | Python env manager for MiroFish's Python 3.11 venv | camel-oasis requires Python <3.12; uv auto-downloads Python 3.11 |

### Supporting
| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| python-dotenv | >=1.0.0 | .env loading inside MiroFish | Used by MiroFish Config class |
| PyMuPDF | >=1.24.0 | PDF parsing for seed documents | Only if PDF seed docs needed (Markdown/TXT is simpler) |
| asyncio | stdlib | Background simulation task scheduling | Trading loop is already fully async |
| Node.js | 25.6 (already installed) | MiroFish frontend (Vue.js) | Only needed if web UI is wanted — NOT needed for headless API use |

### Alternatives Considered
| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| httpx async | aiohttp | Both in requirements.txt; httpx has cleaner async API, better timeout handling, and test mocking |
| OpenAI API | Ollama | Ollama models too small for MiroFish quality — ROADMAP.md is explicit: "gemma3:1b zu klein" |
| Full MiroFish UI flow (5-step wizard) | Direct REST API calls only | UI not needed; programmatic API flow is simpler and fully sufficient |
| MiroFish main branch | MiroFish-Offline fork (nikmcfly) | Offline fork uses Neo4j instead of Zep Cloud; adds complexity; REQUIREMENTS.md mandates Zep Cloud |

**Installation for MiroFish venv (run inside mirofish/backend/):**
```bash
cd mirofish/backend
uv sync
# uv auto-downloads Python 3.11 and installs all deps in mirofish/backend/.venv/
```

**Start MiroFish Flask backend:**
```bash
# From mirofish/backend/ directory
uv run python run.py
# OR on Windows: .venv\Scripts\python.exe run.py
```

**Version verification:** MiroFish `backend/pyproject.toml` requires-python = ">=3.11". camel-oasis PyPI page: Python <3.12, >=3.10. Node.js 25.6.1 and uv 0.10.2 confirmed installed.

---

## Architecture Patterns

### Recommended Project Structure
```
mirofish/                    # Cloned MiroFish repo
├── backend/
│   ├── .venv/               # Python 3.11 venv (uv sync creates this)
│   ├── app/
│   │   ├── api/             # Blueprints: /api/graph, /api/simulation, /api/report
│   │   ├── services/        # OntologyGenerator, SimulationRunner, ReportAgent
│   │   └── config.py        # Config class reads LLM_API_KEY, ZEP_API_KEY from .env
│   ├── pyproject.toml       # requires-python = ">=3.11"
│   ├── run.py               # Entry: Flask on :5001, threaded=True
│   └── .env                 # LLM_API_KEY, ZEP_API_KEY, LLM_MODEL_NAME, LLM_BASE_URL
├── frontend/                # Vue.js (not needed for headless API use)
└── .env.example

ai_engine/
└── mirofish_client.py       # NEW: Async REST client + SwarmAssessment cache

trading/
└── signal_generator.py      # MODIFIED: veto check inserted after line 44

config/
└── settings.py              # MODIFIED: add mirofish_* settings

mirofish_seeds/              # NEW: Gold market seed documents for Zep graph
├── gold_market_overview.md
├── xauusd_macro_factors.md
└── gold_market_actors.md

logs/
└── mirofish_cost.json       # NEW: daily sim counter + token budget state
└── mirofish_state.json      # NEW: persisted project_id + graph_id
```

### Pattern 1: MiroFish as Background Service with Cached Results
**What:** MiroFish runs in a separate process (Flask :5001). A background `asyncio.Task` polls MiroFish every N minutes, stores the latest swarm assessment in memory.
**When to use:** Always — this prevents MiroFish's multi-step simulation (60-180 seconds) from blocking the trading loop.

```python
# ai_engine/mirofish_client.py
import asyncio
import logging
import time
from dataclasses import dataclass, field
from typing import Optional
import httpx

logger = logging.getLogger(__name__)

@dataclass
class SwarmAssessment:
    direction: str        # "BUY", "SELL", or "NEUTRAL"
    confidence: float     # 0.0 to 1.0
    reasoning: str        # German text summary from report
    timestamp: float = field(default_factory=time.monotonic)

class MiroFishClient:
    """Async client for MiroFish REST API on localhost:5001."""

    def __init__(
        self,
        base_url: str = "http://localhost:5001",
        timeout_seconds: float = 180.0,
        cache_ttl_seconds: float = 360.0,
        max_simulations_per_day: int = 48,
        token_budget_per_day: int = 200_000,
    ) -> None:
        self._base_url = base_url
        self._timeout = timeout_seconds
        self._cache_ttl = cache_ttl_seconds
        self._cached: Optional[SwarmAssessment] = None
        self._offline_warned: bool = False
        self._project_id: Optional[str] = None
        self._graph_id: Optional[str] = None

    async def health_check(self) -> bool:
        try:
            async with httpx.AsyncClient(timeout=5.0) as client:
                resp = await client.get(f"{self._base_url}/health")
                return resp.status_code == 200
        except Exception:
            return False

    def get_cached_assessment(self) -> Optional[SwarmAssessment]:
        """Return cached swarm assessment if still valid within TTL."""
        if self._cached is None:
            return None
        age = time.monotonic() - self._cached.timestamp
        if age > self._cache_ttl:
            return None
        return self._cached
```

### Pattern 2: Veto Check in signal_generator.py
**What:** After ML ensemble produces a non-HOLD signal, check cached MiroFish assessment. If swarm direction contradicts ML signal, convert to HOLD.
**When to use:** For every BUY/SELL signal from the ML ensemble (D-06 to D-09).

```python
# trading/signal_generator.py - modification at line 44-45
signal = await self._ai_predictor.predict(
    candle_data=candle_data,
    primary_timeframe="5m",
)

# MiroFish veto check (secondary signal)
if signal and signal.get("action") not in (None, "HOLD"):
    signal = await self._apply_mirofish_veto(signal)

return signal
```

```python
# Add to SignalGeneratorMixin:
async def _apply_mirofish_veto(self: TradingSystem, signal: dict) -> dict:
    """Check MiroFish swarm and veto if contradicted (D-06 to D-09)."""
    if not self.settings.mirofish_enabled:
        return signal

    if self._mirofish_client is None:
        from ai_engine.mirofish_client import MiroFishClient
        self._mirofish_client = MiroFishClient(
            base_url=self.settings.mirofish_url,
        )

    assessment = self._mirofish_client.get_cached_assessment()
    if assessment is None:
        return signal  # No cache — trade without MiroFish (D-16)

    ml_action = signal["action"]
    swarm_direction = assessment.direction

    if (
        (ml_action == "BUY" and swarm_direction == "SELL") or
        (ml_action == "SELL" and swarm_direction == "BUY")
    ):
        veto_reason = (
            f"MiroFish veto: swarm={swarm_direction}, ml={ml_action}. "
            f"{assessment.reasoning}"
        )
        logger.info("Trade BLOCKED by MiroFish: %s", veto_reason)
        return {
            **signal,
            "action": "HOLD",
            "mirofish_veto": True,
            "mirofish_reasoning": veto_reason,
        }

    return {
        **signal,
        "mirofish_veto": False,
        "mirofish_direction": swarm_direction,
        "mirofish_reasoning": assessment.reasoning,
    }
```

### Pattern 3: Full Simulation REST API Workflow
**What:** The complete multi-step REST API flow to run one simulation and extract a score.
**When to use:** In the background task that populates the cache.

**Verified API sequence (from MiroFish source):**
```
One-time setup (persist project_id + graph_id):
  POST /api/graph/ontology/generate  body={files, requirements}
  POST /api/graph/build              body={project_id}
  GET  /api/graph/task/{task_id}     poll until status=completed

Per simulation (reuse project_id + graph_id):
  POST /api/simulation/create        body={project_id, graph_id}
  POST /api/simulation/prepare       body={simulation_id, type="profiles"}
  POST /api/simulation/prepare/status  poll until done
  POST /api/simulation/prepare       body={simulation_id, type="config"}
  POST /api/simulation/prepare/status  poll until done
  POST /api/simulation/start         body={simulation_id, platform="parallel",
                                          max_rounds=15,
                                          enable_graph_memory_update=false}
  GET  /api/simulation/{id}/run-status  poll every 3s until completed
  POST /api/report/generate          body={simulation_id}
  POST /api/report/generate/status   poll until completed
  GET  /api/report/{report_id}       -> {data: {content: "markdown..."}}
```

**Key optimization:** Graph build (Steps 1-2) is done ONCE and `graph_id` is reused for all subsequent simulations. This saves 5-15 LLM calls and 30-60 seconds per simulation.

### Pattern 4: API Cost Limiter (MIRO-06)
**What:** A daily counter in a JSON file, checked before each simulation trigger.
**When to use:** Always — required by MIRO-06.

```python
# ai_engine/mirofish_client.py
import json
from datetime import date
from pathlib import Path

class MiroFishCostLimiter:
    """Daily simulation counter + token budget guard (MIRO-06)."""

    def __init__(
        self,
        state_file: str = "logs/mirofish_cost.json",
        max_sims_per_day: int = 48,
        token_budget_per_day: int = 200_000,
    ) -> None:
        self._path = Path(state_file)
        self._max_sims = max_sims_per_day
        self._token_budget = token_budget_per_day

    def _load(self) -> dict:
        today = str(date.today())
        if self._path.exists():
            try:
                data = json.loads(self._path.read_text())
                if data.get("date") == today:
                    return data
            except Exception:
                pass
        return {"date": today, "sim_count": 0, "tokens_used": 0}

    def _save(self, state: dict) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._path.write_text(json.dumps(state))

    def can_run(self) -> tuple[bool, str]:
        """Returns (allowed, reason). Empty reason string means allowed."""
        state = self._load()
        if state["sim_count"] >= self._max_sims:
            return False, f"Daily limit reached: {state['sim_count']}/{self._max_sims}"
        if state["tokens_used"] >= self._token_budget:
            return False, f"Token budget exhausted: {state['tokens_used']}/{self._token_budget}"
        return True, ""

    def record_run(self, tokens_used: int = 5000) -> None:
        state = self._load()
        state["sim_count"] += 1
        state["tokens_used"] += tokens_used
        self._save(state)
```

### Pattern 5: Gold-Specific Seed Template (Markdown)
**What:** Concise Markdown document describing gold market context, injected as seed data.
**When to use:** Stored in `mirofish_seeds/`, uploaded once to build the Zep graph.

Key entities to include for ~10 agent personas:
- Federal Reserve (Fed-Vertreter)
- European Central Bank (EZB-Analyst)
- Inflation Expert (Inflationsexperte)
- US Dollar Analyst (Dollar-Stratege)
- Bond Market Expert (Anleihenmarkt-Analyst)
- Geopolitics Expert (Geopolitik-Analyst)
- Commodities Trader (Rohstoff-Haendler)
- Hedge Fund Manager (Hedgefonds-Manager)
- Central Bank Gold Buyer (Zentralbank-Goldkaeufer)
- Emerging Markets Analyst (Schwellenlaender-Analyst)

### Anti-Patterns to Avoid
- **Blocking the trading loop with simulation:** Never `await` a full simulation inside `_trading_tick()`. Always use cached result only.
- **Running graph build on every simulation:** Graph build costs 5-15 LLM calls. Build once, persist graph_id.
- **Installing MiroFish deps in host project venv:** Never run `pip install camel-oasis` in the host project; it requires Python <3.12 and conflicts. Only install via `uv sync` inside `mirofish/backend/`.
- **Expecting structured JSON from MiroFish reports:** Reports are free-form markdown narrative. Parse with keywords or use `/api/report/chat` for structured extraction.
- **Running all 5 MiroFish UI steps for every poll cycle:** Only repeat simulation create/prepare/start/report. The graph_id is persistent.

---

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Agent conversation management | Custom LLM multi-turn loop | MiroFish OASIS engine | Sequential agent discussion with memory is exactly what OASIS provides |
| Knowledge graph construction | Manual entity extraction from seed text | MiroFish OntologyGenerator + Zep Cloud | Extracts entities, edge types, and builds GraphRAG automatically |
| Report generation from agent outputs | Custom summarization | MiroFish ReportAgent (ReACT loop) | Has InsightForge, PanoramaSearch, InterviewSubAgent tools |
| Agent memory persistence across rounds | Custom database | Zep Cloud (built into MiroFish) | Temporal graph memory; included in MiroFish pipeline |
| Async HTTP calls to MiroFish | requests + ThreadPoolExecutor | httpx.AsyncClient | httpx already in requirements.txt; proper async support |
| Python 3.11 environment for MiroFish | Manual Python download and install | uv python install 3.11 + uv sync | uv auto-downloads the correct Python; already installed (v0.10.2) |

**Key insight:** MiroFish is a self-contained system. The integration layer should be thin — an async HTTP client (httpx) that triggers the API pipeline and parses the report output. Everything inside MiroFish (agents, graph, simulation, report) runs in MiroFish's own process and Python environment.

---

## Common Pitfalls

### Pitfall 1: Python Version Conflict (CRITICAL)
**What goes wrong:** `pip install camel-oasis` fails because camel-oasis requires Python `<3.12` and the host project uses Python 3.12.10.
**Why it happens:** camel-oasis pyproject.toml declares `python = ">=3.10.0,<3.12"`.
**How to avoid:** Always run `uv sync` from within `mirofish/backend/`. uv reads MiroFish's `pyproject.toml` (`requires-python = ">=3.11"`), auto-downloads Python 3.11, and creates an isolated `.venv` inside `mirofish/backend/`. The host project's Python 3.12 is unaffected.
**Warning signs:** "ERROR: Package requires a different Python" during any manual pip install of camel-oasis.

```bash
# CORRECT — run from mirofish/backend/ only
cd mirofish/backend && uv sync

# WRONG — never do this in the host project venv
pip install camel-oasis  # Fails on Python 3.12
```

### Pitfall 2: Graph Build on Every Simulation
**What goes wrong:** Each simulation triggers a full graph rebuild, costing 5-15 LLM calls and 30-60 extra seconds.
**Why it happens:** Following the full 5-step UI flow every time without reusing graph_id.
**How to avoid:** Persist `project_id` and `graph_id` in `logs/mirofish_state.json` after first successful build. Verify validity on startup via `GET /api/graph/data/{graph_id}`. Only rebuild if seed data changes.
**Warning signs:** API cost per simulation > $1.00; simulation prep taking > 3 minutes.

### Pitfall 3: Simulation Blocking the Trading Loop
**What goes wrong:** Full simulation pipeline takes 60-180 seconds. If awaited inside `_trading_tick()`, the trading loop stalls.
**Why it happens:** Naive synchronous integration.
**How to avoid:** Run simulations in a separate `asyncio.Task` (background). Signal generator reads cache only; never triggers a new simulation.
**Warning signs:** Trading interval increases from 60s to 120-300s.

### Pitfall 4: Zep Cloud Free Tier Rate Limits
**What goes wrong:** HTTP 429 from Zep Cloud during rapid graph builds.
**Why it happens:** Rebuilding graph too frequently or with very large seed documents.
**How to avoid:** Reuse graph_id. Keep seed documents concise (under 2000 words total). The free tier is sufficient for one persistent gold market graph.
**Warning signs:** HTTP 429 in MiroFish Flask logs.

### Pitfall 5: MiroFish Flask Port Conflict on Windows
**What goes wrong:** MiroFish fails to start because port 5001 is already in use.
**Why it happens:** Port 5001 can be occupied by other services on Windows.
**How to avoid:** Add health check before each background simulation cycle. If health check fails, log one warning (D-17), then fall back to trading without MiroFish. Use `FLASK_PORT` env var to configure alternative port if needed.
**Warning signs:** `OSError: [WinError 10048] Only one usage of each socket address` in MiroFish startup.

### Pitfall 6: Report Is Markdown Narrative, Not Structured JSON
**What goes wrong:** Code tries to `json.loads()` the report content and crashes.
**Why it happens:** MiroFish report endpoint returns free-form markdown, not structured data.
**How to avoid:** Parse markdown with keyword matching (see Code Examples). For higher reliability, use `POST /api/report/chat` with a structured extraction prompt after report generation.
**Warning signs:** `mirofish_direction` always returns "NEUTRAL" regardless of market conditions.

### Pitfall 7: Windows Path Issues with uv Run
**What goes wrong:** `uv run python run.py` fails because Flask can't find its own modules.
**Why it happens:** Working directory matters for module imports.
**How to avoid:** Always cd into `mirofish/backend/` before running, or use `uv run --directory mirofish/backend python run.py`. On Windows, the Python executable is at `mirofish/backend/.venv/Scripts/python.exe`.

### Pitfall 8: Token Runaway from Uncontrolled Rounds
**What goes wrong:** Simulation consumes 50,000+ tokens in one run.
**Why it happens:** `max_rounds` not set; OASIS default is 10 rounds but with many agents and verbose output, token use multiplies.
**How to avoid:** Always pass `max_rounds: 15` in the start request. For 10 agents x 15 rounds with gpt-4o-mini: estimated 15,000-30,000 tokens per simulation = ~$0.005-0.02 per run. At 48 runs/day, daily cost < $1.00.

---

## Code Examples

Verified patterns from MiroFish source code and project codebase:

### Settings Extension
```python
# config/settings.py — add to Settings class
# Source: project settings.py pattern (pydantic-settings BaseSettings)

# -- MiroFish Swarm Intelligence (Phase 6) --------------------------------
mirofish_enabled: bool = False           # Opt-in; False = graceful fallback (D-16)
mirofish_url: str = "http://localhost:5001"
mirofish_cache_ttl_seconds: int = 360   # 6 minutes — cached result validity (D-11)
mirofish_poll_interval_seconds: int = 300  # 5 minutes — background sim frequency (D-10)
mirofish_max_sims_per_day: int = 48     # MIRO-06: max daily simulations
mirofish_token_budget_per_day: int = 200_000  # MIRO-06: ~$0.04/day at gpt-4o-mini
mirofish_simulation_timeout_seconds: float = 180.0  # 3 min max per sim
mirofish_max_rounds: int = 15           # OASIS simulation rounds
```

### MiroFish .env Configuration
```bash
# mirofish/backend/.env
# Source: MiroFish config.py fields
LLM_API_KEY=sk-...          # OpenAI API key (same as project's OPENAI_API_KEY)
LLM_BASE_URL=https://api.openai.com/v1
LLM_MODEL_NAME=gpt-4o-mini
ZEP_API_KEY=z_...           # From app.getzep.com Free Tier
FLASK_PORT=5001
```

### Parse Swarm Direction from Markdown Report
```python
# Source: Pattern derived from expected German MiroFish output (D-05 agents discuss in German)

def parse_swarm_direction(report_markdown: str) -> tuple[str, float, str]:
    """
    Parse direction, confidence, and summary from MiroFish report markdown.
    Returns: (direction, confidence, reasoning_summary)
    direction: "BUY" | "SELL" | "NEUTRAL"
    """
    text = report_markdown.lower()

    bullish_keywords = [
        "aufwartstrend", "steigende preise", "kaufsignal", "bullish",
        "preissteigerung", "hausse", "nachfrage steigt", "positive entwicklung",
        "zentralbank kauft", "geopolitische unsicherheit steigt",
        "inflationsdruck", "dollar schwacht",
    ]
    bearish_keywords = [
        "abwartstrend", "fallende preise", "verkaufssignal", "bearish",
        "baisse", "kurs fallt", "dollar starkt", "zinsanstieg",
        "restriktive geldpolitik", "druck auf goldpreis", "risikoappetit steigt",
    ]

    bullish_count = sum(1 for kw in bullish_keywords if kw in text)
    bearish_count = sum(1 for kw in bearish_keywords if kw in text)
    total = bullish_count + bearish_count

    if total == 0:
        return "NEUTRAL", 0.5, "Keine klare Richtung erkennbar"

    margin = abs(bullish_count - bearish_count)
    confidence = min(0.9, 0.5 + margin / (total * 2.0))

    if bullish_count > bearish_count:
        summary = f"Bullish: {bullish_count} Signale, Bearish: {bearish_count}"
        return "BUY", confidence, summary
    elif bearish_count > bullish_count:
        summary = f"Bearish: {bearish_count} Signale, Bullish: {bullish_count}"
        return "SELL", confidence, summary
    else:
        return "NEUTRAL", 0.5, f"Unentschieden: je {bullish_count} Signale"
```

### MiroFish Background Task (asyncio)
```python
# ai_engine/mirofish_client.py — background polling task
# Source: project async patterns from trading_loop.py

async def run_simulation_loop(client: "MiroFishClient", interval_seconds: int = 300) -> None:
    """Background task: run simulation every N seconds, update cache."""
    while True:
        try:
            is_alive = await client.health_check()
            if not is_alive:
                if not client._offline_warned:
                    logger.warning("MiroFish backend offline — trading without swarm signal")
                    client._offline_warned = True
            else:
                client._offline_warned = False
                allowed, reason = client._cost_limiter.can_run()
                if allowed:
                    await client._run_one_simulation()
                else:
                    logger.debug("MiroFish cost limit: %s", reason)
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            logger.debug("MiroFish simulation error (non-fatal): %s", exc)

        await asyncio.sleep(interval_seconds)
```

### MiroFish Backend Subprocess Start (Windows)
```python
# Source: MiroFish run.py pattern + Windows path conventions

import subprocess
from pathlib import Path

def start_mirofish_backend(mirofish_dir: str = "mirofish/backend") -> subprocess.Popen:
    """Start MiroFish Flask backend as subprocess on Windows."""
    backend_path = Path(mirofish_dir).resolve()
    python_exe = backend_path / ".venv" / "Scripts" / "python.exe"

    if not python_exe.exists():
        raise RuntimeError(
            f"MiroFish venv not found at {python_exe}. "
            f"Run: cd {backend_path} && uv sync"
        )

    proc = subprocess.Popen(
        [str(python_exe), "run.py"],
        cwd=str(backend_path),
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    return proc
```

---

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| Single LLM call for market analysis | Multi-agent OASIS simulation with persistent memory | 2024-2025 | Emergent perspectives from agent interaction; richer than single prompt |
| Zep as chat history only | Zep as GraphRAG knowledge graph (entities + edges) | Zep Cloud 3.x | Graph relationships between entities, not just episode history |
| camel-ai direct | camel-oasis wrapper for social simulation | 0.2.5 (Dec 2025) | Pre-built Twitter/Reddit simulation infrastructure; MiroFish uses it |
| pip for all dependencies | uv for packages with Python version constraints | uv 0.x | Handles Python version isolation natively; auto-downloads required Python |

**Deprecated/outdated:**
- Ollama for MiroFish: ROADMAP.md explicitly overrides CONTEXT.md — "Ollama gemma3:1b zu klein fuer MiroFish". Verified correct: OASIS requires robust LLM reasoning for multi-agent economic simulation.
- Docker for MiroFish: Not needed. Source install with `uv sync` is simpler and works on Windows 11 without Docker Desktop.
- MiroFish-Offline fork: Uses Neo4j instead of Zep Cloud. REQUIREMENTS.md mandates Zep Cloud. Do not use this fork.

---

## Open Questions

1. **Graph ID validity after MiroFish process restarts**
   - What we know: graph_id is returned after graph build; persisting it saves LLM calls
   - What's unclear: Does Zep Cloud graph persist between MiroFish restarts? The graph lives in Zep Cloud (not MiroFish's local state), so it should persist.
   - Recommendation: Persist graph_id in `logs/mirofish_state.json`. Verify on startup with `GET /api/graph/data/{graph_id}`. If 404, rebuild graph. Expected: graph should persist since it's stored in Zep Cloud.

2. **Report content parsing reliability**
   - What we know: MiroFish report is free-form markdown narrative in German (D-05). Keyword matching is fragile.
   - What's unclear: How consistent is report structure across different market conditions?
   - Recommendation: Use `POST /api/report/chat` as a secondary extraction after report generation. Send: "Antworte nur mit JSON: {\"richtung\": \"KAUFEN\"|\"VERKAUFEN\"|\"NEUTRAL\", \"konfidenz\": 0.0-1.0, \"begruendung\": \"...\"}". This is one additional gpt-4o-mini call but gives structured output.

3. **Agent count from seed documents**
   - What we know: Agent count is derived from Zep graph entities extracted from seed documents. MiroFish user guide says no manual agent count config.
   - What's unclear: Whether 10 agents (D-01) can be reliably achieved.
   - Recommendation: Include exactly 10 named entity types in seed documents. The `POST /api/simulation/generate-profiles` endpoint may also allow explicit profile count — verify during implementation.

4. **First run duration estimate**
   - What we know: Graph build + sim prepare + sim run + report = multiple sequential steps; each involves LLM calls.
   - What's unclear: Total wall-clock time for first run on the hardware profile (Ryzen 5 4500, gpt-4o-mini API latency ~1-2s/call).
   - Recommendation: Expect 5-15 minutes for first full pipeline (including graph build). Set `mirofish_simulation_timeout_seconds=600` for first run. Subsequent runs (reusing graph_id): expect 3-7 minutes.

---

## Environment Availability

| Dependency | Required By | Available | Version | Fallback |
|------------|------------|-----------|---------|----------|
| Python 3.12 | Host project | ✓ | 3.12.10 | — |
| Python 3.11 | MiroFish camel-oasis | auto via uv | uv auto-downloads | `uv python install 3.11` |
| uv | MiroFish dep install | ✓ | 0.10.2 | — |
| Node.js | MiroFish frontend (optional) | ✓ | 25.6.1 | Not needed for headless API use |
| git | Clone MiroFish | ✓ | 2.52.0 | — |
| httpx | MiroFish REST client | ✓ | 0.28.1 | aiohttp 3.11+ (also in requirements.txt) |
| pytest | Test suite | ✓ | 9.0.2 | — |
| MiroFish backend | Simulation engine | ✗ (not cloned) | — | Bot trades without it (D-16, mirofish_enabled=False) |
| Zep Cloud API key | Knowledge graph | ✗ (needs account) | — | MiroFish disabled until configured |
| OpenAI API key | LLM inside MiroFish | ✓ (already in .env) | gpt-4o-mini | — |
| Port 5001 | MiroFish Flask | unverified | — | FLASK_PORT env var for alternative |

**Missing dependencies with no fallback:**
- MiroFish must be cloned and `uv sync` run before any simulation is possible
- Zep Cloud account + ZEP_API_KEY required for graph building

**Missing dependencies with fallback:**
- All trading bot functions continue normally when MiroFish is unavailable (D-16)
- `mirofish_enabled: bool = False` default means zero impact until explicitly configured
- If MiroFish goes offline mid-session: bot continues trading using ML ensemble only (D-18)

---

## Validation Architecture

### Test Framework
| Property | Value |
|----------|-------|
| Framework | pytest 9.0.2 |
| Config file | pyproject.toml `[tool.pytest.ini_options]` |
| Quick run command | `python -m pytest tests/test_mirofish_client.py -x --tb=short` |
| Full suite command | `python -m pytest tests/ -x --tb=short` |

### Phase Requirements to Test Map
| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|-------------|
| MIRO-01 | MiroFish Flask health check returns 200 | integration (skipif no backend) | `pytest tests/test_mirofish_client.py::test_health_check -x` | ❌ Wave 0 |
| MIRO-02 | Zep graph build result can be stored and retrieved | integration (skipif no API key) | `pytest tests/test_mirofish_client.py::test_graph_state_persistence -x` | ❌ Wave 0 |
| MIRO-03 | .env LLM_API_KEY + ZEP_API_KEY readable by MiroFish config | unit | `pytest tests/test_mirofish_client.py::test_env_config -x` | ❌ Wave 0 |
| MIRO-04 | Simulation produces non-empty report markdown | integration (skipif no backend) | `pytest tests/test_mirofish_client.py::test_simulation_produces_report -x` | ❌ Wave 0 |
| MIRO-05 | BUY signal blocked when cached swarm direction is SELL | unit | `pytest tests/test_mirofish_client.py::test_veto_buy_blocked_by_sell -x` | ❌ Wave 0 |
| MIRO-05 | SELL signal blocked when cached swarm direction is BUY | unit | `pytest tests/test_mirofish_client.py::test_veto_sell_blocked_by_buy -x` | ❌ Wave 0 |
| MIRO-05 | BUY signal passes when swarm is NEUTRAL | unit | `pytest tests/test_mirofish_client.py::test_veto_neutral_passthrough -x` | ❌ Wave 0 |
| MIRO-05 | Signal passes unchanged when mirofish_enabled=False | unit | `pytest tests/test_mirofish_client.py::test_disabled_passthrough -x` | ❌ Wave 0 |
| MIRO-05 | Signal passes when no cached assessment available | unit | `pytest tests/test_mirofish_client.py::test_no_cache_passthrough -x` | ❌ Wave 0 |
| MIRO-06 | Cost limiter blocks when sim_count >= max_sims_per_day | unit | `pytest tests/test_mirofish_client.py::test_cost_limiter_max_sims -x` | ❌ Wave 0 |
| MIRO-06 | Cost limiter blocks when tokens_used >= budget | unit | `pytest tests/test_mirofish_client.py::test_cost_limiter_token_budget -x` | ❌ Wave 0 |
| MIRO-06 | Cost limiter resets on new day | unit | `pytest tests/test_mirofish_client.py::test_cost_limiter_daily_reset -x` | ❌ Wave 0 |

### Sampling Rate
- **Per task commit:** `python -m pytest tests/test_mirofish_client.py -x --tb=short`
- **Per wave merge:** `python -m pytest tests/ -x --tb=short`
- **Phase gate:** Full suite green before `/gsd:verify-work`

### Wave 0 Gaps
- [ ] `tests/test_mirofish_client.py` — covers all MIRO-01 through MIRO-06 tests above
- [ ] Fixture: mock httpx responses for unit tests (use `respx` or `pytest-httpx` for httpx mocking)
- [ ] Integration tests decorated with `@pytest.mark.skipif(not MIROFISH_AVAILABLE, reason="MiroFish not running")`
- [ ] Fixture: temporary `logs/mirofish_cost.json` for cost limiter tests

---

## Project Constraints (from CLAUDE.md)

No `CLAUDE.md` found in the project root. No additional project-specific constraints to enforce.

---

## Sources

### Primary (HIGH confidence)
- MiroFish GitHub repo https://github.com/666ghj/MiroFish — backend structure, blueprints, API routes
- MiroFish `backend/pyproject.toml` — requires-python = ">=3.11", exact dep versions
- MiroFish `backend/app/config.py` — Config class fields: LLM_API_KEY, ZEP_API_KEY, LLM_BASE_URL defaults, LLM_MODEL_NAME defaults
- MiroFish `backend/run.py` — Flask on port 5001, threaded=True, Config.validate() on startup
- MiroFish `backend/app/__init__.py` — three blueprints: /api/graph, /api/simulation, /api/report; /health endpoint
- camel-oasis GitHub pyproject.toml — `python = ">=3.10.0,<3.12"` confirmed via WebFetch
- Project `requirements.txt` — httpx 0.28.1, aiohttp, Python 3.12.10 confirmed
- Project `config/settings.py` — pydantic-settings BaseSettings pattern to follow
- Project `trading/signal_generator.py` — exact integration point at lines 41-45
- ROADMAP.md Phase 6 — authoritative: OpenAI gpt-4o-mini (not Ollama), Zep Cloud mandatory

### Secondary (MEDIUM confidence)
- DeepWiki MiroFish overview https://deepwiki.com/666ghj/MiroFish — end-to-end workflow, API call sequence
- MiroFish simulation API routes (verified via WebFetch of simulation.py) — POST /create, /prepare, /start, run-status
- MiroFish report API routes — POST /generate, GET /{report_id}
- MiroFish graph API routes — POST /ontology/generate, /build
- PyPI camel-oasis — version 0.2.5, Python <3.12 requirement
- PyPI zep-cloud — version 3.18.0, Python >=3.9
- OpenClaw MiroFish deployment guide — RAM requirements (16GB for 40+ rounds)
- OpenAI pricing — gpt-4o-mini $0.15/1M input, $0.60/1M output tokens (verified 2026)
- uv docs — `uv sync` creates isolated venv with auto Python download

### Tertiary (LOW confidence)
- Report parsing keyword heuristic — derived from expected German output pattern (D-05), not tested against actual MiroFish output
- Per-simulation token estimates (15,000-30,000 tokens) — estimated from agent count and round count, not measured
- Graph ID Zep Cloud persistence across restarts — logically expected (Zep is the store), not verified empirically

---

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH — verified via MiroFish pyproject.toml, PyPI pages, live GitHub inspection
- Python conflict + uv solution: HIGH — camel-oasis pyproject.toml is explicit; uv behavior is documented
- Architecture: HIGH — MiroFish API endpoints verified from source; integration pattern matches existing async codebase
- Cost estimates: MEDIUM — gpt-4o-mini pricing verified; per-simulation token usage is an estimate
- Report parsing: LOW — keyword heuristic is unverified against actual MiroFish output in German

**Research date:** 2026-03-24
**Valid until:** 2026-04-24 (MiroFish is actively developed — re-verify before implementation if >2 weeks pass)
