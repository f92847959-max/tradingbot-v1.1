"""Monte Carlo simulation engine for trade sequence projection.

Provides drawdown distributions, ruin probability, and optimal
position sizing — a pure numerical module with no database dependencies.
"""

import logging
from dataclasses import dataclass

import numpy as np

logger = logging.getLogger(__name__)


@dataclass
class SimulationResult:
    """Result of a Monte Carlo simulation run.

    Attributes:
        max_drawdown_pcts: Maximum drawdown (as fraction 0-1) per path.
        final_equities: Terminal equity per path.
        ruin_probability: Fraction of paths where max drawdown >= ruin_threshold.
        drawdown_percentiles: Percentile breakdown of max drawdowns.
            Keys: "p50", "p75", "p90", "p95", "p99".
        return_percentiles: Percentile breakdown of final returns (%).
            Keys: "p5", "p25", "p50", "p75", "p95".
        num_paths: Number of simulation paths run.
        num_trades: Number of trades simulated per path.
    """

    max_drawdown_pcts: list[float]
    final_equities: list[float]
    ruin_probability: float
    drawdown_percentiles: dict  # {"p50": x, "p75": x, "p90": x, "p95": x, "p99": x}
    return_percentiles: dict    # {"p5": x, "p25": x, "p50": x, "p75": x, "p95": x}
    num_paths: int
    num_trades: int


class MonteCarloSimulator:
    """Monte Carlo simulation for trade sequence projection.

    Simulates ``num_paths`` independent sequences of ``num_trades`` trades
    drawn from provided win/loss statistics.  All heavy computation is
    vectorised with NumPy so that 1 000 paths × 200 trades completes in
    well under 5 seconds.

    Args:
        ruin_threshold: Drawdown fraction at which a path is counted as
            "ruined" (default 0.5 = 50 % peak-to-trough drawdown).
    """

    def __init__(self, ruin_threshold: float = 0.5) -> None:
        self.ruin_threshold = ruin_threshold

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def simulate(
        self,
        win_rate: float,
        avg_win: float,
        avg_loss: float,
        num_trades: int = 200,
        num_paths: int = 1000,
        initial_equity: float = 10_000.0,
        position_fraction: float = 0.02,
        seed: int | None = None,
    ) -> SimulationResult:
        """Run Monte Carlo simulation.

        Each path evolves equity trade-by-trade using fixed-fractional sizing:
        - Win:  equity += equity * position_fraction * (avg_win / avg_loss)
        - Loss: equity -= equity * position_fraction

        Args:
            win_rate: Probability [0, 1] of a winning trade.
            avg_win: Average winning trade size (in any consistent unit, e.g. pips).
            avg_loss: Average losing trade size (same unit as avg_win).
            num_trades: Trades to simulate per path.
            num_paths: Number of independent paths to run.
            initial_equity: Starting equity for every path.
            position_fraction: Fixed fraction of equity risked per trade.
            seed: Random seed for reproducible results.

        Returns:
            SimulationResult with drawdown distribution and statistics.
        """
        rng = np.random.default_rng(seed)

        # Win/loss ratio (reward-to-risk expressed as equity multiplier)
        rrr = avg_win / avg_loss if avg_loss > 0 else 1.0

        # Equity multiplier per outcome
        win_mult = position_fraction * rrr   # fractional equity gain on win
        loss_mult = position_fraction         # fractional equity loss on loss

        # Generate outcome matrix: True = win, False = loss
        # Shape: (num_paths, num_trades)
        outcomes = rng.random((num_paths, num_trades)) < win_rate

        # --- Vectorised equity simulation ---
        # We iterate over the trades axis (length num_trades) but all
        # num_paths paths are updated in parallel at each step.
        equity = np.full(num_paths, initial_equity, dtype=np.float64)
        peak = equity.copy()
        max_drawdown_frac = np.zeros(num_paths, dtype=np.float64)

        for t in range(num_trades):
            wins = outcomes[:, t]
            # Update equity
            equity = np.where(wins,
                              equity * (1.0 + win_mult),
                              equity * (1.0 - loss_mult))
            # Clamp equity to a floor of 0 to avoid negative values
            np.maximum(equity, 0.0, out=equity)
            # Update running peak
            np.maximum(peak, equity, out=peak)
            # Compute drawdown fraction for this step
            # drawdown = (peak - equity) / peak  (guard against zero peak)
            drawdown = np.where(peak > 0, (peak - equity) / peak, 0.0)
            np.maximum(max_drawdown_frac, drawdown, out=max_drawdown_frac)

        # --- Aggregate statistics ---
        max_drawdown_pcts = max_drawdown_frac.tolist()
        final_equities = equity.tolist()

        # Ruin probability
        ruin_probability = float(np.mean(max_drawdown_frac >= self.ruin_threshold))

        # Drawdown percentiles (expressed as fractions, same as max_drawdown_pcts)
        dd_percentiles = np.percentile(max_drawdown_frac, [50, 75, 90, 95, 99])
        drawdown_percentiles = {
            "p50": float(dd_percentiles[0]),
            "p75": float(dd_percentiles[1]),
            "p90": float(dd_percentiles[2]),
            "p95": float(dd_percentiles[3]),
            "p99": float(dd_percentiles[4]),
        }

        # Return percentiles (%)
        returns_pct = (equity - initial_equity) / initial_equity * 100.0
        ret_percentiles_vals = np.percentile(returns_pct, [5, 25, 50, 75, 95])
        return_percentiles = {
            "p5":  float(ret_percentiles_vals[0]),
            "p25": float(ret_percentiles_vals[1]),
            "p50": float(ret_percentiles_vals[2]),
            "p75": float(ret_percentiles_vals[3]),
            "p95": float(ret_percentiles_vals[4]),
        }

        logger.info(
            "MC simulation: %d paths x %d trades, ruin_prob=%.3f, median_dd=%.1f%%",
            num_paths,
            num_trades,
            ruin_probability,
            drawdown_percentiles["p50"] * 100,
        )

        return SimulationResult(
            max_drawdown_pcts=max_drawdown_pcts,
            final_equities=final_equities,
            ruin_probability=ruin_probability,
            drawdown_percentiles=drawdown_percentiles,
            return_percentiles=return_percentiles,
            num_paths=num_paths,
            num_trades=num_trades,
        )

    def optimal_f(
        self,
        win_rate: float,
        avg_win: float,
        avg_loss: float,
        num_trades: int = 200,
        num_paths: int = 500,
        seed: int | None = 42,
    ) -> float:
        """Find position fraction that maximises median terminal wealth.

        Tests 20 candidate fractions from 0.005 to 0.10 in steps of 0.005.
        For each fraction, runs a simulation and computes median terminal
        equity.  Returns the fraction yielding the highest median equity.

        Args:
            win_rate: Probability of a winning trade.
            avg_win: Average winning trade size.
            avg_loss: Average losing trade size.
            num_trades: Trades per path in each candidate simulation.
            num_paths: Paths per candidate simulation.
            seed: Base seed for reproducibility (each candidate uses
                  ``seed + i`` to keep candidates independent but deterministic).

        Returns:
            Optimal position fraction as a float in (0.0, 1.0].
        """
        candidates = [round(0.005 * i, 4) for i in range(1, 21)]  # 0.005 .. 0.10
        best_f = candidates[0]
        best_median_equity = -np.inf

        for i, fraction in enumerate(candidates):
            candidate_seed = None if seed is None else seed + i
            result = self.simulate(
                win_rate=win_rate,
                avg_win=avg_win,
                avg_loss=avg_loss,
                num_trades=num_trades,
                num_paths=num_paths,
                position_fraction=fraction,
                seed=candidate_seed,
            )
            median_equity = float(np.median(result.final_equities))
            if median_equity > best_median_equity:
                best_median_equity = median_equity
                best_f = fraction

        best_return_pct = (best_median_equity / 10_000.0 - 1.0) * 100.0
        logger.info(
            "optimal_f: best fraction=%.4f, median_return=%.1f%%",
            best_f,
            best_return_pct,
        )
        return float(best_f)
