---
phase: 11
plan: 01
subsystem: news-sentiment
tags: [foundation, dependencies, schema, tests, wave-0]
one_liner: "Foundation laid: feedparser + vaderSentiment pinned, Settings gets 9 opt-in sentiment_* fields, NewsSentiment ORM + Alembic migration, and tests/sentiment/ scaffold with 24 red tests covering all 5 SENT requirements"
requires:
  - none (enabling foundation for Phase 11)
provides:
  - Settings.sentiment_* configuration block (9 fields, opt-in via sentiment_enabled)
  - NewsSentiment ORM model + news_sentiment SQLite/PostgreSQL table
  - Alembic migration 20260416_news_sent (down_revision=None; first in versions/)
  - tests/sentiment/ scaffold (10 files, 24 red tests, 2 fixture assets)
affects:
  - config/settings.py (added Phase 11 block + validator)
  - database/models.py (appended NewsSentiment after EconomicEventRecord)
  - requirements.txt, pyproject.toml (new pinned deps + optional finbert extras)
tech-stack:
  added:
    - feedparser==6.0.12
    - vaderSentiment==3.3.2
    - transformers>=5.0.0 (optional via [sentiment-finbert] extras)
    - torch>=2.0.0 (optional via [sentiment-finbert] extras)
  patterns:
    - Opt-in boolean flag + graceful 0.0 fallback (mirrors MiroFish Phase 6)
    - JSON_COMPAT column (JSONB on PostgreSQL, JSON on SQLite)
    - Literal[...] typed settings with pydantic field_validator guards
    - Wave 0 red tests with pytest.fail bodies (to be filled by Plan 11-02/03)
key-files:
  created:
    - database/migrations/versions/20260416_add_news_sentiment.py
    - tests/sentiment/__init__.py
    - tests/sentiment/conftest.py
    - tests/sentiment/fixtures/sample_feed.xml
    - tests/sentiment/fixtures/sample_articles.json
    - tests/sentiment/test_news_fetcher.py
    - tests/sentiment/test_sentiment_analyzer.py
    - tests/sentiment/test_sentiment_aggregator.py
    - tests/sentiment/test_sentiment_features.py
    - tests/sentiment/test_sentiment_repository.py
    - tests/sentiment/test_feature_engineer_sentiment.py
  modified:
    - requirements.txt
    - pyproject.toml
    - config/settings.py
    - database/models.py
decisions:
  - entry_id (feedparser-normalised) used as unique dedup key (not url, which is UTM-polluted) per CONTEXT D-08
  - Alembic down_revision = None -- this is the first migration ever in versions/ (only README existed)
  - sentiment_source_weights default-factory dict at settings layer (kitco=1.0, investing=0.9, marketwatch=0.8, goldbroker=0.7)
  - Validator enforces sentiment_poll_interval_seconds >= 60 (prevents feed-source abuse)
  - conftest.py drops pytest_asyncio dependency (not installed in venv); relies on pyproject `asyncio_mode=auto` plus plain @pytest.fixture yielding AsyncSession
metrics:
  duration_minutes: ~3
  tasks_completed: 3
  tests_added: 24 (all red via pytest.fail)
  files_created: 11
  files_modified: 4
  completed: 2026-04-17
---

# Phase 11 Plan 01: Dependencies, Schema & Test Scaffold Summary

## Objective Recap

Lay the foundation for the Phase 11 News-Sentiment pipeline: pin NLP dependencies, extend Settings with opt-in sentiment_* flags, add the NewsSentiment ORM model + Alembic migration, and create the Wave 0 test scaffolding that Plans 11-02 and 11-03 will fill in.

## What Was Built

### Dependencies pinned
- `requirements.txt`: added `feedparser==6.0.12` and `vaderSentiment==3.3.2`
- `pyproject.toml` `[project.dependencies]`: same two pins
- `pyproject.toml` `[project.optional-dependencies].sentiment-finbert`: `transformers>=5.0.0`, `torch>=2.0.0` (opt-in upgrade path; not installed by default)

### Settings fields added (9 new keys)
| Field | Type | Default |
|-------|------|---------|
| `sentiment_enabled` | `bool` | `False` |
| `sentiment_model` | `Literal["vader", "finbert"]` | `"vader"` |
| `sentiment_poll_interval_seconds` | `int` | `300` (validator: >= 60) |
| `sentiment_retention_days` | `int` | `30` |
| `sentiment_min_keywords` | `int` | `1` |
| `sentiment_seed_update_hours` | `int` | `1` |
| `sentiment_finbert_cache_path` | `str` | `""` |
| `sentiment_halflife_minutes` | `int` | `30` |
| `sentiment_source_weights` | `dict[str, float]` | `{kitco:1.0, investing:0.9, marketwatch:0.8, goldbroker:0.7}` |

### NewsSentiment schema
Table `news_sentiment` (12 columns):
| Column | Type | Notes |
|--------|------|-------|
| `id` | Integer PK | |
| `published_at` | DateTime(tz) NOT NULL | indexed |
| `fetched_at` | DateTime(tz) NOT NULL, server_default=now() | |
| `source` | String(50) NOT NULL | indexed |
| `headline` | Text NOT NULL | |
| `summary` | Text NULL | |
| `url` | Text NULL | |
| `entry_id` | Text NOT NULL | **unique indexed (dedup key)** |
| `sentiment_score` | Numeric(5,4) NOT NULL | -1..+1 compound |
| `source_weight` | Numeric(4,3) NOT NULL default 1.0 | |
| `keywords_matched` | JSON_COMPAT NULL | JSONB on PG, JSON on SQLite |
| `model_used` | String(20) NOT NULL default "vader" | |

Indices:
- `idx_news_sentiment_published` (non-unique, published_at)
- `idx_news_sentiment_source` (non-unique, source)
- `uq_news_sentiment_entry_id` (unique, entry_id)

### Alembic migration
- Path: `database/migrations/versions/20260416_add_news_sentiment.py`
- Revision ID: `20260416_news_sent`
- **down_revision = `None`** (versions/ previously held only README; this is the first migration)
- `upgrade()`: create_table + 3 create_index calls
- `downgrade()`: drop_index (x3) + drop_table (reverse order)

### Test scaffolding (10 files)
| File | Purpose |
|------|---------|
| `tests/sentiment/__init__.py` | Package marker (empty) |
| `tests/sentiment/conftest.py` | 4 fixtures: `sample_feed_bytes`, `sample_articles`, `reference_now`, `sentiment_session` (in-memory SQLite) |
| `tests/sentiment/fixtures/sample_feed.xml` | RSS 2.0 with 3 items: gold-bullish, non-gold, gold-bearish; UTM-tagged URL for normalisation test |
| `tests/sentiment/fixtures/sample_articles.json` | 6 pre-scored articles spanning 1h/4h/24h windows vs 2026-04-16T12:00Z |
| `tests/sentiment/test_news_fetcher.py` | SENT-01 (4 tests): gold filtering, keyword threshold, ETag, URL normalisation |
| `tests/sentiment/test_sentiment_analyzer.py` | SENT-02 (4 tests): VADER range, positive/negative headlines, HTML stripping |
| `tests/sentiment/test_sentiment_aggregator.py` | SENT-03 (6 tests): ewm_1h/4h/24h, momentum, divergence, empty fallback |
| `tests/sentiment/test_sentiment_features.py` | SENT-04 (3 tests): feature_columns, FEATURE_NAMES, disabled zero-fallback |
| `tests/sentiment/test_sentiment_repository.py` | SENT-05 (4 tests, async): save/load, dedup, query window, retention cleanup |
| `tests/sentiment/test_feature_engineer_sentiment.py` | SENT-04 integration (3 tests): includes sent_* names, disabled zero cols, cache bypass |

**Total collected: 24 tests.** All fail with `pytest.fail("Wave 0 red test ...")` -- Plan 11-02 and 11-03 replace the bodies.

## Decisions Made

- **entry_id over url** for dedup key (CONTEXT D-08): feedparser normalises entry.id; urls carry UTM tracking that fragments the same article
- **down_revision = None** verified by `ls database/migrations/versions/`: only README present, so this is the first Alembic revision
- **Literal type for sentiment_model**: gives pydantic validation that rejects any value other than "vader" or "finbert" at Settings load time
- **dropped pytest_asyncio import** from conftest: the module is not in the venv. Project's `pyproject.toml` sets `asyncio_mode = "auto"`, which already handles `async def` tests and fixtures at pytest collection; explicit `@pytest_asyncio.fixture` was unnecessary and would have blocked collection

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 3 - Blocking] Removed pytest_asyncio import in conftest.py**
- **Found during:** Task 3 verify step (`pytest tests/sentiment/ --collect-only`)
- **Issue:** `ModuleNotFoundError: No module named 'pytest_asyncio'` blocked all sentiment test collection. Plan specified `import pytest_asyncio` and `@pytest_asyncio.fixture` but that dep is not installed in the venv.
- **Fix:** Dropped the import; converted `@pytest_asyncio.fixture` to plain `@pytest.fixture` with `async def ... yield` body. Project's `pyproject.toml` sets `asyncio_mode = "auto"` which handles async fixtures without the explicit plugin. Lazy-imported SQLAlchemy async helpers inside the fixture body (keeps import-time surface minimal).
- **Files modified:** `tests/sentiment/conftest.py`
- **Commit:** `8264801`
- **Verification:** `python -m pytest tests/sentiment/ --collect-only -q` now reports 24 tests collected in 0.11s, 0 errors.

## Verification Results

1. `python -c "from config.settings import Settings; print(Settings().sentiment_enabled, Settings().sentiment_poll_interval_seconds)"` prints `False 300` ✓
2. `python -c "from database.models import NewsSentiment; print(NewsSentiment.__tablename__)"` prints `news_sentiment` ✓
3. `python -m pytest tests/sentiment/ --collect-only -q` reports 24 tests collected ✓
4. `grep "feedparser==6.0.12" requirements.txt` matches ✓
5. `python -m pytest tests/ --collect-only -q --ignore=tests/sentiment` reports 533 tests collected, no regressions ✓
6. All 12 columns + 3 indices on NewsSentiment asserted in Task 2 verify command ✓
7. 11/11 required test names present in collection output ✓

## Known Issues / Follow-ups for Plan 11-02

- **Feedparser/vaderSentiment not yet installed** in the venv. Plan 11-02 MUST run `pip install -r requirements.txt` (or `pip install feedparser==6.0.12 vaderSentiment==3.3.2`) before implementing `sentiment/news_fetcher.py` and `sentiment/sentiment_analyzer.py`, else those tests will fail with ImportError, not assertion errors.
- **Alembic migration not applied yet.** Running integration tests that hit a real database will need `alembic upgrade head` first. The in-memory SQLite fixture in conftest uses `Base.metadata.create_all`, which bypasses Alembic entirely -- fine for unit tests of the repository.
- **Investing.com feed reachability** (RESEARCH Open Question 1): untested in this plan. Plan 11-02's Wave 0 needs to confirm the URL responds to feedparser.parse() with 200, else fall back to GoldBroker.
- **FinBERT path** (`sentiment_finbert_cache_path` setting exists but no code reads it yet). Plan 11-02 sentiment_analyzer.py must set `os.environ["TRANSFORMERS_CACHE"]` from this setting before loading the pipeline (Windows path-safety, RESEARCH Pitfall 6).

## Commits

| Task | Message | Hash |
|------|---------|------|
| 1 | feat(11-01): pin NLP dependencies and extend Settings with sentiment block | `b225455` |
| 2 | feat(11-01): add NewsSentiment ORM model and Alembic migration | `c3c1eca` |
| 3 | test(11-01): add Wave 0 sentiment test scaffolding (red tests + fixtures) | `8264801` |

## Self-Check: PASSED

- FOUND: database/migrations/versions/20260416_add_news_sentiment.py
- FOUND: tests/sentiment/conftest.py
- FOUND: tests/sentiment/fixtures/sample_feed.xml
- FOUND: tests/sentiment/fixtures/sample_articles.json
- FOUND: tests/sentiment/test_news_fetcher.py
- FOUND: tests/sentiment/test_sentiment_analyzer.py
- FOUND: tests/sentiment/test_sentiment_aggregator.py
- FOUND: tests/sentiment/test_sentiment_features.py
- FOUND: tests/sentiment/test_sentiment_repository.py
- FOUND: tests/sentiment/test_feature_engineer_sentiment.py
- FOUND commit: b225455
- FOUND commit: c3c1eca
- FOUND commit: 8264801
