# Roadmap: GoldBot 2

## Milestone: v1.0 — Profitable Demo Trading

**Goal:** Bot trades profitably on Capital.com demo account with a clean, maintainable codebase and functional web control interface.

---

### Phase 1: Code Cleanup & Project Foundation
**Goal:** Clean, well-structured codebase ready for improvements
**Requirements:** CODE-01, CODE-02, CODE-03, CODE-04, CODE-05, CODE-06
**Plans:** 4 plans

Plans:
- [ ] 01-01-PLAN.md — Gitignore update and German-to-English comment translation
- [ ] 01-02-PLAN.md — main.py refactor into trading/ mixin modules + lazy import fixes
- [ ] 01-03-PLAN.md — trainer.py split into trade_filter.py and pipeline.py
- [ ] 01-04-PLAN.md — Full test suite verification (no regressions)

**Scope:**
- Refactor main.py into smaller modules
- Split trainer.py into sub-modules
- Fix lazy imports
- Standardize comments to English
- Add proper .gitignore
- Verify all existing tests still pass

**UAT:**
- [ ] main.py < 200 lines, trading logic in separate module
- [ ] trainer.py split into files < 300 lines each
- [ ] No lazy imports inside methods
- [ ] .gitignore covers .venv, __pycache__, .env, logs, saved_models
- [ ] All existing tests pass

---

### Phase 2: Training Pipeline — Walk-Forward Validation
**Goal:** Training produces models validated with walk-forward method, preventing overfitting
**Requirements:** TRAIN-01, TRAIN-02, TRAIN-05, TRAIN-06, TRAIN-07
**Plans:** 3 plans

Plans:
- [ ] 02-01-PLAN.md — Walk-forward validation engine + 6-month data validation
- [ ] 02-02-PLAN.md — Model versioning with version.json and production pointer
- [ ] 02-03-PLAN.md — Training report generation + end-to-end integration

**Scope:**
- Implement walk-forward validation (train on rolling window, test on next period)
- Ensure features computed after split (no data leakage)
- Add model versioning (save metadata per training run)
- Generate walk-forward training report
- Ensure minimum 6 months of data used

**UAT:**
- [ ] Walk-forward validation with at least 5 windows
- [ ] Features computed per-window, not on full dataset
- [ ] Each model save includes version.json with date, params, metrics
- [ ] Training report shows metrics per window

---

### Phase 3: Feature Engineering — SHAP & Pruning
**Goal:** Remove noisy features, keep only those that contribute to model performance
**Requirements:** TRAIN-03, TRAIN-04
**Plans:** 3 plans

Plans:
- [ ] 03-01-PLAN.md — SHAP importance module + dependencies (compute_shap_importance, save_feature_importance_chart)
- [ ] 03-02-PLAN.md — Replace feature selection with SHAP pruning in walk-forward windows
- [ ] 03-03-PLAN.md — Wire SHAP persistence into pipeline and version directory

**Scope:**
- Integrate SHAP for feature importance analysis
- Automatic pruning of low-importance features
- Compare model performance with full vs pruned feature sets
- Visualize feature importance

**UAT:**
- [ ] SHAP values computed and saved per training run
- [ ] Feature pruning removes bottom 50% by importance
- [ ] Pruned model performance >= full model performance
- [ ] Feature importance chart saved with training report

---

### Phase 4: Strategy Improvements — Dynamic TP/SL & Regime Detection
**Goal:** Trading strategy adapts to market conditions instead of using fixed parameters
**Requirements:** STRAT-01, STRAT-02, STRAT-03, STRAT-04
**Plans:** 3 plans

Plans:
- [ ] 04-01-PLAN.md — Regime detection foundation (MarketRegime enum, RegimeDetector, REGIME_PARAMS)
- [ ] 04-02-PLAN.md — Dynamic ATR-based label generation and backtester alignment
- [ ] 04-03-PLAN.md — Regime-aware strategy parameters and ATR position sizing

**Scope:**
- Replace fixed 50/30 pip TP/SL with ATR-based dynamic levels
- Implement market regime detection (trending/ranging/volatile)
- Adjust strategy parameters per regime
- ATR-based position sizing

**UAT:**
- [ ] TP/SL calculated from ATR, not hardcoded
- [ ] Regime detector classifies market into at least 3 states
- [ ] Different strategy params applied per regime
- [ ] Position size adapts to ATR

---

### Phase 5: Backtesting & Validation
**Goal:** Proven strategy performance on historical data with realistic conditions
**Requirements:** BACK-01, BACK-02, BACK-03, BACK-04
**Plans:** 2 plans

Plans:
- [ ] 05-01-PLAN.md — Commission support, BacktestRunner, and BacktestReport with consistency checks
- [ ] 05-02-PLAN.md — CLI backtest script and end-to-end integration test

**Scope:**
- Build/improve backtesting framework with realistic costs
- Run walk-forward backtest across multiple time periods
- Generate comprehensive performance report
- Validate consistency across periods

**UAT:**
- [ ] Backtest includes spread, slippage, commissions
- [ ] Report shows Sharpe ratio, max drawdown, win rate, profit factor
- [ ] Walk-forward backtest shows positive results in >60% of windows
- [ ] No single window has >20% drawdown

---

### Phase 6: Control App — Core Interface
**Goal:** Functional web interface to control and monitor the bot
**Requirements:** CTRL-01, CTRL-02, CTRL-03

**Scope:**
- Unify Control App to use main bot API (remove duplicate backend)
- Implement Start/Stop controls
- Live status display (running state, positions, P&L)
- WebSocket connection for real-time updates

**UAT:**
- [ ] Control App makes API calls to main bot, no duplicate backend
- [ ] Start/Stop buttons work
- [ ] Live status updates in real-time
- [ ] WebSocket connected and updating

---

### Phase 7: Control App — Dashboard & History
**Goal:** Complete dashboard with trade history and model performance
**Requirements:** CTRL-04, CTRL-05, CTRL-06

**Scope:**
- Trade history view with filtering (date, direction, P&L)
- Model performance metrics display
- Real-time trade notifications in UI

**UAT:**
- [ ] Trade history shows all trades with filters
- [ ] Model metrics page shows accuracy, profit factor per model version
- [ ] New trades appear in UI without page refresh

---

### Phase 8: Demo Trading Validation
**Goal:** Bot runs profitably on demo account, proving the system works
**Requirements:** DEMO-01, DEMO-02, DEMO-03, DEMO-04

**Scope:**
- Deploy bot on Capital.com demo account
- Run for 2+ weeks continuously
- Monitor and log all trades
- Evaluate profitability

**UAT:**
- [ ] Bot runs 24+ hours without crashes
- [ ] Trades open and close automatically
- [ ] Positive P&L over 2-week period
- [ ] All trades logged with full details

---

**Total phases:** 8
**Total v1 requirements:** 31
**All requirements mapped.**

---
*Roadmap created: 2026-03-03*
*Last updated: 2026-03-09 after phase 5 planning*
