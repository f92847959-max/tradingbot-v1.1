---
gsd_state_version: 1.0
milestone: v1.0
milestone_name: — Profitable Demo Trading
current_phase: 14
current_plan: 1
status: Phase 12.7 complete; autonomous continuing with Phase 14
last_updated: "2026-04-29T00:00:00.000Z"
progress:
  total_phases: 20
  completed_phases: 16
  total_plans: 54
  completed_plans: 47
  percent: 87
---

# Project State

**Project:** GoldBot 2
**Milestone:** v1.0 -- Profitable Demo Trading
**Current Phase:** 14
**Current Plan:** 1
**Phase Status:** Phase 12.7 (AI Training Pipeline Hardening) completed. Phase 6 is explicitly excluded by user request. Continuing with Phase 14.
**Total Phases:** 20

## Next Action

Execute Phase 14 (Elliott Wave Theorie Integration), skipping Phase 6.

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
- [Phase 11]: Feedparser/VADER dependencies are used when installed, but deterministic local fallbacks keep tests runnable in lean environments
- [Phase 11]: FeatureEngineer sentiment mode disables candle-cache reuse so fresh news state is queried per feature call
- [Phase 11]: SentimentService uses APScheduler jobs and remains fail-soft when sentiment startup fails
- [Phase 12]: TTL default 3600s aligned between AssetFetcher constructor and correlation_cache_ttl_seconds setting
- [Phase 12]: Index normalisation uses tz_convert('UTC').tz_localize(None) to preserve UTC semantics
- [Phase 12]: Correlation calculation is a pure DataFrame-to-CorrelationSnapshot transform with bounded neutral fallback values for missing or insufficient inputs
- [Phase 12]: Correlation features are always present in FeatureEngineer output; missing snapshots broadcast 0.0 and non-null snapshots bypass feature-cache reuse
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
- [Phase 12.7]: Training data preflight now separates trainable span, row-loss telemetry, dataset manifests, and explicit allow-short-data override
- [Phase 12.7]: Training output now carries causal label, split, row-loss, and promotion manifests while preserving the existing entry-label model target
- [Phase 12.7]: Champion-report mode gates production pointer updates; legacy no-champion training remains backward-compatible
- [Phase 13]: Capital.com has no true multi-level DOM; Phase 13 uses OHLCV-derived `flow_*` features as the primary path and optional L1 quote imbalance as enrichment
- [Phase 13]: New order-flow features must use the `flow_` prefix and must not duplicate existing `l1_*`, `l2_*`, or `micro_*` microstructure features
- [Phase 13]: Order-flow integration is feature/data only; runtime trading policy remains unchanged until a later phase explicitly consumes those features
- [Phase 15]: Implementation based on density clustering (MeanShift) and Hough Transforms (trendln) to avoid noisy TA markers.
- [Phase 15]: Confluence scoring aggregates SR, Fib, and Trendlines into high-probability zones.

## Accumulated Context

### Roadmap Evolution

- Phase 12.1 inserted after Phase 12: AI Confidence Calibration & Decision Governance (URGENT)
- Phase 12.3 inserted after Phase 12.1: AI Indicator Specialist Training
- Phase 12.4 inserted after Phase 12.3: Exit AI Training & Baseline Evaluation
- Phase 12.5 inserted after Phase 12.4: Exit AI Runtime Integration & Governance
- Phase 12.7 inserted after Phase 12.6: AI Training Pipeline Hardening (URGENT)
- Phase 14 added: Elliott Wave Theorie Integration
- Phase 15 redefined: Fibonacci Engine & S/R Zones (Automated structure detection)
- Phase 16 shifted: Demo Trading Validation (formerly Phase 15)

## Session Log

- 2026-04-28: Phase 15 (Fibonacci Engine & S/R Zones) planned with 3 detailed executable plans. ROADMAP updated to reflect shifted phases. STATE updated to Current Phase 15.
- 2026-04-29: Phase 11 completed under autonomous mode. Phase 6 remained excluded per user instruction.
- 2026-04-29: Phase 12 completed under autonomous mode. Verified correlation fetcher/calculator/features with 21 passing targeted tests. Phase 6 remained excluded per user instruction.
- 2026-04-29: Phase 12.7 completed under autonomous mode. Verified training coverage, causal labels, split manifests, promotion gates, and pipeline calibration regression with 24 passing targeted tests. Phase 6 remained excluded per user instruction.
