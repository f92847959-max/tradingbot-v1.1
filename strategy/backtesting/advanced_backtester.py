import logging
import numpy as np
import pandas as pd
from typing import Any, Dict, List, Optional
from ai_engine.training.backtester import Backtester

logger = logging.getLogger(__name__)

class AdvancedBacktester(Backtester):
    """
    Extended backtester focused on realism:
    - Dynamic slippage (based on volatility or randomness)
    - Variable spreads (simulates news events or liquid/illiquid phases)
    - Limit order simulation (optional)
    """

    def __init__(
        self,
        initial_balance: float = 10000.0,
        risk_per_trade_pct: float = 1.0,
        tp_pips: float = 50.0,
        sl_pips: float = 30.0,
        base_spread_pips: float = 2.5,
        base_slippage_pips: float = 0.5,
        pip_size: float = 0.01,
        pip_value: float = 1.0,
        min_confidence: float = 0.70,
        volatility_factor: float = 2.0, # Multiplier for slippage during high volatility
    ) -> None:
        super().__init__(
            initial_balance=initial_balance,
            risk_per_trade_pct=risk_per_trade_pct,
            tp_pips=tp_pips,
            sl_pips=sl_pips,
            spread_pips=base_spread_pips,
            slippage_pips=base_slippage_pips,
            pip_size=pip_size,
            pip_value=pip_value,
            min_confidence=min_confidence
        )
        self.base_spread = base_spread_pips
        self.base_slippage = base_slippage_pips
        self.volatility_factor = volatility_factor

    def run_reality_check(
        self,
        predictions: np.ndarray,
        actual_labels: np.ndarray,
        volatility_data: Optional[np.ndarray] = None, # e.g. ATR or standard deviation
    ) -> Dict[str, Any]:
        """
        Runs a backtest with dynamic costs.
        Simulates the harsh conditions of the real market.
        """
        preds = np.array(predictions)
        truths = np.array(actual_labels)

        # Normalize to -1, 0, 1
        if preds.min() >= 0: preds = preds - 1
        if truths.min() >= 0: truths = truths - 1

        trade_mask = preds != 0
        n_trades = trade_mask.sum()

        if n_trades == 0:
            return self._empty_report()

        pred_trades = preds[trade_mask]
        true_trades = truths[trade_mask]

        # Simulate volatility if not provided (random noise)
        if volatility_data is None:
            # 0 = normal, 1 = high (e.g. news)
            volatility_data = np.random.choice([0, 1], size=n_trades, p=[0.85, 0.15])
        else:
            volatility_data = volatility_data[trade_mask]

        # Calculate dynamic costs
        # During news (volatility=1) we multiply spread by 2.5 and slippage by 8
        dynamic_spreads = np.where(volatility_data == 1, self.base_spread * 2.5, self.base_spread)
        dynamic_slippage = np.where(volatility_data == 1, self.base_slippage * 8.0, self.base_slippage * 1.5)

        total_costs = dynamic_spreads + dynamic_slippage

        # Win/Loss
        wins = pred_trades == true_trades

        # Calculation: TP becomes harder to reach, SL triggers more easily (due to costs)
        pips_per_trade = np.where(wins, self.tp_pips - total_costs, -(self.sl_pips + total_costs))
        usd_per_trade = pips_per_trade * self.pip_value

        # Equity Curve
        equity = np.cumsum(usd_per_trade) + self.initial_balance
        equity_curve = np.insert(equity, 0, self.initial_balance)

        # Trades list for report
        trades = []
        for i in range(n_trades):
            trades.append({
                "direction": "BUY" if pred_trades[i] == 1 else "SELL",
                "won": bool(wins[i]),
                "pnl_pips": float(pips_per_trade[i]),
                "pnl_usd": float(usd_per_trade[i]),
                "is_volatile": bool(volatility_data[i]),
                "cost_pips": float(total_costs[i])
            })

        logger.info(f"REALITY CHECK: Simulating {n_trades} trades with variable costs...")
        logger.info(f"   Average cost: {total_costs.mean():.2f} Pips (Base: {self.base_spread + self.base_slippage:.2f})")

        return self._generate_report(trades, equity_curve.tolist())

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(message)s")

    # Test data
    n = 200
    y_true = np.random.choice([-1, 1], n)
    y_pred = y_true.copy()
    # 60% win rate in theory
    noise = np.random.random(n) < 0.40
    y_pred[noise] = -y_pred[noise]

    bt = AdvancedBacktester(base_spread_pips=2.5, base_slippage_pips=0.5)

    print("\n--- STANDARD BACKTEST ---")
    report_std = bt.run_simple(y_pred, y_true)

    print("\n--- BRUTAL REALITY CHECK (Dynamic Costs) ---")
    report_real = bt.run_reality_check(y_pred, y_true)

    diff = report_std['final_balance'] - report_real['final_balance']
    print(f"\nProfit loss due to reality simulation: ${diff:,.2f}")
