---
phase: 08-wirtschaftskalender-integration
plan: 02
subsystem: calendar
tags: [economic-calendar, trading-loop, event-veto, force-close, lifecycle, background-refresh]

# Dependency graph
requires:
  - phase: 08-wirtschaftskalender-integration
    plan: 01
    provides: calendar/ package with EventService, EventRules, EconomicEvent, event_filter
provides:
  - "EventService wired into trading_loop.py _trading_tick (veto + force-close)"
  - "Background calendar refresh loop in lifecycle.py (_calendar_refresh_loop)"
  - "Graceful degradation when calendar_enabled=False (self._event_service = None)"
  - "57 tests covering models, rules, filter, service, wiring, and integration"
affects: [09-advanced-risk-position-sizing, 10-smart-exit-engine]

# Tech tracking
tech-stack:
  added: []
  patterns: [guard-pattern-none-check, pre-tick-veto, background-async-loop]

key-files:
  created:
    - tests/test_calendar.py
    - tests/test_calendar_integration.py
    - tests/test_calendar_wiring.py
  modified:
    - trading/trading_loop.py
    - trading/lifecycle.py
    - calendar/__init__.py

key-decisions:
  - "Force-close check placed before high-impact window check in _trading_tick (force-close is more urgent)"
  - "Veto at tick level (before signal generation) to avoid wasted AI compute during event windows"
  - "Stdlib calendar __init__.py fixup extended to re-export ALL public attributes (not just timegm) for pandas/_strptime compatibility"

patterns-established:
  - "Pre-tick veto pattern: guard checks (kill switch, force-close, event window) return early before any data fetch or AI calls"
  - "Background async loop pattern: _calendar_refresh_loop sleeps interval then refreshes, guarded by _running flag"
  - "None-check guard pattern: all event_service calls guarded by 'if self._event_service is not None'"

requirements-completed: [ECAL-01, ECAL-02, ECAL-03]

# Metrics
duration: 6min
completed: 2026-04-10
---

# Phase 8 Plan 02: Calendar Trading Integration Summary

**EventService wired into trading loop with veto/force-close checks, background refresh, and 57 comprehensive tests**

## Performance

- **Duration:** 6 min
- **Started:** 2026-04-10T12:14:13Z
- **Completed:** 2026-04-10T12:20:00Z
- **Tasks:** 2
- **Files modified:** 6

## Accomplishments
- Trading loop now vetoes new trades during high-impact event windows (NFP, FOMC, CPI)
- Force-close triggers automatically before extreme USD events (positions closed, tick skipped)
- Background refresh loop refreshes calendar every 6 hours (configurable via calendar_fetch_interval_minutes)
- Graceful degradation: when calendar_enabled=False, no event checks run, trading proceeds normally
- 57 tests (40 unit + 9 integration + 8 wiring) covering all calendar behavior and edge cases

## Task Commits

Each task was committed atomically:

1. **Task 1: Wire EventService into trading_loop.py and lifecycle.py** - `c98943f` (feat)
2. **Task 2: Unit and integration tests for calendar module and veto behavior** - `416619b` (test)

## Files Created/Modified
- `trading/trading_loop.py` - Added force-close check and high-impact window veto in _trading_tick
- `trading/lifecycle.py` - Added EventService init, initial refresh in start(), _calendar_refresh_loop, gather integration
- `calendar/__init__.py` - Extended stdlib fixup to re-export all public attributes (day_abbr, day_name, etc.)
- `tests/test_calendar.py` - 40 unit tests: models (7), rules (16), filter (9), service (8)
- `tests/test_calendar_integration.py` - 9 integration tests: veto, force-close, cooldown, degradation
- `tests/test_calendar_wiring.py` - 8 structural tests: verifying wiring correctness in source code

## Decisions Made
- **Force-close before veto check**: should_force_close() runs before is_high_impact_window() in _trading_tick because closing positions is more urgent than blocking new trades
- **Veto at tick level**: The calendar veto returns before signal generation to avoid wasted API calls to the AI engine during event windows
- **Extended stdlib fixup**: The original __init__.py only re-exported timegm; pandas and _strptime need day_abbr, day_name, etc. Extended to re-export all public stdlib calendar attributes

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 3 - Blocking] Extended stdlib calendar fixup for pandas/_strptime compatibility**
- **Found during:** Task 1 (running initial tests)
- **Issue:** The calendar/__init__.py from Plan 01 only re-exported `timegm` for aiohttp. But pandas imports `_strptime` which accesses `calendar.day_abbr` and `calendar.day_name`, causing `AttributeError: module 'calendar' has no attribute 'day_abbr'`
- **Fix:** Changed from single `timegm = _stdlib_cal.timegm` to loop re-exporting ALL public stdlib attributes via `for _attr in dir(_stdlib_cal): globals()[_attr] = getattr(_stdlib_cal, _attr)`
- **Files modified:** calendar/__init__.py
- **Verification:** `import calendar; assert hasattr(calendar, 'day_abbr'); import pandas; print('OK')` passes
- **Committed in:** c98943f (Task 1 commit)

---

**Total deviations:** 1 auto-fixed (1 blocking)
**Impact on plan:** Essential fix for test runner to work at all (pandas is imported by conftest.py fixtures). No scope creep.

## Issues Encountered
- Stdlib calendar shadowing continues to be the main complexity in this package. The fixup is now comprehensive (all public attributes) rather than targeted (only timegm).

## User Setup Required
None - no external service configuration required.

## Next Phase Readiness
- Phase 8 complete: calendar module built (Plan 01) and wired into trading (Plan 02)
- EventService.is_high_impact_window() ready for Phase 9 (advanced risk) to use as additional risk factor
- EventService.should_force_close() ready for Phase 10 (smart exits) to integrate with exit strategies
- 57 tests validate all calendar behavior

## Self-Check: PASSED

All 6 files verified present. Both task commits (c98943f, 416619b) verified in git log.

---
*Phase: 08-wirtschaftskalender-integration*
*Completed: 2026-04-10*
