# Phase 1: Code Cleanup & Project Foundation - Research

**Researched:** 2026-03-03
**Domain:** Python refactoring, module decomposition, import hygiene, .gitignore
**Confidence:** HIGH — findings based directly on reading the actual source files

---

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|-----------------|
| CODE-01 | main.py refactored into smaller, focused modules (TradingLoop, SignalGenerator, SystemLifecycle) | main.py is 824 lines with a single TradingSystem class. Clear split lines identified: SystemLifecycle (~lines 73-346), TradingLoop (~lines 356-570), SignalGenerator (~lines 573-656) |
| CODE-02 | trainer.py split into manageable sub-modules (<300 lines each) | trainer.py is 627 lines. Training pipeline logic in `train_all()` is 330+ lines. The static helper methods (`_probs_to_trade_signals`, `_trade_metrics_rank`, `_tune_trade_filter`) are natural extraction candidates |
| CODE-03 | All lazy imports moved to top-level or proper factory pattern | 6 lazy imports confirmed in main.py at lines 150, 205, 358, 472, 661, 779. Plus multi-level nested lazy imports at lines 216, 259, 633-634, 673, 717 |
| CODE-04 | Consistent English code comments (German OK for user-facing strings) | German content confirmed in 16+ source files across ai_engine/, config/, monitoring/. trainer.py has ~30 German log messages. All f-string logger calls use German |
| CODE-05 | Proper .gitignore covering .venv, __pycache__, .env, saved_models, logs | Current .gitignore is missing: `.venv/`, `ai_engine/saved_models/`, `*.pkl`, `*.json` (model metadata), `data/`, `*.lock` |
| CODE-06 | All existing tests pass after refactoring | 7 tests currently failing pre-refactor. 8 test files fail to collect (missing modules). The 171 passing tests are the baseline to protect |
</phase_requirements>

---

## Summary

main.py is 824 lines containing the `TradingSystem` class with 13 methods that span three distinct responsibilities: system lifecycle (startup/shutdown), the trading decision loop, and background monitoring loops. This class can be split along clean method boundaries with no circular dependency risk because all shared state lives on the `TradingSystem` instance.

trainer.py is 627 lines (not 1000+ as noted in architecture docs — it was previously larger and has been partially reduced). The `train_all()` method is the dominant concern at ~350 lines. The static trade filter helpers (`_probs_to_trade_signals`, `_trade_metrics_rank`, `_tune_trade_filter`) are self-contained and can be extracted to a `trade_filter.py` module. The main training pipeline steps could move to a `pipeline.py`. However: the existing sub-modules (`backtester.py`, `data_preparation.py`, `evaluation.py`) are already independent and WITHIN the 300-line limit. Only `trainer.py` itself and `evaluation.py` (459 lines) exceed the limit.

The test suite has a split baseline: 171 tests pass, 7 tests fail pre-refactor (pre-existing bugs unrelated to this phase), and 8 test files fail to collect due to missing modules (`scripts.train_ai`, `scripts.monitor_training_chart`, `ai_engine.prediction.prompt_builder`). CODE-06 must preserve the 171 passing tests — it does NOT mean fixing the 7 pre-existing failures or the 8 broken collection files.

**Primary recommendation:** Refactor by moving code into new files, not by rewriting logic. The safest approach is extract-and-delegate: keep `TradingSystem` as a thin shell that delegates to focused sub-modules. This means `test_lifecycle.py`'s imports of `from main import TradingSystem` and `api/dependencies.py`'s `TYPE_CHECKING` import continue to work without changes.

---

## Current State Analysis

### main.py (824 lines)

The file has three clear logical sections:

**SystemLifecycle group** (lines 73-346):
- `__init__` — component wiring
- `_health_check` — startup validation
- `start` — initialization + gather loops
- `stop` — graceful shutdown with position reconciliation
- `set_trading_mode` — runtime mode switch

**TradingLoop group** (lines 356-570):
- `_trading_loop` — error-handling wrapper with backoff
- `_trading_tick` — single iteration: data → signal → risk → execute
- `_fetch_mtf_parallel` — parallel multi-timeframe fetch
- `_generate_signal` — lazy-loads AIPredictor, calls predict
- `_save_signal` — persist signal to DB

**MonitoringLoops group** (lines 659-748):
- `_daily_cleanup_loop` — midnight DB candle cleanup
- `_position_monitor_loop` — 30-second position checks
- `_handle_position_closed` — handle TP/SL close events

**Entry point** (lines 755-824):
- `main()` — settings validation, signal handlers, API server setup

### trainer.py (627 lines)

The file structure:
- `ModelTrainer.__init__` — component wiring (lines 55-111)
- `_probs_to_trade_signals` — static, pure function (lines 114-136)
- `_trade_metrics_rank` — static, pure function (lines 139-162)
- `_tune_trade_filter` — grid search on validation data (lines 164-209)
- `train_all` — the 350-line main pipeline (lines 211-558)
- `train_from_csv` — thin CSV loading wrapper (lines 560-573)
- `__main__` block — synthetic test data (lines 576-627)

### Lazy imports in main.py

| Line | Import | Location | Fix |
|------|--------|----------|-----|
| 150 | `import os` | `_health_check()` | Already imported at top (line 15) — duplicate, just remove |
| 205 | `from market_data.historical import download_historical_candles` | `start()` | Move to top-level |
| 216 | `from database.repositories.trade_repo import TradeRepository` | `start()` | Move to top-level |
| 259 | `from notifications.confirmation_handler import ConfirmationHandler` | `start()` | Move to top-level |
| 358 | `from shared.exceptions import classify_error, ErrorCategory` | `_trading_loop()` | Move to top-level |
| 472 | `import time as _time_mod` | `_trading_tick()` | Move `import time` to top-level |
| 633-634 | `from database.models import Signal as SignalModel` + `from database.repositories.signal_repo import SignalRepository` | `_save_signal()` | Move to top-level |
| 661 | `from datetime import timezone as _tz` | `_daily_cleanup_loop()` | Add `timezone` to existing datetime import |
| 673 | `from database.repositories.candle_repo import CandleRepository` | `_daily_cleanup_loop()` | Move to top-level |
| 717 | `from database.repositories.trade_repo import TradeRepository` | `_handle_position_closed()` | Move to top-level (already needed at line 216) |
| 775 | `import functools` | `main()` | Move to top-level |
| 779 | `import time as _time` | `main()` | Move `import time` to top-level |
| 785-786 | `import uvicorn` + `from api.app import create_app` | `main()` | These are legitimately conditional (only when API enabled) — factory pattern is correct |
| 802 | `import contextlib` | `main()` | Move to top-level |

**Note:** `from ai_engine.prediction.predictor import AIPredictor` in `_generate_signal()` (line 600) is a true lazy-load (intentional, for startup performance). This is a factory pattern: the predictor is loaded on first use. This should stay as-is — or better, document it explicitly as intentional with a comment.

### German content scope

Files with German log messages or comments (excluding .venv):
- `ai_engine/features/` — 6 files
- `ai_engine/models/` — 3 files (base_model.py, lightgbm_model.py, xgboost_model.py)
- `ai_engine/training/` — 6 files (all training submodules)
- `config/settings.py` — 1 file
- `monitoring/watchdog_service.py` — 1 file
- `strategy/backtesting/advanced_backtester.py` — 1 file

Total: ~17 files have German-language developer-facing strings in logger calls.

### .gitignore gaps

Current content covers: `.env`, `logs/`, `__pycache__/`, `*.pyc`, `.idea/`, `.vscode/`

Missing entries needed per CODE-05:
- `.venv/` — virtual environment directory (present in repo root)
- `ai_engine/saved_models/` — trained model files (.pkl present in repo)
- `*.pkl` — pickled model files
- `data/` — downloaded historical data
- `*.lock` — process lock files (e.g., `overnight_training_gc.lock` in logs/)
- `alembic/versions/*.py` may need consideration

### Test suite pre-refactor baseline

**171 tests pass** (these must still pass after Phase 1)

**7 tests fail pre-refactor** (pre-existing bugs, not Phase 1's responsibility):
- `tests/test_indicators.py` — 6 failures: tests expect `atr` column that `calculate_indicators()` no longer produces
- `tests/test_risk_integration.py::TestKillSwitch::test_kill_switch_sync_failure_activates_fail_safe` — 1 failure: behavior change in kill switch retry logic

**8 test files fail to collect** (missing source modules, not Phase 1's responsibility):
- `test_gpt_predictor.py` — GPT predictor module removed
- `test_monitor_training_chart_parser.py` — `scripts.monitor_training_chart` module missing
- `test_prompt_builder.py` — `ai_engine.prediction.prompt_builder` module missing
- `test_train_ai_gate.py` — `scripts.train_ai` module missing
- `test_train_ai_hybrid_source.py` — same
- `test_train_ai_progress_jsonl.py` — same
- `test_train_ai_runtime.py` — same
- `test_train_ai_synthetic_mode.py` — same

**The refactoring must not reduce the 171 passing count.**

---

## Architecture Patterns

### Pattern 1: Extract-and-Delegate (for main.py refactor)

**What:** Move method groups into separate modules while keeping `TradingSystem` as the public interface. Tests and consumers (`test_lifecycle.py`, `api/dependencies.py`) import `TradingSystem` from `main.py` — this interface MUST stay stable.

**When to use:** When consumers depend on the class location and you cannot change them in the same pass.

**Recommended structure:**
```
main.py                              # TradingSystem shell + entry point
trading/
    __init__.py
    lifecycle.py                     # SystemLifecycle mixin or composed class
    trading_loop.py                  # _trading_loop, _trading_tick, _fetch_mtf_parallel
    signal_generator.py              # _generate_signal, _save_signal
    monitors.py                      # _position_monitor_loop, _daily_cleanup_loop, _handle_position_closed
```

OR (simpler approach — mixin composition):
```python
# main.py — TradingSystem stays importable from main
class TradingSystem(LifecycleMixin, TradingLoopMixin, MonitorMixin):
    pass
```

**The planner should choose:** Whether to use composition (separate module files, TradingSystem delegates) or inheritance mixins. Both satisfy CODE-01. Composition is safer for future refactoring.

**Example — delegation approach:**
```python
# trading/trading_loop.py
class TradingLoop:
    def __init__(self, system):
        self._system = system  # back-reference to access shared state

# main.py
class TradingSystem:
    def __init__(self, settings):
        # ...
        self._loop = TradingLoop(self)

    async def _trading_loop(self):
        return await self._loop.run()
```

### Pattern 2: Static Method Extraction (for trainer.py)

**What:** Move the three static helper methods out of `ModelTrainer` into a dedicated `trade_filter.py` module.

**Recommended structure:**
```
ai_engine/training/
    trainer.py              # ModelTrainer class, trimmed to < 300 lines
    trade_filter.py         # TradeFilterTuner class (or module-level functions)
    pipeline.py             # train_all() pipeline logic extracted from ModelTrainer
```

**Alternative (simpler):** Extract just the `train_all` pipeline into `pipeline.py`, leaving the static helpers in `trainer.py`. This gets `trainer.py` under 300 lines without needing a new abstraction.

**Approximate line budget after extraction:**
- `trainer.py` (after extracting `train_all` body): ~200 lines (class skeleton + init + static helpers + thin `train_all` shell)
- `pipeline.py` (the extracted `train_all` logic): ~350 lines — still over limit
- Solution: also extract trade filter tuning into `trade_filter.py` (~60 lines), bringing `pipeline.py` to ~280 lines

### Pattern 3: Import Discipline

**Top-level imports for non-conditional dependencies:**
```python
# main.py — after refactor
import asyncio
import contextlib
import functools
import logging
import os
import signal
import sys
import time
from datetime import datetime, timezone
from logging.handlers import RotatingFileHandler

from dotenv import load_dotenv

from config.settings import get_settings, Settings
from database.connection import init_db, close_db, get_session
from database.models import Signal as SignalModel
from database.repositories.candle_repo import CandleRepository
from database.repositories.signal_repo import SignalRepository
from database.repositories.trade_repo import TradeRepository
from market_data.broker_client import CapitalComClient
from market_data.data_provider import DataProvider
from market_data.historical import download_historical_candles
from notifications.confirmation_handler import ConfirmationHandler
from notifications.notification_manager import NotificationManager
from order_management.order_manager import OrderManager
from risk.risk_manager import RiskManager
from shared.exceptions import (
    BrokerError, ConfigurationError, DataError, PredictionError,
    classify_error, ErrorCategory,
)
from strategy.strategy_manager import StrategyManager
from api.dependencies import set_trading_system
```

**Legitimate lazy-load (factory pattern) — keep as-is with comment:**
```python
async def _generate_signal(self, df, mtf_data=None) -> dict | None:
    # AIPredictor is lazy-loaded on first use to avoid heavy ML imports at startup
    if self._ai_predictor is None:
        from ai_engine.prediction.predictor import AIPredictor
        self._ai_predictor = AIPredictor(...)
```

**Conditional imports in main() — acceptable pattern:**
```python
if settings.api_enabled:
    import uvicorn
    from api.app import create_app
```

### Pattern 4: .gitignore for Python ML Projects

Standard Python ML .gitignore entries:
```gitignore
# Python
.venv/
venv/
__pycache__/
*.pyc
*.pyo
*.pyd
.Python

# Environment
.env
.env.local

# IDE
.idea/
.vscode/
*.swp
*.swo

# ML Models
ai_engine/saved_models/
*.pkl
*.h5
*.onnx
model_metadata.json

# Data
data/
*.csv

# Logs
logs/
*.log
*.lock

# OS
.DS_Store
Thumbs.db
```

---

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Comment/string language audit | Custom AST parser | `grep` with Unicode range `[\u00c0-\u024f]` or simple string search | The scope is known (17 files), mechanical sed/replace is sufficient |
| Circular import detection | Manual dependency graph | Python import system itself — if `python -c "import main"` works, no circulars | Test-driven verification is enough |
| Import ordering | Manual sort | `ruff --fix` with isort rules | Already in dev deps (`ruff>=0.8.0` in pyproject.toml) |

---

## Common Pitfalls

### Pitfall 1: Breaking `from main import TradingSystem`

**What goes wrong:** Moving `TradingSystem` out of `main.py` into `trading/lifecycle.py` breaks `test_lifecycle.py` and `api/dependencies.py` which both do `from main import TradingSystem`.

**Why it happens:** Forgetting that consumers import by module path, not just by name.

**How to avoid:** Either keep `TradingSystem` defined in `main.py` (extract code out to it, not away from it), OR add a compatibility re-export in `main.py`:
```python
# main.py
from trading.system import TradingSystem  # noqa: F401 — re-export for consumers
```

**Warning signs:** Any import error mentioning `from main import TradingSystem`.

### Pitfall 2: Circular imports when splitting main.py

**What goes wrong:** If `trading/trading_loop.py` imports from `main.py` to access `TradingSystem`, and `main.py` imports from `trading/trading_loop.py`, Python raises `ImportError: cannot import name`.

**Why it happens:** Back-references from extracted modules to the orchestrator class.

**How to avoid:** Extracted modules must NEVER import from `main.py`. Use dependency injection — pass `self` (the TradingSystem) as a constructor argument to sub-modules, or use `TYPE_CHECKING` guards:
```python
from __future__ import annotations
from typing import TYPE_CHECKING
if TYPE_CHECKING:
    from main import TradingSystem
```

**Warning signs:** `ImportError` or `AttributeError` at startup on a circular path.

### Pitfall 3: trainer.py step numbers go out of order

**What goes wrong:** The `train_all` method labels steps "1/12, 2/12, 3/12 ... 6/12, 7/12, 8/12, 9/12" but the actual code runs step 9a THEN step 8 (feature selection) THEN 9b. Log output shows "9/12 Training" then "8/12 Feature Selection" — the numbers are already wrong in the source.

**Why it happens:** Steps were added/reordered without updating labels.

**How to avoid:** When splitting `train_all` into `pipeline.py`, fix the step numbering to be sequential. This is a comment-cleanup task, not a logic change.

**Warning signs:** Log output showing step numbers out of sequence.

### Pitfall 4: German strings in f-string logger calls

**What goes wrong:** Replacing German logger messages globally with sed-style search/replace corrupts emoji characters and Unicode box-drawing characters already present (the `╔══╗` box chars in trainer.py show as `â•â•â•` due to encoding issues — these are rendering artifacts in the current file).

**Why it happens:** The file has encoding issues (`â€"`, `ðŸ"¥`, `â†'` etc. are garbled Unicode). Simply replacing German words may leave surrounding characters intact.

**How to avoid:** When translating German log messages, rewrite the entire log line rather than just translating words. Drop the emoji/box-drawing characters entirely in favor of plain ASCII — this resolves the encoding artifact problem at the same time.

**Warning signs:** Garbled characters (`â€"`, `ðŸ"¥`) appearing in translated log output.

### Pitfall 5: .gitignore doesn't retroactively untrack already-committed files

**What goes wrong:** Adding `ai_engine/saved_models/` to .gitignore doesn't remove already-tracked `.pkl` files from git history.

**Why it happens:** .gitignore only ignores untracked files.

**How to avoid:** If `.pkl` files are already committed, run `git rm --cached ai_engine/saved_models/*.pkl` before or alongside the .gitignore update. This is part of CODE-05 scope.

**Warning signs:** `git status` still shows `ai_engine/saved_models/*.pkl` as tracked after adding to .gitignore.

### Pitfall 6: Test baseline confusion

**What goes wrong:** Treating the 7 pre-existing test failures as something CODE-06 requires fixing. CODE-06 says "all EXISTING tests pass" — but 7 tests already fail before any refactoring. Spending time on pre-existing failures is out of scope.

**Why it happens:** Natural tendency to want a clean test run.

**How to avoid:** Document the pre-refactor baseline explicitly (171 pass, 7 fail, 8 collection errors) and define CODE-06 success as "171 still pass, 7 still fail, 8 collection errors unchanged." The refactoring must not INTRODUCE new failures.

---

## Code Examples

### Module decomposition for main.py — minimal approach

The simplest approach that satisfies CODE-01 without breaking existing imports:

```python
# trading/trading_loop.py
"""Trading loop and signal execution logic."""
from __future__ import annotations
from typing import TYPE_CHECKING
import asyncio
import logging

if TYPE_CHECKING:
    from main import TradingSystem

logger = logging.getLogger(__name__)


class TradingLoopMixin:
    """Mixin providing trading loop methods for TradingSystem."""

    async def _trading_loop(self: "TradingSystem") -> None:
        """Main trading loop — runs every N seconds."""
        # ... extracted from main.py verbatim

    async def _trading_tick(self: "TradingSystem") -> None:
        """Single iteration of the trading loop."""
        # ... extracted from main.py verbatim
```

```python
# main.py — after refactor
from trading.lifecycle import LifecycleMixin
from trading.trading_loop import TradingLoopMixin
from trading.signal_generator import SignalGeneratorMixin
from trading.monitors import MonitorMixin


class TradingSystem(LifecycleMixin, TradingLoopMixin, SignalGeneratorMixin, MonitorMixin):
    """Main trading system orchestrator."""

    def __init__(self, settings: Settings) -> None:
        # ... init code stays here (shared state for all mixins)
```

### Trade filter extraction for trainer.py

```python
# ai_engine/training/trade_filter.py
"""Trade filter tuning — confidence/margin gate optimization."""
import numpy as np
from typing import Any, Dict


def probs_to_trade_signals(
    y_probs: np.ndarray,
    min_confidence: float,
    min_margin: float,
) -> np.ndarray:
    """Convert class probabilities [SELL, HOLD, BUY] to signal labels [-1, 0, 1]."""
    # ... extracted from ModelTrainer._probs_to_trade_signals


def trade_metrics_rank(
    metrics: Dict[str, Any],
    *,
    min_trades: int,
) -> tuple[float, float, float, float, float]:
    """Ranking key for trade filter tuning (higher is better)."""
    # ... extracted from ModelTrainer._trade_metrics_rank
```

### .gitignore additions

```gitignore
# Virtual environment
.venv/
venv/

# ML model artifacts
ai_engine/saved_models/
*.pkl
*.h5

# Data files
data/

# Process locks
*.lock
```

---

## State of the Art

| Old Approach | Current Approach | Impact |
|--------------|------------------|--------|
| Lazy imports everywhere | Top-level imports + TYPE_CHECKING guards for circular cases | Faster startup error detection, clearer dependencies |
| Monolithic god-class | Mixin composition or delegated sub-modules | Testability, single-responsibility |
| `import os` inside method | Stdlib imports at module top | No performance impact, better readability |

---

## Open Questions

1. **Mixin vs. composition for main.py split**
   - What we know: Both approaches make `TradingSystem` importable from `main.py`
   - What's unclear: The planner must choose — mixins are simpler (no `__init__` threading), composition is more explicit
   - Recommendation: Use mixins for Phase 1 (simpler, less risk, same result). Refactor to composition in a later phase if needed.

2. **trainer.py split target: 2 files or 3 files?**
   - What we know: `trainer.py` at 627 lines needs to drop below 300. Extracting `trade_filter.py` alone (~90 lines) leaves `trainer.py` at ~537 lines. Extracting the `train_all` pipeline body into `pipeline.py` is needed.
   - What's unclear: Whether to create `pipeline.py` as a standalone module or as a `TrainingPipeline` class
   - Recommendation: Extract `train_all` body into a `TrainingPipeline` class in `pipeline.py`. `ModelTrainer.train_all` becomes a thin wrapper that instantiates and calls it. Clean class boundary, easy to test.

3. **Should pre-existing test failures be fixed in Phase 1?**
   - What we know: 7 tests fail now for unrelated reasons (ATR column name change in indicators, kill switch retry behavior change)
   - What's unclear: Whether fixing them is in scope
   - Recommendation: Out of scope for Phase 1. Document the baseline (171 pass), and define CODE-06 as "no regression in the 171 passing tests." File a note in the plan for Phase 2+ to address them.

---

## Sources

### Primary (HIGH confidence)
- Direct source file reading: `main.py` (all 824 lines), `ai_engine/training/trainer.py` (all 627 lines)
- Test suite execution: `pytest tests/` — actual pass/fail counts confirmed
- File system inspection: `.gitignore`, `pyproject.toml`, `tests/` directory

### Secondary (MEDIUM confidence)
- `api/dependencies.py` — confirmed TYPE_CHECKING import of TradingSystem
- `tests/test_lifecycle.py` — confirmed `from main import TradingSystem` pattern
- Module line counts: all `ai_engine/training/*.py` files measured

---

## Metadata

**Confidence breakdown:**
- Current code structure: HIGH — read directly from source files
- Lazy import locations: HIGH — verified with grep
- Test baseline: HIGH — ran pytest, counted actual results
- German content scope: HIGH — grep confirmed 17 files
- .gitignore gaps: HIGH — compared current .gitignore against filesystem
- Refactoring approach (mixin vs composition): MEDIUM — either works, trade-offs are judgment calls

**Research date:** 2026-03-03
**Valid until:** 2026-04-03 (stable codebase, no fast-moving dependencies)
