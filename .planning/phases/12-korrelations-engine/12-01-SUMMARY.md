---
phase: 12
plan: 01
subsystem: correlation
tags: [correlation, yfinance, ttl-cache, dataclass, foundation]
requirements: [CORR-01]
dependency-graph:
  requires: []
  provides:
    - "correlation.snapshot.CorrelationSnapshot (20-field frozen dataclass)"
    - "correlation.asset_fetcher.AssetFetcher (yfinance batch + monotonic TTL cache)"
    - "config.settings.correlation_enabled / correlation_cache_ttl_seconds / correlation_lookback_days"
  affects:
    - "requirements.txt (yfinance pin)"
tech-stack:
  added:
    - "yfinance==1.1.0"
  patterns:
    - "Opt-in toggle (correlation_enabled=False) mirrors Phase 6 mirofish_enabled and Phase 11 sentiment_enabled"
    - "Monotonic-clock TTL cache matches MiroFishClient cache style"
    - "Frozen dataclass with default-0.0 fields enables neutral graceful-fallback snapshot"
key-files:
  created:
    - "correlation/__init__.py"
    - "correlation/snapshot.py"
    - "correlation/asset_fetcher.py"
    - "tests/test_asset_fetcher.py"
  modified:
    - "requirements.txt"
    - "config/settings.py"
decisions:
  - "TTL default 3600s aligned between AssetFetcher constructor and correlation_cache_ttl_seconds setting"
  - "Index normalisation uses tz_convert('UTC').tz_localize(None) (only when tz-aware) — RESEARCH suggested either, this preserves UTC semantics"
  - "correlation/__init__.py exports both CorrelationSnapshot and AssetFetcher; compute_snapshot to be added in Plan 12-02"
metrics:
  tasks_completed: 3
  tests_added: 5
  test_total_before: 303
  test_total_after: 308
  duration_minutes: ~5
  completed: "2026-04-18"
---

# Phase 12 Plan 01: Foundation — yfinance pin + correlation package skeleton + AssetFetcher Summary

One-liner: Lays the Phase 12 foundation by pinning yfinance 1.1.0, adding opt-in `correlation_*` settings, defining the 20-field `CorrelationSnapshot` dataclass, and implementing `AssetFetcher` (batch yfinance download with monotonic TTL cache) — all RED→GREEN via 5 unit tests.

## Files

### Created
- `correlation/__init__.py` — Package marker; exports `CorrelationSnapshot`, `AssetFetcher`.
- `correlation/snapshot.py` — `CorrelationSnapshot` frozen dataclass with 20 fields (5 assets × 3 windows + 2 divergences + 1 regime + 2 lead/lag), all defaults `0.0`.
- `correlation/asset_fetcher.py` — `AssetFetcher.fetch_daily_closes(lookback_days=200)` — batches `yf.download` for all 6 tickers, renames to internal names, strips tz from index, drops all-NaN rows, monotonic TTL cache.
- `tests/test_asset_fetcher.py` — 5 tests covering fetch+rename+naive-index, TTL hit, TTL expiry, all-NaN dropping, period/interval propagation.

### Modified
- `requirements.txt` — added `yfinance==1.1.0`.
- `config/settings.py` — added `correlation_enabled` (False), `correlation_cache_ttl_seconds` (3600), `correlation_lookback_days` (200).

## Tests
- 5 new tests, all green: `pytest tests/test_asset_fetcher.py -x -q` → `5 passed`.
- Test count: 303 → 308 (no regressions touched).

## Decisions Made
1. **TTL default = 3600s** aligned between the constructor (`AssetFetcher.__init__`) and the new `correlation_cache_ttl_seconds` setting so wiring later in Plan 12-03 needs no adjustments.
2. **tz handling = `tz_convert("UTC").tz_localize(None)`** rather than bare `tz_localize(None)`. The plan's RESEARCH note flagged both as viable; `tz_convert` preserves true UTC semantics when yfinance returns America/New_York timestamps (the common case).
3. **`compute_snapshot` not exported yet** — `correlation/__init__.py` only exports the two symbols that exist after Plan 12-01. Plan 12-02 will add `compute_snapshot` and update `__all__`.

## TDD Cycle (CORR-01)
- **RED** (`cbac943`): 5 tests written referencing `correlation.asset_fetcher` — `ModuleNotFoundError` confirmed RED.
- **GREEN** (`6de8d02`): `AssetFetcher` implemented per RESEARCH Pattern 2; all 5 tests pass.
- **REFACTOR**: Not required — implementation already minimal.

## Deviations from Plan
None — plan executed exactly as written. (Minor: tz handling chose `tz_convert("UTC").tz_localize(None)` over the alternative `tz_localize(None)`; both were acknowledged as acceptable in the plan body, see Decision 2.)

## Handoff to Plan 12-02
- `AssetFetcher.fetch_daily_closes()` returns a `pd.DataFrame` indexed by naive UTC dates with columns `[dxy, us10y, silver, vix, sp500, gold]`.
- Plan 12-02 (`correlation/correlation_calculator.py`) builds `compute_snapshot(closes: pd.DataFrame) -> CorrelationSnapshot` against this exact contract.
- Settings already wired: `correlation_lookback_days` controls fetch window; `correlation_cache_ttl_seconds` controls cache; `correlation_enabled` is the opt-in toggle Plan 12-03 will gate on.

## Commits
- `6e9e8cb` feat(12-01): scaffold correlation package + pin yfinance + opt-in settings
- `cbac943` test(12-01): add failing AssetFetcher tests for CORR-01 (RED)
- `6de8d02` feat(12-01): implement AssetFetcher with yfinance batch + monotonic TTL cache (GREEN)

## Self-Check: PASSED
- `correlation/__init__.py` — FOUND
- `correlation/snapshot.py` — FOUND
- `correlation/asset_fetcher.py` — FOUND
- `tests/test_asset_fetcher.py` — FOUND
- Commits `6e9e8cb`, `cbac943`, `6de8d02` — FOUND in git log
- `pytest tests/test_asset_fetcher.py -x -q` — 5 passed
