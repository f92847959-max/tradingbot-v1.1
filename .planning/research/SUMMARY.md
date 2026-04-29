# Research Summary — GoldBot 2

## Key Findings

### 1. No pre-trained models exist for gold trading
There are no production-ready open-source models for gold/forex that can be plugged in. The best path is to **fix the existing training pipeline** rather than looking for external models.

### 2. Walk-forward validation is the #1 missing piece
The current training uses a simple 70/15/15 chronological split. This almost certainly leads to overfitting. **Walk-forward validation** (train on rolling windows, test on the next period) is the single most impactful improvement for profitability.

### 3. Too many features, no pruning
~60 features are computed but there's no systematic way to know which ones actually help. SHAP-based feature selection could remove noisy features and improve model performance.

### 4. Fixed TP/SL ignores market conditions
50 pip TP / 30 pip SL is used regardless of whether the market is calm or volatile. ATR-based dynamic levels would adapt to conditions.

### 5. The codebase is solid but needs refactoring
The architecture is well-modularized. Key issues are:
- main.py and trainer.py are too large
- Control App has a duplicate backend
- Mixed language comments
- No model versioning

### 6. Transaction costs are already handled
The LabelGenerator correctly accounts for spread and slippage. This is a strong point.

## Recommended Phase Order

| Priority | Area | Impact | Effort |
|----------|------|--------|--------|
| 1 | Code cleanup & project setup | Foundation | Medium |
| 2 | Training pipeline (walk-forward) | CRITICAL for profitability | High |
| 3 | Feature engineering (SHAP, pruning) | High for profitability | Medium |
| 4 | Strategy improvements (dynamic TP/SL) | High for profitability | Medium |
| 5 | Backtesting & validation framework | Needed to prove profitability | Medium |
| 6 | Control App frontend | User experience | High |
| 7 | Control App backend unification | Code quality | Medium |
| 8 | Demo trading & monitoring | Final validation | Medium |

## Risk Assessment

| Risk | Likelihood | Impact | Mitigation |
|------|-----------|--------|------------|
| Overfitting | HIGH | Model fails in live | Walk-forward validation |
| Look-ahead bias | MEDIUM | Inflated backtest results | Feature computation after split |
| Insufficient data | MEDIUM | Model can't learn | Ensure 6-12 months of data |
| API instability | LOW | Missed trades | Already has retry logic |

## Stack Decisions

- **Keep**: XGBoost + LightGBM, Capital.com, FastAPI, PostgreSQL, React
- **Add**: SHAP, vectorbt (backtesting), walk-forward validation, Optuna (hyperparams)
- **Don't add**: Deep learning, RL, pre-trained LLMs, sentiment analysis
