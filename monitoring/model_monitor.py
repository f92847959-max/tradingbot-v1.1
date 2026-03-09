"""Model degradation monitoring — tracks prediction quality over time."""

import logging
import time
from collections import deque
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)

@dataclass
class PredictionRecord:
    timestamp: float
    action: str  # BUY, SELL, HOLD
    confidence: float
    actual_pnl: float | None = None  # filled after trade closes

class ModelMonitor:
    """Rolling-window monitor for model prediction quality."""

    def __init__(
        self,
        window_size: int = 100,
        min_confidence_threshold: float = 0.60,
        min_win_rate_threshold: float = 0.50,
        min_trades_for_alert: int = 50,
    ) -> None:
        self.window_size = window_size
        self.min_confidence_threshold = min_confidence_threshold
        self.min_win_rate_threshold = min_win_rate_threshold
        self.min_trades_for_alert = min_trades_for_alert
        self._predictions: deque[PredictionRecord] = deque(maxlen=window_size)
        self._last_hourly_log: float = 0.0

    def record_prediction(self, action: str, confidence: float) -> None:
        """Record a new prediction signal."""
        self._predictions.append(PredictionRecord(
            timestamp=time.time(),
            action=action,
            confidence=confidence,
        ))
        self._check_degradation()

    def record_outcome(self, pnl: float) -> None:
        """Record the P&L outcome of the most recent trade prediction."""
        # Find last prediction without an outcome
        for rec in reversed(self._predictions):
            if rec.action != "HOLD" and rec.actual_pnl is None:
                rec.actual_pnl = pnl
                break
        self._check_degradation()

    @property
    def avg_confidence(self) -> float:
        if not self._predictions:
            return 0.0
        return sum(r.confidence for r in self._predictions) / len(self._predictions)

    @property
    def win_rate(self) -> float:
        """Win rate over closed trades in the window."""
        closed = [r for r in self._predictions if r.actual_pnl is not None]
        if not closed:
            return 0.0
        wins = sum(1 for r in closed if r.actual_pnl > 0)
        return wins / len(closed)

    @property
    def total_signals(self) -> int:
        return len(self._predictions)

    @property
    def closed_trades(self) -> int:
        return sum(1 for r in self._predictions if r.actual_pnl is not None)

    def _check_degradation(self) -> None:
        """Alert if model quality has degraded."""
        if self.avg_confidence < self.min_confidence_threshold and self.total_signals >= 10:
            logger.warning(
                "MODEL DEGRADATION: avg confidence %.2f < threshold %.2f (last %d signals)",
                self.avg_confidence, self.min_confidence_threshold, self.total_signals,
            )

        closed = self.closed_trades
        if closed >= self.min_trades_for_alert:
            wr = self.win_rate
            if wr < self.min_win_rate_threshold:
                logger.warning(
                    "MODEL DEGRADATION: win rate %.1f%% < threshold %.1f%% (last %d trades)",
                    wr * 100, self.min_win_rate_threshold * 100, closed,
                )

    def hourly_summary(self) -> dict:
        """Return summary dict and log it (call periodically)."""
        now = time.time()
        summary = {
            "total_signals": self.total_signals,
            "closed_trades": self.closed_trades,
            "avg_confidence": round(self.avg_confidence, 4),
            "win_rate": round(self.win_rate, 4),
        }
        if now - self._last_hourly_log >= 3600:
            logger.info("Model monitor hourly summary: %s", summary)
            self._last_hourly_log = now
        return summary

    def status(self) -> dict:
        """Status dict for API/health endpoints."""
        return {
            "total_signals": self.total_signals,
            "closed_trades": self.closed_trades,
            "avg_confidence": round(self.avg_confidence, 4),
            "win_rate": round(self.win_rate, 4),
            "degraded": (
                (self.avg_confidence < self.min_confidence_threshold and self.total_signals >= 10)
                or (self.closed_trades >= self.min_trades_for_alert and self.win_rate < self.min_win_rate_threshold)
            ),
        }
