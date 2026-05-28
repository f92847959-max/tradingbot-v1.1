---
phase: 14-elliott-wave-master-structure
plan: 02
subsystem: ai_engine.elliott_wave
tags: [elliott-wave, fibonacci, scoring, advanced-patterns, technical-analysis]
requirements: [EWT-02]
dependency_graph:
  requires:
    - ai_engine.elliott_wave.models (Wave 1: WavePoint, WavePattern, PatternType, ExtremumType)
    - ai_engine.elliott_wave.rules (Wave 1: BaseRule, ImpulseRule, ZigzagRule, RuleEngine)
  provides:
    - ai_engine.elliott_wave.fibonacci (calculate_retracement, calculate_projection, get_wave_targets, STANDARD_*_RATIOS, IDEAL_WAVE_RATIOS)
    - ai_engine.elliott_wave.advanced_rules (DiagonalRule, FlatRule, TriangleRule)
    - ai_engine.elliott_wave.scoring (score_pattern, rank_patterns, get_primary_count)
    - RuleEngine default registration now includes all 5 rule classes
  affects:
    - Wave 3 (14-03): feature engineering will consume scoring.get_primary_count + fibonacci.get_wave_targets to build ML features and MiroFish structural context
tech_stack:
  added: []
  patterns:
    - Hardcoded standard Fibonacci ratio tables sourced from a single module constant (T-14-04 mitigation)
    - Sub-type metadata stamped on valid WavePattern.violations[0] as "sub_type=<name>" to avoid expanding the dataclass shape mid-phase
    - Lazy import in RuleEngine.__post_init__ to register advanced rules without an import cycle
    - Per-wave confluence scoring vs ideal ratios with multi-ideal weighted max; barely-valid floor + per-violation penalty
key_files:
  created:
    - ai_engine/elliott_wave/fibonacci.py
    - ai_engine/elliott_wave/advanced_rules.py
    - ai_engine/elliott_wave/scoring.py
    - tests/test_elliott_wave_advanced.py
  modified:
    - ai_engine/elliott_wave/rules.py (RuleEngine default rule list now includes Diagonal/Flat/Triangle)
    - ai_engine/elliott_wave/__init__.py (docstring updated to describe Wave 2 surface)
    - tests/test_elliott_wave.py (single regression test updated: see Deviations)
decisions:
  - "[Phase 14-02]: Advanced rule classes live in advanced_rules.py rather than extending rules.py — rules.py was at 382 lines and the additional 4 rule families would push it past CLAUDE.md's 500-line hard cap"
  - "[Phase 14-02]: Sub-type tag (contracting/expanding/regular/expanded/running) is encoded as 'sub_type=...' in WavePattern.violations[0] on valid patterns; _structural_violations filters this prefix when computing penalties"
  - "[Phase 14-02]: Fibonacci ratio tables (STANDARD_RETRACEMENT_RATIOS, STANDARD_PROJECTION_RATIOS, IDEAL_WAVE_RATIOS) are module-level immutable tuples/Mappings; score_pattern accepts only the pattern argument so callers cannot inject custom ratios (T-14-04 mitigation)"
  - "[Phase 14-02]: Per-wave confluence score uses weighted max across multiple acceptable ratios (preferred ratio gets weight 1.0, second 0.85, third 0.7); errors beyond 40% of an ideal contribute 0 instead of going negative"
  - "[Phase 14-02]: Tie-break order in rank_patterns is (score desc, pattern_priority desc, input order); priority: Impulse > Diagonal > Zigzag > Flat > Triangle > Complex"
metrics:
  duration_seconds: ~1500
  duration_human: "~25m"
  task_count: 3
  file_count_created: 4
  file_count_modified: 3
  test_count_added: 42
  test_count_total: 77
tests:
  command: "python -m pytest tests/test_elliott_wave.py tests/test_elliott_wave_advanced.py -q"
  result: "77 passed in 1.51s"
completed: "2026-05-28T11:25:00Z"
---

# Phase 14 Plan 02: Fibonacci Projections & Advanced Patterns Summary

Built the Fibonacci confluence and advanced-pattern layer on top of Wave 1's detection core: a pure-math Fibonacci module (retracement/projection/target helpers + standard ratio constants), three new rule classes (Diagonal, Flat, Triangle) that share the BaseRule contract, and a scoring engine that selects a "Primary Count" from competing valid candidates using weighted distance to ideal EWT ratios.

**One-liner:** Fibonacci math (`calculate_retracement`, `calculate_projection`, `get_wave_targets`), three new rule classes (`DiagonalRule` with W4/W1 overlap, `FlatRule` regular/expanded/running classification, `TriangleRule` contracting/expanding ratio bounds), and a confluence scoring engine (`score_pattern`, `rank_patterns`, `get_primary_count`) that ranks competing valid counts against hardcoded `IDEAL_WAVE_RATIOS` — covered by 42 new unit tests with no regression on Wave 1's 35 tests.

## What Changed

### Created

- `ai_engine/elliott_wave/fibonacci.py` (274 lines) — Ratio math and target projection.
  - `calculate_retracement(start, end, ratio)`: price at `ratio` retracement of the move from `start` to `end`.
  - `calculate_projection(w1_start, w1_end, w3_start, ratio)`: target from `w3_start` using `ratio * |w1_end - w1_start|` in W1's direction. The Task 1 verify case `calculate_projection(100, 200, 150, 1.618) == 311.8` passes exactly (Python float exactness preserved).
  - `get_wave_targets(pattern)`: per-`PatternType` dispatch returning a dict like `{"w3_1.618": 311.8, "w2_retracement_0.618": 138.2, ...}`. Defensive: returns `{}` for malformed/unknown patterns.
  - `STANDARD_RETRACEMENT_RATIOS = (0.236, 0.382, 0.5, 0.618, 0.786)`.
  - `STANDARD_PROJECTION_RATIOS = (1.0, 1.272, 1.618, 2.0, 2.618, 4.236)`.
  - `IDEAL_WAVE_RATIOS`: mapping keyed by `(PatternType, wave_label)` to a tuple of acceptable Fibonacci ratios, ordered by preference. Used by the scoring engine.

- `ai_engine/elliott_wave/advanced_rules.py` (411 lines) — Rule classes for the EWT pattern families beyond Impulse/Zigzag.
  - `DiagonalRule` (6 points / 5 waves): requires Wave 4 to overlap Wave 1's territory (the defining feature), enforces strict W1>W3>W5 length monotonicity for contracting diagonals or W1<W3<W5 for expanding. Still enforces "W3 not shortest" and "W2 < 100% retrace of W1". Returns the sub-type (`contracting`/`expanding`/`irregular`) in `violations[0]` on valid patterns.
  - `FlatRule` (4 points / 3 waves): classifies into `regular` (B retracement 90-105% of A), `expanded` (B > 100% A with C > 100% B), or `running` (B > 100% A but C falls short of A's terminus). Enforces alternation and that C continues past B in A's direction.
  - `TriangleRule` (6 points / 5 legs): validates each leg's length ratio vs the previous. Contracting: 0.50-0.95; expanding: 1.05-2.00. Stamps `contracting`/`expanding` sub-type on valid patterns; flags irregular ratios as violations.

- `ai_engine/elliott_wave/scoring.py` (342 lines) — Fibonacci confluence scoring.
  - `score_pattern(pattern) -> float`: per-pattern wave ratios (W2/W1, W3/W1, W4/W3, W5/W1 for impulses; B/A, C/A for zigzags/flats; leg ratios for triangles) scored against `IDEAL_WAVE_RATIOS` with a multi-ideal weighted-max distance metric. Returns `0.0` for invalid, `_BARELY_VALID_FLOOR=0.05` for valid-but-no-confluence, up to `1.0` for perfect canonical match. Per-violation penalty `0.20`. **Signature accepts only the pattern argument — no caller-supplied ratio override per T-14-04.**
  - `rank_patterns(patterns)`: stable score-descending sort with `_PATTERN_PRIORITY` tie-break (Impulse=5, Diagonal=4, Zigzag=3, Flat=2, Triangle=1, Complex=0).
  - `get_primary_count(patterns)`: returns the highest-scoring valid pattern or `None`.

- `tests/test_elliott_wave_advanced.py` (483 lines) — 42 unit tests organised into:
  - `TestCalculateRetracement` (7): boundary values, 0.618 forward/backward, NaN/negative rejection, type rejection.
  - `TestCalculateProjection` (4): the plan's exact verify case, bearish projection, flat-W1, negative ratio rejection.
  - `TestGetWaveTargets` (4): empty pattern → `{}`, impulse W3/W2-retracement/W5 dict keys + values, zigzag C target, unknown pattern → `{}`.
  - `TestStandardConstants` (3): presence of 0.618, 1.618/2.618, and `IDEAL_WAVE_RATIOS` keying.
  - `TestDiagonalRule` (4): valid contracting bullish, rejection of non-overlapping W4 (impulse shape), wrong point count, zero W1.
  - `TestFlatRule` (5): valid regular, valid expanded, valid running (added after FlatRule sign fix), zero A, wrong point count.
  - `TestTriangleRule` (3): valid contracting, valid expanding, rejection of impulse-shape (leg ratios outside bounds).
  - `TestRuleEngineWithAdvancedRules` (3): default engine registers all 5 rule classes; engine detects Diagonal and Triangle patterns.
  - `TestScorePattern` (4): invalid/None → 0.0; ideal impulse > weak impulse; score in [0, 1].
  - `TestRankAndPrimaryCount` (4): empty input handling; primary count picks ideal over weak; rank descending; all-invalid → None.
  - `TestScoringSecurityHardening` (1): `inspect.signature(score_pattern)` confirms only `pattern` parameter (T-14-04).

### Modified

- `ai_engine/elliott_wave/rules.py` — `RuleEngine.__post_init__` now registers all 5 rule classes (`ImpulseRule`, `ZigzagRule`, `DiagonalRule`, `FlatRule`, `TriangleRule`). The advanced-rules import is local to `__post_init__` to avoid a circular import (advanced_rules imports `BaseRule` from rules).
- `ai_engine/elliott_wave/__init__.py` — Docstring updated to describe the Wave 2 surface; no new symbol re-exports (callers import the modules directly, matching Wave 1's surface policy).
- `tests/test_elliott_wave.py` — One test updated (`TestRuleEngine::test_engine_validate_one_unknown_raises`): switched the "no rule attached" pattern from `PatternType.TRIANGLE` to `PatternType.COMPLEX`. Wave 2 legitimately registers `TRIANGLE`, so the old assumption is no longer true; `COMPLEX` remains unregistered and preserves the contract being tested. See Deviations.

## Verification

```
$ python -m pytest tests/test_elliott_wave.py tests/test_elliott_wave_advanced.py -q
77 passed in 1.51s
```

Per-task verify commands all green:
- Task 1: `python -c "from ai_engine.elliott_wave.fibonacci import calculate_projection; print('OK' if calculate_projection(100, 200, 150, 1.618) == 311.8 else 'FAIL')"` → `OK`.
- Task 2: `python -m pytest tests/test_elliott_wave_advanced.py` → 42 passed.
- Task 3: `python -m pytest tests/test_elliott_wave_advanced.py` → 42 passed.

Plan-level success criteria:
- [x] Fibonacci targets are calculated and align with EWT standards (`TestCalculateProjection`, `TestGetWaveTargets`, `TestCalculateRetracement`).
- [x] Advanced patterns (Flats, Triangles, Diagonals) are detected in test data (`TestFlatRule`, `TestTriangleRule`, `TestDiagonalRule`, `TestRuleEngineWithAdvancedRules`).
- [x] Multiple counts are handled, and the "Primary Count" is the most logical one (`TestRankAndPrimaryCount::test_primary_count_picks_highest` and `TestScorePattern::test_ideal_impulse_scores_higher_than_weak`).

Threat model:
- T-14-03 (Information Disclosure on Projections): accepted in plan — `calculate_projection` derives from public EWT rules only.
- T-14-04 (Tampering on Scoring Logic): **mitigated** — all ratios sourced from module constants in `fibonacci.py`; `score_pattern` signature inspection confirms no override parameter (`TestScoringSecurityHardening::test_score_pattern_signature_takes_only_pattern`).

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Inverted `c_undershoot` inequality in `FlatRule`**
- **Found during:** Post-Task 3 advisor review.
- **Issue:** For a bullish flat (A ends at peak), "C undershoots A's end" means `c_end < a_end` (price below A's high). The first draft had `c_end > a_end`. Bearish flats were also inverted symmetrically. The `running` sub-type classification branch was therefore unreachable for the cases it claimed to catch.
- **Fix:** Reversed both inequalities; added test `TestFlatRule::test_valid_running_flat` exercising the running branch. Removed the unused `c_overshoot` variable.
- **Files modified:** `ai_engine/elliott_wave/advanced_rules.py`, `tests/test_elliott_wave_advanced.py`
- **Commit:** `604d752`

**2. [Rule 1 - Regression in Wave 1 test caused by Wave 2 surface expansion]**
- **Found during:** Task 2 regression check (Wave 1 tests).
- **Issue:** `tests/test_elliott_wave.py::TestRuleEngine::test_engine_validate_one_unknown_raises` asserted that `engine.validate_one(..., PatternType.TRIANGLE)` raises `KeyError`. That was true under Wave 1 but Wave 2 legitimately registers `TriangleRule` in the default engine. The test's intent (assert behaviour for an unregistered pattern type) is preserved, but the *example* of an unregistered pattern had to change.
- **Fix:** Switched the test to use `PatternType.COMPLEX`, which remains unregistered after Wave 2 (the COMPLEX W-X-Y / W-X-Y-X-Z patterns are explicitly out of scope for Phase 14 per the research doc — they would belong to a hypothetical Wave 4).
- **Files modified:** `tests/test_elliott_wave.py`
- **Commit:** `df0d27b`

**3. [Rule 3 - Blocking: CLAUDE.md 500-line hard cap]**
- **Found during:** Task 2 planning.
- **Issue:** The plan's `files_modified` block lists `rules.py` as the destination for the new rule classes. Wave 1's `rules.py` is already 382 lines; adding `DiagonalRule` + `FlatRule` + `TriangleRule` (~400 lines combined) would push the file to ~780 lines, violating the project-wide hard cap of 500 lines per file (CLAUDE.md "File Organization" / "Project Architecture" sections).
- **Fix:** Created `ai_engine/elliott_wave/advanced_rules.py` (411 lines) for the new rule classes. `rules.py` was modified only minimally: a 7-line addition to `RuleEngine.__post_init__` that lazy-imports and registers the three new classes (to avoid a circular import). The public surface — `RuleEngine()` returns an engine with all 5 rules — is unchanged; consumers do not need to know about the split.
- **Files modified:** `ai_engine/elliott_wave/rules.py` (added registration), `ai_engine/elliott_wave/advanced_rules.py` (new)
- **Commits:** `df0d27b`

### Plan Adjustments

- **`type="tdd"` was not present on Wave 2's tasks**, so the strict RED-before-GREEN cycle is not required (Plan frontmatter is `type: execute`). Tests were written immediately after each task's implementation, in the same commit pair (feat + test). The verify commands target the *new* test file, which is also what the plan specifies.
- **SUMMARY output path** — Plan's `<output>` block specifies `.planning/phases/plan 14 eliotwafe/14-02-SUMMARY.md` (stale). The active phase directory is `14-elliott-wave-master-structure/`, which is where this summary lives (matching Wave 1's correction and the orchestrator's success criteria).

## Commits

| Task    | Type | Commit    | Description                                                                                |
| ------- | ---- | --------- | ------------------------------------------------------------------------------------------ |
| 1       | feat | `e3059cf` | Fibonacci retracement/projection/target math + 18 tests                                    |
| 2       | feat | `df0d27b` | DiagonalRule, FlatRule, TriangleRule in advanced_rules.py + engine registration + 14 tests |
| 3       | feat | `0d91237` | scoring.py: score_pattern, rank_patterns, get_primary_count + 9 tests                      |
| Post-3  | fix  | `604d752` | Inverted c_undershoot sign in FlatRule (Rule 1 from advisor review) + running-flat test    |

## TDD Gate Compliance

Plan-level frontmatter is `type: execute`, so global RED/GREEN/REFACTOR gate enforcement does not apply. Each task ships implementation and tests as paired commits.

## Authentication Gates

None — fully autonomous Python implementation.

## Known Stubs

None. The fix commit (`604d752`) ensures all three flat sub-types are reachable; `PatternType.COMPLEX` remains intentionally unregistered (planned for a future phase if/when W-X-Y / W-X-Y-X-Z become in-scope).

## Threat Flags

None. The Wave 2 implementation introduces no new network endpoints, auth paths, file access patterns, or schema changes. The only declared trust boundary (`Scoring -> Signal`, T-14-04) is mitigated by hardcoding the ratio table and exposing a single-parameter `score_pattern` signature.

## Self-Check: PASSED

Files verified to exist on disk:
- `ai_engine/elliott_wave/fibonacci.py` — FOUND (274 lines)
- `ai_engine/elliott_wave/advanced_rules.py` — FOUND (411 lines)
- `ai_engine/elliott_wave/scoring.py` — FOUND (342 lines)
- `tests/test_elliott_wave_advanced.py` — FOUND (483 lines)

Commits verified in `git log`:
- `e3059cf` — FOUND (Task 1: fibonacci.py + tests)
- `df0d27b` — FOUND (Task 2: advanced_rules.py + engine + regression-fix test)
- `0d91237` — FOUND (Task 3: scoring.py + tests)
- `604d752` — FOUND (post-task fix: FlatRule running branch)

Test suite: `python -m pytest tests/test_elliott_wave.py tests/test_elliott_wave_advanced.py` → **77 passed in 1.51s** (35 Wave 1 regression + 42 Wave 2 new).

File-size cap: all created/modified files are ≤ 483 lines (well under CLAUDE.md's 500-line hard cap).

Plan success criteria: all three checked items pass with cited tests; T-14-04 mitigation verified by `inspect.signature` test.
