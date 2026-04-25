"""Causal Exit-AI snapshot generation and action labeling."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any, Mapping

import numpy as np
import pandas as pd

from exit_engine.dynamic_sl import calculate_dynamic_sl
from exit_engine.partial_close import evaluate_partial_close
from exit_engine.trailing_manager import calculate_trailing_stop
from exit_engine.types import StructureLevel
from strategy.regime_detector import MarketRegime

EXIT_AI_ACTIONS: tuple[str, ...] = (
    "HOLD",
    "TIGHTEN_SL",
    "PARTIAL_CLOSE",
    "FULL_EXIT",
)
ACTION_TO_LABEL = {action: idx for idx, action in enumerate(EXIT_AI_ACTIONS)}
LABEL_TO_ACTION = {idx: action for action, idx in ACTION_TO_LABEL.items()}
FUTURE_OUTCOME_COLUMNS = (
    "future_adverse_r",
    "future_favorable_r",
    "future_return_r",
)


@dataclass(frozen=True)
class ExitTrainingSample:
    """A single causal trade-management snapshot for Exit-AI training."""

    timestamp: str
    features: dict[str, float]
    action: str
    action_label: int
    baseline_context: dict[str, Any]
    future_outcome: dict[str, float]


class ExitSnapshotBuilder:
    """Build deterministic Exit-AI samples from trade-management snapshots."""

    def __init__(
        self,
        *,
        close_fraction: float = 0.5,
        activation_r: float = 1.0,
        trail_atr_multiplier: float = 1.0,
    ) -> None:
        self.close_fraction = close_fraction
        self.activation_r = activation_r
        self.trail_atr_multiplier = trail_atr_multiplier

    def build_snapshot(self, record: Mapping[str, Any]) -> ExitTrainingSample:
        """Create one leak-safe Exit-AI sample."""
        direction = _coerce_direction(record.get("direction"))
        regime = _coerce_regime(record.get("regime", "RANGING"))

        entry_price = _safe_float(record.get("entry_price"), default=0.0)
        current_price = _safe_float(
            record.get("current_price", record.get("close")),
            default=entry_price,
        )
        atr = max(_safe_float(record.get("atr"), default=1.0), 0.01)
        current_stop_loss = _safe_float(
            record.get("current_stop_loss", record.get("stop_loss")),
            default=0.0,
        )
        initial_stop_loss = _safe_float(
            record.get("initial_stop_loss", current_stop_loss),
            default=current_stop_loss,
        )
        if current_stop_loss == 0.0:
            current_stop_loss = initial_stop_loss
        if initial_stop_loss == 0.0:
            initial_stop_loss = current_stop_loss

        take_profit = _safe_float(record.get("take_profit"), default=0.0)
        if take_profit == 0.0:
            base_risk = max(abs(entry_price - initial_stop_loss), 0.5)
            take_profit = (
                entry_price + (base_risk * 2.5)
                if direction == "BUY"
                else entry_price - (base_risk * 2.5)
            )

        tp1 = _safe_float(
            record.get("tp1"),
            default=_default_tp1(
                direction=direction,
                entry_price=entry_price,
                take_profit=take_profit,
            ),
        )

        baseline_context = self._build_baseline_context(
            record=record,
            direction=direction,
            regime=regime,
            entry_price=entry_price,
            current_price=current_price,
            current_stop_loss=current_stop_loss,
            initial_stop_loss=initial_stop_loss,
            take_profit=take_profit,
            tp1=tp1,
            atr=atr,
        )

        action_hint = record.get("label_action", record.get("action_hint"))
        if action_hint is not None:
            action = _validate_action(str(action_hint))
        else:
            action = self._derive_action(record, baseline_context)

        features = self._build_features(
            record=record,
            direction=direction,
            entry_price=entry_price,
            current_price=current_price,
            current_stop_loss=current_stop_loss,
            initial_stop_loss=initial_stop_loss,
            take_profit=take_profit,
            tp1=tp1,
            atr=atr,
            baseline_context=baseline_context,
        )

        timestamp = str(
            record.get("timestamp")
            or record.get("snapshot_time")
            or record.get("time")
            or ""
        )
        future_outcome = {
            column: _safe_float(record.get(column), default=0.0)
            for column in FUTURE_OUTCOME_COLUMNS
        }

        return ExitTrainingSample(
            timestamp=timestamp,
            features=features,
            action=action,
            action_label=ACTION_TO_LABEL[action],
            baseline_context=baseline_context,
            future_outcome=future_outcome,
        )

    def build_samples(self, frame: pd.DataFrame) -> dict[str, Any]:
        """Build a serializable dataset package from a snapshot frame."""
        if frame.empty:
            raise ValueError("Exit snapshot frame is empty")

        samples: list[ExitTrainingSample] = [
            self.build_snapshot(record)
            for record in frame.to_dict(orient="records")
        ]
        feature_names = list(samples[0].features.keys())

        dataset_rows: list[dict[str, Any]] = []
        for sample in samples:
            row = dict(sample.features)
            row["timestamp"] = sample.timestamp
            row["action"] = sample.action
            row["action_label"] = sample.action_label
            for key, value in sample.future_outcome.items():
                row[key] = value
            dataset_rows.append(row)

        dataset_frame = pd.DataFrame(dataset_rows)
        action_counts = {
            action: int(sum(sample.action == action for sample in samples))
            for action in EXIT_AI_ACTIONS
        }

        return {
            "schema_version": 1,
            "samples": [asdict(sample) for sample in samples],
            "frame": dataset_frame,
            "feature_names": feature_names,
            "action_manifest": build_exit_action_manifest(feature_names),
            "class_balance": {
                "total_samples": len(samples),
                "action_counts": action_counts,
                "hold_ratio": round(
                    action_counts["HOLD"] / max(len(samples), 1),
                    6,
                ),
                "non_hold_ratio": round(
                    1.0 - (action_counts["HOLD"] / max(len(samples), 1)),
                    6,
                ),
            },
        }

    def _build_baseline_context(
        self,
        *,
        record: Mapping[str, Any],
        direction: str,
        regime: MarketRegime,
        entry_price: float,
        current_price: float,
        current_stop_loss: float,
        initial_stop_loss: float,
        take_profit: float,
        tp1: float,
        atr: float,
    ) -> dict[str, Any]:
        structure_levels = _build_structure_levels(record)
        dynamic_sl = calculate_dynamic_sl(
            direction=direction,
            entry_price=entry_price,
            atr=atr,
            regime=regime,
            structure_levels=structure_levels,
        )
        trailing = calculate_trailing_stop(
            direction=direction,
            entry_price=entry_price,
            current_price=current_price,
            initial_stop_loss=initial_stop_loss,
            atr=atr,
            current_stop_loss=current_stop_loss,
            activation_r=self.activation_r,
            trail_atr_multiplier=self.trail_atr_multiplier,
        )
        partial_close = evaluate_partial_close(
            direction=direction,
            current_price=current_price,
            tp1=tp1,
            close_fraction=self.close_fraction,
            already_closed=bool(record.get("already_closed", False)),
        )
        return {
            "baseline_dynamic_sl": float(dynamic_sl.sl),
            "baseline_dynamic_sl_reason": dynamic_sl.reason,
            "baseline_trailing_sl": (
                None if trailing.new_sl is None else float(trailing.new_sl)
            ),
            "baseline_trailing_reason": trailing.reason,
            "baseline_partial_close_fraction": float(partial_close.close_fraction),
            "baseline_partial_close_reason": partial_close.reason,
            "baseline_partial_close_target": partial_close.target_hit,
            "baseline_profit_r": float(trailing.profit_r),
            "baseline_take_profit": float(take_profit),
            "baseline_tp1": float(tp1),
        }

    def _derive_action(
        self,
        record: Mapping[str, Any],
        baseline_context: Mapping[str, Any],
    ) -> str:
        if any(
            bool(record.get(flag, False))
            for flag in (
                "force_full_exit",
                "reversal_exit",
                "time_exit",
                "risk_exit",
                "max_holding_exit",
            )
        ):
            return "FULL_EXIT"
        if baseline_context["baseline_partial_close_fraction"] > 0:
            return "PARTIAL_CLOSE"
        if baseline_context["baseline_trailing_sl"] is not None:
            return "TIGHTEN_SL"
        return "HOLD"

    def _build_features(
        self,
        *,
        record: Mapping[str, Any],
        direction: str,
        entry_price: float,
        current_price: float,
        current_stop_loss: float,
        initial_stop_loss: float,
        take_profit: float,
        tp1: float,
        atr: float,
        baseline_context: Mapping[str, Any],
    ) -> dict[str, float]:
        initial_risk = max(abs(entry_price - initial_stop_loss), 0.01)
        current_risk = max(abs(current_price - current_stop_loss), 0.0)
        reward_distance = abs(take_profit - current_price)
        total_reward = max(abs(take_profit - entry_price), 0.01)
        profit_r = _signed_distance(direction, entry_price, current_price) / initial_risk
        price_progress = _signed_distance(direction, entry_price, current_price) / total_reward
        tp1_progress = _signed_distance(direction, entry_price, current_price) / max(
            abs(tp1 - entry_price),
            0.01,
        )
        trailing_sl = baseline_context["baseline_trailing_sl"]
        trailing_gap = 0.0
        if trailing_sl is not None:
            trailing_gap = abs(float(trailing_sl) - current_stop_loss)

        features = {
            "direction_sign": 1.0 if direction == "BUY" else -1.0,
            "entry_price": float(entry_price),
            "current_price": float(current_price),
            "current_stop_loss": float(current_stop_loss),
            "initial_stop_loss": float(initial_stop_loss),
            "take_profit": float(take_profit),
            "tp1": float(tp1),
            "atr": float(atr),
            "current_stop_buffer_r": round(current_risk / initial_risk, 6),
            "reward_distance_r": round(reward_distance / initial_risk, 6),
            "profit_r": round(profit_r, 6),
            "price_progress": round(price_progress, 6),
            "tp1_progress": round(tp1_progress, 6),
            "hours_open": _safe_float(record.get("hours_open"), default=0.0),
            "volume_ratio": _safe_float(record.get("volume_ratio"), default=1.0),
            "spread_pips": _safe_float(record.get("spread_pips"), default=0.0),
            "baseline_dynamic_sl_gap": round(
                abs(baseline_context["baseline_dynamic_sl"] - current_stop_loss),
                6,
            ),
            "baseline_trailing_gap": round(trailing_gap, 6),
            "baseline_partial_close_fraction": round(
                baseline_context["baseline_partial_close_fraction"],
                6,
            ),
            "baseline_profit_r": round(
                baseline_context["baseline_profit_r"],
                6,
            ),
        }
        return {
            key: 0.0 if not np.isfinite(value) else float(value)
            for key, value in features.items()
        }


def build_exit_action_manifest(feature_names: list[str]) -> dict[str, Any]:
    """Return a machine-readable manifest for the Exit-AI action space."""
    return {
        "schema_version": 1,
        "allowed_actions": list(EXIT_AI_ACTIONS),
        "label_map": dict(ACTION_TO_LABEL),
        "feature_names": list(feature_names),
        "outcome_columns": list(FUTURE_OUTCOME_COLUMNS),
    }


def build_exit_training_samples(
    frame: pd.DataFrame,
    *,
    builder: ExitSnapshotBuilder | None = None,
) -> dict[str, Any]:
    """Build the full Exit-AI dataset package."""
    snapshot_builder = builder or ExitSnapshotBuilder()
    return snapshot_builder.build_samples(frame)


def _coerce_direction(value: Any) -> str:
    direction = str(value or "").upper()
    if direction not in {"BUY", "SELL"}:
        raise ValueError(f"direction must be BUY or SELL, got {value!r}")
    return direction


def _coerce_regime(value: Any) -> MarketRegime:
    if isinstance(value, MarketRegime):
        return value
    text = str(value or "RANGING").upper()
    return getattr(MarketRegime, text, MarketRegime.RANGING)


def _build_structure_levels(record: Mapping[str, Any]) -> list[StructureLevel]:
    levels: list[StructureLevel] = []
    support = _safe_float(
        record.get("support_level", record.get("structure_support")),
        default=0.0,
    )
    resistance = _safe_float(
        record.get("resistance_level", record.get("structure_resistance")),
        default=0.0,
    )
    if support > 0:
        levels.append(
            StructureLevel(
                price=support,
                level_type="support",
                strength=2,
                source="snapshot",
            )
        )
    if resistance > 0:
        levels.append(
            StructureLevel(
                price=resistance,
                level_type="resistance",
                strength=2,
                source="snapshot",
            )
        )
    return levels


def _validate_action(action: str) -> str:
    action = str(action).upper()
    if action not in ACTION_TO_LABEL:
        raise ValueError(
            f"Unsafe Exit-AI action {action!r}; allowed actions: {EXIT_AI_ACTIONS}"
        )
    return action


def _default_tp1(
    *,
    direction: str,
    entry_price: float,
    take_profit: float,
) -> float:
    distance = abs(take_profit - entry_price) * 0.5
    if direction == "BUY":
        return entry_price + distance
    return entry_price - distance


def _signed_distance(direction: str, start_price: float, end_price: float) -> float:
    if direction == "BUY":
        return end_price - start_price
    return start_price - end_price


def _safe_float(value: Any, *, default: float) -> float:
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return float(default)
    if not np.isfinite(parsed):
        return float(default)
    return float(parsed)
