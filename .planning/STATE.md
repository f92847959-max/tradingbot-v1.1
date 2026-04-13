---
gsd_state_version: 1.0
milestone: v1.0
milestone_name: — Profitable Demo Trading
current_phase: 09
current_plan: Not started
status: Ready to plan
last_updated: "2026-04-13T19:02:51.480Z"
progress:
  total_phases: 13
  completed_phases: 7
  total_plans: 27
  completed_plans: 20
---

# Project State

**Project:** GoldBot 2
**Milestone:** v1.0 -- Profitable Demo Trading
**Current Phase:** 09
**Current Plan:** Not started
**Phase Status:** Phase 8 complete (2/2 plans complete)
**Total Phases:** unowen

## Next Action

Phase 08 complete (2/2 plans) -- proceed to Phase 09 (Advanced Risk & Position Sizing)

## Decisions

- Expanding (anchored) windows for walk-forward validation (train_start=0)
- Dynamic window count: 9 windows for 12000 samples
- min_train_samples=1500, min_test_samples=200
- Per-window fresh FeatureScaler (TRAIN-02)
- 85/15 internal train/val split within each window
- Version directory format: v{NNN}_{YYYYMMDD}_{HHMMSS}
- production.json pointer file (not symlinks) for Windows compatibility
- Retain 5 most recent versions, delete older ones
- Aggregate PF from total gross_profit / total gross_loss (not averaged ratios)
- Best model selected by aggregate profit factor
- Sharpe annualized with sqrt(2600) from per-trade pips
- Use shap.TreeExplainer explicitly (not generic shap.Explainer) to avoid KernelExplainer fallback
- Handle both list and 3D array SHAP output formats for version compatibility
- Fixed seed RandomState(42) for reproducible subsampling
- matplotlib Agg backend set at module level before pyplot import
- SHAP importance computed on test data (not training) to measure generalization
- Performance guard compares pruned vs full model profit factor before accepting
- Default accept pruning when full model has 0 trades (no basis for comparison)
- result["feature_selection"] replaced by result["feature_pruning"] and result["shap_importance"]
- Store full shap_importance dict in version.json (acceptable for 50-80 features)
- Chart filename stored as basename only in version.json (version dir is context)
- feature_selection key replaced with feature_pruning and shap_importance keys in pipeline.py
- [Phase 04]: ADX + ATR ratio sufficient for 3-state regime classification (BB width excluded)
- [Phase 04]: RANGING is the safest default for all fallback/error cases
- [Phase 04]: LabelGenerator defaults use_dynamic_atr=False; ModelTrainer defaults True
- [Phase 04]: Keep _vectorized_labeling and _vectorized_labeling_dynamic separate (scalar vs array)
- [Phase 05]: CLI defaults report output to {version_dir}/backtest_report.json for co-location with model
- [Phase 05]: E2E tests use use_dynamic_atr=False for deterministic label generation in tests
- [Phase 05]: Module-scoped pytest fixture trains model once (7000 candles) shared across all 4 UAT tests
- [Phase 06]: Use OpenAI API gpt-4o-mini not Ollama for MiroFish (Ollama too small per ROADMAP override)
- [Phase 06]: mirofish_enabled defaults to False for D-16 graceful degradation (bot trades without MiroFish)
- [Phase 06]: LLM_API_KEY reuses OPENAI_API_KEY from host .env to avoid duplicate key management
- [Phase 06]: uv sync creates isolated Python 3.11 venv for MiroFish (camel-oasis requires Python <3.12)
- [Phase 06]: Stub only database.connection/models/signal_repo leaf modules (not parent packages) for integration tests to avoid sys.modules pollution
- [Phase 08]: Stdlib calendar fixup in __init__.py to prevent aiohttp import conflict (calendar/ package shadows stdlib)
- [Phase 08]: Domain model (calendar/models.py) separate from ORM model (database/models.py) for clean architecture
- [Phase 08]: EventRules is pure logic (no DB, no async) for testability; EventService is the async facade
- [Phase 08]: Force-close check placed before high-impact window check in _trading_tick (more urgent)
- [Phase 08]: Veto at tick level (before signal generation) to avoid wasted AI compute during event windows
- [Phase 08]: Extended stdlib calendar fixup to re-export ALL public attributes (not just timegm) for pandas compatibility

## Session Log

- 2026-03-03: Project initialized from goldbot v2.0 codebase
- 2026-03-03: Research completed (STACK, FEATURES, ARCHITECTURE, PITFALLS)
- 2026-03-03: Requirements defined (31 v1 requirements)
- 2026-03-03: Roadmap created (8 phases)
- 2026-03-06: Phase 1 complete (4/4 plans done)
  - 01-01: .gitignore updated, German translated to English (17+ files)
  - 01-02: main.py refactored from 824 to 151 lines (mixin composition)
  - 01-03: trainer.py split into 3 modules (trainer, pipeline, trade_filter)
  - 01-04: Test suite verified (171 passed, 7 pre-existing failures, 0 regressions)
- 2026-03-06: Phase 2 planned (3 plans, checker PASS)
  - 02-01: Walk-forward validation engine + 6-month data validation
  - 02-02: Model versioning with version.json and production pointer
  - 02-03: Training report generation + end-to-end integration
- 2026-03-06: Plan 02-01 complete (4/4 tasks, 17 tests, 264s)
  - WalkForwardValidator with expanding windows in walk_forward.py
  - 6-month data validation in data_preparation.py
  - pipeline.py refactored for walk-forward loop
- 2026-03-06: Plan 02-02 complete (4/4 tasks, 7 tests, 172s)
  - model_versioning.py with create/write/pointer/cleanup functions
  - pipeline.py save step uses versioned directories
  - version.json extends model_metadata.json with walk-forward metrics
- 2026-03-06: Phase 7 context gathered (dashboard/history UI decisions captured)
  - Context file: .planning/phases/07-control-app-dashboard-history/07-CONTEXT.md
  - Focus: compact adaptive feed/error panes, one-line status strip, minimal dark glass style, micro-animations
- 2026-03-07: Plan 02-03 complete (4/4 tasks, 1 test added, 291s)
  - generate_training_report() with combined-trade aggregation in walk_forward.py
  - Report wired into pipeline.py (JSON save + console output)
  - train_models.py updated with walk-forward summary output + --min-data-months
  - End-to-end integration test verifying all Phase 2 UAT criteria
- 2026-03-07: Phase 2 complete (3/3 plans, 25 tests total, all passing)
- 2026-03-07: Plan 03-01 complete (3/3 tasks, 6 tests, 159s)
  - shap_importance.py module: compute_shap_importance + save_feature_importance_chart
  - shap==0.51.0 and matplotlib>=3.8 added to requirements.txt
  - 6 unit tests, 0 regressions in existing test suite
- 2026-03-07: Plan 03-02 complete (4/4 tasks, 6 tests, 210s)
  - SHAP pruning replaces XGBoost gain importance in walk_forward.py step 5
  - Performance guard: pruned vs full model profit factor comparison
  - Training report enriched with SHAP top features and pruning info per window
  - 6 integration tests, 0 regressions in existing 23 tests
- 2026-03-07: Plan 03-03 complete (3/3 tasks, 0 new tests, 245s)
  - SHAP persistence wired into pipeline.py (chart PNG + version.json data)
  - Feature pruning summary added to train_models.py console output
  - E2e test extended with all 4 Phase 3 UAT assertions (13/13 SHAP tests pass)
- 2026-03-07: Phase 3 complete (3/3 plans, 13 SHAP tests total, 208/208 passing, 0 regressions)
- 2026-03-08: Plan 04-01 complete (5/5 tasks, 33 tests added, 413s)
  - RegimeDetector class with MarketRegime enum (TRENDING/RANGING/VOLATILE)
  - detect() with hysteresis for live trading, detect_series() stateless for backtesting
  - REGIME_PARAMS lookup table with per-regime TP/SL/confidence parameters
  - 33 tests covering classification, hysteresis, edge cases, params
- 2026-03-08: Plan 04-02 complete (7/7 tasks, 18 tests added, 526s)
  - LabelGenerator: use_dynamic_atr flag with per-candle ATR-based TP/SL distances
  - Backtester: run_simple() with per-trade ATR-based TP/SL evaluation
  - ModelTrainer: ATR params forwarded to LabelGenerator (default dynamic=True)
  - walk_forward.py: ATR mode info stored in window result dict
  - train_models.py: --dynamic-atr, --no-dynamic-atr, --tp/sl-atr-mult CLI args
  - E2e test updated for dynamic ATR default; 260 passing, 0 regressions
- 2026-03-25: Plan 05-01 complete (18 unit tests, backtest engine + report module)
  - BacktestRunner: loads version dir, runs OOS walk-forward backtest with cost modeling
  - backtest_report.py: generate_backtest_report, check_consistency, print_backtest_report
  - 18 unit tests in test_backtest_runner.py, 0 regressions
- 2026-03-25: Plan 05-02 complete (2/2 tasks, 4 e2e tests, ~8 min)
  - scripts/run_backtest.py: CLI entry point for OOS backtest with argparse (8 args)
  - tests/test_backtest_e2e.py: E2e test validating all 4 Phase 5 UAT criteria
  - All 4 BACK-01..BACK-04 criteria verified: OOS windows, cost deduction, metrics, consistency
  - Decisions: CLI defaults output to version_dir; module-scoped fixture trains once for speed
- 2026-03-26: Plan 06-03 complete (2/2 tasks, 6 new integration tests, ~12 min)
  - MiroFishClient wired into lifecycle.py (init + asyncio background task in start(), cancel in stop())
  - Veto check wired into signal_generator.py after ML prediction (HOLD/disabled/no-cache all skip veto)
  - 6 integration tests in test_mirofish_integration.py (33 total MiroFish tests, 27+6)
  - Stopped at Task 3: human-verify checkpoint (awaiting user verification)
- 2026-04-10: Plan 08-01 complete (3/3 tasks, 9 files, ~5 min)
  - calendar/models.py: EconomicEvent dataclass + EventImpact enum
  - calendar/event_repository.py: EventRepository with upsert and query methods
  - calendar/event_fetcher.py: ForexFactory fetcher via faireconomy.media JSON API
  - calendar/event_filter.py: Gold-relevant filter (6 currencies + 30 keywords)
  - calendar/event_rules.py: Pure-logic EventRules (block window, force-close)
  - calendar/event_service.py: EventService facade for Phase 9/10
  - Fixed stdlib calendar shadow conflict with aiohttp (Rule 3 deviation)
- 2026-04-10: Plan 08-02 complete (2/2 tasks, 57 tests, ~6 min)
  - trading/trading_loop.py: force-close check + high-impact window veto in _trading_tick
  - trading/lifecycle.py: EventService init, initial refresh, _calendar_refresh_loop, gather integration
  - calendar/__init__.py: Extended stdlib fixup to re-export all public attributes
  - tests/test_calendar.py: 40 unit tests (models, rules, filter, service)
  - tests/test_calendar_integration.py: 9 integration tests (veto, force-close, cooldown)
  - tests/test_calendar_wiring.py: 8 structural tests (wiring correctness)
  - Phase 08 complete (2/2 plans): calendar module built and wired into trading
