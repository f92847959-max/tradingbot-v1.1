"""Strategy manager — coordinates signal evaluation and trade approval."""

import logging
from datetime import datetime, timezone
from typing import Optional

import pandas as pd

from strategy.session_filter import SessionFilter
from strategy.trade_scorer import TradeScorer
from strategy.multi_timeframe import check_alignment
from strategy.regime_detector import RegimeDetector, MarketRegime, RegimeState
from strategy.regime_params import get_regime_params
from shared.constants import MIN_TRADE_SCORE, MIN_AI_CONFIDENCE

logger = logging.getLogger(__name__)


class StrategyManager:
    """Evaluates AI signals and decides whether to execute a trade.

    Pipeline:
    1. Check if signal action is not HOLD
    2. Fast reject: confidence < base threshold
    3. Check session filter (trading hours)
    4. Calculate multi-TF alignment
    5. Extract indicator values
    6. Detect market regime
    7. Re-check confidence against regime threshold
    8. Calculate composite trade score (regime-aware)
    9. Approve if score >= regime min_score
    """

    def __init__(
        self,
        min_score: int = MIN_TRADE_SCORE,
        min_confidence: float = MIN_AI_CONFIDENCE,
    ) -> None:
        self.min_score = min_score
        self.min_confidence = min_confidence
        self.session = SessionFilter()
        self.scorer = TradeScorer()
        self.regime_detector = RegimeDetector()

    def evaluate(
        self,
        signal: dict,
        mtf_data: Optional[dict[str, pd.DataFrame]] = None,
        dt: Optional[datetime] = None,
    ) -> Optional[dict]:
        """Evaluate a signal and return enriched signal dict or None.

        Args:
            signal: Signal dict from AI engine or fallback strategy.
                    Expected keys: action, confidence, entry_price, stop_loss,
                                   take_profit, reasoning (optional)
            mtf_data: Dict of timeframe -> DataFrame with indicators.
            dt: Datetime to use for session check (default: now UTC).

        Returns:
            Enriched signal dict with 'trade_score' key if approved.
            None if signal is rejected.
        """
        if dt is None:
            dt = datetime.now(timezone.utc)

        action = signal.get("action", "HOLD").upper()
        confidence = float(signal.get("confidence", 0.0))

        # 1. Reject HOLD
        if action == "HOLD":
            logger.debug("Signal rejected: action=HOLD")
            return None

        # 2. Check confidence
        if confidence < self.min_confidence:
            logger.debug(
                "Signal rejected: confidence %.3f < %.3f threshold",
                confidence, self.min_confidence,
            )
            return None

        # 3. Session filter
        if not self.session.is_active(dt):
            logger.debug("Signal rejected: outside trading hours (%s)", dt.strftime("%H:%M UTC"))
            return None

        current_session = self.session.current_session(dt)

        # 4. Multi-TF alignment
        if mtf_data:
            mtf_alignment = check_alignment(mtf_data, direction=action)
        else:
            mtf_alignment = 0.5  # neutral fallback

        # 5. Extract indicator values for scoring
        adx = None
        atr = None
        atr_average = None
        if mtf_data and "5m" in mtf_data:
            df = mtf_data["5m"]
            if not df.empty:
                last = df.iloc[-1]
                adx = float(last.get("adx", 0) or 0) or None
                atr = float(last.get("atr_14", 0) or 0) or None
                if atr and len(df) >= 20:
                    atr_average = float(df["atr_14"].tail(20).mean()) if "atr_14" in df.columns else None

        # 6. Detect market regime
        regime_state: Optional[RegimeState] = None
        regime = MarketRegime.RANGING  # safest default fallback
        if mtf_data and "5m" in mtf_data:
            df = mtf_data["5m"]
            # Warmup: need at least 50 candles AND a non-empty atr_14
            # column. A short window can produce NaN-only ATR which
            # would otherwise leak a bogus RANGING classification.
            has_atr = (
                "atr_14" in df.columns
                and not df["atr_14"].isna().all()
            )
            if not df.empty and len(df) >= 50 and has_atr:
                regime_state = self.regime_detector.detect(df)
                regime = regime_state.regime

        # Get regime-specific parameters
        regime_params = get_regime_params(regime)
        effective_min_confidence = regime_params["min_confidence"]
        effective_min_score = regime_params["min_trade_score"]

        # 7. Re-check confidence against regime-specific threshold
        if confidence < effective_min_confidence:
            logger.debug(
                "Signal rejected: confidence %.3f < %.3f regime threshold (%s)",
                confidence, effective_min_confidence, regime.value,
            )
            return None

        # 8. Composite score (regime-aware)
        trade_score = self.scorer.score(
            signal=signal,
            mtf_alignment=mtf_alignment,
            session=current_session,
            adx=adx,
            atr=atr,
            atr_average=atr_average,
            regime=regime,
        )

        if trade_score < effective_min_score:
            logger.info(
                "Signal rejected: score %d < %d regime minimum (action=%s, conf=%.3f, session=%s, align=%.2f, regime=%s)",
                trade_score, effective_min_score, action, confidence,
                current_session, mtf_alignment, regime.value,
            )
            return None

        # Approved — return enriched signal
        approved = {
            **signal,
            "trade_score": trade_score,
            "session": current_session,
            "mtf_alignment": round(mtf_alignment, 3),
            "regime": regime.value,
            "regime_confidence": regime_state.confidence if regime_state else 0.0,
        }
        logger.info(
            "Signal APPROVED: action=%s, score=%d, conf=%.3f, session=%s, align=%.2f, regime=%s",
            action, trade_score, confidence, current_session, mtf_alignment, regime.value,
        )
        return approved
