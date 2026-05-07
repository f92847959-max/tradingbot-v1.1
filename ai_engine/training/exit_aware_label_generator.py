"""Exit-aware demotion pass for entry labels."""

from __future__ import annotations

import logging
from dataclasses import dataclass

import numpy as np
import pandas as pd

from exit_engine.trailing_manager import calculate_trailing_stop

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class ExitAwareLabelConfig:
    enabled: bool = False
    activation_r: float = 1.0
    max_adverse_r_before_activation: float = 0.75
    trail_atr_multiplier: float = 1.0


class ExitAwareLabelDemoter:
    """Demote entry labels to HOLD when deterministic exit logic would bail early."""

    def __init__(self, config: ExitAwareLabelConfig) -> None:
        self.config = config

    def demote_labels(
        self,
        df: pd.DataFrame,
        labels: np.ndarray,
        *,
        tp_dist: np.ndarray,
        sl_dist: np.ndarray,
        max_candles: int,
    ) -> np.ndarray:
        if not self.config.enabled:
            return labels
        if "atr_14" not in df.columns:
            logger.warning("Exit-aware labels requested but atr_14 is missing; skipping demotion")
            return labels

        close = df["close"].to_numpy(dtype=np.float64)
        high = df["high"].to_numpy(dtype=np.float64)
        low = df["low"].to_numpy(dtype=np.float64)
        atr = df["atr_14"].to_numpy(dtype=np.float64)

        out = labels.copy()
        demoted = 0
        n_limit = max(0, len(out) - max_candles)
        for idx in range(n_limit):
            direction_label = int(out[idx])
            if direction_label == 0:
                continue

            risk = float(sl_dist[idx])
            reward = float(tp_dist[idx])
            if not np.isfinite(risk) or risk <= 0 or not np.isfinite(reward) or reward <= 0:
                continue

            direction = "BUY" if direction_label == 1 else "SELL"
            entry = float(close[idx])
            if direction == "BUY":
                initial_stop = entry - risk
                original_tp = entry + reward
            else:
                initial_stop = entry + risk
                original_tp = entry - reward

            current_stop = initial_stop
            activated = False
            should_demote = False
            for j in range(1, max_candles + 1):
                pos = idx + j
                if pos >= len(out):
                    break
                current_atr = max(float(atr[pos]) if np.isfinite(atr[pos]) else risk, 0.01)
                current_price = float(close[pos])
                if not np.isfinite(current_price):
                    continue

                try:
                    trailing = calculate_trailing_stop(
                        direction=direction,
                        entry_price=entry,
                        current_price=current_price,
                        initial_stop_loss=initial_stop,
                        atr=current_atr,
                        current_stop_loss=current_stop,
                        activation_r=self.config.activation_r,
                        trail_atr_multiplier=self.config.trail_atr_multiplier,
                    )
                    activated = activated or trailing.activated
                    if trailing.new_sl is not None:
                        current_stop = float(trailing.new_sl)
                except ValueError:
                    pass

                if direction == "BUY":
                    favorable_r = (float(high[pos]) - entry) / risk
                    adverse_r = (entry - float(low[pos])) / risk
                    stop_hit = float(low[pos]) <= current_stop
                    tp_hit = float(high[pos]) >= original_tp
                else:
                    favorable_r = (entry - float(low[pos])) / risk
                    adverse_r = (float(high[pos]) - entry) / risk
                    stop_hit = float(high[pos]) >= current_stop
                    tp_hit = float(low[pos]) <= original_tp

                if (
                    not activated
                    and adverse_r >= self.config.max_adverse_r_before_activation
                    and favorable_r < self.config.activation_r
                ):
                    should_demote = True
                    break
                if stop_hit and not tp_hit and not activated:
                    should_demote = True
                    break
                if tp_hit:
                    break

            if should_demote:
                out[idx] = 0
                demoted += 1

        if demoted:
            logger.info(
                "Exit-aware label pass demoted %d/%d trade labels to HOLD",
                demoted,
                int(np.count_nonzero(labels)),
            )
        return out
