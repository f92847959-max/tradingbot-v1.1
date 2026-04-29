# Autonomous Debug Report

## Scope
- Request: autonomous diagnosis-only debug run with 3 parallel agents.
- Repo: `C:\Users\fuhhe\OneDrive\Desktop\ai\ai\ai trading gold`
- Focus: AI decision logic, risk and order lifecycle, training and data integrity.
- Source changes applied: none.

## Commands Run
- `& '.\.venv\Scripts\python.exe' -m pytest tests/test_ensemble.py tests/test_risk_manager.py tests/test_correlation_features.py tests/test_walk_forward.py -p no:cacheprovider -q`
  - Result: failed
  - Signal: 4 failed, 33 passed
  - Notes: exposed ensemble contract drift and an async test-environment blocker
- `& '.\.venv\Scripts\python.exe' -m pytest tests/test_trade_filter_tuning.py tests/test_exit_engine_core.py tests/sentiment/test_sentiment_features.py -p no:cacheprovider -q`
  - Result: failed
  - Signal: 3 failed, 25 passed
  - Notes: all 3 sentiment failures are explicit placeholder RED tests, not newly reproduced logic regressions
- `& '.\.venv\Scripts\python.exe' -c "import pytest_asyncio; print(pytest_asyncio.__version__)"`
  - Result: failed
  - Signal: `ModuleNotFoundError: No module named 'pytest_asyncio'`
  - Notes: explains the async pytest failures and the `Unknown config option: asyncio_mode` warning
- Parallel read-only diagnosis agents:
  - AI logic lane
  - risk and order lane
  - data, training, correlation lane

## Findings

### 1. Advanced sizing is applied after the risk envelope is validated
- Severity: high
- Status: confirmed
- Suspected logic flaw: `RiskManager` validates one lot size, then later replaces it with an advanced Kelly-derived lot size before execution.
- Evidence: `risk/risk_manager.py:386`, `risk/risk_manager.py:400`, `risk/risk_manager.py:438`, `risk/risk_manager.py:478`, `trading/trading_loop.py:248`, `risk/position_sizer.py:154`, `risk/position_sizing.py:47`, `tests/test_risk_integration_advanced.py:174`
- Why this is a logic bug: a trade can pass margin, leverage, and heat checks under a smaller validated size and still execute under a larger returned size.
- Recommended next verification: add a focused test where Kelly sizing is active and assert the returned lot still satisfies the exact constraints that were validated.

### 2. Kill-switch bulk close can drop tracking even when database close persistence fails
- Severity: high
- Status: confirmed
- Suspected logic flaw: the bulk close path logs DB close failures but still removes in-memory trade tracking.
- Evidence: `order_management/order_manager.py:406`, `order_management/order_manager.py:454`, `order_management/order_manager.py:468`, `order_management/order_manager.py:493`, `order_management/order_manager.py:496`
- Why this is a logic bug: a broker-closed position can disappear from memory while the DB still shows it as open or closing, which corrupts restart recovery and PnL continuity.
- Recommended next verification: force `repo.close_trade` to fail during `close_all()` and assert the trade is retained for reconciliation or durably queued before tracking is dropped.

### 3. Training data loading silently accepts the wrong timeframe
- Severity: high
- Status: confirmed
- Suspected logic flaw: timeframe filtering only applies when the filtered frame is non-empty, so a non-matching file can still load successfully.
- Evidence: `ai_engine/training/data_source.py:147`, `tests/test_training_data_source.py:15`
- Why this is a logic bug: training can run on a different timeframe than requested while reporting success.
- Recommended next verification: add a targeted test with only non-matching timeframe rows and assert the loader fails or returns no usable rows.

### 4. Malformed OHLC rows are silently dropped instead of raising a data integrity error
- Severity: high
- Status: confirmed
- Suspected logic flaw: normalization drops NaN and invalid OHLC rows without surfacing a hard integrity signal.
- Evidence: `ai_engine/training/data_source.py:246`, `ai_engine/training/data_source.py:249`
- Why this is a logic bug: corrupted upstream market data can shrink training history invisibly and bias later model or validation steps.
- Recommended next verification: add a test with one malformed candle and assert the loader emits a hard failure or explicit integrity warning rather than truncating silently.

### 5. Multi-timeframe conflict governance drifted from a hard HOLD gate to soft penalties
- Severity: high
- Status: likely
- Suspected logic flaw: the ensemble path no longer enforces the conflict gate the tests expect and now only applies confidence penalties.
- Evidence: `tests/test_ensemble.py:173`, `ai_engine/prediction/ensemble.py:628`, `ai_engine/prediction/ensemble.py:730`
- Why this is a logic bug: conflicting timeframe or model signals can still produce `BUY` or `SELL`, which weakens decision governance in exactly the disagreement cases that should be safest.
- Recommended next verification: run a disagreement case through `predict()` and assert the final action becomes `HOLD` when conflict exceeds the configured threshold.

### 6. Configured trading hours are ignored by the pre-trade guard
- Severity: medium
- Status: confirmed
- Suspected logic flaw: configured `trading_start` and `trading_end` values are passed into the checker but the actual trading-hours check uses a hard-coded helper instead.
- Evidence: `risk/risk_manager.py:174`, `risk/risk_manager.py:184`, `risk/pre_trade_check.py:49`, `risk/pre_trade_check.py:128`, `shared/utils.py:41`
- Why this is a logic bug: changing the configured session window has no effect, so the bot may trade outside the intended allowed hours.
- Recommended next verification: add a unit test with custom hours like `09:00-10:00` and assert `08:30` is rejected while `09:30` passes.

### 7. Correlation asset caching ignores `lookback_days`
- Severity: medium
- Status: confirmed
- Suspected logic flaw: cache reuse depends only on TTL and cached data presence, not on the requested historical window.
- Evidence: `correlation/asset_fetcher.py:48`, `tests/test_asset_fetcher.py:49`
- Why this is a logic bug: a later request for a longer lookback can silently reuse a shorter cached dataset, producing stale or undersized correlation features.
- Recommended next verification: issue two sequential fetches with different lookbacks inside the cache TTL and assert the second request bypasses cache.

### 8. Ensemble default weights drifted from the tested 55/45 split to 50/50
- Severity: medium
- Status: confirmed
- Suspected logic flaw: the tested default weighting contract no longer matches the constructor defaults.
- Evidence: `tests/test_ensemble.py:21`, `ai_engine/prediction/ensemble.py:112`
- Why this is a logic bug: it changes baseline predictor behavior and calibration without the surrounding tests or governance logic being updated accordingly.
- Recommended next verification: rerun the ensemble tests and review whether downstream confidence-calibration logic assumes the previous 55/45 balance.

## Additional Likely Issues
- `min_agreement` appears to behave like a soft penalty rather than a hard disagreement gate in the ensemble path.
- `strategy/regime_detector.py` likely classifies warmup rows too early because missing ATR averages are replaced before regime labeling.

## Blockers and Gaps
- Async pytest coverage is currently blocked by missing `pytest-asyncio` in the repo virtualenv.
- `tests/sentiment/test_sentiment_features.py` contains explicit RED placeholder failures and should not be treated as a newly discovered runtime regression.
- `tests/test_gpt_predictor.py` could not be assessed in this checkout because `ai_engine.prediction.gpt_predictor` is not present.

## Fixes Not Applied
- This run was diagnosis-only. No source files were modified.

---

## Resolution (2026-04-25)

**Status: RESOLVED**

### Logic findings (1–8): all already fixed in current code
Re-verification on 2026-04-25 confirmed every finding above was already addressed:

1. Advanced sizing — `risk/risk_manager.py:382-424` now calculates final lot **before** validation. Comment confirms intent: "Calculate the FINAL lot size first — every downstream guard must validate the actual trade we will place".
2. Kill-switch close_all DB failure — `order_management/order_manager.py:521-540` queues to `orphan_close_queue` and `continue`s when `db_updated=False`, retaining tracking for reconciliation.
3. Timeframe filter empty result — `ai_engine/training/data_source.py:149-154` raises `DataSourceError` instead of silently passing through.
4. Malformed OHLC rows — `ai_engine/training/data_source.py:251-265` raises `DataSourceError` on NaN OHLC and invalid relations.
5. Multi-timeframe HOLD gate — `ai_engine/prediction/ensemble.py:651-670` enforces hard HOLD when `agreement_count < self.min_agreement`.
6. Trading-hours config — `risk/pre_trade_check.py:126-150` uses `self.trading_start`/`self.trading_end`; weekend gate added at line 136.
7. Correlation cache — `correlation/asset_fetcher.py:45-77` includes `_cache_lookback_days` in cache key.
8. Ensemble defaults — `ai_engine/prediction/ensemble.py:119-122` restored to `{"xgboost": 0.55, "lightgbm": 0.45}`.

### Test infrastructure repairs (2026-04-25)
While verifying, additional pre-existing test-only failures (contract drift, not logic bugs) were fixed:

- **Time-flaky risk tests** (8 tests in `tests/test_risk_manager.py` and `tests/test_risk_integration_advanced.py`): Wall-clock-dependent — failed on weekends. Fixed by `tests/conftest.py` autouse fixture that freezes `risk.risk_manager.datetime.now()` to Friday 2026-04-24 10:00 UTC for these specific files only.
- **`tests/test_risk.py::test_all_pass_nominal`**: `_run_all` helper missing `notional_value`/`equity` for the new leverage check. Defaults added.
- **`tests/test_risk_integration.py::test_all_checks_pass`**: Hardcoded count `== 11` was stale; PreTradeChecker.run_all now returns 12 results. Updated assertion.
- **`tests/test_regime_integration.py` (2 tests)**: `_make_df` had `rows=30`, but `StrategyManager.evaluate()` requires ≥50 candles before invoking regime detection (warmup guard). Default raised to 60. Also added `ema_9`/`ema_21` columns expected by `strategy/multi_timeframe.py`.
- **`tests/test_lifecycle.py::TestGracefulShutdown` (4 tests)**: Patched `main.close_db`, but `close_db()` is imported from `database.connection` and used in `trading/lifecycle.py`. Patches retargeted to `trading.lifecycle.close_db`.

### Final test status
```
$ pytest tests/ --ignore=tests/sentiment -p no:cacheprovider -q
631 passed, 1 skipped, 77 warnings in 56.31s
```

(Sentiment tests excluded — explicit RED placeholders, unchanged from initial scope.)

### Round 2 — main.py signal-handler hardening (2026-04-25)
User flagged `main.py:105`: the `(signum, frame)` parameters were unused, and the
overall handler had no idempotency. Fixed:
- Renamed parameters to `(_signum, _frame)` (silences linter noise on signal-handler signatures).
- Added `shutdown_requested` guard so a second Ctrl+C doesn't spawn a second `system.stop()` task racing the first.
- Added `loop.is_closed()` guard in both Unix and Windows code paths so signals arriving during shutdown teardown don't raise `RuntimeError`.
- Consolidated Unix and Windows paths through a single `_request_stop()` so both branches share the same idempotency.
Verified: `pytest tests/test_lifecycle.py` still 11/11 GREEN.

### Round 3 — autonom-debug repo-hygiene fixes applied (2026-04-25)
After re-running `/gsd-autonom-debug --depth=deep`, the safe items were applied autonomously:
- `.gitignore`: appended `.claude/`, `.claude-flow/`, `.obsidian/`, `.mcp.json`, `pytest_*.txt` so local-tooling artifacts stop showing up as untracked.
- Removed stale files at repo root (untracked-only): `pytest_errors.txt`, `pytest_failures.txt`, `pytest_last_failure.txt`, `.js`.
- Renamed `.planning/phases/14-elliott-wave-theorie-integration-...` (228 chars) → `.planning/phases/14-elliott-wave` (16 chars). Inner file `beispiel .md` → `beispiel.md` (removed embedded space).
- Set `git config core.longpaths true` in this repo so Windows MAX_PATH issues don't block git scans.

See `20260425-103916-TRIAGE.md` for the full triage report and Top-3 Actions.

### NOT applied (require user judgment)
- 199 uncommitted files / 142 unpushed commits — user should review before committing/pushing to ensure no secrets slip in.
- Pin `requirements.txt` (23/27 entries unpinned, no lockfile) — adopting `pip-compile`/`uv`/`poetry` is a substantive workflow choice.
- Add `.github/workflows/tests.yml` — creating CI infrastructure is a substantive new file.

### Fresh-diagnosis attempt (Option C)
Three parallel agents (`gsd-debugger`) for AI-logic / risk-order / data-training were spawned but all three failed with `"You've hit your org's monthly usage limit"`. Fresh diagnosis blocked at the Anthropic plan level — retry after quota reset.
