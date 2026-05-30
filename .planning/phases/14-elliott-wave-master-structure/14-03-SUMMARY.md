---
phase: 14-elliott-wave-master-structure
plan: 03
subsystem: ai_engine.elliott_wave / trading
tags: [elliott-wave, ml-features, mirofish, signal-filter, integration]
requirements: [EWT-03, EWT-04]
dependency_graph:
  requires:
    - ai_engine.elliott_wave.detector (WaveDetector)
    - ai_engine.elliott_wave.rules (RuleEngine)
    - ai_engine.elliott_wave.scoring (get_primary_count)
    - ai_engine.elliott_wave.fibonacci (get_wave_targets)
    - ai_engine.elliott_wave.models (PatternType, WavePattern)
  provides:
    - ai_engine.features.elliott_wave_features (extract_ew_features, ElliottWaveFeatures, FEATURE_NAMES)
    - ai_engine.mirofish_wave_context (structural-context string builder, sanitised)
    - trading.signal_generator (evaluate_ew_buy_filter, apply_ew_filter, _decide_from_wave_context)
  affects:
    - FeatureEngineer feature matrix gains 4 EW columns (consumed by ML training/inference)
    - MiroFish prompts gain a "Structural Context" section
    - Live BUY signals can be vetoed/supported by EW count when ew_filter_enabled
tech_stack:
  added: []
  patterns:
    - Causal feature extraction (compute once on the window, broadcast to rows; no lookahead)
    - Pure decision core + thin detection shell (testable verdict logic isolated from I/O)
    - Opt-in feature gated by settings.*_enabled defaulting False (mirrors MiroFish/sentiment)
    - Reuse extract_ew_features as the single source of truth for wave state
key_files:
  created:
    - ai_engine/features/elliott_wave_features.py
    - ai_engine/mirofish_wave_context.py
    - tests/test_signal_generator_ewt.py
  modified:
    - ai_engine/features/feature_engineer.py (register the 4 EW features)
    - ai_engine/mirofish_client.py (_prepare_prompt injects sanitised Structural Context)
    - trading/signal_generator.py (EW BUY filter + _resolve_primary_df + wiring into _generate_signal)
    - config/settings.py (ew_filter_enabled, ew_veto_completion)
decisions:
  - "[Phase 14-03]: EW state is exposed as 4 causal ML features (ew_pattern_type int-encoded, ew_wave_number, ew_completion [0,1], ew_is_motive 0/1); computed once on the last EW_MAX_WINDOW=300 candles and broadcast (no per-row lookahead)"
  - "[Phase 14-03]: T-14-06 (DoS) mitigated by an input window cap (EW_MAX_WINDOW=300) rather than SIGALRM, because signal-based timeouts are unavailable on Windows"
  - "[Phase 14-03]: MiroFish wave-context builder lives in its own module ai_engine/mirofish_wave_context.py (not inline in mirofish_client) to keep files under the 500-line cap; the context string is sanitised before prompt injection (T-14-05)"
  - "[Phase 14-03]: EW signal filter is BUY-only and opt-in via settings.ew_filter_enabled (default False); SELL/HOLD pass through untouched, matching the mirofish/sentiment graceful-fallback pattern"
  - "[Phase 14-03]: Veto BUY when a motive Wave 3 or 5 is >= ew_veto_completion (default 0.8) complete (Wave 4 / ABC correction imminent) or a corrective Wave A is in progress; mark BUY 'supported' when a fresh Wave 3 or 5 is starting (wave 2 or 4 just completed)"
  - "[Phase 14-03]: Filter verdict logic isolated in pure _decide_from_wave_context (no EW imports) so all branches are deterministically unit-tested; evaluate_ew_buy_filter reuses extract_ew_features and decodes the int encoding back to PatternType names for readable reasons"
  - "[Phase 14-03]: apply_ew_filter never mutates the input signal (returns a copy); a veto converts action BUY->HOLD and records ew_vetoed_action + ew_filter context for audit"
metrics:
  task_count: 3
  file_count_created: 3
  file_count_modified: 4
  test_count_added: 15
  test_count_total_ew: 92
tests:
  command: "python -m pytest tests/test_elliott_wave.py tests/test_elliott_wave_advanced.py tests/test_signal_generator_ewt.py -q"
  result: "92 passed in 3.21s"
completed: "2026-05-30T10:30:00Z"
---

# Phase 14 Plan 03: System Integration & ML Features Summary

Wired the Elliott Wave engine (built in Waves 1–2) into the live trading system across three integration points: ML feature extraction, MiroFish structural context, and a signal-level BUY filter. The Elliott Wave count now informs model training (4 new features), AI swarm reasoning (prompt context), and trade gating (optional veto/support).

**One-liner:** `extract_ew_features` exposes 4 causal EW features through `FeatureEngineer`; `mirofish_wave_context` injects a sanitised "Structural Context" section into MiroFish prompts; and an opt-in `apply_ew_filter` vetoes BUY when a motive Wave 3/5 is near completion (or a corrective Wave A is running) and marks BUY as supported when a fresh Wave 3/5 is starting — 15 new tests, 92 EW tests green, zero regression.

## What Changed

### Task 1 — Elliott Wave ML Features (commit `1874bb1`)
- **Created `ai_engine/features/elliott_wave_features.py`** — `extract_ew_features(ohlcv_df)` runs `WaveDetector` → `RuleEngine` → `get_primary_count` and returns 4 features:
  `ew_pattern_type` (0=NONE,1=IMPULSE,2=ZIGZAG,3=FLAT,4=TRIANGLE,5=DIAGONAL,6=COMPLEX), `ew_wave_number` (1–5, or A/B/C→1/2/3), `ew_completion` (fraction [0,1] from `get_wave_targets`), `ew_is_motive` (0/1). Computed causally on the last `EW_MAX_WINDOW=300` candles and broadcast uniformly; the pipeline never raises (returns zeros on any failure).
- **Modified `ai_engine/features/feature_engineer.py`** — registers the EW feature group.
- **Verify (plan Task 1):** `FeatureEngineer().get_feature_names()` contains `ew_pattern_type` → **True**.

### Task 2 — Structural Context to MiroFish (commit `2bbfee3`)
- **Created `ai_engine/mirofish_wave_context.py`** — builds the human-readable structural-context string (e.g. "Gold is in Wave 3 of a Bullish Impulse. Target 161.8% at …") from the primary count + Fibonacci targets, **sanitised** before use (T-14-05).
- **Modified `ai_engine/mirofish_client.py`** — `_prepare_prompt` injects a "Structural Context" section.
- **Verify (plan Task 2):** `MiroFishClient()._prepare_prompt({})` contains `"Structural Context"` → **True**.

### Task 3 — Wave Counts in the Signal Generator (commit `9705218`)
- **Modified `trading/signal_generator.py`** — added a pure verdict core `_decide_from_wave_context`, a detection shell `evaluate_ew_buy_filter` (reuses `extract_ew_features`, imports `ai_engine.elliott_wave.models.PatternType` — satisfies the planned key-link), `apply_ew_filter` (BUY-only; veto→HOLD, support→annotate, never mutates input), a `_resolve_primary_df` helper, and wiring into `_generate_signal` beside the MiroFish veto.
- **Modified `config/settings.py`** — `ew_filter_enabled: bool = False`, `ew_veto_completion: float = 0.8` (governance).
- **Created `tests/test_signal_generator_ewt.py`** — 15 tests: 8 cover every branch of the pure verdict core; 6 cover `apply_ew_filter` gating/veto/support/passthrough/no-mutation (with `evaluate_ew_buy_filter` monkeypatched); 1 smoke-tests the real detection path on degenerate data.
- **Verify (plan Task 3):** `python -m pytest tests/test_signal_generator_ewt.py` → **15 passed**.

## Verification

```
$ python -m pytest tests/test_elliott_wave.py tests/test_elliott_wave_advanced.py tests/test_signal_generator_ewt.py -q
92 passed in 3.21s
```

Plan must-haves (all met):
- [x] Elliott Wave state available as ML features for model training (Task 1 verify).
- [x] MiroFish agents receive structural market context in their prompts (Task 2 verify).
- [x] Trading signals are filtered/vetoed based on Elliott Wave count (Task 3 — 15 tests, wired into `_generate_signal`).

Key-links:
- [x] `feature_engineer.py` → `elliott_wave_features.py` (feature integration).
- [x] `signal_generator.py` → `ai_engine.elliott_wave` (signal filtering — `evaluate_ew_buy_filter` imports `ai_engine.elliott_wave.models`).

## Threat Model
- **T-14-05 (Spoofing / prompt injection on MiroFish context):** mitigated — the wave-context string is sanitised in `mirofish_wave_context` before injection.
- **T-14-06 (DoS on feature extraction):** mitigated — `EW_MAX_WINDOW=300` caps detector input (Windows-safe alternative to SIGALRM).

## Deviations from Plan

- **Mid-plan handoff (process):** Tasks 1 & 2 were executed by a `gsd-executor` subagent; the run was stopped after Task 2 (clean inter-task state, 77 tests green) and **Task 3 was completed inline in the main session** per a new user preference ("work without agents"). No work was lost — the two task commits are intact and were verified before continuing.
- **Task 2 file split:** The plan listed only `ai_engine/mirofish_client.py`. The wave-context builder was extracted to a new `ai_engine/mirofish_wave_context.py` to respect CLAUDE.md's 500-line cap and keep the client lean (same rationale as Wave 2's `advanced_rules.py` split).
- **Task 3 added `config/settings.py`:** Not in the plan's `files_modified`, but required to make the filter "optional and governable" as the task action specifies — added two typed opt-in settings mirroring the MiroFish/sentiment pattern. The filter also reads them defensively via `getattr` so it degrades safely if absent.
- **Task 3 reuses `extract_ew_features`** instead of re-running the detector, keeping a single source of truth for wave state (DRY, inherits the T-14-06 window cap).
- **SUMMARY path:** the plan's `<output>` block names the stale `plan 14 eliotwafe/` directory; this summary lives in the canonical `14-elliott-wave-master-structure/` (matching Waves 1–2).

## Code Review (inline)
Per the no-subagents preference, the agent-based `gsd-code-review` was replaced with an inline self-review of the Task 3 diff: the filter is opt-in (default off), the verdict core is pure and fully branch-tested, the input signal is never mutated, the detection path is exception-safe (returns zeros→neutral), and `ruff` ran clean via the pre-commit hook on commit `9705218`. No issues found.

## Authentication Gates
None — fully autonomous Python implementation.

## Known Stubs
None.

## Self-Check: PASSED

Files verified on disk:
- `ai_engine/features/elliott_wave_features.py` — FOUND
- `ai_engine/mirofish_wave_context.py` — FOUND
- `tests/test_signal_generator_ewt.py` — FOUND
- modified: `feature_engineer.py`, `mirofish_client.py`, `trading/signal_generator.py`, `config/settings.py` — FOUND

Commits verified in `git log`:
- `1874bb1` — Task 1 (EW features) — FOUND
- `2bbfee3` — Task 2 (MiroFish context) — FOUND
- `9705218` — Task 3 (signal filter) — FOUND

Test suite: `python -m pytest tests/test_elliott_wave.py tests/test_elliott_wave_advanced.py tests/test_signal_generator_ewt.py` → **92 passed** (35 + 42 + 15).
File-size cap: all created/modified files ≤ 500 lines.
