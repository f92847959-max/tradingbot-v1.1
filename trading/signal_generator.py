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

                # Elliott Wave structural filter (Phase 14-03, EWT-04) --
                # optional & governable; only BUY signals are evaluated.
                if (
                    signal
                    and signal.get("action") == "BUY"
                    and getattr(self.settings, "ew_filter_enabled", False)
                ):
                    ew_df = self._resolve_primary_df(candle_data, "5m")
                    if ew_df is not None:
                        signal = apply_ew_filter(
                            signal,
                            ew_df,
                            enabled=True,
                            veto_completion=float(
                                getattr(self.settings, "ew_veto_completion", 0.8)
                            ),
                        )

                # Dow Theory structural filter (Phase 14.1, DOW-02) --
                # optional & governable; only BUY signals are evaluated.
                if (
                    signal
                    and signal.get("action") == "BUY"
                    and getattr(self.settings, "dow_filter_enabled", False)
                ):
                    dow_df = self._resolve_primary_df(candle_data, "5m")
                    if dow_df is not None:
                        signal = apply_dow_filter(signal, dow_df, enabled=True)
                return signal
        except (PredictionError, DataError) as e:
            logger.warning("AI engine error: %s", e)
        except Exception as e:
            logger.exception("AI engine failed unexpectedly: %s", e)

        # Fallback HOLD -- the actual cause is logged above.
        return {"action": "HOLD", "confidence": 0.0}

    @staticmethod
    def _resolve_primary_df(candle_data, primary_timeframe: str = "5m"):
        """Return the primary-timeframe DataFrame from multi-timeframe data.

        ``get_multi_timeframe_data`` returns ``dict[str, DataFrame]``; fall back
        to the first available frame, or pass through a bare DataFrame. Returns
        ``None`` when nothing usable is present (the filter then no-ops).
        """
        try:
            if isinstance(candle_data, dict):
                df = candle_data.get(primary_timeframe)
                if df is None and candle_data:
                    df = next(iter(candle_data.values()))
                return df
            return candle_data
        except Exception:
            return None

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


# ---------------------------------------------------------------------------
# Elliott Wave signal filter (Phase 14-03, EWT-04)
#
# Pure decision core + thin detection shell.  The BUY veto/support mapping is
# expressed entirely in ``_decide_from_wave_context`` (no I/O, fully unit
# testable); ``evaluate_ew_buy_filter`` runs the Elliott Wave engine and feeds
# the numeric wave state into that core; ``apply_ew_filter`` applies the verdict
# to a signal dict.  Disabled by default -- governed by ``settings``.
# ---------------------------------------------------------------------------


def _decide_from_wave_context(
    pattern_name: str,
    is_motive: bool,
    wave_number: int,
    completion: float,
    veto_completion: float,
) -> tuple[str, str]:
    """Map an Elliott Wave count to a BUY verdict.

    Returns ``(decision, reason)`` where decision is ``"veto"`` (correction
    imminent), ``"support"`` (fresh impulse leg starting), or ``"neutral"``.
    """
    if pattern_name == "NONE":
        return ("neutral", "no Elliott Wave count available")

    if is_motive:
        if wave_number == 3 and completion >= veto_completion:
            return ("veto", f"{pattern_name} W3 ~{completion:.0%} done -- W4 correction imminent")
        if wave_number == 5 and completion >= veto_completion:
            return ("veto", f"{pattern_name} W5 ~{completion:.0%} done -- ABC correction imminent")
        if wave_number == 2:
            return ("support", f"{pattern_name} W2 done -- W3 impulse starting")
        if wave_number == 4:
            return ("support", f"{pattern_name} W4 done -- W5 starting")
        return ("neutral", f"{pattern_name} motive wave {wave_number} ({completion:.0%} done)")

    # Corrective patterns (zigzag / flat / triangle / complex).
    if wave_number == 1:  # Wave A in progress
        return ("veto", f"{pattern_name} corrective W-A -- B bounce then C down; BUY risky")
    return ("neutral", f"{pattern_name} corrective wave {wave_number}")


def evaluate_ew_buy_filter(candle_df, veto_completion: float) -> tuple[str, str]:
    """Run Elliott Wave detection on ``candle_df`` and return ``(decision, reason)``.

    Reuses the causal feature extractor from
    :mod:`ai_engine.features.elliott_wave_features` (single source of truth for
    wave state, incl. the T-14-06 window cap) and decodes its integer pattern
    encoding back to readable :class:`~ai_engine.elliott_wave.models.PatternType`
    names for the verdict reason.  Never raises -- on any failure the extractor
    returns zeros, which map to a ``"neutral"`` verdict.
    """
    from ai_engine.elliott_wave.models import PatternType
    from ai_engine.features.elliott_wave_features import extract_ew_features

    feats = extract_ew_features(candle_df)

    # Integer encoding mirrors elliott_wave_features._PATTERN_ENCODING.
    pattern_names = {
        0: "NONE",
        1: PatternType.IMPULSE.name,
        2: PatternType.ZIGZAG.name,
        3: PatternType.FLAT.name,
        4: PatternType.TRIANGLE.name,
        5: PatternType.DIAGONAL.name,
        6: PatternType.COMPLEX.name,
    }
    pattern_name = pattern_names.get(int(feats.get("ew_pattern_type", 0)), "NONE")

    return _decide_from_wave_context(
        pattern_name,
        bool(feats.get("ew_is_motive", 0)),
        int(feats.get("ew_wave_number", 0)),
        float(feats.get("ew_completion", 0.0)),
        veto_completion,
    )


def apply_ew_filter(signal, candle_df, *, enabled: bool, veto_completion: float = 0.8):
    """Apply the Elliott Wave structural filter to a signal dict.

    Only ``BUY`` signals are evaluated; ``SELL`` / ``HOLD`` (and ``None``) pass
    through untouched.  A ``veto`` converts the BUY to ``HOLD``; a ``support``
    annotates the signal but leaves the action intact.  The original ``signal``
    dict is never mutated.  No-ops when ``enabled`` is False.
    """
    if not enabled or signal is None:
        return signal
    if signal.get("action") != "BUY":
        return signal

    decision, reason = evaluate_ew_buy_filter(candle_df, veto_completion)
    context = {"decision": decision, "reason": reason}

    if decision == "veto":
        result = dict(signal)
        result["action"] = "HOLD"
        result["ew_vetoed_action"] = "BUY"
        result["ew_filter"] = context
        prior = result.get("reasoning") or ""
        result["reasoning"] = f"{prior} | EW veto: {reason}".strip(" |")
        logger.info("Elliott Wave filter vetoed BUY -> HOLD: %s", reason)
        return result

    result = dict(signal)
    result["ew_filter"] = context
    if decision == "support":
        prior = result.get("reasoning") or ""
        result["reasoning"] = f"{prior} | EW support: {reason}".strip(" |")
    return result


# ---------------------------------------------------------------------------
# Dow Theory signal filter (Phase 14.1, DOW-02)
#
# Same pure-core + detection-shell shape as the EW filter. The primary Dow trend
# gates BUY signals: a DOWN trend vetoes the long (BUY -> HOLD), an UP trend marks
# it supported, RANGE is neutral. Disabled by default (settings.dow_filter_enabled).
# ---------------------------------------------------------------------------


def _decide_from_dow_trend(dow_trend: int) -> tuple[str, str]:
    """Map a Dow primary trend to a BUY verdict.

    ``dow_trend`` uses the DowTrend encoding (0=DOWN, 1=RANGE, 2=UP).
    Returns ``(decision, reason)`` with decision in {veto, support, neutral}.
    """
    if dow_trend == 0:  # DOWN
        return ("veto", "Dow primary trend DOWN -- contradicts BUY")
    if dow_trend == 2:  # UP
        return ("support", "Dow primary trend UP -- confirms BUY")
    return ("neutral", "Dow primary trend RANGE -- no directional read")


def evaluate_dow_buy_filter(candle_df) -> tuple[str, str]:
    """Run Dow trend detection on ``candle_df`` and return ``(decision, reason)``.

    Reuses ``extract_dow_features`` (single source of truth for the Dow trend,
    incl. the T-14.1-01 window cap). Never raises — degenerate input yields a
    RANGE trend, which maps to a neutral verdict.
    """
    from ai_engine.dow_theory import DowTrend
    from ai_engine.features.dow_theory_features import extract_dow_features

    feats = extract_dow_features(candle_df)
    return _decide_from_dow_trend(int(feats.get("dow_trend", int(DowTrend.RANGE))))


def apply_dow_filter(signal, candle_df, *, enabled: bool):
    """Apply the Dow Theory trend filter to a signal dict.

    Only ``BUY`` signals are evaluated; ``SELL`` / ``HOLD`` / ``None`` pass
    through untouched. A ``veto`` (DOWN trend) converts BUY to HOLD; a ``support``
    (UP trend) annotates the signal but keeps the action. The original ``signal``
    is never mutated. No-ops when ``enabled`` is False.
    """
    if not enabled or signal is None:
        return signal
    if signal.get("action") != "BUY":
        return signal

    decision, reason = evaluate_dow_buy_filter(candle_df)
    context = {"decision": decision, "reason": reason}

    if decision == "veto":
        result = dict(signal)
        result["action"] = "HOLD"
        result["dow_vetoed_action"] = "BUY"
        result["dow_filter"] = context
        prior = result.get("reasoning") or ""
        result["reasoning"] = f"{prior} | Dow veto: {reason}".strip(" |")
        logger.info("Dow Theory filter vetoed BUY -> HOLD: %s", reason)
        return result

    result = dict(signal)
    result["dow_filter"] = context
    if decision == "support":
        prior = result.get("reasoning") or ""
        result["reasoning"] = f"{prior} | Dow support: {reason}".strip(" |")
    return result
