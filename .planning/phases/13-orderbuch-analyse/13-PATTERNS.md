# Phase 13 - Pattern Map

**Phase:** 13 - Orderbuch-Analyse  
**Created:** 2026-04-25  
**Source:** Local pattern mapping from Phase 13 research and current codebase.

---

## Target Files

| Target | Role | Closest Existing Analog | Pattern to Reuse |
|--------|------|-------------------------|------------------|
| `ai_engine/features/orderflow_features.py` | New `flow_*` feature group | `ai_engine/features/microstructure_features.py` | `FEATURE_NAMES`, `calculate(df)`, `get_feature_names()`, neutral defaults, `cleanup_dataframe_features()` |
| `tests/test_orderflow_features.py` | Unit coverage for delta, profile, liquidity, FVG, absorption | `tests/test_microstructure_features.py` | synthetic OHLCV fixture, assert feature subset, NaN-free output, safe defaults |
| `market_data/orderflow_stream.py` | Quote payload aggregation and L1 imbalance | `market_data/broker_client.py` | consume `quote` payloads without logging credentials or changing broker auth flow |
| `tests/test_orderflow_stream.py` | Unit coverage for quote imbalance and candle buckets | `tests/test_microstructure_features.py` | deterministic payload fixtures and exact output assertions |
| `ai_engine/features/feature_engineer.py` | Feature group integration | existing `FeatureEngineer` constructor and `get_feature_groups()` | instantiate feature group, append names, call `calculate()` before cleanup |
| `config/settings.py` | Tunable flow windows/thresholds | sentiment/correlation settings blocks | opt-in/default-safe config fields with conservative defaults |
| `tests/test_orderflow_integration.py` | ML integration gate | `tests/test_microstructure_features.py`, `tests/test_correlation_features.py` | assert feature names exposed and `create_features()` produces clean matrices |

---

## Existing Feature Group Pattern

`MicrostructureFeatures` is the direct template:

- class-level `FEATURE_NAMES: List[str]`
- `calculate(self, df: pd.DataFrame) -> pd.DataFrame`
- copy the input frame before mutation
- use numeric coercion for optional inputs
- safe defaults when optional source columns are missing
- call `cleanup_dataframe_features(out, self.FEATURE_NAMES)`
- return `self.FEATURE_NAMES.copy()` from `get_feature_names()`

Phase 13 must not duplicate these existing features:

- `l1_spread_pips`
- `l2_order_imbalance`
- `l2_order_imbalance_ema_10`
- `l2_imbalance_abs`
- `l2_depth_ratio`
- `micro_pressure`
- `micro_liquidity_stress`

All new features use the `flow_` prefix.

---

## Planned Feature Set

Core OHLCV-derived features:

- `flow_delta`
- `flow_delta_cumulative_20`
- `flow_delta_divergence`
- `flow_buy_pressure`
- `flow_poc_distance`
- `flow_vah_distance`
- `flow_val_distance`
- `flow_liq_zone_above`
- `flow_liq_zone_below`
- `flow_fvg_above`
- `flow_fvg_below`
- `flow_absorption_score`
- `flow_volume_zscore`

Optional quote enrichment:

- `flow_l1_imbalance`
- `flow_l1_imbalance_ema_10`

---

## Data Flow

1. Historical/backtest path: OHLCV candles enter `FeatureEngineer.create_features()`.
2. `OrderFlowFeatures.calculate()` computes BVC delta, cumulative delta, profile distances, swing/liquidity zones, FVG distances, absorption score, and neutral quote defaults.
3. Live optional path: Capital.com `quote` payloads feed `market_data/orderflow_stream.py`; the aggregator emits candle-aligned `flow_l1_imbalance` values.
4. `FeatureEngineer` exposes `flow_*` names through `get_feature_names()` and `get_feature_groups()`.
5. Training and prediction pipelines consume `flow_*` features like any other feature group.

---

## Guardrails

- Do not claim true Level 2/DOM from Capital.com; only L1 quote quantities are available.
- Do not add `smartmoneyconcepts` as a hard dependency unless compatibility with pandas 3.0 is proven first.
- Avoid lookahead in FVG/liquidity logic; only confirmed closed-candle events can affect the current row.
- Missing `volume`, `bidQty`, or `ofrQty` must degrade to neutral values instead of crashing.
- Keep Phase 13 as feature/data integration only; do not change runtime trade decision policy in this phase.
