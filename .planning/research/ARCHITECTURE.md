# Architecture Research — GoldBot 2

## Current Architecture (Analysis)

### Strengths
- **Well-modularized** — Clear separation: ai_engine, strategy, risk, order_management, market_data, etc.
- **Async-first** — Proper use of asyncio throughout
- **Repository pattern** — Clean DB access via repositories
- **Error classification** — Errors categorized as transient/permanent/unknown
- **Kill switch** — Multi-layer safety system
- **Triple Barrier Labels** — Industry-standard labeling with cost modeling

### Weaknesses Found
1. **main.py is monolithic** — TradingSystem class does too much (~824 lines). Should separate trading loop, signal generation, and system lifecycle
2. **trainer.py is massive** — ~1000+ lines, handles entire pipeline in one file
3. **No walk-forward validation** — Uses simple chronological split (70/15/15). This is the #1 reason models may not be profitable
4. **Feature engineer claims ~60 features** — No pruning, many may be noise
5. **Control App duplicates backend** — goldbot-control-app/backend has its own FastAPI app separate from api/. Should share or proxy
6. **Mixed language comments** — German and English throughout
7. **Lazy imports inside methods** — `import time as _time_mod` inside _trading_tick, etc.
8. **No model versioning** — Models are saved to ai_engine/saved_models/ with no version tracking

## Recommended Architecture Changes

### Phase 1: Code Cleanup
- Extract TradingSystem into smaller classes (TradingLoop, SignalGenerator, SystemLifecycle)
- Consolidate lazy imports to top of file
- Standardize language (English for code, German OK for user-facing strings)
- Add .gitignore for proper ignoring of .venv, __pycache__, etc.

### Phase 2: Training Pipeline
- Add walk-forward validation (most critical change)
- Add SHAP-based feature selection
- Add model versioning and tracking
- Split trainer.py into smaller modules

### Phase 3: Control App
- Unify API: Control App should proxy to main bot API, not duplicate it
- Complete React frontend components
- Add WebSocket for real-time updates

## Data Flow

```
Market Data → DataProvider → FeatureEngineer → AIPredictor → StrategyManager → RiskManager → OrderManager → Capital.com
     ↑                                                                                              ↓
     └──────────────────────── PositionMonitor ←──────────────────────────────────────────────────────┘
```

## Build Order (Dependencies)
1. Code cleanup (no dependencies)
2. Training pipeline improvements (depends on code cleanup)
3. Backtesting validation (depends on training pipeline)
4. Control App (can run parallel to 2-3)
5. Demo trading validation (depends on 2-3)
