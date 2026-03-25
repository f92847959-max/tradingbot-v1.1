# Requirements: GoldBot 2

**Defined:** 2026-03-03
**Core Value:** Der Bot muss im Demo-Modus profitabel traden — deutlich mehr Gewinne als Verluste, nachweisbar über Zeit.

## v1 Requirements

### Code Quality

- [ ] **CODE-01**: main.py is refactored into smaller, focused modules (TradingLoop, SignalGenerator, SystemLifecycle)
- [ ] **CODE-02**: trainer.py is split into manageable sub-modules (<300 lines each)
- [ ] **CODE-03**: All lazy imports moved to top-level or proper factory pattern
- [ ] **CODE-04**: Consistent English code comments (German OK for user-facing strings)
- [ ] **CODE-05**: Proper .gitignore covering .venv, __pycache__, .env, saved_models, logs
- [ ] **CODE-06**: All existing tests pass after refactoring

### Training Pipeline

- [ ] **TRAIN-01**: Walk-forward validation replaces simple chronological split
- [ ] **TRAIN-02**: Features are computed AFTER train/test split to prevent data leakage
- [ ] **TRAIN-03**: SHAP-based feature importance analysis is integrated
- [ ] **TRAIN-04**: Bottom 50% features by importance can be pruned automatically
- [ ] **TRAIN-05**: Model versioning — each training run saves version metadata (date, params, metrics)
- [x] **TRAIN-06**: Training report shows walk-forward results across all windows
- [ ] **TRAIN-07**: Minimum 6 months of historical data used for training

### Strategy

- [x] **STRAT-01**: Dynamic TP/SL based on ATR instead of fixed 50/30 pips
- [ ] **STRAT-02**: ATR-based position sizing adapts to market volatility
- [x] **STRAT-03**: Regime detection classifies market as trending/ranging/volatile
- [ ] **STRAT-04**: Strategy parameters differ per detected regime

### Backtesting

- [x] **BACK-01**: Backtesting framework validates strategy on out-of-sample data
- [x] **BACK-02**: Backtest includes realistic costs (spread, slippage, commissions)
- [x] **BACK-03**: Backtest report shows key metrics (Sharpe ratio, max drawdown, win rate, profit factor)
- [x] **BACK-04**: Walk-forward backtest shows consistent performance across time periods

### MiroFish Swarm Intelligence

- [x] **MIRO-01**: MiroFish (666ghj/MiroFish) kloned, uv-Deps installiert, Flask-Backend laeuft auf localhost:5001 (Windows 11, Python 3.12, kein Docker)
- [x] **MIRO-02**: Zep Cloud verbunden (Free Tier), Knowledge Graph erstellt Gold-Markt-Ontologie aus Seed-Daten
- [x] **MIRO-03**: LLM via OpenAI API (gpt-4o-mini), .env konfiguriert mit LLM_API_KEY + ZEP_API_KEY + LLM_MODEL_NAME
- [ ] **MIRO-04**: Gold-Agenten (Trader, Analysten, Zentralbanker) simulieren XAUUSD-Szenarien, Ergebnis als Prediction-Score
- [ ] **MIRO-05**: mirofish_client.py integriert Swarm-Score in signal_generator.py neben XGBoost/LightGBM Ensemble
- [ ] **MIRO-06**: API-Kosten-Limiter begrenzt Simulationen pro Tag (Token-Budget fuer gpt-4o-mini)

### Demo Trading

- [ ] **DEMO-01**: Bot runs stable on Capital.com demo account for 24+ hours without crashes
- [ ] **DEMO-02**: Bot opens and closes trades automatically based on AI signals
- [ ] **DEMO-03**: Bot shows positive P&L over a 2-week demo period
- [ ] **DEMO-04**: All trades are logged with entry/exit prices, P&L, reasoning

## v2 Requirements

### Advanced ML

- **ML-01**: Ensemble model weights auto-tuned based on recent performance
- **ML-02**: Online learning — model updates incrementally with new data
- **ML-03**: Correlation features (DXY, US10Y, S&P500) added to feature set

### Notifications

- **NOTIF-01**: WhatsApp notifications for trade opens/closes
- **NOTIF-02**: Daily performance summary notification
- **NOTIF-03**: Kill switch activation alert

### Monitoring

- **MON-01**: Model degradation detection with automatic retraining trigger
- **MON-02**: API latency monitoring dashboard
- **MON-03**: Automated health checks with alerting

## Out of Scope

| Feature | Reason |
|---------|--------|
| Deep learning models (LSTM/Transformer) | Overfit easily on small datasets, XGBoost/LightGBM better for this |
| Sentiment analysis | Noisy, unreliable for intraday gold trading |
| Multiple trading pairs | Focus on Gold only until profitable |
| Mobile app | Web interface sufficient |
| Live trading with real money | Must prove profitability in demo first |
| Broker switch | Capital.com integration works, no reason to change |
| Pre-trained external models | None exist for gold trading that are production-ready |
| Reinforcement learning | Extremely hard to get right, overkill |

## Traceability

| Requirement | Phase | Status |
|-------------|-------|--------|
| CODE-01 | Phase 1 | Pending |
| CODE-02 | Phase 1 | Pending |
| CODE-03 | Phase 1 | Pending |
| CODE-04 | Phase 1 | Pending |
| CODE-05 | Phase 1 | Pending |
| CODE-06 | Phase 1 | Pending |
| TRAIN-01 | Phase 2 | Pending |
| TRAIN-02 | Phase 2 | Pending |
| TRAIN-03 | Phase 3 | Pending |
| TRAIN-04 | Phase 3 | Pending |
| TRAIN-05 | Phase 2 | Pending |
| TRAIN-06 | Phase 2 | Complete |
| TRAIN-07 | Phase 2 | Pending |
| STRAT-01 | Phase 4 | Complete |
| STRAT-02 | Phase 4 | Pending |
| STRAT-03 | Phase 4 | Complete |
| STRAT-04 | Phase 4 | Pending |
| BACK-01 | Phase 5 | Pending |
| BACK-02 | Phase 5 | Pending |
| BACK-03 | Phase 5 | Pending |
| BACK-04 | Phase 5 | Pending |
| MIRO-01 | Phase 6 | Complete |
| MIRO-02 | Phase 6 | Complete |
| MIRO-03 | Phase 6 | Complete |
| MIRO-04 | Phase 6 | Pending |
| MIRO-05 | Phase 6 | Pending |
| MIRO-06 | Phase 6 | Pending |
| DEMO-01 | Phase 7 | Pending |
| DEMO-02 | Phase 7 | Pending |
| DEMO-03 | Phase 7 | Pending |
| DEMO-04 | Phase 7 | Pending |

**Coverage:**
- v1 requirements: 31 total
- Mapped to phases: 31
- Unmapped: 0

---
*Requirements defined: 2026-03-03*
*Last updated: 2026-03-03 after initial definition*
