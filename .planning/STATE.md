---
gsd_state_version: 1.0
milestone: v1.0
milestone_name: — Profitable Demo Trading
current_phase: 12.7
current_plan: 1
status: Phase 12.6 complete
last_updated: "2026-04-25T08:27:23.144Z"
progress:
  total_phases: 14
  completed_phases: 12
  total_plans: 44
  completed_plans: 37
  percent: 84
---

# Project State

**Project:** GoldBot 2
**Milestone:** v1.0 -- Profitable Demo Trading
**Current Phase:** 12.7
**Current Plan:** 1
**Phase Status:** Phases 12.4, 12.5 and 12.6 complete; Phase 12.7 ready for execution
**Total Phases:** 19

## Next Action

Execute Phase 12.7 (AI Training Pipeline Hardening)

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
- [Phase 09-02]: Use numpy.random.default_rng(seed) for reproducible MC simulations (not legacy np.random.seed)
- [Phase 09-02]: Store max_drawdown_pcts as fraction [0,1] for consistent arithmetic; multiply by 100 only in log output
- [Phase 09-02]: Vectorise paths dimension, iterate sequentially over trades axis — best NumPy tradeoff for in-place peak tracking
- [Phase 09-02]: optimal_f scans 20 candidates 0.005..0.10; each candidate uses seed+i for independent-but-deterministic runs
- [Phase 09]: Kelly MAX_KELLY cap set to 0.3 (not 0.25) to match plan spec: kelly_fraction(0.6, 2.0, 1.0) == 0.3
- [Phase 09]: AdvancedPositionSizer in new file risk/position_sizer.py (not position_sizing.py) to preserve RiskManager backward compatibility
- [Phase 09]: ATR=0 edge case: safe_atr=max(atr, 0.01) floor; factor clamped to max_scale (low ATR = allow larger position)
- [Phase 09]: approve_trade adds confidence/atr params with backward-compatible defaults; advanced sizing only activates when kelly_fraction > 0
- [Phase 09]: EquityCurveFilter defaults to allowed=True with insufficient data; portfolio heat check uses sl_distance * lot_size as estimated_risk
- [Phase 10]: Fibonacci 2.618 level = swing_high + range * 1.618 (formula: base + range * (ratio-1.0))
- [Phase 10]: calculate_dynamic_sl: BUY uses max(atr_sl, structure_sl), SELL uses min(atr_sl, structure_sl) for most protective SL
- [Phase 11]: entry_id (feedparser-normalised) used as dedup key for news_sentiment (not url with UTM noise)
- [Phase 11]: sentiment_enabled defaults to False for graceful fallback (mirrors MiroFish Phase 6 opt-in pattern)
- [Phase 11]: Alembic down_revision=None for 20260416_news_sent migration (first in versions/ directory)
- [Phase 11]: Test scaffold uses pyproject asyncio_mode=auto instead of pytest_asyncio (not in venv)
- [Phase 12]: TTL default 3600s aligned between AssetFetcher constructor and correlation_cache_ttl_seconds setting
- [Phase 12]: Index normalisation uses tz_convert('UTC').tz_localize(None) to preserve UTC semantics
- [Phase 12.1]: Planning split fixed into 3 waves: calibration artifacts -> runtime governance -> persistence and challenger monitoring
- [Phase 12.1]: Governance decisions are persisted even for HOLD and blocked outcomes; artifact versions are sanitized to basename-only values
- [Phase 12.1]: Challenger promotion and retraining decisions use calibrated evidence (Brier/log-loss, drawdown, PF, trade count) instead of raw confidence alone
- [Phase 12.3]: Planning split fixed into 3 waves: specialist feature block -> separate specialist training/comparison -> runtime overlay with governance-safe logging
- [Phase 12.3]: Specialist artifacts live under ai_engine/saved_models/specialists/market_structure_liquidity with a specialist-local production pointer and no core-root overwrite
- [Phase 12.3]: Core vs Core+Specialist comparison reuses shared walk-forward windows and per-window train-only scaling to keep uplift claims leakage-safe
- [Phase 12.3]: Runtime specialist overlay stays no-op when artifacts are absent and can confirm, weaken, or veto a core signal but never create a standalone trade
- [Phase 12.4]: Exit AI is a separate trade-management specialist trained from Smart Exit Engine context, not a replacement for deterministic exits
- [Phase 12.4]: Exit action space is constrained to HOLD, TIGHTEN_SL, PARTIAL_CLOSE, FULL_EXIT with causal snapshot generation and baseline comparison
- [Phase 12.5]: Runtime Exit AI may only reduce risk through existing modify/close/partial-close paths and must remain strict no-op when disabled or artifacts are absent
- [Phase 12.6]: Existing deterministic systems remain runtime teachers and hard guards while autonomy is distilled into the current AI stack
- [Phase 12.6]: Autonomy head stays within `BUY/HOLD/SELL` and may not bypass `DecisionGovernor`, `StrategyManager`, calendar blocks, or `RiskManager`

## Accumulated Context

### Roadmap Evolution

- Phase 12.1 inserted after Phase 12: AI Confidence Calibration & Decision Governance (URGENT)

- Phase 12.3 inserted after Phase 12.1: AI Indicator Specialist Training (additional AI model for a second indicator/feature block)

- Phase 12.4 inserted after Phase 12.3: Exit AI Training & Baseline Evaluation (Smart-Exit-Engine-based specialist for trade-management decisions)

- Phase 12.5 inserted after Phase 12.4: Exit AI Runtime Integration & Governance (governed overlay for tighten/partial/full-exit actions)

- Phase 12.7 inserted after Phase 12.6: AI Training Pipeline Hardening (URGENT)

- Phase 14 added: Elliott Wave Theorie Integration — automatische Wellenzaehlung (1-5 Impuls, A-B-C Korrektur), Fibonacci-Targets aus Wellen-Verhaeltnissen, Wellen-Position als ML-Feature, Integration in signal_generator.py und MiroFish-Seed-Templates

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
- 2026-04-13: Plan 09-02 complete (1/1 task, 19 tests, ~3 min)
  - risk/monte_carlo.py: MonteCarloSimulator + SimulationResult (pure numerical, no DB)
  - Vectorised NumPy simulation: 1000 paths x 200 trades in ~0.3s
  - Drawdown percentiles (p50/p75/p90/p95/p99), ruin probability, optimal_f
  - 19 tests covering structure, edge strength, reproducibility, performance, no-DB-imports
  - Stopped at: Completed 09-02-PLAN.md
- 2026-04-13: Plan 09-03 complete (2/2 tasks, 54 tests, ~7 min)
  - risk/portfolio_heat.py: PortfolioHeatManager (heat tracking, 5% max limit)
  - risk/equity_curve_filter.py: EquityCurveFilter (EMA-based, insufficient data defaults to allowed)
  - risk/risk_manager.py: extended with advanced sizing, heat check, equity filter check
  - trading/trading_loop.py: passes confidence+atr to approve_trade, tracks heat
  - risk/__init__.py: full package exports for all 9 risk classes
  - Phase 09 complete (3/3 plans): full advanced risk pipeline wired
- 2026-04-14: Plan 10-01 complete (2/2 tasks, 21 tests, ~7 min)
  - exit_engine/types.py: StructureLevel, ExitLevels, TrailingResult, PartialCloseAction, ExitSignal
  - exit_engine/dynamic_sl.py: calculate_dynamic_sl (ATR + regime + structure) and find_swing_levels
  - exit_engine/dynamic_tp.py: fibonacci_extensions, find_sr_levels, calculate_dynamic_tp (Fib+S/R+ATR)
  - exit_engine/exit_signals.py: check_exit_signals (engulfing, shooting star, hammer, RSI divergence)
  - tests/test_exit_engine_core.py: 21 unit tests, all pass (EXIT-01, EXIT-02, EXIT-05)
  - Stopped at: Completed 10-01-PLAN.md
- 2026-04-16: Phase 14 added to roadmap — Elliott Wave Theorie Integration (not yet planned)
- 2026-04-17: Plan 11-01 complete (3/3 tasks, 24 red tests, 15 files, ~3 min)
  - requirements.txt + pyproject.toml: pinned feedparser==6.0.12, vaderSentiment==3.3.2; added [sentiment-finbert] optional extras
  - config/settings.py: 9 new sentiment_* fields (opt-in, defaults per CONTEXT D-01..D-07) + sentiment_poll_interval_seconds >= 60 validator
  - database/models.py: NewsSentiment ORM model with 12 cols, 3 indices (entry_id unique dedup key per D-08)
  - database/migrations/versions/20260416_add_news_sentiment.py: first Alembic migration (down_revision=None)
  - tests/sentiment/: 10 files, 24 red tests (pytest.fail bodies) covering SENT-01..SENT-05
  - Rule 3 deviation: dropped pytest_asyncio import (not in venv); project pyproject asyncio_mode=auto handles async fixtures
  - Stopped at: Completed 11-01-PLAN.md (Plan 11-02 can proceed)
- 2026-04-23: Phase 12.1 planned (3 plans, ready once Phase 12 dependency is complete)
  - 12.1-01: calibration artifacts, threshold tuning, and walk-forward integration
  - 12.1-02: DecisionGovernor runtime integration in EnsemblePredictor
  - 12.1-03: governance audit logging, champion/challenger, and retraining triggers
- 2026-04-23: Phase 12.1 complete (3/3 plans, 43 targeted tests passing)
  - 12.1-01: calibration artifacts, threshold tuning, and walk-forward integration
  - 12.1-02: DecisionGovernor runtime integration in EnsemblePredictor
  - 12.1-03: governance audit logging, champion/challenger, and retraining triggers
- 2026-04-23: Phase 12.3 planned (3 plans, ready for execution after Phase 12.1)
  - 12.3-01: specialist feature block and leakage-safe feature-engineering integration
  - 12.3-02: specialist training pipeline, storage, and walk-forward uplift comparison
  - 12.3-03: runtime specialist overlay and governance-compatible logging
- 2026-04-24: Phase 12.3 complete (3/3 plans, 14 targeted tests passing)
  - 12.3-01: specialist feature block and leakage-safe feature-engineering integration
  - 12.3-02: specialist training pipeline, storage, isolated versioning, and walk-forward uplift comparison
  - 12.3-03: runtime specialist overlay with governance-safe logging and no-trade-alone guardrails
- 2026-04-24: Phase 12.4 planned (3 plans, Exit AI training and baseline evaluation)
  - 12.4-01: exit snapshot dataset, action labels, and leakage-safe sample builder
  - 12.4-02: exit AI training pipeline, specialist storage, and walk-forward baseline comparison
  - 12.4-03: exit AI calibration, promotion gate, and training/reporting entrypoints
- 2026-04-24: Phase 12.5 planned (3 plans, governed Exit AI runtime integration)
  - 12.5-01: runtime loader, advisor contract, and no-risk-widening guardrails
  - 12.5-02: order-manager integration for tighten-SL, partial-close, and full-exit actions
  - 12.5-03: audit logging, drift monitoring, and reconciliation checks
- 2026-04-25: Phase 12.6 planned (3 plans, existing AI autonomy distillation)
  - 12.6-01: teacher snapshot capture, hierarchical labels, and distillation dataset manifest
  - 12.6-02: learned decision head, calibration reuse, and walk-forward promotion gate
  - 12.6-03: shadow rollout, challenger logging, and guarded runtime selection
- 2026-04-25: Phases 12.4, 12.5 and 12.6 complete (9/9 plans, 37 targeted tests passing)
  - 12.4: Exit-AI dataset, isolated specialist training, baseline comparison, promotion gate, and CLI
  - 12.5: Exit-AI runtime advisor, OrderManager application path, audit and reconciliation context
  - 12.6: teacher snapshots, distillation dataset, decision-head artifacts, and guarded rollout metadata
