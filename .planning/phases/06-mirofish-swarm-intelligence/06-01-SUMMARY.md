---
phase: 06-mirofish-swarm-intelligence
plan: "01"
subsystem: mirofish-infrastructure
tags: [mirofish, zep-cloud, openai, flask, setup, config, seeds]
dependency_graph:
  requires: []
  provides:
    - mirofish-seed-data
    - mirofish-settings
    - mirofish-startup-script
  affects:
    - config/settings.py
    - scripts/start_mirofish.py
    - mirofish_seeds/
tech_stack:
  added:
    - uv (isolated Python 3.11 venv for MiroFish/camel-oasis)
    - MiroFish (github.com/666ghj/MiroFish, Flask backend on :5001)
    - gpt-4o-mini via OpenAI API (LLM_API_KEY in mirofish/backend/.env)
    - Zep Cloud (ZEP_API_KEY, knowledge graph for agent memory)
  patterns:
    - Settings fields with safe defaults (mirofish_enabled=False for D-16 graceful degradation)
    - Self-contained setup script with argparse subcommands (setup/start/status)
    - subprocess.Popen for non-blocking Flask backend launch with health-check polling
key_files:
  created:
    - mirofish_seeds/gold_market_overview.md
    - mirofish_seeds/xauusd_macro_factors.md
    - mirofish_seeds/gold_market_actors.md
    - scripts/start_mirofish.py
  modified:
    - config/settings.py
decisions:
  - Use OpenAI API (gpt-4o-mini) not Ollama -- RESEARCH.md overrides CONTEXT.md D-12/D-13 (Ollama too small)
  - mirofish_enabled defaults to False (D-16 graceful degradation -- bot trades normally without MiroFish)
  - LLM_API_KEY reuses OPENAI_API_KEY from host .env (user avoids maintaining two keys)
  - uv sync creates isolated Python 3.11 venv -- camel-oasis requires Python <3.12, host runs 3.12
metrics:
  duration_minutes: 7
  completed_date: "2026-03-25"
  tasks_completed: 3
  files_created: 4
  files_modified: 1
---

# Phase 6 Plan 1: MiroFish Infrastructure Setup Summary

**One-liner:** Gold-specific Zep knowledge graph seed data, MiroFish settings fields with graceful-off defaults, and automated clone/install/launch script for MiroFish Flask backend on localhost:5001.

## Tasks Completed

| # | Task | Commit | Files |
|---|------|--------|-------|
| 1 | Create gold market seed templates for Zep knowledge graph | 70ff08d | mirofish_seeds/gold_market_overview.md, xauusd_macro_factors.md, gold_market_actors.md |
| 2 | Extend config/settings.py with MiroFish configuration | 46aed2e | config/settings.py |
| 3 | Create MiroFish setup and startup script | 91b3683 | scripts/start_mirofish.py |

## What Was Built

### Task 1: Gold Market Seed Templates

Three German-language Markdown seed documents created in `mirofish_seeds/`:

- **gold_market_overview.md** (~400 words): XAUUSD Goldmarkt overview covering Safe-Haven role, price development, key influencers (inflation, rates, USD, geopolitics), historical correlations (Gold-DXY inverse, Gold-Realzinsen inverse), and trading hours/liquidity.
- **xauusd_macro_factors.md** (~550 words): 9 section macro factors -- Federal Reserve policy, ECB policy and EUR/USD, US inflation data (CPI/PCE), USD strength (DXY), bond markets (10Y yields, real rates, yield curve), geopolitical risks, commodities (oil-gold correlation), EM demand (China/India), central bank gold buying, and market sentiment (ETF flows, COT, VIX).
- **gold_market_actors.md** (~500 words): Exactly 10 named economic entity types for MiroFish agent generation, each with 3-4 German sentences: Fed-Vertreter, EZB-Analyst, Inflationsexperte, Dollar-Stratege, Anleihenmarkt-Analyst, Geopolitik-Analyst, Rohstoff-Haendler, Hedgefonds-Manager, Zentralbank-Goldkaeufer, Schwellenlaender-Analyst.

All files are in natural German prose with Markdown `##` headers for Zep graph entity extraction.

### Task 2: Settings Configuration Fields

Eight MiroFish fields added to `config/settings.py` in a new `# -- MiroFish Swarm Intelligence (Phase 6)` section:

- `mirofish_enabled: bool = False` -- opt-in, default off (D-16)
- `mirofish_url: str = "http://localhost:5001"` -- Flask backend URL
- `mirofish_cache_ttl_seconds: int = 360` -- 6 minute cache validity (D-11)
- `mirofish_poll_interval_seconds: int = 300` -- 5 minute background sim frequency (D-10)
- `mirofish_max_sims_per_day: int = 48` -- MIRO-06 cost limiter
- `mirofish_token_budget_per_day: int = 200_000` -- MIRO-06 ~$0.04/day at gpt-4o-mini rates
- `mirofish_simulation_timeout_seconds: float = 180.0` -- 3 min max per simulation
- `mirofish_max_rounds: int = 15` -- OASIS simulation rounds cap

All fields have safe defaults. No validators needed. Existing test suite: 0 regressions (81 core tests passing).

### Task 3: MiroFish Setup and Startup Script

`scripts/start_mirofish.py` (374 lines) -- self-contained Python script automating the full MiroFish setup workflow:

**Subcommands (argparse):**
- `setup` -- Step 1: `git clone` MiroFish repo; Step 2: `uv sync` (creates isolated Python 3.11 venv); Step 3: create `mirofish/backend/.env` from host `.env` OPENAI_API_KEY + ZEP_API_KEY input
- `start` -- `subprocess.Popen` to launch `mirofish/backend/.venv/Scripts/python.exe run.py`, polls `GET http://localhost:5001/health` for up to 15s
- `status` -- health check only
- (no args) -- setup + start combined

**Key details:**
- Reads host `.env` via python-dotenv (with fallback parser) to reuse OPENAI_API_KEY as LLM_API_KEY
- Writes `mirofish/backend/.env` with `LLM_API_KEY`, `LLM_BASE_URL=https://api.openai.com/v1`, `LLM_MODEL_NAME=gpt-4o-mini`, `ZEP_API_KEY`, `FLASK_PORT=5001`
- Windows-specific venv path: `.venv/Scripts/python.exe`
- All output in German per D-05 convention
- No imports from trading bot codebase -- fully self-contained

## Deviations from Plan

None -- plan executed exactly as written.

The `test_e2e_trading.py` and `test_ensemble.py` test failures are pre-existing (missing `sqlalchemy`/`xgboost` in system Python -- these modules require the `.venv` environment). They are not regressions introduced by this plan.

## Verification Results

- `ls mirofish_seeds/*.md | wc -l` returns 3 ✓
- `python -c "from config.settings import Settings; s = Settings(); print(s.mirofish_enabled, s.mirofish_url)"` prints `False http://localhost:5001` ✓
- `python -c "import ast; ast.parse(open('scripts/start_mirofish.py').read())"` exits 0 ✓
- 81 core tests passing, 0 regressions ✓

## Known Stubs

None -- all files deliver their intended content. MiroFish infrastructure is ready for Phase 6 Plan 2 (Zep knowledge graph population and agent simulation).

## Self-Check: PASSED

- mirofish_seeds/gold_market_overview.md -- EXISTS
- mirofish_seeds/xauusd_macro_factors.md -- EXISTS
- mirofish_seeds/gold_market_actors.md -- EXISTS
- scripts/start_mirofish.py -- EXISTS
- config/settings.py -- EXISTS (modified)
- Commit 70ff08d -- EXISTS
- Commit 46aed2e -- EXISTS
- Commit 91b3683 -- EXISTS
