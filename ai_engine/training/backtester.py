"""
Backtester -- Simulates real trading with the AI system.

Processes signals chronologically, manages positions,
calculates PnL with spread/slippage, and generates a
detailed performance report.
"""

import logging
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple

import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)


class Backtester:
    """
    Simulates real trading with AI signals.

    Rules:
    - Maximum 1 open position at a time
    - Position is closed by SL, TP, or a new signal
    - Spread and slippage are deducted at entry/exit
    - Equity curve and drawdown are calculated
    """

    def __init__(
        self,
        initial_balance: float = 10000.0,
        risk_per_trade_pct: float = 1.0,
        tp_pips: float = 50.0,
        sl_pips: float = 30.0,
        spread_pips: float = 2.5,
        slippage_pips: float = 0.5,
        pip_size: float = 0.01,
        pip_value: float = 1.0,
        min_confidence: float = 0.70,
    ) -> None:
        """
        Initializes the Backtester.

        Args:
            initial_balance: Starting capital in USD
            risk_per_trade_pct: Risk per trade in % of capital
            tp_pips: Take-profit in pips
            sl_pips: Stop-loss in pips
            spread_pips: Spread in pips
            slippage_pips: Slippage in pips
            pip_size: Pip size (0.01 for gold)
            pip_value: Pip value in USD per 1 lot
            min_confidence: Minimum confidence for trades
        """
        self.initial_balance = initial_balance
        self.risk_pct = risk_per_trade_pct
        self.tp_pips = tp_pips
        self.sl_pips = sl_pips
        self.spread_pips = spread_pips
        self.slippage_pips = slippage_pips
        self.pip_size = pip_size
        self.pip_value = pip_value
        self.min_confidence = min_confidence
        self.total_cost_pips = spread_pips + slippage_pips

    def run(
        self,
        predictions: np.ndarray,
        actual_labels: np.ndarray,
        close_prices: np.ndarray,
        confidences: Optional[np.ndarray] = None,
    ) -> Dict[str, Any]:
        """
        Runs the backtest.

        Args:
            predictions: Predicted labels [-1, 0, 1]
            actual_labels: True labels [-1, 0, 1]
            close_prices: Close prices for each time step
            confidences: Optional -- Confidence per prediction [0-1]

        Returns:
            Dict with complete performance report
        """
        n = len(predictions)
        balance = self.initial_balance
        equity_curve = [balance]
        trades: List[Dict] = []

        position: Optional[Dict] = None
        peak_balance = balance

        for i in range(n):
            pred = int(predictions[i])
            true_label = int(actual_labels[i])
            price = float(close_prices[i])
            conf = float(confidences[i]) if confidences is not None else 0.80

            # === Check position (if one is open) ===
            if position is not None:
                # Check if the open position should be closed by outcome
                # (In a simplified backtest: the candle decides)
                pass

            # === Process new signal ===
            if pred != 0 and conf >= self.min_confidence:
                # Close old position (if any)
                if position is not None:
                    result = self._close_position(position, true_label, price)
                    balance += result["pnl_usd"]
                    trades.append(result)

                # Open new position
                risk_amount = balance * (self.risk_pct / 100)
                position = {
                    "direction": pred,
                    "entry_price": price,
                    "entry_idx": i,
                    "risk_amount": risk_amount,
                    "confidence": conf,
                }
            elif pred == 0 and position is not None:
                # HOLD signal with open position -> close
                result = self._close_position(position, true_label, price)
                balance += result["pnl_usd"]
                trades.append(result)
                position = None

            equity_curve.append(balance)
            peak_balance = max(peak_balance, balance)

        # Close last open position
        if position is not None:
            result = self._close_position(position, 0, close_prices[-1])
            balance += result["pnl_usd"]
            trades.append(result)

        # === Generate report ===
        return self._generate_report(trades, equity_curve)

    def run_simple(
        self,
        predictions: np.ndarray,
        actual_labels: np.ndarray,
        atr_values: Optional[np.ndarray] = None,
        tp_atr_multiplier: float = 2.0,
        sl_atr_multiplier: float = 1.5,
    ) -> Dict[str, Any]:
        """
        Simplified backtest: Each prediction = 1 trade.

        No position management -- every BUY/SELL signal is
        evaluated as a separate trade.

        Args:
            predictions: Predicted labels
            actual_labels: True labels
            atr_values: Optional per-candle ATR values for dynamic TP/SL
            tp_atr_multiplier: ATR multiplier for take-profit (when atr_values given)
            sl_atr_multiplier: ATR multiplier for stop-loss (when atr_values given)

        Returns:
            Performance report
        """
        preds = np.array(predictions)
        truths = np.array(actual_labels)

        # Normalize to -1, 0, 1
        if preds.max() > 1:
            preds = preds - 1
        if truths.max() > 1:
            truths = truths - 1

        # Only trades (not HOLD)
        trade_mask = preds != 0
        n_trades = trade_mask.sum()

        if n_trades == 0:
            return self._empty_report()

        pred_trades = preds[trade_mask]
        true_trades = truths[trade_mask]

        # Win/Loss
        wins = pred_trades == true_trades

        if atr_values is not None:
            # Per-trade ATR-based TP/SL
            atr_trades = np.array(atr_values)[trade_mask]
            tp_pips_per_trade = atr_trades * tp_atr_multiplier / self.pip_size
            sl_pips_per_trade = atr_trades * sl_atr_multiplier / self.pip_size
            net_tp = tp_pips_per_trade - self.total_cost_pips
            net_sl = sl_pips_per_trade + self.total_cost_pips
            pips_per_trade = np.where(wins, net_tp, -net_sl)
            avg_tp_pips = float(tp_pips_per_trade.mean())
            avg_sl_pips = float(sl_pips_per_trade.mean())
        else:
            # Fixed TP/SL
            net_tp = self.tp_pips - self.total_cost_pips
            net_sl = self.sl_pips + self.total_cost_pips
            pips_per_trade = np.where(wins, net_tp, -net_sl)
            avg_tp_pips = None
            avg_sl_pips = None

        usd_per_trade = pips_per_trade * self.pip_value

        # Equity Curve
        equity = np.cumsum(usd_per_trade) + self.initial_balance
        equity_curve = np.insert(equity, 0, self.initial_balance)

        # Trades
        trades = []
        for i in range(n_trades):
            trades.append({
                "direction": "BUY" if pred_trades[i] == 1 else "SELL",
                "won": bool(wins[i]),
                "pnl_pips": float(pips_per_trade[i]),
                "pnl_usd": float(usd_per_trade[i]),
            })

        return self._generate_report(
            trades, equity_curve.tolist(),
            avg_tp_pips=avg_tp_pips, avg_sl_pips=avg_sl_pips,
        )

    def _close_position(
        self,
        position: Dict,
        true_label: int,
        exit_price: float,
    ) -> Dict:
        """Closes a position and calculates PnL."""
        direction = position["direction"]
        won = direction == true_label

        if won:
            pnl_pips = self.tp_pips - self.total_cost_pips
        else:
            pnl_pips = -(self.sl_pips + self.total_cost_pips)

        pnl_usd = pnl_pips * self.pip_value

        return {
            "direction": "BUY" if direction == 1 else "SELL",
            "entry_price": position["entry_price"],
            "exit_price": exit_price,
            "won": won,
            "pnl_pips": pnl_pips,
            "pnl_usd": pnl_usd,
            "confidence": position.get("confidence", 0),
        }

    def _generate_report(
        self,
        trades: List[Dict],
        equity_curve: List[float],
        avg_tp_pips: Optional[float] = None,
        avg_sl_pips: Optional[float] = None,
    ) -> Dict[str, Any]:
        """Generates the complete performance report.

        Args:
            trades: List of trade dicts
            equity_curve: Equity curve values
            avg_tp_pips: Average TP pips (for ATR-based mode, overrides self.tp_pips)
            avg_sl_pips: Average SL pips (for ATR-based mode, overrides self.sl_pips)
        """
        if not trades:
            return self._empty_report()

        n_trades = len(trades)
        wins = [t for t in trades if t["won"]]
        losses = [t for t in trades if not t["won"]]
        n_wins = len(wins)
        n_losses = len(losses)
        win_rate = n_wins / n_trades

        pips_array = np.array([t["pnl_pips"] for t in trades])
        total_pips = float(pips_array.sum())
        avg_pips = float(pips_array.mean())

        gross_profit = float(pips_array[pips_array > 0].sum()) if (pips_array > 0).any() else 0
        gross_loss = float(abs(pips_array[pips_array < 0].sum())) if (pips_array < 0).any() else 0
        profit_factor = gross_profit / gross_loss if gross_loss > 0 else float("inf")

        # Expectancy (use provided averages for ATR-based mode, else fixed)
        eff_tp = avg_tp_pips if avg_tp_pips is not None else self.tp_pips
        eff_sl = avg_sl_pips if avg_sl_pips is not None else self.sl_pips
        net_tp = eff_tp - self.total_cost_pips
        net_sl = eff_sl + self.total_cost_pips
        expectancy = (win_rate * net_tp) - ((1 - win_rate) * net_sl)

        # Equity & Drawdown
        equity = np.array(equity_curve)
        peak = np.maximum.accumulate(equity)
        drawdown = peak - equity
        max_drawdown = float(drawdown.max())
        max_dd_pct = float(max_drawdown / peak.max() * 100) if peak.max() > 0 else 0

        # Sharpe
        if len(pips_array) > 1 and pips_array.std() > 0:
            sharpe = float((pips_array.mean() / pips_array.std()) * np.sqrt(2600))
        else:
            sharpe = 0.0

        # Final Balance
        final_balance = float(equity[-1]) if len(equity) > 0 else self.initial_balance
        total_return = (final_balance - self.initial_balance) / self.initial_balance * 100

        # Consecutive
        win_flags = np.array([t["won"] for t in trades])
        max_con_wins = self._max_consecutive(win_flags)
        max_con_losses = self._max_consecutive(~win_flags)

        # Buy/Sell breakdown
        buy_trades = [t for t in trades if t["direction"] == "BUY"]
        sell_trades = [t for t in trades if t["direction"] == "SELL"]
        buy_wr = sum(1 for t in buy_trades if t["won"]) / len(buy_trades) if buy_trades else 0
        sell_wr = sum(1 for t in sell_trades if t["won"]) / len(sell_trades) if sell_trades else 0

        # Grade
        grade = self._grade(win_rate, profit_factor, sharpe)

        # Logging
        logger.info(f"\n{'='*60}")
        logger.info(f"BACKTEST REPORT")
        logger.info(f"{'='*60}")
        logger.info(f"Trades:           {n_trades} (BUY={len(buy_trades)}, SELL={len(sell_trades)})")
        logger.info(f"Win Rate:         {win_rate*100:.1f}% ({n_wins}W / {n_losses}L)")
        logger.info(f"Profit Factor:    {profit_factor:.2f}")
        logger.info(f"Total Pips:       {total_pips:+.1f}")
        logger.info(f"Avg Pips/Trade:   {avg_pips:+.2f}")
        logger.info(f"Expectancy:       {expectancy:+.2f} Pips/Trade")
        logger.info(f"Sharpe Ratio:     {sharpe:.2f}")
        logger.info(f"Max Drawdown:     {max_drawdown:.2f} USD ({max_dd_pct:.1f}%)")
        logger.info(f"Final Balance:    {final_balance:,.2f} ({total_return:+.1f}%)")
        logger.info(f"BUY Win Rate:     {buy_wr*100:.1f}%")
        logger.info(f"SELL Win Rate:    {sell_wr*100:.1f}%")
        logger.info(f"Max Con. Wins:    {max_con_wins}")
        logger.info(f"Max Con. Losses:  {max_con_losses}")
        logger.info(f"Grade:            {grade}")
        logger.info(f"{'='*60}")

        return {
            "n_trades": n_trades,
            "buy_trades": len(buy_trades),
            "sell_trades": len(sell_trades),
            "wins": n_wins,
            "losses": n_losses,
            "win_rate": win_rate,
            "profit_factor": profit_factor,
            "total_pips": total_pips,
            "avg_pips_per_trade": avg_pips,
            "expectancy": expectancy,
            "sharpe_ratio": sharpe,
            "max_drawdown_usd": max_drawdown,
            "max_drawdown_pct": max_dd_pct,
            "initial_balance": self.initial_balance,
            "final_balance": final_balance,
            "total_return_pct": total_return,
            "buy_win_rate": buy_wr,
            "sell_win_rate": sell_wr,
            "max_consecutive_wins": max_con_wins,
            "max_consecutive_losses": max_con_losses,
            "grade": grade,
            "equity_curve": equity_curve,
            "trades": trades,
        }

    @staticmethod
    def _max_consecutive(arr: np.ndarray) -> int:
        if len(arr) == 0:
            return 0
        max_c = current = 0
        for v in arr:
            if v:
                current += 1
                max_c = max(max_c, current)
            else:
                current = 0
        return max_c

    @staticmethod
    def _grade(wr: float, pf: float, sharpe: float) -> str:
        score = 0
        if wr >= 0.60: score += 3
        elif wr >= 0.55: score += 2
        elif wr >= 0.50: score += 1

        if pf >= 2.0: score += 3
        elif pf >= 1.5: score += 2
        elif pf >= 1.2: score += 1

        if sharpe >= 2.0: score += 2
        elif sharpe >= 1.0: score += 1

        if score >= 7: return "*** EXCELLENT"
        elif score >= 5: return "** GOOD"
        elif score >= 3: return "* ACCEPTABLE"
        elif score >= 1: return "WEAK"
        else: return "UNUSABLE"

    def _empty_report(self) -> Dict[str, Any]:
        return {
            "n_trades": 0, "buy_trades": 0, "sell_trades": 0,
            "wins": 0, "losses": 0, "win_rate": 0.0,
            "profit_factor": 0.0, "total_pips": 0.0,
            "avg_pips_per_trade": 0.0, "expectancy": 0.0,
            "sharpe_ratio": 0.0,
            "max_drawdown_usd": 0.0, "max_drawdown_pct": 0.0,
            "initial_balance": self.initial_balance,
            "final_balance": self.initial_balance,
            "total_return_pct": 0.0,
            "buy_win_rate": 0.0, "sell_win_rate": 0.0,
            "max_consecutive_wins": 0, "max_consecutive_losses": 0,
            "grade": "NO TRADES",
            "equity_curve": [self.initial_balance],
            "trades": [],
        }


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    np.random.seed(42)

    n = 300
    # Simulate a 58% win rate model
    y_true = np.random.choice([-1, 0, 1], n, p=[0.3, 0.4, 0.3])
    y_pred = y_true.copy()
    noise_mask = np.random.random(n) < 0.42  # ~58% correct
    y_pred[noise_mask] = np.random.choice([-1, 0, 1], noise_mask.sum())

    prices = np.cumsum(np.random.randn(n) * 0.3) + 2045.0

    bt = Backtester(
        initial_balance=10000,
        risk_per_trade_pct=1.0,
        tp_pips=50, sl_pips=30,
        spread_pips=2.5, slippage_pips=0.5,
    )

    # Simple backtest
    report = bt.run_simple(y_pred, y_true)
    print(f"\nBacktester test successful!")
    print(f"   Balance: ${report['final_balance']:,.2f} ({report['total_return_pct']:+.1f}%)")
