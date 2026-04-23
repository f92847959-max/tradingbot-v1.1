"""Model degradation monitoring -- tracks calibrated prediction quality over time."""

from __future__ import annotations

import logging
import math
import time
from collections import deque
from dataclasses import dataclass

from ai_engine.governance.promotion import evaluate_retraining_trigger

logger = logging.getLogger(__name__)


@dataclass
class PredictionRecord:
    timestamp: float
    action: str  # BUY, SELL, HOLD
    confidence: float
    threshold_source: str = "defaults"
    artifact_version: str | None = None
    actual_pnl: float | None = None
    brier_score: float | None = None
    drawdown_pct: float | None = None


class ModelMonitor:
    """Rolling-window monitor for calibrated prediction quality."""

    def __init__(
        self,
        window_size: int = 100,
        min_confidence_threshold: float = 0.60,
        min_win_rate_threshold: float = 0.50,
        min_trades_for_alert: int = 50,
        max_brier_score: float = 0.24,
        min_profit_factor: float = 1.0,
        max_drawdown_pct: float = 0.12,
        min_degradation_streak: int = 3,
    ) -> None:
        self.window_size = window_size
        self.min_confidence_threshold = min_confidence_threshold
        self.min_win_rate_threshold = min_win_rate_threshold
        self.min_trades_for_alert = min_trades_for_alert
        self.max_brier_score = max_brier_score
        self.min_profit_factor = min_profit_factor
        self.max_drawdown_pct = max_drawdown_pct
        self.min_degradation_streak = min_degradation_streak
        self._predictions: deque[PredictionRecord] = deque(maxlen=window_size)
        self._last_hourly_log: float = 0.0

    def record_prediction(
        self,
        action: str,
        confidence: float,
        *,
        threshold_source: str = "defaults",
        artifact_version: str | None = None,
    ) -> None:
        """Record a new calibrated prediction signal."""
        self._predictions.append(
            PredictionRecord(
                timestamp=time.time(),
                action=action,
                confidence=confidence,
                threshold_source=threshold_source,
                artifact_version=artifact_version,
            )
        )
        self._check_degradation()

    def record_outcome(
        self,
        pnl: float,
        *,
        brier_score: float | None = None,
        drawdown_pct: float | None = None,
        artifact_version: str | None = None,
    ) -> None:
        """Record the trade outcome and calibrated monitoring metrics."""
        for rec in reversed(self._predictions):
            if rec.action != "HOLD" and rec.actual_pnl is None:
                rec.actual_pnl = pnl
                if brier_score is not None:
                    rec.brier_score = float(brier_score)
                if drawdown_pct is not None:
                    rec.drawdown_pct = float(drawdown_pct)
                if artifact_version is not None:
                    rec.artifact_version = artifact_version
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
    def avg_brier_score(self) -> float:
        scores = [r.brier_score for r in self._predictions if r.brier_score is not None]
        if not scores:
            return 0.0
        return sum(scores) / len(scores)

    @property
    def profit_factor(self) -> float:
        closed = [r.actual_pnl for r in self._predictions if r.actual_pnl is not None]
        profits = sum(v for v in closed if v > 0)
        losses = abs(sum(v for v in closed if v < 0))
        if losses == 0:
            return math.inf if profits > 0 else 0.0
        return profits / losses

    @property
    def max_drawdown(self) -> float:
        values = [r.drawdown_pct for r in self._predictions if r.drawdown_pct is not None]
        if not values:
            return 0.0
        return max(values)

    @property
    def total_signals(self) -> int:
        return len(self._predictions)

    @property
    def closed_trades(self) -> int:
        return sum(1 for r in self._predictions if r.actual_pnl is not None)

    def _degradation_streak(self) -> int:
        streak = 0
        for rec in reversed(self._predictions):
            if rec.actual_pnl is None:
                continue
            degraded = False
            if rec.brier_score is not None and rec.brier_score > self.max_brier_score:
                degraded = True
            if rec.actual_pnl <= 0:
                degraded = True
            if rec.drawdown_pct is not None and rec.drawdown_pct > self.max_drawdown_pct:
                degraded = True
            if not degraded:
                break
            streak += 1
        return streak

    def retraining_status(self) -> dict:
        metrics = {
            "trade_count": self.closed_trades,
            "avg_confidence": self.avg_confidence,
            "win_rate": self.win_rate,
            "mean_brier_score": self.avg_brier_score,
            "profit_factor": self.profit_factor if math.isfinite(self.profit_factor) else 99.0,
            "max_drawdown_pct": self.max_drawdown,
            "degradation_streak": self._degradation_streak(),
        }
        return evaluate_retraining_trigger(
            metrics,
            min_trade_count=self.min_trades_for_alert,
            confidence_floor=self.min_confidence_threshold,
            min_win_rate=self.min_win_rate_threshold,
            max_brier_score=self.max_brier_score,
            min_profit_factor=self.min_profit_factor,
            max_drawdown_pct=self.max_drawdown_pct,
            min_degradation_streak=self.min_degradation_streak,
        )

    def _check_degradation(self) -> None:
        """Alert if calibrated model quality has degraded."""
        status = self.retraining_status()
        if status["trigger_retraining"]:
            logger.warning(
                "MODEL DEGRADATION: calibrated retraining trigger %s",
                ", ".join(status["reasons"]),
            )

    def hourly_summary(self) -> dict:
        """Return summary dict and log it (call periodically)."""
        now = time.time()
        retraining = self.retraining_status()
        summary = {
            "total_signals": self.total_signals,
            "closed_trades": self.closed_trades,
            "avg_confidence": round(self.avg_confidence, 4),
            "win_rate": round(self.win_rate, 4),
            "avg_brier_score": round(self.avg_brier_score, 4),
            "profit_factor": round(self.profit_factor, 4) if math.isfinite(self.profit_factor) else None,
            "max_drawdown_pct": round(self.max_drawdown, 4),
            "retraining_recommended": retraining["trigger_retraining"],
        }
        if now - self._last_hourly_log >= 3600:
            logger.info("Model monitor hourly summary: %s", summary)
            self._last_hourly_log = now
        return summary

    def status(self) -> dict:
        """Status dict for API/health endpoints."""
        retraining = self.retraining_status()
        return {
            "total_signals": self.total_signals,
            "closed_trades": self.closed_trades,
            "avg_confidence": round(self.avg_confidence, 4),
            "win_rate": round(self.win_rate, 4),
            "avg_brier_score": round(self.avg_brier_score, 4),
            "profit_factor": round(self.profit_factor, 4) if math.isfinite(self.profit_factor) else None,
            "max_drawdown_pct": round(self.max_drawdown, 4),
            "degraded": retraining["trigger_retraining"],
            "retraining_recommended": retraining["trigger_retraining"],
            "degradation_reasons": retraining["reasons"],
        }
