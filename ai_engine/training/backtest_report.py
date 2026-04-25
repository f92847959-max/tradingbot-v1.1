"""
Backtest Report -- Report generation and consistency validation.

Generates consolidated backtest reports with per-window and aggregate
metrics, and enforces consistency checks (>60% positive windows,
no window >20% drawdown).
"""

import logging
from datetime import datetime
from typing import Any, Dict, List

import numpy as np

logger = logging.getLogger(__name__)


def generate_backtest_report(
    per_window_results: List[Dict[str, Any]],
    version_info: Dict[str, Any],
) -> Dict[str, Any]:
    """Generate a consolidated backtest report from per-window results.

    Aggregate profit factor is computed from total gross_profit / total
    gross_loss across all windows (not averaged per-window ratios).

    Args:
        per_window_results: List of per-window backtest report dicts
            (as returned by Backtester.run_simple()).
        version_info: Version metadata dict from version.json.

    Returns:
        JSON-serializable report dict with per_window + aggregate sections.
    """
    # Per-window entries
    per_window = []
    for r in per_window_results:
        per_window.append({
            "window_id": r.get("window_id", 0),
            "n_trades": r.get("n_trades", 0),
            "total_pips": r.get("total_pips", 0.0),
            "win_rate": r.get("win_rate", 0.0),
            "profit_factor": r.get("profit_factor", 0.0),
            "sharpe_ratio": r.get("sharpe_ratio", 0.0),
            "max_drawdown_pct": r.get("max_drawdown_pct", 0.0),
            "grade": r.get("grade", "NO TRADES"),
        })

    # Aggregate metrics from combined trades
    all_pips: List[float] = []
    total_gross_profit = 0.0
    total_gross_loss = 0.0
    total_trades = 0

    for r in per_window_results:
        trades = r.get("trades", [])
        for t in trades:
            pnl = t.get("pnl_pips", 0.0)
            all_pips.append(pnl)
            if pnl > 0:
                total_gross_profit += pnl
            elif pnl < 0:
                total_gross_loss += abs(pnl)
        total_trades += r.get("n_trades", 0)

    # Combined metrics
    pips_array = np.array(all_pips) if all_pips else np.array([0.0])
    agg_total_pips = float(pips_array.sum())
    agg_win_rate = float(
        np.sum(pips_array > 0) / len(pips_array)
    ) if len(all_pips) > 0 else 0.0
    agg_profit_factor = (
        total_gross_profit / total_gross_loss
        if total_gross_loss > 0
        else float("inf")
    )

    # Sharpe from combined pips
    if len(pips_array) > 1 and pips_array.std() > 0:
        agg_sharpe = float(
            (pips_array.mean() / pips_array.std()) * np.sqrt(2600)
        )
    else:
        agg_sharpe = 0.0

    # Max drawdown across all windows (worst single window)
    agg_max_drawdown_pct = float(
        max((r.get("max_drawdown_pct", 0.0) for r in per_window_results), default=0.0)
    )

    aggregate = {
        "n_windows": len(per_window_results),
        "total_trades": total_trades,
        "total_pips": agg_total_pips,
        "win_rate": agg_win_rate,
        "profit_factor": agg_profit_factor,
        "sharpe_ratio": agg_sharpe,
        "max_drawdown_pct": agg_max_drawdown_pct,
        "gross_profit": total_gross_profit,
        "gross_loss": total_gross_loss,
    }

    return {
        "report_type": "backtest",
        "report_date": datetime.now().isoformat(),
        "version_info": {
            k: v for k, v in version_info.items()
            if k not in ("walk_forward",)  # exclude large nested data
        } if version_info else {},
        "per_window": per_window,
        "aggregate": aggregate,
    }


def check_consistency(
    per_window_results: List[Dict[str, Any]],
) -> Dict[str, Any]:
    """Check walk-forward consistency per BACK-04 criteria.

    Criteria:
        - >60% of windows with trades must be profitable (total_pips > 0)
        - No single window may exceed 20% max drawdown
        - Zero-trade windows are excluded from the 60% calculation

    Args:
        per_window_results: List of per-window backtest report dicts.

    Returns:
        Dict with consistency check results including overall_pass boolean.
    """
    n_windows = len(per_window_results)
    if n_windows == 0:
        return {
            "n_windows": 0,
            "windows_with_trades": 0,
            "zero_trade_windows": 0,
            "positive_windows": 0,
            "positive_pct": 0.0,
            "passes_60pct": False,
            "dd_violations": 0,
            "passes_20pct_dd": True,
            "overall_pass": False,
        }

    windows_with_trades = [
        w for w in per_window_results if w.get("n_trades", 0) > 0
    ]
    zero_trade_windows = n_windows - len(windows_with_trades)

    positive_windows = sum(
        1 for w in windows_with_trades if w.get("total_pips", 0.0) > 0
    )
    positive_pct = (
        positive_windows / len(windows_with_trades)
        if windows_with_trades
        else 0.0
    )
    passes_60pct = positive_pct > 0.60

    dd_violations = sum(
        1 for w in per_window_results
        if w.get("max_drawdown_pct", 0.0) > 20.0
    )
    passes_20pct_dd = dd_violations == 0

    return {
        "n_windows": n_windows,
        "windows_with_trades": len(windows_with_trades),
        "zero_trade_windows": zero_trade_windows,
        "positive_windows": positive_windows,
        "positive_pct": positive_pct,
        "passes_60pct": passes_60pct,
        "dd_violations": dd_violations,
        "passes_20pct_dd": passes_20pct_dd,
        "overall_pass": passes_60pct and passes_20pct_dd,
    }


def print_backtest_report(
    report: Dict[str, Any],
    consistency: Dict[str, Any],
) -> None:
    """Print a formatted backtest report to the console via logger.

    Args:
        report: Report dict from generate_backtest_report().
        consistency: Consistency dict from check_consistency().
    """
    agg = report.get("aggregate", {})
    per_window = report.get("per_window", [])

    logger.info("")
    logger.info("=" * 70)
    logger.info("  BACKTEST REPORT (Out-of-Sample Walk-Forward)")
    logger.info("=" * 70)

    # Per-window table
    logger.info("")
    logger.info(
        f"  {'Win':>3s} | {'Trades':>6s} | {'Pips':>8s} | "
        f"{'WR':>5s} | {'PF':>5s} | {'Sharpe':>6s} | "
        f"{'MaxDD%':>6s} | Grade"
    )
    logger.info("  " + "-" * 64)
    for w in per_window:
        pf_str = (
            f"{w['profit_factor']:5.2f}"
            if w["profit_factor"] != float("inf")
            else "  inf"
        )
        logger.info(
            f"  {w['window_id']:>3d} | {w['n_trades']:>6d} | "
            f"{w['total_pips']:>+8.1f} | {w['win_rate']*100:>4.1f}% | "
            f"{pf_str} | {w['sharpe_ratio']:>6.2f} | "
            f"{w['max_drawdown_pct']:>5.1f}% | {w['grade']}"
        )

    # Aggregate
    logger.info("")
    logger.info("  AGGREGATE")
    logger.info(f"    Windows:        {agg.get('n_windows', 0)}")
    logger.info(f"    Total Trades:   {agg.get('total_trades', 0)}")
    logger.info(f"    Total Pips:     {agg.get('total_pips', 0):+.1f}")
    logger.info(f"    Win Rate:       {agg.get('win_rate', 0)*100:.1f}%")
    pf = agg.get("profit_factor", 0)
    pf_str = f"{pf:.2f}" if pf != float("inf") else "inf"
    logger.info(f"    Profit Factor:  {pf_str}")
    logger.info(f"    Sharpe Ratio:   {agg.get('sharpe_ratio', 0):.2f}")

    # Consistency
    logger.info("")
    logger.info("  CONSISTENCY CHECK")
    pos_pct = consistency.get("positive_pct", 0) * 100
    p60 = "PASS" if consistency.get("passes_60pct") else "FAIL"
    p20 = "PASS" if consistency.get("passes_20pct_dd") else "FAIL"
    overall = "PASS" if consistency.get("overall_pass") else "FAIL"
    logger.info(
        f"    Positive windows:  {consistency.get('positive_windows', 0)}"
        f"/{consistency.get('windows_with_trades', 0)}"
        f" ({pos_pct:.0f}%) — {p60}"
    )
    logger.info(
        f"    Zero-trade windows: {consistency.get('zero_trade_windows', 0)}"
    )
    logger.info(
        f"    DD violations:     {consistency.get('dd_violations', 0)} — {p20}"
    )
    logger.info(f"    Overall:           {overall}")
    logger.info("=" * 70)
