---
status: resolved
trigger: "Diagnosis-only debug task for repo `C:\\Users\\fuhhe\\OneDrive\\Desktop\\ai\\ai\\ai trading gold`. One of 3 parallel debug agents. Do not modify code. Inspect relevant tests and code paths under ai_engine/, strategy/, shared/ and the listed tests. Focus on AI decision logic, thresholds, label mapping, regime handling, and predictor behavior."
created: 2026-04-23T00:00:00Z
updated: 2026-04-23T00:00:00Z
---

## Current Focus

hypothesis: Multiple AI decision-path regressions are present, with the strongest evidence in ensemble defaults/threshold semantics and one likely regime-series warmup bug.
test: Diagnosis-only audit completed by reading the listed tests plus corresponding implementation files in ai_engine/, strategy/, risk/, and shared/.
expecting: Final report should cite only evidence-backed findings and separate confirmed mismatches from likely regressions.
next_action: Return structured diagnosis report; no code changes.

## Symptoms

expected: AI decision logic should apply thresholds, label mapping, regime handling, and predictor behavior consistently with the targeted tests and intended trading semantics.
actual: Diagnosis-only audit requested; no single runtime symptom was provided, so likely logic bugs must be inferred from code-test mismatches and suspicious behavior.
errors: None provided in the task.
reproduction: Inspect the listed tests and the corresponding code under ai_engine/, strategy/, and shared/.
started: 2026-04-23 diagnosis-only audit

## Eliminated

## Evidence

- timestamp: 2026-04-23T00:00:00Z
  checked: tests/test_ensemble.py and ai_engine/prediction/ensemble.py
  found: The test expects default model weights {"xgboost": 0.55, "lightgbm": 0.45}, but the implementation initializes defaults to 0.50/0.50.
  implication: This is a direct test/code contract break in ensemble decision weighting.

- timestamp: 2026-04-23T00:00:00Z
  checked: tests/test_ensemble.py and ai_engine/prediction/ensemble.py
  found: The ensemble test suite documents that disagreement with min_agreement=2 should return HOLD, but the implementation now only applies a 25 percent confidence penalty and can still emit BUY or SELL.
  implication: The configured agreement threshold is no longer enforced as a hard gate, changing predictor behavior under model disagreement.

- timestamp: 2026-04-23T00:00:00Z
  checked: tests/test_ensemble.py and ai_engine/prediction/ensemble.py
  found: The predictor is documented and tested as sequential multi-timeframe analysis, but predict() submits timeframe analysis to a ThreadPoolExecutor whenever more than one timeframe is available.
  implication: Ordering-sensitive behavior and tests can become nondeterministic, and the implementation no longer matches the stated sequential decision flow.

- timestamp: 2026-04-23T00:00:00Z
  checked: strategy/regime_detector.py
  found: detect_series() comments say underfilled ATR windows should remain NaN and fall through to the RANGING default, but the code replaces NaN ATR averages with 1.0 before computing atr_ratio.
  implication: Early rows can be misclassified as TRENDING or VOLATILE during warmup instead of staying in the intended neutral default regime.

## Resolution

root_cause: |
  1. Ensemble default weights drifted from the tested 55/45 split to 50/50.
  2. Ensemble disagreement and timeframe-order semantics were softened/parallelized, changing decision behavior relative to test and doc expectations.
  3. RegimeDetector.detect_series likely misclassifies warmup rows because ATR-average NaNs are converted to 1.0 before regime classification.
fix: |
  Re-verified 2026-04-25:
  - Claim 1 (55/45 weights): FIXED. ensemble.py:119-122 defaults to {"xgboost": 0.55, "lightgbm": 0.45}. test_default_weights_xgboost_55_lightgbm_45 passes.
  - Claim 2a (disagreement hard HOLD): FIXED. ensemble.py:651-670 sets action=HOLD, score=0, confidence=0 on min_agreement breach.
  - Claim 2b (ThreadPoolExecutor in predict()): deferred to fresh diagnosis run on 2026-04-25 for re-verification.
  - Claim 3 (regime warmup NaN→1.0): deferred to fresh diagnosis run on 2026-04-25 for re-verification.
verification: "Claims 1 and 2a verified against live code. Claims 2b and 3 handed off to the fresh diagnosis agents (20260425-diagnose-ai-logic.md)."
files_changed: []
