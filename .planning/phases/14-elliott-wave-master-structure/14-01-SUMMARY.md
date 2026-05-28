---
phase: 14-elliott-wave-master-structure
plan: 01
subsystem: ai_engine.elliott_wave
tags: [elliott-wave, pattern-detection, technical-analysis, scipy, rules-engine]
requirements: [EWT-01]
dependency_graph:
  requires:
    - scipy.signal.find_peaks
    - pandas (rolling SMA)
    - numpy
  provides:
    - ai_engine.elliott_wave.models (WavePoint, Wave, WavePattern, ExtremumType, PatternType)
    - ai_engine.elliott_wave.detector (find_extrema, calculate_ewo, WaveDetector)
    - ai_engine.elliott_wave.rules (BaseRule, ImpulseRule, ZigzagRule, RuleEngine)
  affects:
    - Wave 2 (14-02): Fibonacci scoring will consume WavePattern + valid candidates
    - Wave 3 (14-03): feature engineering will read WaveDetector output
tech_stack:
  added: []
  patterns:
    - Rule-based pattern validation (BaseRule -> Concrete rules)
    - ATR-aware prominence filtering for extrema detection
    - Same-type alternation enforcement to canonicalise swing sequences
key_files:
  created:
    - ai_engine/elliott_wave/__init__.py
    - ai_engine/elliott_wave/models.py
    - ai_engine/elliott_wave/detector.py
    - ai_engine/elliott_wave/rules.py
    - tests/test_elliott_wave.py
  modified: []
decisions:
  - "[Phase 14-01]: pandas_ta has no ewo helper -> EWO implemented manually as SMA(fast=5) - SMA(slow=35) on close via pandas rolling"
  - "[Phase 14-01]: WavePattern surface kept minimal (pattern_type, points, is_valid, violations, direction); Fibonacci scoring deferred to Wave 2"
  - "[Phase 14-01]: WaveDetector enforces strict peak/valley alternation by collapsing adjacent same-type extrema (keeps higher peak / lower valley)"
  - "[Phase 14-01]: Input validation hard-caps prices at MAX_INPUT_LENGTH=100k and rejects NaNs (T-14-01, T-14-02 mitigations)"
metrics:
  duration_seconds: 276
  duration_human: "~4m36s"
  task_count: 3
  file_count_created: 5
  file_count_modified: 0
  test_count: 35
tests:
  command: "python -m pytest tests/test_elliott_wave.py -v"
  result: "35 passed in 1.47s"
completed: "2026-05-28T10:55:11Z"
---

# Phase 14 Plan 01: Elliott Wave Detection Core Summary

Built the structural foundation of the Elliott Wave engine: extrema detection via `scipy.signal.find_peaks`, a manually-implemented Elliott Wave Oscillator (EWO), and a rule engine validating Impulse (1-5) and Zigzag (A-B-C) patterns.

**One-liner:** Rule-based EWT detection core using `scipy.signal.find_peaks` for extrema, SMA-difference EWO, and a `BaseRule`-derived engine enforcing Elliott's three impulse rules (W2 retracement <100%, W3 not shortest, W4 no W1 overlap) plus Zigzag B/C constraints — covered by 35 passing unit tests.

## What Changed

### Created

- `ai_engine/elliott_wave/__init__.py` — package surface exporting the model types.
- `ai_engine/elliott_wave/models.py` — `WavePoint`, `Wave`, `WavePattern` dataclasses plus `ExtremumType` and `PatternType` enums. `WavePattern.waves` derives labelled wave segments from consecutive points.
- `ai_engine/elliott_wave/detector.py` — extrema detection and oscillator pipeline:
  - `find_extrema(prices, atr, distance, prominence_factor, timestamps)` runs `scipy.signal.find_peaks` on the price series and its inverse, returning a chronologically ordered list of `WavePoint`s. Inputs are validated (NaN, type, length cap `MAX_INPUT_LENGTH=100_000`).
  - `calculate_ewo(df, fast=5, slow=35)` computes the Elliott Wave Oscillator manually because `pandas_ta` ships no `ewo` helper. Output is index-aligned with the input frame.
  - `WaveDetector` wraps the two helpers, optionally filters extrema by EWO strength, and enforces strict peak/valley alternation by collapsing adjacent same-type extrema (keeping the higher peak / lower valley).
- `ai_engine/elliott_wave/rules.py` — rule engine:
  - `BaseRule` abstract base with `validate(points)` returning a `WavePattern`.
  - `ImpulseRule` (6 points / 5 waves) enforces Elliott's three core rules and handles bullish + bearish orientations symmetrically.
  - `ZigzagRule` (4 points / 3 waves) enforces B-retracement and C-extension constraints.
  - `RuleEngine` slides over a sorted extrema list and emits all valid candidates; `validate_one()` checks an explicit candidate against a named pattern type; `include_invalid=True` returns diagnostics for unit tests.
- `tests/test_elliott_wave.py` — 35 unit tests covering find_extrema (sine wave, ATR prominence filtering, validation errors), calculate_ewo (alignment, NaN window, fast<slow contract, sign), ImpulseRule (valid bullish/bearish, Rule 1/2/3 violations, alternation, point-count), ZigzagRule (valid bullish/bearish, Rule 1/2 violations), RuleEngine (detection, validate_one, include_invalid, default rule registration), and a synthetic gold-like end-to-end pipeline.

### Modified

- None.

## Verification

```
$ python -m pytest tests/test_elliott_wave.py -v
35 passed in 1.47s
```

Plan-level success criteria checked against the spec:

- [x] Extrema detection correctly identifies major swings (`test_sine_wave_finds_alternating_extrema`, `test_detector_finds_5_anchor_swings`).
- [x] EWO is calculated and visible in dataframes (`test_returns_index_aligned_series`, `test_uptrending_series_yields_positive_ewo`).
- [x] Core rules (1-5, ABC) are correctly applied to extrema sequences (full `TestImpulseRule`, `TestZigzagRule`, `TestRuleEngine` suites).

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 3 - Blocking] Created missing `ai_engine/elliott_wave/__init__.py`**
- **Found during:** Task 1
- **Issue:** Plan context (`14-CONTEXT.md`) stated the package "already exists as a placeholder", but the directory was absent on disk. Without a package, the imports specified in the plan (`from ai_engine.elliott_wave.detector import ...`) would not resolve.
- **Fix:** Created the package with an `__init__.py` re-exporting model symbols.
- **Files added:** `ai_engine/elliott_wave/__init__.py`
- **Commit:** `eb5f4e1`

**2. [Rule 1 - Bug in plan spec] EWO via manual SMA difference, not `pandas_ta.ewo`**
- **Found during:** Task 1 pre-flight check
- **Issue:** The plan's verify block calls `pandas_ta.ewo` / `df.ta.ewo`, but the installed `pandas_ta` (0.4.71b0) does not expose an `ewo` accessor or function (`'ewo' in dir(ta)` is `False`).
- **Fix:** Implemented EWO directly as `SMA(close, fast=5) - SMA(close, slow=35)` using pandas rolling — Bill Williams' canonical definition. The verify command was adapted to call our `calculate_ewo` helper, which is what the plan's verify snippet imports and uses (`from ai_engine.elliott_wave.detector import calculate_ewo`).
- **Files affected:** `ai_engine/elliott_wave/detector.py`
- **Commit:** `eb5f4e1`

**3. [Rule 2 - Threat-model mitigations] Input validation hard-caps and NaN guards**
- **Found during:** Task 1
- **Issue:** Plan threat model (T-14-01, T-14-02) calls for input validation and DoS protection on `find_peaks`, but the plan's task action does not explicitly enumerate the checks.
- **Fix:** Added explicit type/NaN/length validation in `_validate_price_series`, ATR scalar reduction guard, and a `MAX_INPUT_LENGTH=100_000` hard cap. `WaveDetector.detect_swings` also rejects NaN columns and missing columns up-front.
- **Files affected:** `ai_engine/elliott_wave/detector.py`
- **Commit:** `eb5f4e1`

### Plan Adjustments

- **Task 3 `tdd="true"` flag treated as "comprehensive tests first run after implementation".** Strict RED-before-GREEN was not feasible because Tasks 1 and 2 ship the implementation by design. Tests were authored after the implementation was committed, ran green on first execution, and were committed under a `test(...)` prefix. No synthetic RED phase was fabricated.
- **SUMMARY output path:** Plan's `<output>` block specifies a stale directory `plan 14 eliotwafe`. The active phase directory is `14-elliott-wave-master-structure/`, which is where this summary lives (matching the orchestrator's success criteria).

## Commits

| Task | Type | Commit  | Description |
| ---- | ---- | ------- | --- |
| 1    | feat | `eb5f4e1` | Models, find_extrema, calculate_ewo, WaveDetector with validation guards |
| 2    | feat | `00a8259` | BaseRule, ImpulseRule (3 core rules), ZigzagRule (B/C constraints), RuleEngine |
| 3    | test | `15d433b` | 35 unit tests covering detector + rules + end-to-end pipeline |

## TDD Gate Compliance

The plan-level frontmatter is `type: execute` (not `tdd`), so global RED/GREEN/REFACTOR gate enforcement does not apply. Task 3's `tdd="true"` attribute was treated as "comprehensive test addition" because Tasks 1 and 2 explicitly require the implementation up-front. Test commit (`15d433b`) lands after feature commits (`eb5f4e1`, `00a8259`); all 35 tests pass on first run.

## Authentication Gates

None — fully autonomous Python implementation.

## Known Stubs

None. All exported symbols have working implementations; the only intentionally-deferred surface is the `PatternType` enum members `FLAT`, `TRIANGLE`, `DIAGONAL`, `COMPLEX`, which Wave 2 will populate with concrete rule classes. These are enum placeholders, not runtime stubs.

## Threat Flags

None. The implementation introduces no new network endpoints, auth paths, file access patterns, or schema changes. Input validation already covers the trust boundary described in the plan's threat model.

## Self-Check: PASSED

Files verified to exist on disk:
- `ai_engine/elliott_wave/__init__.py` — FOUND
- `ai_engine/elliott_wave/models.py` — FOUND
- `ai_engine/elliott_wave/detector.py` — FOUND
- `ai_engine/elliott_wave/rules.py` — FOUND
- `tests/test_elliott_wave.py` — FOUND

Commits verified in `git log`:
- `eb5f4e1` — FOUND (Task 1: models + detector)
- `00a8259` — FOUND (Task 2: rules engine)
- `15d433b` — FOUND (Task 3: tests)

Test suite: `python -m pytest tests/test_elliott_wave.py` → **35 passed in 1.47s**.

Plan success criteria: all three checked items pass with cited tests.
