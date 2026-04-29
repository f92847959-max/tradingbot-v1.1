# Pitfalls Research — GoldBot 2

## Critical Pitfalls

### 1. Look-Ahead Bias in Training
- **Risk**: Using future data to train the model (data leakage). Most common reason ML trading bots fail
- **Warning Signs**: Model accuracy >70% on test set but fails in live trading
- **Current Status**: LabelGenerator uses future candles for labels (correct by design — Triple Barrier). But the train/test split may leak: features computed on full dataset before split
- **Prevention**:
  - Compute features AFTER splitting data
  - Use walk-forward validation instead of simple split
  - Add purging gap between train and test periods (code has this, verify it's large enough)
- **Phase**: Training Pipeline (Phase 2-3)

### 2. Overfitting to Historical Data
- **Risk**: Model memorizes noise instead of learning patterns. Gold market changes regime frequently
- **Warning Signs**: Great backtest results, poor forward performance
- **Current Status**: No walk-forward validation. Simple 70/15/15 split. HIGH RISK of overfitting
- **Prevention**:
  - Walk-forward validation (train on 6 months, test on next month, slide)
  - Limit model complexity (max_depth, min_child_weight)
  - Feature selection — remove features with low importance
  - Use multiple evaluation periods, not just one
- **Phase**: Training Pipeline (Phase 2-3)

### 3. Survivorship Bias in Features
- **Risk**: Using ~60 features, many may be noise. Models that use noisy features will overfit
- **Warning Signs**: Feature importance shows many features with near-zero importance
- **Prevention**:
  - SHAP analysis to identify which features actually matter
  - Remove bottom 50% features by importance
  - Test with reduced feature set vs full set
- **Phase**: Feature Engineering (Phase 2)

### 4. Fixed TP/SL in Changing Markets
- **Risk**: Using fixed 50 pip TP / 30 pip SL regardless of market volatility. In low-vol markets this is too wide, in high-vol too tight
- **Warning Signs**: Long periods of only HOLD signals, or rapid SL hits
- **Prevention**:
  - Dynamic TP/SL based on ATR (Average True Range)
  - Different parameters for different market regimes
- **Phase**: Strategy Improvement (Phase 3-4)

### 5. Capital.com API Gotchas
- **Risk**: Rate limits, session expiry, WebSocket disconnects
- **Warning Signs**: BrokerError spikes, missed trades
- **Current Status**: Code has retry logic and health checks. Seems reasonably robust
- **Prevention**:
  - Monitor API latency
  - Implement proper session refresh
  - Handle rate limit (429) gracefully
- **Phase**: Infrastructure (Phase 1)

## Medium Pitfalls

### 6. Training on Insufficient Data
- **Risk**: Gold 5-minute candles — need at least 6-12 months for meaningful training
- **Prevention**: Ensure data source provides enough history. Current broker API may be limited
- **Phase**: Data Pipeline (Phase 2)

### 7. Ignoring Transaction Costs
- **Risk**: Model looks profitable before costs but loses money after spread/slippage
- **Current Status**: ALREADY HANDLED — LabelGenerator includes spread (2.5 pips) and slippage (0.5 pips)
- **Status**: Low risk, already mitigated

### 8. Dual Backend Problem
- **Risk**: Control App has its own FastAPI backend that may conflict with or diverge from main bot API
- **Prevention**: Unify APIs or have Control App proxy to main API
- **Phase**: Control App (Phase 5+)
