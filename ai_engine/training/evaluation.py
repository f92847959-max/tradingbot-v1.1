"""
Evaluation -- Model evaluation with ML AND trading metrics.

ML metrics: Accuracy, Precision, Recall, F1
Trading metrics: Win Rate, Profit Factor, Sharpe Ratio, Max Drawdown, Expectancy
"""

import logging
from typing import Any, Dict, List

import numpy as np

logger = logging.getLogger(__name__)


class ModelEvaluator:
    """
    Evaluates ML models with standard ML metrics AND trading metrics.

    ML metrics show how well the model classifies.
    Trading metrics show whether the system would actually be profitable.
    """

    LABEL_NAMES = {0: "SELL", 1: "HOLD", 2: "BUY"}

    def evaluate(
        self,
        y_true: np.ndarray,
        y_pred: np.ndarray,
        label_space: str = "auto",
        model_name: str = "model",
    ) -> Dict[str, Any]:
        """
        ML evaluation: Accuracy, Precision, Recall, F1.

        Args:
            y_true: True labels (values: -1, 0, 1 or 0, 1, 2)
            y_pred: Predicted labels
            model_name: Name of the model

        Returns:
            Dict with ML metrics
        """
        from sklearn.metrics import (
            accuracy_score,
            classification_report,
            confusion_matrix,
            f1_score,
            precision_score,
            recall_score,
        )

        y_true = self._ensure_mapped(y_true, label_space=label_space)
        y_pred = self._ensure_mapped(y_pred, label_space=label_space)

        accuracy = accuracy_score(y_true, y_pred)
        precision = precision_score(y_true, y_pred, average="weighted", zero_division=0)
        recall = recall_score(y_true, y_pred, average="weighted", zero_division=0)
        f1 = f1_score(y_true, y_pred, average="weighted", zero_division=0)
        conf_matrix = confusion_matrix(y_true, y_pred, labels=[0, 1, 2])
        class_report = classification_report(
            y_true, y_pred,
            labels=[0, 1, 2],
            target_names=["SELL", "HOLD", "BUY"],
            zero_division=0,
            output_dict=True,
        )

        logger.info(f"\n{'='*50}")
        logger.info(f"ML Evaluation: {model_name}")
        logger.info(f"{'='*50}")
        logger.info(f"Accuracy:  {accuracy:.4f} ({accuracy*100:.1f}%)")
        logger.info(f"Precision: {precision:.4f}")
        logger.info(f"Recall:    {recall:.4f}")
        logger.info(f"F1-Score:  {f1:.4f}")
        logger.info("\nConfusion Matrix:")
        logger.info("         SELL  HOLD  BUY")
        for i, row in enumerate(conf_matrix):
            label = ["SELL", "HOLD", "BUY"][i]
            logger.info(f"  {label:4s}  {row[0]:5d} {row[1]:5d} {row[2]:5d}")

        return {
            "model_name": model_name,
            "accuracy": float(accuracy),
            "precision": float(precision),
            "recall": float(recall),
            "f1_score": float(f1),
            "confusion_matrix": conf_matrix.tolist(),
            "classification_report": class_report,
            "n_samples": len(y_true),
        }

    def evaluate_probabilities(
        self,
        y_true: np.ndarray,
        y_probs: np.ndarray,
        label_space: str = "auto",
        model_name: str = "model",
    ) -> Dict[str, Any]:
        """Evaluates with probabilities (including Log-Loss)."""
        from sklearn.metrics import log_loss

        y_true_mapped = self._ensure_mapped(y_true, label_space=label_space)
        y_pred = np.argmax(y_probs, axis=1)

        result = self.evaluate(y_true_mapped, y_pred, label_space="class", model_name=model_name)

        try:
            logloss = log_loss(y_true_mapped, y_probs, labels=[0, 1, 2])
            result["log_loss"] = float(logloss)
            logger.info(f"Log-Loss: {logloss:.4f}")
        except Exception as e:
            logger.warning(f"Log-Loss failed: {e}")
            result["log_loss"] = None

        return result

    def evaluate_trading(
        self,
        y_true: np.ndarray,
        y_pred: np.ndarray,
        tp_pips: float = 50.0,
        sl_pips: float = 30.0,
        spread_pips: float = 2.5,
        label_space: str = "auto",
        model_name: str = "model",
        log_details: bool = True,
    ) -> Dict[str, Any]:
        """
        Trading-specific evaluation.

        Simulates what would have happened if the signals had been followed.
        Each BUY/SELL signal is treated as an individual trade.

        Args:
            y_true: True labels (-1=SELL, 0=HOLD, 1=BUY)
            y_pred: Predicted labels
            tp_pips: Take-Profit in pips
            sl_pips: Stop-Loss in pips
            spread_pips: Spread costs in pips
            label_space: "signal" for -1/0/1, "class" for 0/1/2, "auto" for detection
            model_name: Name of the model

        Returns:
            Dict with trading metrics
        """
        y_true_orig = np.array(y_true)
        y_pred_orig = np.array(y_pred)

        if label_space not in {"auto", "signal", "class"}:
            raise ValueError("label_space must be one of: auto, signal, class")

        # Normalize to -1, 0, 1
        if label_space == "class":
            y_true_orig = y_true_orig - 1
            y_pred_orig = y_pred_orig - 1
        elif label_space == "auto":
            if y_true_orig.max() > 1:
                y_true_orig = y_true_orig - 1
            if y_pred_orig.max() > 1:
                y_pred_orig = y_pred_orig - 1

        # Only consider trades (BUY or SELL predictions)
        trade_mask = y_pred_orig != 0
        n_trades = trade_mask.sum()

        if n_trades == 0:
            if log_details:
                logger.warning(f"{model_name}: No trades predicted!")
            return self._empty_trading_metrics(model_name)

        pred_trades = y_pred_orig[trade_mask]
        true_trades = y_true_orig[trade_mask]

        # Win: prediction matches the true direction
        wins = pred_trades == true_trades
        losses = ~wins

        n_wins = wins.sum()
        n_losses = losses.sum()
        win_rate = n_wins / n_trades

        # Profit/Loss per trade (in pips)
        net_tp = tp_pips - spread_pips  # Net TP after spread
        net_sl = sl_pips + spread_pips  # Net SL including spread

        # HOLD predictions on actual trades: no profit
        # Correct trades: +net_tp pips, Incorrect trades: -net_sl pips
        pips_per_trade = np.where(wins, net_tp, -net_sl)

        total_pips = pips_per_trade.sum()
        avg_pips = pips_per_trade.mean()

        gross_profit = pips_per_trade[pips_per_trade > 0].sum()
        gross_loss = abs(pips_per_trade[pips_per_trade < 0].sum())

        # Profit Factor
        profit_factor = gross_profit / gross_loss if gross_loss > 0 else float("inf")

        # Expectancy (average profit per trade)
        expectancy = (win_rate * net_tp) - ((1 - win_rate) * net_sl)

        # Equity Curve and Max Drawdown
        equity_curve = np.cumsum(pips_per_trade)
        peak = np.maximum.accumulate(equity_curve)
        drawdown = peak - equity_curve
        max_drawdown = drawdown.max() if len(drawdown) > 0 else 0

        # Sharpe Ratio (annualized, based on trade returns)
        if len(pips_per_trade) > 1 and pips_per_trade.std() > 0:
            # Assumption: ~50 trades per week, ~2600 per year
            sharpe = (pips_per_trade.mean() / pips_per_trade.std()) * np.sqrt(2600)
        else:
            sharpe = 0.0

        # Consecutive Wins/Losses
        max_consecutive_wins = self._max_consecutive(wins)
        max_consecutive_losses = self._max_consecutive(losses)

        # Buy/Sell Breakdown
        buy_signals = (pred_trades == 1).sum()
        sell_signals = (pred_trades == -1).sum()

        # Logging
        if log_details:
            logger.info(f"\n{'='*55}")
            logger.info(f"TRADING Evaluation: {model_name}")
            logger.info(f"{'='*55}")
            logger.info(f"Trades:          {n_trades} (BUY={buy_signals}, SELL={sell_signals})")
            logger.info(f"Win Rate:        {win_rate*100:.1f}% ({n_wins}W / {n_losses}L)")
            logger.info(f"Profit Factor:   {profit_factor:.2f}")
            logger.info(f"Total Pips:      {total_pips:+.1f}")
            logger.info(f"Avg Pips/Trade:  {avg_pips:+.2f}")
            logger.info(f"Expectancy:      {expectancy:+.2f} Pips/Trade")
            logger.info(f"Max Drawdown:    {max_drawdown:.1f} Pips")
            logger.info(f"Sharpe Ratio:    {sharpe:.2f}")
            logger.info(f"Max Con. Wins:   {max_consecutive_wins}")
            logger.info(f"Max Con. Losses: {max_consecutive_losses}")
            logger.info(f"{'='*55}")

        # Quality assessment
        grade = self._grade_performance(win_rate, profit_factor, sharpe, max_drawdown)
        if log_details:
            logger.info(f"Assessment: {grade}")

        return {
            "model_name": model_name,
            "n_trades": int(n_trades),
            "buy_signals": int(buy_signals),
            "sell_signals": int(sell_signals),
            "wins": int(n_wins),
            "losses": int(n_losses),
            "win_rate": float(win_rate),
            "profit_factor": float(profit_factor),
            "total_pips": float(total_pips),
            "avg_pips_per_trade": float(avg_pips),
            "expectancy": float(expectancy),
            "max_drawdown_pips": float(max_drawdown),
            "sharpe_ratio": float(sharpe),
            "max_consecutive_wins": int(max_consecutive_wins),
            "max_consecutive_losses": int(max_consecutive_losses),
            "grade": grade,
            "tp_pips": tp_pips,
            "sl_pips": sl_pips,
            "spread_pips": spread_pips,
        }

    def compare_models(
        self,
        results: List[Dict[str, Any]],
    ) -> Dict[str, Any]:
        """Compares multiple models (ML metrics)."""
        logger.info(f"\n{'='*60}")
        logger.info("Model comparison")
        logger.info(f"{'='*60}")
        logger.info(f"{'Model':<15} {'Accuracy':>10} {'Precision':>10} {'Recall':>10} {'F1':>10}")
        logger.info(f"{'-'*55}")

        best_model = None
        best_f1 = -1

        for r in results:
            name = r["model_name"]
            logger.info(
                f"{name:<15} {r['accuracy']:>10.4f} {r['precision']:>10.4f} "
                f"{r['recall']:>10.4f} {r['f1_score']:>10.4f}"
            )
            if r["f1_score"] > best_f1:
                best_f1 = r["f1_score"]
                best_model = name

        logger.info(f"\nBest model: {best_model} (F1: {best_f1:.4f})")
        return {"best_model": best_model, "best_f1": best_f1, "all_results": results}

    def compare_trading(
        self,
        results: List[Dict[str, Any]],
    ) -> Dict[str, Any]:
        """Compares multiple models (trading metrics)."""
        logger.info(f"\n{'='*70}")
        logger.info("Trading comparison")
        logger.info(f"{'='*70}")
        logger.info(f"{'Model':<15} {'WinRate':>10} {'PF':>8} {'Pips':>10} {'Sharpe':>8} {'DD':>10}")
        logger.info(f"{'-'*61}")

        best_model = None
        best_pf = -1

        for r in results:
            name = r["model_name"]
            logger.info(
                f"{name:<15} {r['win_rate']*100:>9.1f}% {r['profit_factor']:>8.2f} "
                f"{r['total_pips']:>+10.1f} {r['sharpe_ratio']:>8.2f} {r['max_drawdown_pips']:>10.1f}"
            )
            if r["profit_factor"] > best_pf:
                best_pf = r["profit_factor"]
                best_model = name

        logger.info(f"\nBest model: {best_model} (PF: {best_pf:.2f})")
        return {"best_model": best_model, "best_profit_factor": best_pf, "all_results": results}

    @staticmethod
    def _grade_performance(
        win_rate: float,
        profit_factor: float,
        sharpe: float,
        max_drawdown: float,
    ) -> str:
        """Evaluates the trading performance."""
        score = 0

        # Win Rate
        if win_rate >= 0.60:
            score += 3
        elif win_rate >= 0.55:
            score += 2
        elif win_rate >= 0.50:
            score += 1

        # Profit Factor
        if profit_factor >= 2.0:
            score += 3
        elif profit_factor >= 1.5:
            score += 2
        elif profit_factor >= 1.2:
            score += 1

        # Sharpe
        if sharpe >= 2.0:
            score += 2
        elif sharpe >= 1.0:
            score += 1

        # Max Drawdown (low = good)
        if max_drawdown < 100:
            score += 2
        elif max_drawdown < 200:
            score += 1

        if score >= 8:
            return "EXCELLENT (Production Ready)"
        elif score >= 6:
            return "GOOD (Promising)"
        elif score >= 4:
            return "ACCEPTABLE (Needs improvement)"
        elif score >= 2:
            return "WEAK (Not recommended)"
        else:
            return "UNUSABLE (Needs rework)"

    @staticmethod
    def _max_consecutive(arr: np.ndarray) -> int:
        """Calculates maximum consecutive streak."""
        if len(arr) == 0:
            return 0
        max_count = 0
        count = 0
        for val in arr:
            if val:
                count += 1
                max_count = max(max_count, count)
            else:
                count = 0
        return max_count

    @staticmethod
    def _ensure_mapped(y: np.ndarray, label_space: str = "auto") -> np.ndarray:
        """
        Ensures that labels are in the range [0, 1, 2].

        label_space:
        - "signal": expects -1/0/1 -> maps to 0/1/2
        - "class": expects 0/1/2 -> unchanged
        - "auto": heuristic, but robust for signal-space subsets
        """
        values = np.array(y, dtype=int)
        if values.size == 0:
            return values

        if label_space not in {"auto", "signal", "class"}:
            raise ValueError("label_space must be one of: auto, signal, class")

        if label_space == "signal":
            return (values + 1).astype(int)
        if label_space == "class":
            return values.astype(int)

        unique = set(values.tolist())
        # All <= 1 is signal-space in our pipeline context
        if values.max() <= 1:
            return (values + 1).astype(int)
        if values.min() < 0:
            return (values + 1).astype(int)
        if unique.issubset({0, 1, 2}):
            return values.astype(int)
        return values.astype(int)

    @staticmethod
    def _empty_trading_metrics(model_name: str) -> Dict[str, Any]:
        """Empty trading metrics."""
        return {
            "model_name": model_name,
            "n_trades": 0, "buy_signals": 0, "sell_signals": 0,
            "wins": 0, "losses": 0, "win_rate": 0.0,
            "profit_factor": 0.0, "total_pips": 0.0,
            "avg_pips_per_trade": 0.0, "expectancy": 0.0,
            "max_drawdown_pips": 0.0, "sharpe_ratio": 0.0,
            "max_consecutive_wins": 0, "max_consecutive_losses": 0,
            "grade": "NO TRADES",
            "tp_pips": 0, "sl_pips": 0, "spread_pips": 0,
        }


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    np.random.seed(42)

    n = 500
    y_true = np.random.choice([-1, 0, 1], n, p=[0.3, 0.4, 0.3])
    # Simulate ~58% correct predictions
    y_pred = y_true.copy()
    noise_mask = np.random.random(n) < 0.42
    y_pred[noise_mask] = np.random.choice([-1, 0, 1], noise_mask.sum())

    evaluator = ModelEvaluator()

    # ML Evaluation
    result_ml = evaluator.evaluate(y_true, y_pred, "TestModel")

    # Trading Evaluation
    result_trading = evaluator.evaluate_trading(
        y_true, y_pred,
        tp_pips=50, sl_pips=30, spread_pips=2.5,
        model_name="TestModel"
    )

    print("\nEvaluation test successful!")
