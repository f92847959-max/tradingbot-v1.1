# Stack Research — GoldBot 2

## Current Stack (Keep)
- **ML**: XGBoost + LightGBM Ensemble (confirmed — good choice for tabular financial data)
- **Broker**: Capital.com REST + WebSocket API
- **Backend**: Python 3.11+, FastAPI, async
- **Frontend**: React + TypeScript (Control App)
- **DB**: PostgreSQL (prod) + SQLite (fallback), Alembic migrations
- **Dashboard**: Streamlit (simple monitoring)

## Recommended Additions

### Feature Engineering & Validation
- **ta-lib / pandas-ta** — Technical indicator library (RSI, MACD, Bollinger, etc.) — Confidence: HIGH
- **SHAP** — Model explainability, understand WHY the model predicts what it predicts — Confidence: HIGH
- **great_expectations or pandera** — Data validation to catch bad training data early — Confidence: MEDIUM

### Backtesting & Evaluation
- **vectorbt** — Fast vectorized backtesting, walk-forward analysis — Confidence: HIGH
- **Walk-forward validation** — Time-series cross-validation instead of random splits — Confidence: CRITICAL

### Model Monitoring
- **MLflow** or simple custom logging — Track training runs, compare model versions — Confidence: MEDIUM

## Pre-trained Open-Source Models

### Finding: No Production-Ready Pre-trained Gold Models Exist
Research shows there are NO reliable pre-trained open-source models for gold/forex trading that can be plugged in directly. What exists:
- Academic LSTM demos (GitHub: forex-price-prediction) — toy projects, not production
- TradingView community indicators — not ML models
- Generic time-series models — not trained on gold specifically

### Recommendation
**Improve own training pipeline** rather than looking for pre-trained models. The value is in:
1. Better feature engineering (more/better indicators)
2. Proper walk-forward validation (no look-ahead bias)
3. Better hyperparameter tuning
4. Regime detection (trending vs ranging market)

## What NOT to Use
- **Deep Learning (LSTM/Transformer)** for price prediction — overfits easily on small datasets, XGBoost/LightGBM are better for this use case
- **Reinforcement Learning** — extremely hard to get right, overkill for this project
- **Pre-trained LLMs for trading signals** — unreliable, no edge
