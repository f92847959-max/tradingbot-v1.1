"""Deterministic-ish demo data generator for the terminal UI."""

from __future__ import annotations

import math
import random
import time
from dataclasses import dataclass, field

from .config import DemoConfig


@dataclass
class TrainingSeries:
    equity: list[float] = field(default_factory=lambda: [1000.0])
    train_loss: list[float] = field(default_factory=lambda: [2.0])
    validation_loss: list[float] = field(default_factory=lambda: [2.1])
    accuracy: list[float] = field(default_factory=lambda: [0.4])
    confidence: list[float] = field(default_factory=lambda: [0.1])


@dataclass(frozen=True)
class TrainingStats:
    epochs: int
    final_eq: float
    best_eq: float
    final_acc: float
    best_acc: float
    final_loss: float
    min_loss: float
    duration_sec: float

    def as_mapping(self) -> dict[str, float | int]:
        return {
            "epochs": self.epochs,
            "final_eq": self.final_eq,
            "best_eq": self.best_eq,
            "final_acc": self.final_acc,
            "best_acc": self.best_acc,
            "final_loss": self.final_loss,
            "min_loss": self.min_loss,
            "duration": self.duration_sec,
        }


@dataclass(frozen=True)
class TrainingFrame:
    epoch: int
    validation_loss: float
    accuracy: float
    reward: float
    drawdown_pct: float
    trades_per_batch: int
    series: TrainingSeries
    stats: TrainingStats


class TrainingSimulator:
    def __init__(
        self,
        config: DemoConfig,
        rng: random.Random | None = None,
    ) -> None:
        self.config = config
        self.rng = rng or random.Random()
        self.series = TrainingSeries()
        self.started_at = time.time()

    def step(self, epoch: int) -> TrainingFrame:
        last_equity = self.series.equity[-1]
        self.series.equity.append(last_equity + self.rng.uniform(-5.0, 8.0) + epoch * 0.005)

        base_loss = 2.0 * math.exp(-epoch / 200)
        self.series.train_loss.append(base_loss + self.rng.uniform(0.0, 0.05))
        validation_loss = base_loss + self.rng.uniform(0.0, 0.1) + epoch * 0.0001
        self.series.validation_loss.append(validation_loss)

        accuracy = 0.4 + 0.3 * (1 - math.exp(-epoch / 300)) + self.rng.uniform(-0.02, 0.02)
        confidence = 0.1 + 0.7 * (1 - math.exp(-epoch / 400)) + self.rng.uniform(-0.05, 0.05)
        self.series.accuracy.append(accuracy)
        self.series.confidence.append(confidence)

        self._trim_history()

        drawdown_pct = self.rng.uniform(1.0, 3.5)
        trades_per_batch = self.rng.randint(40, 60)
        stats = TrainingStats(
            epochs=epoch,
            final_eq=self.series.equity[-1],
            best_eq=max(self.series.equity),
            final_acc=self.series.accuracy[-1],
            best_acc=max(self.series.accuracy),
            final_loss=self.series.validation_loss[-1],
            min_loss=min(self.series.validation_loss),
            duration_sec=time.time() - self.started_at,
        )
        return TrainingFrame(
            epoch=epoch,
            validation_loss=validation_loss,
            accuracy=accuracy,
            reward=accuracy * 10.0,
            drawdown_pct=drawdown_pct,
            trades_per_batch=trades_per_batch,
            series=self.series,
            stats=stats,
        )

    def _trim_history(self) -> None:
        limit = max(1, self.config.history_len)
        for values in (
            self.series.equity,
            self.series.train_loss,
            self.series.validation_loss,
            self.series.accuracy,
            self.series.confidence,
        ):
            del values[:-limit]
