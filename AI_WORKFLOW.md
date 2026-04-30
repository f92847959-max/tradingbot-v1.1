# AI Workflow

This file is the contract for any AI assistant (Claude, Cursor, Aider, Codex, ChatGPT, etc.) working in this repository. Read it first — it overrides general defaults the assistant might bring in from elsewhere.

---

## 1 · Project Context

This is an **automated trading bot** for the Capital.com broker, focused on gold (XAU). It is experimental, **not** a production trading product.

Core stack:
- **Python 3.12** (CI pins this version)
- **FastAPI** for the local control API (`api/`, `goldbot-control-app/backend/`)
- **SQLAlchemy 2.x async** for persistence (`database/`)
- **pytest** + `pytest-asyncio` (mode = auto) for tests
- **ruff** for linting (line length 100, target py311)
- **LightGBM / XGBoost / scikit-learn** for the AI engine (`ai_engine/`)

The repo also contains a **React/Vite control app** under `goldbot-control-app/` — it has its own toolchain and is out of scope for most backend changes.

---

## 2 · Critical Safety Rules — NEVER violate these

These rules exist because this is **trading code that can move real money**. A bug here is not just a failed test, it is a financial loss.

1. **Never enable live trading by default.** Defaults in any new config, fixture, or test must be `CAPITAL_DEMO=true` and `TRADING_MODE=semi_auto`.
2. **Never relax risk caps without explicit user approval.** The defaults in `.env.example` (`MAX_RISK_PER_TRADE_PCT=0.5`, `MAX_DAILY_LOSS_PCT=2.0`, `MAX_OPEN_POSITIONS=1`, `MAX_TRADES_PER_DAY=5`) are not arbitrary — do not raise them.
3. **Never commit secrets.** Read `.gitignore` and `SECURITY.md`. Real credentials live in `C:\Users\<you>\secrets\ai-trading-gold\.env`, not in the repo.
4. **Never disable `API_AUTH_ENABLED` or bind APIs to `0.0.0.0` without an explicit user request.** Default is `127.0.0.1` for a reason.
5. **Never bypass the kill switch or risk manager.** If a code path needs to skip them, that is a design decision and requires user discussion first.
6. **Never delete trade logs, the database, or model artifacts to "fix" a test.** Investigate the root cause.

If you are about to do any of the above because "the test/build needs it", stop and ask the user.

---

## 3 · Code Architecture

The codebase follows a pragmatic domain-oriented layout. New code goes into the directory whose responsibility it matches.

| Directory | Owns |
|---|---|
| `ai_engine/` | Feature engineering, model training, inference, walk-forward eval |
| `api/` | FastAPI routes for the local control endpoint |
| `calendar/` | Economic event fetching and filtering |
| `config/` | Pydantic settings, env loading |
| `correlation/` | Cross-asset correlation engine |
| `dashboard/` | Streamlit dashboard |
| `database/` | SQLAlchemy models, repositories, async connection |
| `exit_engine/` | Partial-close, exit-AI runtime |
| `market_data/` | Broker client, historical/live candles, data provider |
| `monitoring/` | Health checks, metrics |
| `notifications/` | Twilio, confirmation handlers |
| `order_management/` | Order executor, position monitor, trailing stop, order manager (orchestrator) |
| `portfolio/` | Position tracking |
| `risk/` | Risk manager, position sizing, kill switch |
| `sentiment/` | News sentiment pipeline (placeholder tests, may fail in CI by design) |
| `shared/` | Cross-cutting constants and types |
| `strategy/` | Signal generation, regime detection, trade scoring |
| `tests/` | All pytest tests |
| `trading/` | Lifecycle (startup/shutdown), orchestration |

**Rules:**
- Keep modules under ~500 lines. If a file gets too big, split by responsibility, not by line count.
- Public functions and class methods get type hints. `from __future__ import annotations` is used everywhere.
- Cross-module imports go through the package root (`from database.connection import get_session`), not relative `..` imports.
- Heavy / DB-side imports may stay top-level **only if** patchability is needed (see § 5 "Common Pitfalls"). Otherwise, inline imports inside functions are fine to defer cost or break import cycles.

---

## 4 · Code Style

- **Linter:** `ruff` with the config in `pyproject.toml`. Run `ruff check .` before committing.
- **Line length:** 100.
- **Imports:** stdlib → third-party → first-party, separated by blank lines. ruff handles ordering.
- **Async:** prefer `async def` for any I/O-bound code (broker calls, DB, HTTP). Pure CPU work stays sync.
- **Logging:** `logger = logging.getLogger(__name__)` per module. Use `logger.info`, `.warning`, `.error`, `.critical`. Do **not** print.
- **Errors:** raise specific exceptions (`BrokerError`, `RuntimeError("…")`, `ValueError(...)`), not bare `Exception`. Catch what you can recover from, let everything else bubble.
- **Comments:** explain *why*, not *what*. The code already says what.
- **Docstrings:** one-line summary for everything public; full docstrings only when the contract is non-obvious.

---

## 5 · Test Workflow

CI runs the equivalent of:

```bash
pip install -r requirements.lock
python -m pytest tests/ --ignore=tests/sentiment -p no:cacheprovider --tb=short -q
```

`tests/sentiment/` is allowed to fail in CI (placeholder).

### Running tests locally

```bash
# Full suite (skip sentiment)
python -m pytest tests/ --ignore=tests/sentiment -q

# A single file
python -m pytest tests/test_lifecycle.py -q

# A single test
python -m pytest tests/test_lifecycle.py::TestHealthCheck::test_health_check_passes_all -q
```

### Mock pattern — read this carefully

Tests use `unittest.mock.patch("<module>.<name>")`. For the patch to work, **`<name>` must be an attribute of `<module>`** at the time the patch enters.

Lazy imports inside function bodies are **invisible to `patch`**:

```python
# ❌ BAD — test cannot patch trading.lifecycle.init_db
async def _health_check(self):
    from database.connection import init_db   # local name, not a module attribute
    await init_db()
```

```python
# ✅ GOOD — module-level import, patchable
from database.connection import init_db

async def _health_check(self):
    await init_db()
```

If you add a function that the tests want to mock, **import its name at the module level**. If you must keep the import lazy (e.g., to break a real circular dependency), document it and provide a separate patchable seam.

### Writing new tests

- Place tests under `tests/`, file name `test_<feature>.py`.
- One class per feature area, one method per scenario.
- Use `pytest.mark.asyncio` only when needed — `asyncio_mode = "auto"` already covers most cases.
- For DB-touching tests, mock the session or use the SQLite fallback. Do **not** require a running PostgreSQL.
- For broker-touching tests, mock `CapitalComClient` or its methods. Never hit the real broker.
- Assertions on numeric scores (e.g., `TradeScorer`) must isolate the dimension under test — neutralize other dimensions so a regime swap in one factor doesn't get cancelled by a swing in another.

---

## 6 · Git / PR Workflow

### Branches

- `master` is the default branch. CI runs on every push to `master` and on every PR.
- For non-trivial work, branch off `master`: `git checkout -b feat/<short-name>` or `fix/<short-name>`.
- Keep branches short-lived. Rebase, don't merge `master` back in.

### Commits

- **Conventional Commit prefix** + short summary, then a blank line, then a body that explains *why*.
- Prefixes used in this repo: `feat`, `fix`, `chore`, `docs`, `test`, `refactor`, `perf`, `security`.
- Example:

  ```
  fix(order_manager): hoist get_session import for patchability

  Tests targeting order_management.order_manager.get_session failed
  because the symbol was only bound inside _get_db_dependencies().
  Module-level import keeps existing call sites intact and exposes
  the name for unittest.mock.patch.
  ```

- Subject line under ~70 characters, imperative mood, no trailing period.

### Before you push

1. `ruff check .` — clean
2. `python -m pytest tests/ --ignore=tests/sentiment -q` — green
3. `git status --short` — no `.env`, no logs, no model artifacts, no `data/`
4. `git log --oneline -5` — commit messages make sense

If a pre-commit hook fails, **fix the issue and create a new commit**. Do not amend a commit that may already be pushed, and **never** use `--no-verify` to bypass hooks.

### Pull Requests

- One PR = one logical change.
- Title follows the same Conventional Commit format as the squashed commit.
- Body answers: *what changed, why, how to verify.*
- Don't open a PR with red CI. If CI is red on `master` for unrelated reasons, mention it.
- Security findings go through GitHub Security Advisories (see `SECURITY.md`), not public PRs.

---

## 7 · Common Pitfalls in this Repo

A short list of bugs that have actually happened. Don't reintroduce them.

1. **Lazy imports breaking `mock.patch`** (§ 5). Hoist DB and lifecycle helpers to module scope when the tests target them.
2. **Score tests confounded by regime-aware sub-scores.** When asserting that a regime change shifts one sub-score (e.g., trend ADX), make sure the other regime-dependent sub-scores (e.g., RR) are saturated or constant — otherwise opposite swings cancel out.
3. **Forgetting the `.env.ci` injection in CI.** `config.settings` validates on import; new required settings must have CI-safe defaults or be added to the `.env.ci` heredoc in `.github/workflows/tests.yml`.
4. **Committing files from the `.planning/` workspace.** That folder is intentionally absent from the public branch and is internal-only.
5. **Adding broker calls to test setup.** Always mock the broker client. The real one will rate-limit and may even place an order.

---

## 8 · When Unsure

Ask the user. Especially for:

- Anything that touches money flow, position sizing, or risk
- New external dependencies
- Schema migrations on the trade database
- Changes to CI/CD pipelines
- Rewriting Git history (force pushes, filter-branch, rebase of pushed commits)

Better one extra question than one wrong autonomous action on a trading system.
