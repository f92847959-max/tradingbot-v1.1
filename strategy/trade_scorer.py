"""Trade scorer — evaluates signal quality on a 0-100 scale."""

import logging
from typing import Optional

from strategy.entry_calculator import risk_reward_ratio
from strategy.regime_detector import MarketRegime

logger = logging.getLogger(__name__)


class TradeScorer:
    """Scores a trade signal 0-100 based on 6 weighted criteria.

    Score breakdown (max 100):
      - AI confidence        0-25  (confidence * 25)
      - Multi-TF alignment   0-20  (alignment * 20)
      - Trend strength       0-15  (ADX-based)
      - Session quality      0-15  (London/Overlap > NY > Off)
      - Volatility           0-15  (ATR in optimal range)
      - Risk/Reward          0-10  (RR >= 2.0 = full score)

    Minimum score to execute: 60
    """

    SESSION_SCORES = {
        "Overlap": 15,
        "London": 13,
        "NewYork": 10,
        "Off": 0,
    }

    def score(
        self,
        signal: dict,
        mtf_alignment: float = 0.5,
        session: str = "London",
        adx: Optional[float] = None,
        atr: Optional[float] = None,
        atr_average: Optional[float] = None,
        regime: Optional[MarketRegime] = None,
    ) -> int:
        """Calculate composite trade score.

        Args:
            signal: Signal dict with keys: confidence, entry_price, stop_loss, take_profit
            mtf_alignment: Multi-timeframe alignment score 0.0-1.0
            session: Current session name
            adx: Current ADX value (trend strength 0-100)
            atr: Current ATR value
            atr_average: Average ATR over last N candles (for volatility check)

        Returns:
            Integer score 0-100
        """
        total = 0.0

        # 1. AI Confidence (0-25)
        confidence = float(signal.get("confidence", 0.0))
        confidence_score = min(confidence * 25, 25.0)
        total += confidence_score

        # 2. Multi-TF Alignment (0-20)
        alignment_score = min(mtf_alignment * 20, 20.0)
        total += alignment_score

        # 3. Trend Strength via ADX (0-15) — regime-adjusted weights
        if adx is not None:
            if regime == MarketRegime.TRENDING:
                # Boost trend scores in trending regime (ADX confirms)
                if adx >= 40:
                    trend_score = 15.0
                elif adx >= 25:
                    trend_score = 12.0
                elif adx >= 15:
                    trend_score = 7.0
                else:
                    trend_score = 0.0
            elif regime == MarketRegime.RANGING:
                # Reduce trend importance in ranging regime
                if adx >= 40:
                    trend_score = 10.0
                elif adx >= 25:
                    trend_score = 7.0
                elif adx >= 15:
                    trend_score = 3.0
                else:
                    trend_score = 0.0
            else:
                # VOLATILE or None: original weights
                if adx >= 40:
                    trend_score = 15.0
                elif adx >= 25:
                    trend_score = 10.0
                elif adx >= 15:
                    trend_score = 5.0
                else:
                    trend_score = 0.0
        else:
            trend_score = 7.5  # neutral when unknown
        total += trend_score

        # 4. Session Quality (0-15)
        session_score = self.SESSION_SCORES.get(session, 0)
        total += session_score

        # 5. Volatility — ATR in optimal range (0-15) — regime-adjusted
        if atr is not None and atr_average is not None and atr_average > 0:
            ratio = atr / atr_average
            if regime == MarketRegime.VOLATILE:
                # Narrow ideal band and cap score in volatile regime
                if 0.8 <= ratio <= 1.2:
                    vol_score = 10.0
                elif 0.5 <= ratio <= 2.0:
                    vol_score = 5.0
                else:
                    vol_score = 0.0
            else:
                # TRENDING, RANGING, or None: original weights
                if 0.7 <= ratio <= 1.5:
                    vol_score = 15.0
                elif 0.5 <= ratio <= 2.0:
                    vol_score = 8.0
                else:
                    vol_score = 0.0
        else:
            vol_score = 7.5  # neutral when unknown
        total += vol_score

        # 6. Risk/Reward Ratio (0-10)
        entry = signal.get("entry_price", 0.0)
        sl = signal.get("stop_loss")
        tp = signal.get("take_profit")
        if entry and sl and tp:
            rr = risk_reward_ratio(float(entry), float(sl), float(tp))
            if rr >= 2.5:
                rr_score = 10.0
            elif rr >= 2.0:
                rr_score = 8.0
            elif rr >= 1.5:
                rr_score = 5.0
            else:
                rr_score = 0.0
        else:
            rr_score = 5.0  # neutral when SL/TP not set
        total += rr_score

        result = int(round(total))
        logger.debug(
            "Trade score: %d (conf=%.1f, align=%.1f, trend=%.1f, session=%d, vol=%.1f, rr=%.1f)",
            result, confidence_score, alignment_score, trend_score,
            session_score, vol_score, rr_score,
        )
        return result
