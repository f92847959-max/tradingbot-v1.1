---
phase: 08-wirtschaftskalender-integration
plan: 01
subsystem: calendar
tags: [forexfactory, aiohttp, economic-calendar, event-filter, xauusd, trading-rules]

# Dependency graph
requires:
  - phase: 01-code-cleanup
    provides: project structure and module conventions
  - phase: 05-backtesting-validation
    provides: database/models.py and BaseRepository pattern
provides:
  - "calendar/ Python package with 7 modules (init, models, repository, fetcher, filter, rules, service)"
  - "EconomicEvent dataclass and EventImpact enum for domain modeling"
  - "EventService facade with is_high_impact_window(), should_force_close(), get_upcoming_events()"
  - "EventRules pure-logic engine for pre-event block, cooldown, and force-close"
  - "ForexFactory fetcher via faireconomy.media free JSON API"
  - "Gold-relevant event filter (USD/EUR/GBP/JPY/CHF/CNY + keyword matching)"
  - "EconomicEventRecord ORM model with unique constraint indexes"
  - "Calendar settings in config/settings.py"
affects: [09-advanced-risk-position-sizing, 10-smart-exit-engine]

# Tech tracking
tech-stack:
  added: [aiohttp (existing, now used for calendar fetching)]
  patterns: [stdlib-shadow-fixup, deferred-import, facade-service-pattern, domain-model-separate-from-orm]

key-files:
  created:
    - calendar/__init__.py
    - calendar/models.py
    - calendar/event_repository.py
    - calendar/event_fetcher.py
    - calendar/event_filter.py
    - calendar/event_rules.py
    - calendar/event_service.py
  modified:
    - database/models.py
    - config/settings.py

key-decisions:
  - "Stdlib calendar fixup in __init__.py to prevent aiohttp import conflict (our calendar/ package shadows stdlib)"
  - "Deferred aiohttp import inside fetch function to avoid module-level shadowing issues"
  - "Domain model (calendar/models.py) kept separate from ORM model (database/models.py) for clean architecture"
  - "EventRules is pure logic (no DB, no async) for testability; EventService is the async facade"

patterns-established:
  - "Stdlib shadow fixup: when package name conflicts with stdlib, pre-load stdlib and re-export needed symbols"
  - "Facade service pattern: EventService wraps fetcher, filter, repo, and rules into single interface"
  - "Domain vs ORM separation: EconomicEvent dataclass for business logic, EconomicEventRecord for persistence"

requirements-completed: [ECAL-01, ECAL-02, ECAL-03]

# Metrics
duration: 5min
completed: 2026-04-10
---

# Phase 8 Plan 01: Economic Calendar Module Summary

**Complete calendar/ package with ForexFactory fetcher, Gold-relevant filter, EventRules engine, and EventService facade for trading protection**

## Performance

- **Duration:** 5 min
- **Started:** 2026-04-10T07:36:44Z
- **Completed:** 2026-04-10T07:42:10Z
- **Tasks:** 3
- **Files modified:** 9

## Accomplishments
- Complete calendar/ package (7 modules) providing economic event awareness for Gold trading
- EventService facade exposes 3-method contract for Phase 9 (risk) and Phase 10 (exits): is_high_impact_window(), should_force_close(), get_upcoming_events()
- ForexFactory fetcher using free faireconomy.media JSON API with aiohttp (no API key needed)
- Gold-relevant filter retaining only events from key currencies (USD, EUR, GBP, JPY, CHF, CNY) and matching Gold keywords (NFP, FOMC, CPI, etc.)
- Stdlib calendar fixup preventing import conflict between our calendar/ package and Python stdlib calendar module

## Task Commits

Each task was committed atomically:

1. **Task 1: DB model, repository, settings, and calendar domain types** - `1438948` (feat)
2. **Task 2: ForexFactory event fetcher and Gold-relevant filter** - `3ed9854` (feat)
3. **Task 3: Event trading rules engine and EventService facade** - `a13a9e1` (feat)

## Files Created/Modified
- `calendar/__init__.py` - Package init with stdlib fixup and public exports (EventService, EconomicEvent, EventImpact)
- `calendar/models.py` - EconomicEvent dataclass and EventImpact enum (domain types, NOT ORM)
- `calendar/event_repository.py` - EventRepository extending BaseRepository with upsert, upcoming, date-range, high-impact queries
- `calendar/event_fetcher.py` - Async ForexFactory fetcher using faireconomy.media JSON API
- `calendar/event_filter.py` - Gold-relevant event filter (6 currencies + 30 keywords)
- `calendar/event_rules.py` - Pure-logic EventRules class (block window, force-close, blocking event)
- `calendar/event_service.py` - EventService facade wrapping all calendar functionality
- `database/models.py` - EconomicEventRecord ORM model added (with idx_econ_events_time and uq_econ_events indexes)
- `config/settings.py` - Calendar settings: calendar_enabled, calendar_fetch_interval_minutes, calendar_block_minutes_before, calendar_cooldown_minutes_after, calendar_force_close_on_extreme

## Decisions Made
- **Stdlib calendar fixup**: Our calendar/ package shadows Python's stdlib calendar module. aiohttp internally uses `calendar.timegm`. Fixed by pre-loading stdlib calendar and re-exporting `timegm` in `__init__.py`.
- **Deferred aiohttp import**: aiohttp is imported inside the async fetch function rather than at module level to avoid circular import issues from the stdlib shadow.
- **Domain/ORM separation**: EconomicEvent (dataclass in calendar/models.py) for business logic, EconomicEventRecord (SQLAlchemy in database/models.py) for persistence. Clean separation maintains existing project patterns.
- **EventRules is pure logic**: No DB, no async -- takes events list and datetime, returns decisions. Maximizes testability.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 3 - Blocking] Stdlib calendar module shadowing causing aiohttp import failure**
- **Found during:** Task 2 (ForexFactory fetcher)
- **Issue:** Naming our package `calendar/` shadows Python's stdlib `calendar` module. aiohttp 3.13.3 imports `calendar.timegm` at module level in `cookiejar.py`, which fails with `AttributeError: module 'calendar' has no attribute 'timegm'` because it finds our package instead of stdlib.
- **Fix:** Added stdlib fixup in `calendar/__init__.py` that temporarily removes project root from sys.path, imports stdlib calendar, restores path, and re-exports `timegm`. Also deferred aiohttp import inside the async function.
- **Files modified:** calendar/__init__.py, calendar/event_fetcher.py
- **Verification:** `import calendar; assert hasattr(calendar, 'timegm'); import aiohttp; print('OK')` passes
- **Committed in:** 3ed9854 (Task 2 commit)

---

**Total deviations:** 1 auto-fixed (1 blocking)
**Impact on plan:** Essential fix for the module to function. No scope creep. The package name `calendar` is specified in the plan; the fixup is the minimal solution to make it work with existing dependencies.

## Issues Encountered
- Stdlib calendar shadowing was the only issue. The fix is robust and handles the CWD being on sys.path (which is Python's default behavior).

## User Setup Required
None - no external service configuration required. The ForexFactory mirror API is free and requires no API key.

## Next Phase Readiness
- EventService facade is ready for Phase 9 (risk) to call `is_high_impact_window()` for trade blocking
- EventService facade is ready for Phase 10 (exits) to call `should_force_close()` for position management
- Plan 08-02 can wire the calendar service into the trading loop and add the refresh scheduler
- All imports verified: `from calendar.event_service import EventService` works

## Self-Check: PASSED

All 7 calendar/ files verified present. All 3 task commits (1438948, 3ed9854, a13a9e1) verified in git log.

---
*Phase: 08-wirtschaftskalender-integration*
*Completed: 2026-04-10*
