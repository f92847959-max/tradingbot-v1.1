# Features Research — GoldBot 2

## Table Stakes (Must Have)

### Signal Generation
- **Triple Barrier Labels with costs** — Already implemented, good quality
- **Walk-forward validation** — MISSING. Currently uses simple chronological split. Critical for avoiding overfitting
- **Feature importance analysis** — Partially implemented. Needs SHAP integration for explainability
- **Multi-timeframe alignment** — Already implemented (5m, 15m, 1h, 4h)

### Risk Management
- **Position sizing** — Already implemented (Kelly criterion based)
- **Kill switch** — Already implemented (11-layer checks)
- **Daily/weekly loss limits** — Already implemented
- **Trailing stops** — Already implemented

### Control & Monitoring
- **Start/Stop bot** — API exists, Control App needs frontend
- **Trade history view** — API exists, needs UI
- **Real-time P&L** — Needs dashboard integration
- **Model performance tracking** — MISSING. No way to see if model is degrading

## Differentiators (Competitive Advantage)

### AI/ML Improvements
- **Walk-forward optimization** — Train on window, test on next period, slide forward. Prevents overfitting. HIGH IMPACT
- **Regime detection** — Classify market as trending/ranging/volatile. Different strategies per regime. HIGH IMPACT
- **Feature selection with SHAP** — Remove noisy features that hurt model performance. MEDIUM IMPACT
- **Purging gap between train/test** — Already in code but may not be correctly sized. MEDIUM IMPACT
- **Hyperparameter search with Optuna** — Already partially implemented. Needs walk-forward integration. MEDIUM IMPACT

### Trading Logic
- **Dynamic TP/SL based on ATR** — Instead of fixed 50/30 pips, use Average True Range. HIGH IMPACT
- **Session-aware trading** — Bot already has session filter, but not optimized. Could focus on London open + NY open. MEDIUM IMPACT
- **Correlation-based signals** — Gold correlates with DXY, US10Y, S&P500. Adding these as features could improve signals. MEDIUM IMPACT

## Anti-Features (DO NOT Build)

- **Deep Learning models** — Overfit easily on limited data, XGBoost/LightGBM are better here
- **Sentiment analysis** — News/social media signals are noisy and unreliable for intraday
- **Multiple trading pairs** — Focus on Gold only, get that working first
- **Copy trading / social features** — Out of scope, adds complexity
- **Auto-optimization** — Dangerous, can optimize into overfitting
