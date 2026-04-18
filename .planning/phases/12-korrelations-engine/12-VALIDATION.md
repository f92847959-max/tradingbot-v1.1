---
phase: 12
slug: korrelations-engine
status: draft
nyquist_compliant: false
wave_0_complete: false
created: 2026-04-18
---

# Phase 12 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest (already in use, 303 tests collected) |
| **Config file** | pytest.ini (or pyproject.toml) |
| **Quick run command** | `pytest tests/test_correlation_features.py tests/test_correlation_calculator.py tests/test_asset_fetcher.py -x -q` |
| **Full suite command** | `pytest tests/ -x -q --ignore=tests/test_order_lifecycle.py --ignore=tests/test_order_lock.py --ignore=tests/test_training_data_source.py` |
| **Estimated runtime** | ~30 seconds |

---

## Sampling Rate

- **After every task commit:** Run `pytest tests/test_correlation_features.py tests/test_correlation_calculator.py tests/test_asset_fetcher.py -x -q`
- **After every plan wave:** Run full suite (see above)
- **Before `/gsd:verify-work`:** Full suite must be green
- **Max feedback latency:** 30 seconds

---

## Per-Task Verification Map

| Task ID | Plan | Wave | Requirement | Test Type | Automated Command | File Exists | Status |
|---------|------|------|-------------|-----------|-------------------|-------------|--------|
| 12-01-01 | 01 | 1 | CORR-01 | unit | `pytest tests/test_asset_fetcher.py -x -q` | ❌ W0 | ⬜ pending |
| 12-01-02 | 01 | 1 | CORR-01 | unit | `pytest tests/test_asset_fetcher.py::test_cache_ttl -x -q` | ❌ W0 | ⬜ pending |
| 12-02-01 | 02 | 2 | CORR-02 | unit | `pytest tests/test_correlation_calculator.py::test_rolling_corr -x -q` | ❌ W0 | ⬜ pending |
| 12-02-02 | 02 | 2 | CORR-02 | unit | `pytest tests/test_correlation_calculator.py::test_insufficient_data -x -q` | ❌ W0 | ⬜ pending |
| 12-02-03 | 02 | 2 | CORR-03 | unit | `pytest tests/test_correlation_calculator.py::test_regime_detection -x -q` | ❌ W0 | ⬜ pending |
| 12-02-04 | 02 | 2 | CORR-03 | unit | `pytest tests/test_correlation_calculator.py::test_divergence_score -x -q` | ❌ W0 | ⬜ pending |
| 12-03-01 | 03 | 3 | CORR-04 | unit | `pytest tests/test_correlation_features.py::test_feature_names -x -q` | ❌ W0 | ⬜ pending |
| 12-03-02 | 03 | 3 | CORR-04 | unit | `pytest tests/test_correlation_features.py::test_none_snapshot -x -q` | ❌ W0 | ⬜ pending |
| 12-03-03 | 03 | 3 | CORR-04 | unit | `pytest tests/test_correlation_features.py::test_feature_engineer_group -x -q` | ❌ W0 | ⬜ pending |
| 12-03-04 | 03 | 3 | CORR-04 | unit | `pytest tests/test_correlation_features.py::test_no_nan -x -q` | ❌ W0 | ⬜ pending |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

---

## Wave 0 Requirements

- [ ] `tests/test_asset_fetcher.py` — stubs for CORR-01 (mock yfinance, TTL cache)
- [ ] `tests/test_correlation_calculator.py` — stubs for CORR-02, CORR-03 (rolling corr, regime, divergence)
- [ ] `tests/test_correlation_features.py` — stubs for CORR-04 (feature names, graceful degradation, no-NaN)
- [ ] `tests/conftest.py` — extend with correlation_snapshot fixture if needed

---

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| Live yfinance fetch returns realistic data for DXY/US10Y/Silber/VIX/SP500 | CORR-01 | External network + market-hours dependent | Run `python -m scripts.fetch_correlations_once` during US market hours, inspect printed DataFrame |
| Correlation-regime reporting in logs (breakdown alert) | CORR-03 | Requires live market stress to reproduce | Monitor logs over a trading week; breakdown z-score > 2.0 should emit WARN |

---

## Validation Sign-Off

- [ ] All tasks have `<automated>` verify or Wave 0 dependencies
- [ ] Sampling continuity: no 3 consecutive tasks without automated verify
- [ ] Wave 0 covers all MISSING references
- [ ] No watch-mode flags
- [ ] Feedback latency < 30s
- [ ] `nyquist_compliant: true` set in frontmatter

**Approval:** pending
