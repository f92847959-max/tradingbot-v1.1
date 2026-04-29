---
phase: 13
slug: orderbuch-analyse
status: draft
nyquist_compliant: true
wave_0_complete: false
created: 2026-04-25
---

# Phase 13 - Validation Strategy

> Per-phase validation contract for feedback sampling during execution.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest 8.x |
| **Config file** | `pyproject.toml` |
| **Quick run command** | `python -m pytest tests/test_orderflow_features.py tests/test_orderflow_stream.py -q` |
| **Full suite command** | `python -m pytest tests/test_orderflow_features.py tests/test_orderflow_stream.py tests/test_orderflow_integration.py -q` |
| **Estimated runtime** | ~15 seconds |

---

## Sampling Rate

- **After every task commit:** Run `python -m pytest tests/test_orderflow_features.py tests/test_orderflow_stream.py -q`
- **After every plan wave:** Run `python -m pytest tests/test_orderflow_features.py tests/test_orderflow_stream.py tests/test_orderflow_integration.py -q`
- **Before `$gsd-verify-work`:** Full targeted suite must be green
- **Max feedback latency:** 30 seconds

---

## Per-Task Verification Map

| Task ID | Plan | Wave | Requirement | Threat Ref | Secure Behavior | Test Type | Automated Command | File Exists | Status |
|---------|------|------|-------------|------------|-----------------|-----------|-------------------|-------------|--------|
| 13-01-01 | 01 | 1 | FLOW-01/FLOW-02 | T-13-01 | OHLCV-only order-flow input is processed without broker DOM assumptions | unit | `python -m pytest tests/test_orderflow_features.py::test_calculate_ohlcv_only -q` | no | pending |
| 13-01-02 | 01 | 1 | FLOW-02 | T-13-02 | Delta is signed, bounded, and safe for zero-range candles | unit | `python -m pytest tests/test_orderflow_features.py::test_delta_direction_and_doji_safety -q` | no | pending |
| 13-01-03 | 01 | 1 | FLOW-03 | T-13-03 | Liquidity zones, POC/VAH/VAL, FVG, and absorption use only closed candles | unit | `python -m pytest tests/test_orderflow_features.py::test_liquidity_zone_and_absorption_features -q` | no | pending |
| 13-02-01 | 02 | 2 | FLOW-01 | T-13-04 | L1 quote imbalance is aggregated without leaking credentials or assuming true Level 2 depth | unit | `python -m pytest tests/test_orderflow_stream.py -q` | no | pending |
| 13-02-02 | 02 | 2 | FLOW-01/FLOW-04 | T-13-05 | Missing quote enrichment falls back to neutral `flow_l1_imbalance` | integration | `python -m pytest tests/test_orderflow_stream.py tests/test_orderflow_features.py -q` | no | pending |
| 13-03-01 | 03 | 3 | FLOW-04 | T-13-06 | `FeatureEngineer` exposes `flow_*` features for ML while avoiding duplicate `l1_*`/`l2_*`/`micro_*` features | integration | `python -m pytest tests/test_orderflow_integration.py -q` | no | pending |
| 13-03-02 | 03 | 3 | FLOW-01..FLOW-04 | T-13-07 | End-to-end feature creation is NaN-free and training-compatible | integration | `python -m pytest tests/test_orderflow_features.py tests/test_orderflow_integration.py -q` | no | pending |

*Status: pending / green / red / flaky*

---

## Wave 0 Requirements

- [ ] `tests/test_orderflow_features.py` - RED tests for FLOW-01 through FLOW-03
- [ ] `tests/test_orderflow_stream.py` - RED tests for quote imbalance and candle aggregation
- [ ] `tests/test_orderflow_integration.py` - RED tests for `FeatureEngineer` and ML feature exposure

---

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| Capital.com live quote field presence | FLOW-01 | Requires live broker stream/session | Run a short demo quote-stream capture and verify payload fields include `bid`, `ofr`, and optionally `bidQty`/`ofrQty`; if quantities are absent, confirm neutral fallback remains active. |

---

## Validation Sign-Off

- [x] All tasks have `<automated>` verify or Wave 0 dependencies
- [x] Sampling continuity: no 3 consecutive tasks without automated verify
- [x] Wave 0 covers all missing references
- [x] No watch-mode flags
- [x] Feedback latency < 30s
- [x] `nyquist_compliant: true` set in frontmatter

**Approval:** approved 2026-04-25
