"""Signal generator mixin -- AI signal generation and persistence."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from database.connection import get_session
from database.models import Signal as SignalModel
from database.repositories.signal_repo import SignalRepository
from shared.exceptions import DataError, PredictionError

if TYPE_CHECKING:
    from main import TradingSystem

logger = logging.getLogger("main")


class SignalGeneratorMixin:
    """AI signal generation and signal persistence."""

    async def _generate_signal(self: TradingSystem, df, mtf_data=None) -> dict | None:
        """Generate AI trading signal using XGBoost + LightGBM ensemble."""
        try:
            # Intentional lazy-load: AIPredictor imports heavy ML libs
            if self._ai_predictor is None:
                from ai_engine.prediction.predictor import AIPredictor

                self._ai_predictor = AIPredictor(
                    saved_models_dir="ai_engine/saved_models",
                    min_confidence=self.settings.min_confidence,
                )

            if self._ai_predictor.is_ready or self._ai_predictor.load():
                # Use pre-fetched MTF data or fetch now
                candle_data = mtf_data
                if candle_data is None:
                    candle_data = await self.data.get_multi_timeframe_data(
                        timeframes=self.settings.timeframes,
                    )
                signal = await self._ai_predictor.predict(
                    candle_data=candle_data,
                    primary_timeframe="5m",
                )
                signal = self._apply_autonomy_rollout(signal)
                # MiroFish veto check (Phase 6, D-06 to D-09)
                if (
                    signal
                    and signal.get("action") not in (None, "HOLD")
                    and self.settings.mirofish_enabled
                    and self._mirofish_client is not None
                ):
                    signal = self._mirofish_client.check_veto(signal)
                return signal
        except (PredictionError, DataError) as e:
            logger.warning("AI engine error: %s", e)
        except Exception as e:
            logger.exception("AI engine failed unexpectedly: %s", e)

        # Fallback HOLD -- the actual cause is logged above.
        return {"action": "HOLD", "confidence": 0.0}

    def _apply_autonomy_rollout(self: TradingSystem, signal: dict | None) -> dict | None:
        """Optionally score the decision-head candidate beside the champion signal."""
        if signal is None:
            return None
        settings = getattr(self, "settings", None)
        mode = str(
            getattr(settings, "autonomy_rollout_mode", None)
            or getattr(settings, "decision_head_rollout_mode", None)
            or "disabled"
        )
        if mode == "disabled":
            return signal

        try:
            from ai_engine.prediction.decision_head import (
                DecisionHeadRuntime,
                apply_autonomy_rollout,
            )

            runtime = getattr(self, "_decision_head_runtime", None)
            if runtime is None:
                runtime = DecisionHeadRuntime(enabled=True)
                setattr(self, "_decision_head_runtime", runtime)
            candidate = runtime.predict_from_signal(signal)
            selected, _metadata = apply_autonomy_rollout(
                signal,
                candidate,
                mode=mode,
            )
            return selected
        except Exception as exc:
            logger.warning("Decision-head rollout failed: %s", exc)
            return signal

    async def _save_signal(
        self: TradingSystem, signal: dict, executed: bool, rejection_reason: str = "",
    ) -> None:
        """Persist signal to database."""
        try:
            sig = SignalModel(
                action=signal["action"],
                confidence=signal.get("confidence", 0),
                trade_score=signal.get("trade_score"),
                entry_price=signal.get("entry_price"),
                stop_loss=signal.get("stop_loss"),
                take_profit=signal.get("take_profit"),
                model_votes=signal.get("model_votes"),
                reasoning=signal.get("reasoning"),
                top_features=signal.get("top_features"),
                was_executed=executed,
                rejection_reason=rejection_reason or None,
                timeframe="5m",
            )

            async with get_session() as session:
                repo = SignalRepository(session)
                await repo.add(sig)
        except Exception as e:
            logger.error("Failed to save signal to DB: %s", e)
