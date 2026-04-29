---
status: resolved
trigger: "Diagnosis-only debug task for repo `C:\\Users\\fuhhe\\OneDrive\\Desktop\\ai\\ai\\ai trading gold`.\n\nYou are one of 3 parallel debug agents. Do not modify code. Do not apply fixes. Do not install dependencies. Read only what you need.\n\nOwnership and scope:\n- Primary code paths: `correlation/`, `data/`, `market_data/`, `calendar/`, `mirofish/`, `notifications/`, `database/`, sentiment-related modules, and training-related paths under `scripts/` or `ai_engine/` when directly tied to data/training flow\n- Primary tests: `tests/test_correlation_calculator.py`, `tests/test_correlation_features.py`, `tests/test_training_data_source.py`, `tests/test_asset_fetcher.py`, `tests/test_calendar.py`, `tests/test_calendar_integration.py`, `tests/test_calendar_wiring.py`, `tests/test_mirofish_client.py`, `tests/test_mirofish_integration.py`, `tests/test_model_versioning.py`, `tests/test_walk_forward.py`, `tests/test_walk_forward_e2e.py`, `tests/sentiment/test_feature_engineer_sentiment.py`, `tests/sentiment/test_news_fetcher.py`, `tests/sentiment/test_sentiment_aggregator.py`, `tests/sentiment/test_sentiment_analyzer.py`, `tests/sentiment/test_sentiment_features.py`, `tests/sentiment/test_sentiment_repository.py`\n- Focus on feature generation, data assumptions, training input integrity, correlation/sentiment wiring, and silent fallback behavior.\n\nTask:\n1. Inspect relevant tests and code paths.\n2. Identify likely logic bugs or behavior regressions.\n3. Distinguish confirmed evidence from speculation.\n4. Return a concise structured report with:\n   - Commands you would run or did run if available in your context\n   - Top 1-3 findings only\n   - For each finding: severity, status confirmed/likely/possible, suspected flaw, evidence, exact file:line references, why it is a logic bug, next verification\n   - Any blockers\n\nDo not patch files. Do not suggest broad refactors. Keep the answer evidence-driven."
created: 2026-04-23T00:00:00+02:00
updated: 2026-04-23T00:18:00+02:00
---

## Current Focus

hypothesis: Confirmed logic bugs exist in training-data and correlation fetch paths around silent fallback and cache invalidation.
test: Minimal Python reproductions against the current code snapshot.
expecting: Reproductions should show wrong-timeframe data being accepted, malformed rows being dropped silently, and cached data being reused for a different lookback request.
next_action: Return the top confirmed findings only, with evidence, line references, and blockers.

## Symptoms

expected: Correlation, sentiment, calendar, mirofish, and training-data paths should preserve input integrity, expose the intended features, and fail loudly when critical upstream data is missing or malformed.
actual: Unknown runtime symptom was provided; this session is a diagnosis-only audit for likely logic bugs and regressions in the current snapshot.
errors: None supplied by the user; rely on code and test evidence.
reproduction: Inspect the specified tests and their exercised code paths under the owned modules only.
started: Current repository snapshot under diagnosis on 2026-04-23.

## Eliminated

## Evidence

- timestamp: 2026-04-23T00:02:00+02:00
  checked: Prior workspace memory for the same repo
  found: Memory points to two previously high-leverage areas in this checkout: correlation feature cache bypass when a snapshot is supplied, and training duration validation after multiple row-loss stages.
  implication: Correlation snapshot wiring and training input integrity are strong hypothesis candidates for this diagnosis pass.

- timestamp: 2026-04-23T00:03:00+02:00
  checked: Required common bug pattern reference
  found: The most relevant categories for this audit are silent error swallowing, changed data shape/API contract, falsy-valid-value handling, and empty-collection/boundary behavior.
  implication: Tests should be examined for cases where code silently defaults or drops data instead of surfacing an integrity problem.

- timestamp: 2026-04-23T00:04:00+02:00
  checked: Targeted test inventory
  found: The owned, directly named high-signal tests in scope include correlation, training data source, asset fetcher, calendar wiring, mirofish, model versioning, and walk-forward; sentiment tests require a separate pass because they live under tests/sentiment.
  implication: Start with correlation and training-data flows, then inspect sentiment feature exposure for incomplete wiring or silent omissions.

- timestamp: 2026-04-23T00:08:00+02:00
  checked: ai_engine/training/data_source.py and tests/test_training_data_source.py
  found: `load_from_file()` only applies timeframe filtering when the filtered result is non-empty, and `_normalize_dataframe()` drops invalid/malformed rows without raising or recording how many were removed.
  implication: Training can proceed on the wrong timeframe or on silently truncated data, which is a direct input-integrity risk not covered by the current tests.

- timestamp: 2026-04-23T00:10:00+02:00
  checked: correlation/asset_fetcher.py and tests/test_asset_fetcher.py
  found: The TTL cache is keyed only by age and not by `lookback_days`, so a second request within TTL can receive a cached frame sized for a different lookback horizon.
  implication: Correlation snapshots can be computed on stale or undersized history while appearing healthy, especially when callers vary the lookback within one process.

- timestamp: 2026-04-23T00:11:00+02:00
  checked: tests/sentiment/* and owned code search
  found: The named sentiment tests are still explicit RED placeholders and no matching implementation files were located under the searched owned paths.
  implication: Sentiment remains more of a coverage/blocker signal than a diagnosable logic regression in this snapshot.

- timestamp: 2026-04-23T00:15:00+02:00
  checked: Runtime reproduction for ai_engine.training.data_source.load_from_file()
  found: A CSV containing only `timeframe=1m` rows still loads successfully when requested as `timeframe='5m'`, returning 2 rows and preserving `['1m']` in the output timeframe column.
  implication: The loader silently falls back to mismatched timeframe data instead of rejecting or returning an empty result.

- timestamp: 2026-04-23T00:16:00+02:00
  checked: Runtime reproduction for ai_engine.training.data_source.normalize_training_dataframe()
  found: A 2-row input with one malformed OHLC row returned only 1 row after normalization, with no exception or integrity warning.
  implication: Malformed training data is silently discarded, which can reduce effective history and mask upstream data quality issues.

- timestamp: 2026-04-23T00:17:00+02:00
  checked: Runtime reproduction for correlation.asset_fetcher.AssetFetcher.fetch_daily_closes()
  found: With a live cache entry set, `fetch_daily_closes(lookback_days=200)` returned the cached DataFrame, did not call `yf.download`, and therefore ignored the new lookback request.
  implication: Correlation history requests can receive stale, undersized data whenever callers vary lookback within the TTL window.

## Resolution

root_cause: Multiple confirmed logic flaws were identified in owned data paths: silent wrong-timeframe fallback in `load_from_file()`, silent row dropping in `_normalize_dataframe()`, and cache reuse across mismatched `lookback_days` requests in `AssetFetcher.fetch_daily_closes()`.
fix: |
  Re-verified 2026-04-25 — all three claims fixed:
  - Timeframe filter: data_source.py:149-154 raises DataSourceError on empty filter.
  - OHLC NaN: data_source.py:251-265 raises DataSourceError on NaN and invalid OHLC relationships.
  - Cache lookback: asset_fetcher.py:45-55,77 — _cache_lookback_days added to cache key; fetch bypasses cache when lookback differs.
verification: "All three claims confirmed fixed in live code on 2026-04-25 via direct file reads at the cited line ranges."
files_changed: []
