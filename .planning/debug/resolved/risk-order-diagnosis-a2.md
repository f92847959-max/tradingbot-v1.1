---
status: resolved
trigger: "Diagnosis-only debug task for repo `C:\\Users\\fuhhe\\OneDrive\\Desktop\\ai\\ai\\ai trading gold`.\n\nYou are one of 3 parallel debug agents. Do not modify code. Do not apply fixes. Do not install dependencies. Read only what you need.\n\nOwnership and scope:\n- Primary code paths: `risk/`, `exit_engine/`, `order_management/`, `trading/`, `portfolio/`\n- Primary tests: `tests/test_risk.py`, `tests/test_risk_manager.py`, `tests/test_risk_integration.py`, `tests/test_risk_integration_advanced.py`, `tests/test_exit_engine_core.py`, `tests/test_exit_engine_management.py`, `tests/test_order_lifecycle.py`, `tests/test_order_lock.py`, `tests/test_portfolio_heat.py`, `tests/test_position_sizer_advanced.py`, `tests/test_trailing_stop.py`, `tests/test_volatility_sizer.py`, `tests/test_e2e_trading.py`, `tests/test_confirmation.py`, `tests/test_lifecycle.py`\n- Focus on risk guards, order lifecycle invariants, exit logic, sizing, and trade execution protections.\n\nTask:\n1. Inspect relevant tests and code paths.\n2. Identify likely logic bugs or behavior regressions.\n3. Distinguish confirmed evidence from speculation.\n4. Return a concise structured report with:\n   - Commands you would run or did run if available in your context\n   - Top 1-3 findings only\n   - For each finding: severity, status confirmed/likely/possible, suspected flaw, evidence, exact file:line references, why it is a logic bug, next verification\n   - Any blockers\n\nDo not patch files. Do not suggest broad refactors. Keep the answer evidence-driven."
created: 2026-04-23T00:00:00+02:00
updated: 2026-04-23T00:20:00+02:00
---

## Current Focus

hypothesis: Confirmed static contradictions exist in the scoped risk/order paths where the code validates one safety envelope but executes another, or where lifecycle persistence guarantees diverge between similar close paths.
test: Trace each candidate from tests/config surface into the exact implementation branch that executes it in production.
expecting: Exact code-level mismatches with safety or lifecycle invariants, not speculative style issues.
next_action: Return the top confirmed findings with file:line references and concrete follow-up verification steps.

## Symptoms

expected: Risk guards, order lifecycle invariants, exit logic, sizing, and trade execution protections should behave as asserted by the scoped tests and should not allow unsafe or inconsistent state transitions.
actual: Unknown; the task is to diagnose likely logic bugs or regressions within the owned paths without modifying code.
errors: None supplied.
reproduction: Inspect the listed tests against current implementations in risk/, exit_engine/, order_management/, trading/, and portfolio/.
started: Not specified.

## Eliminated

## Evidence

- timestamp: 2026-04-23T00:05:00+02:00
  checked: .planning/debug/knowledge-base.md
  found: The repository has no debug knowledge base file yet.
  implication: No prior known-pattern match is available; investigation must proceed from direct test/code evidence.

- timestamp: 2026-04-23T00:05:00+02:00
  checked: Scoped tests and owned directories
  found: All listed tests exist, and the owned directories risk/, exit_engine/, order_management/, trading/, and portfolio/ are present with focused modules for guards, sizing, exit management, and lifecycle handling.
  implication: The requested diagnosis can be grounded directly in the scoped tests and implementations without broad repo exploration.

- timestamp: 2026-04-23T00:20:00+02:00
  checked: risk/risk_manager.py, risk/position_sizer.py, risk/position_sizing.py, trading/trading_loop.py, tests/test_risk_integration_advanced.py
  found: RiskManager.approve_trade performs margin, leverage, and portfolio-heat validation using a fixed-fractional lot size before any advanced sizing is applied, then later overwrites lot_size with AdvancedPositionSizer output and returns that larger size to the trading loop for live order execution.
  implication: When Kelly sizing is active, the executed lot can exceed the validated margin/leverage/heat envelope, so trades may be approved under one risk profile and placed under another.

- timestamp: 2026-04-23T00:20:00+02:00
  checked: order_management/order_manager.py
  found: close_trade() retries DB close persistence and queues failed broker-closed trades for reconciliation, but close_all() only logs DB failures and still removes trailing/position tracking unconditionally.
  implication: A kill-switch bulk close can leave DB rows stale while the in-memory monitor forgets the positions, breaking order lifecycle consistency after an emergency close.

- timestamp: 2026-04-23T00:20:00+02:00
  checked: risk/pre_trade_check.py, shared/utils.py, risk/risk_manager.py
  found: RiskManager passes trading_start/trading_end into PreTradeChecker, and PreTradeChecker stores them, but _check_trading_hours ignores those fields and always delegates to shared.utils.is_trading_hours(), which hard-codes the global session window.
  implication: Custom trading-hour risk guard settings are silently ignored, so the bot can trade outside the configured local guard window.

## Resolution

root_cause: "Three confirmed logic defects were found in the owned paths: advanced Kelly sizing bypasses the lot size that margin/leverage/heat checks validated; kill-switch bulk close forgets positions even if DB close persistence fails; and configurable trading-hour guard settings are ignored because the checker uses a hard-coded global session helper."
fix: "All three defects resolved in code before 2026-04-25 re-verification."
verification: |
  Re-verified 2026-04-25 against live code:
  - Kelly vs envelope: risk_manager.py:382-424 now computes final Kelly lot BEFORE validation.
  - Kill-switch close_all: order_manager.py:521-540 queues orphan_close and continues (skips tracking removal on DB failure).
  - Trading hours: pre_trade_check.py:126-148 now uses self.trading_start/end (configured window honored).
files_changed: []
