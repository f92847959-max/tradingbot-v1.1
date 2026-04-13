"""Tests for Monte Carlo simulation engine — risk/monte_carlo.py."""

import time
import pytest
from risk.monte_carlo import MonteCarloSimulator, SimulationResult


# ---------------------------------------------------------------------------
# SimulationResult structure tests
# ---------------------------------------------------------------------------

class TestSimulationResultStructure:
    """Verify SimulationResult is a dataclass with correct fields."""

    def test_simulation_result_is_dataclass(self):
        """SimulationResult can be instantiated as a dataclass."""
        result = SimulationResult(
            max_drawdown_pcts=[0.1, 0.2],
            final_equities=[10500.0, 10300.0],
            ruin_probability=0.05,
            drawdown_percentiles={"p50": 0.1, "p75": 0.15, "p90": 0.2, "p95": 0.25, "p99": 0.4},
            return_percentiles={"p5": -5.0, "p25": 2.0, "p50": 8.0, "p75": 15.0, "p95": 25.0},
            num_paths=2,
            num_trades=100,
        )
        assert result.num_paths == 2
        assert result.num_trades == 100
        assert result.ruin_probability == 0.05

    def test_simulation_result_has_all_required_fields(self):
        """SimulationResult exposes all 7 required fields."""
        result = SimulationResult(
            max_drawdown_pcts=[],
            final_equities=[],
            ruin_probability=0.0,
            drawdown_percentiles={},
            return_percentiles={},
            num_paths=0,
            num_trades=0,
        )
        assert hasattr(result, "max_drawdown_pcts")
        assert hasattr(result, "final_equities")
        assert hasattr(result, "ruin_probability")
        assert hasattr(result, "drawdown_percentiles")
        assert hasattr(result, "return_percentiles")
        assert hasattr(result, "num_paths")
        assert hasattr(result, "num_trades")


# ---------------------------------------------------------------------------
# MonteCarloSimulator basic tests
# ---------------------------------------------------------------------------

class TestMonteCarloSimulatorBasic:
    """Core simulate() output shape and type tests."""

    @pytest.fixture
    def simulator(self):
        return MonteCarloSimulator()

    @pytest.fixture
    def standard_result(self, simulator):
        return simulator.simulate(
            win_rate=0.6,
            avg_win=3.0,
            avg_loss=1.5,
            num_trades=200,
            num_paths=1000,
            initial_equity=10000.0,
            seed=42,
        )

    def test_simulate_returns_simulation_result(self, simulator):
        result = simulator.simulate(
            win_rate=0.6, avg_win=3.0, avg_loss=1.5,
            num_trades=200, num_paths=100, seed=42,
        )
        assert isinstance(result, SimulationResult)

    def test_num_paths_matches_request(self, standard_result):
        assert standard_result.num_paths == 1000

    def test_num_trades_matches_request(self, standard_result):
        assert standard_result.num_trades == 200

    def test_max_drawdown_pcts_length(self, standard_result):
        """max_drawdown_pcts must have exactly num_paths entries."""
        assert len(standard_result.max_drawdown_pcts) == 1000

    def test_drawdown_percentiles_keys(self, standard_result):
        """drawdown_percentiles must have keys: p50, p75, p90, p95, p99."""
        keys = set(standard_result.drawdown_percentiles.keys())
        assert keys == {"p50", "p75", "p90", "p95", "p99"}

    def test_return_percentiles_keys(self, standard_result):
        """return_percentiles must have keys: p5, p25, p50, p75, p95."""
        keys = set(standard_result.return_percentiles.keys())
        assert keys == {"p5", "p25", "p50", "p75", "p95"}

    def test_ruin_probability_in_range(self, standard_result):
        """ruin_probability must be a valid probability [0, 1]."""
        assert 0.0 <= standard_result.ruin_probability <= 1.0


# ---------------------------------------------------------------------------
# Edge strength tests
# ---------------------------------------------------------------------------

class TestEdgeStrengthRuin:
    """Verify ruin_probability reflects edge strength."""

    def test_strong_edge_low_ruin(self):
        """win_rate=0.6, RRR=2.0 — positive edge — ruin_prob must be < 0.1."""
        sim = MonteCarloSimulator(ruin_threshold=0.5)
        result = sim.simulate(
            win_rate=0.6, avg_win=3.0, avg_loss=1.5,
            num_trades=200, num_paths=1000, seed=42,
        )
        assert result.ruin_probability < 0.1, (
            f"Expected ruin_prob < 0.1 for strong edge, got {result.ruin_probability}"
        )

    def test_no_edge_high_ruin(self):
        """win_rate=0.4, RRR=1.0 — negative edge — ruin_prob must be > 0.3."""
        sim = MonteCarloSimulator(ruin_threshold=0.5)
        result = sim.simulate(
            win_rate=0.4, avg_win=1.0, avg_loss=1.0,
            num_trades=200, num_paths=1000, seed=42,
        )
        assert result.ruin_probability > 0.3, (
            f"Expected ruin_prob > 0.3 for no edge, got {result.ruin_probability}"
        )

    def test_win_rate_zero_near_certain_ruin(self):
        """win_rate=0 — every trade is a loser — ruin_probability close to 1.0."""
        sim = MonteCarloSimulator(ruin_threshold=0.5)
        result = sim.simulate(
            win_rate=0.0, avg_win=3.0, avg_loss=1.5,
            num_trades=200, num_paths=1000, seed=42,
        )
        assert result.ruin_probability >= 0.9, (
            f"Expected ruin_prob >= 0.9 for win_rate=0, got {result.ruin_probability}"
        )

    def test_win_rate_one_zero_ruin(self):
        """win_rate=1 — every trade is a winner — ruin_probability = 0.0."""
        sim = MonteCarloSimulator(ruin_threshold=0.5)
        result = sim.simulate(
            win_rate=1.0, avg_win=3.0, avg_loss=1.5,
            num_trades=200, num_paths=1000, seed=42,
        )
        assert result.ruin_probability == 0.0, (
            f"Expected ruin_prob == 0.0 for win_rate=1, got {result.ruin_probability}"
        )


# ---------------------------------------------------------------------------
# Reproducibility test
# ---------------------------------------------------------------------------

class TestReproducibility:
    """Verify seed parameter produces deterministic results."""

    def test_seed_reproducibility(self):
        """Calling simulate with same seed twice returns identical results."""
        sim = MonteCarloSimulator()
        r1 = sim.simulate(win_rate=0.55, avg_win=2.0, avg_loss=1.0,
                          num_trades=100, num_paths=500, seed=42)
        r2 = sim.simulate(win_rate=0.55, avg_win=2.0, avg_loss=1.0,
                          num_trades=100, num_paths=500, seed=42)
        assert r1.ruin_probability == r2.ruin_probability
        assert r1.max_drawdown_pcts == r2.max_drawdown_pcts
        assert r1.final_equities == r2.final_equities


# ---------------------------------------------------------------------------
# Performance test
# ---------------------------------------------------------------------------

class TestPerformance:
    """Verify simulation completes within time limits."""

    def test_small_simulation_fast(self):
        """simulate with num_paths=10 completes in under 1 second."""
        sim = MonteCarloSimulator()
        start = time.monotonic()
        sim.simulate(win_rate=0.6, avg_win=3.0, avg_loss=1.5,
                     num_trades=200, num_paths=10, seed=42)
        elapsed = time.monotonic() - start
        assert elapsed < 1.0, f"Expected < 1s for 10 paths, took {elapsed:.2f}s"

    def test_large_simulation_under_5_seconds(self):
        """simulate with 1000 paths x 200 trades completes in < 5 seconds."""
        sim = MonteCarloSimulator()
        start = time.monotonic()
        sim.simulate(win_rate=0.6, avg_win=3.0, avg_loss=1.5,
                     num_trades=200, num_paths=1000, seed=42)
        elapsed = time.monotonic() - start
        assert elapsed < 5.0, f"Expected < 5s for 1000 paths, took {elapsed:.2f}s"


# ---------------------------------------------------------------------------
# optimal_f test
# ---------------------------------------------------------------------------

class TestOptimalF:
    """Verify optimal_f returns a valid position fraction."""

    def test_optimal_f_returns_float_in_range(self):
        """optimal_f(win_rate=0.6, avg_win=3.0, avg_loss=1.5) returns float in (0, 1]."""
        sim = MonteCarloSimulator()
        f = sim.optimal_f(win_rate=0.6, avg_win=3.0, avg_loss=1.5)
        assert isinstance(f, float)
        assert 0.0 < f <= 1.0, f"Expected f in (0, 1], got {f}"

    def test_optimal_f_reproducible(self):
        """optimal_f with same inputs returns same result."""
        sim = MonteCarloSimulator()
        f1 = sim.optimal_f(win_rate=0.6, avg_win=3.0, avg_loss=1.5, seed=42)
        f2 = sim.optimal_f(win_rate=0.6, avg_win=3.0, avg_loss=1.5, seed=42)
        assert f1 == f2


# ---------------------------------------------------------------------------
# No forbidden imports
# ---------------------------------------------------------------------------

class TestNoDatabaseImports:
    """Verify monte_carlo module does not import database/config modules."""

    def test_no_database_import(self):
        """Module must not import from database/ or trading/ packages."""
        import ast
        import inspect
        from risk import monte_carlo

        source = inspect.getsource(monte_carlo)
        tree = ast.parse(source)

        forbidden_prefixes = ("database", "trading", "config")
        for node in ast.walk(tree):
            if isinstance(node, (ast.Import, ast.ImportFrom)):
                if isinstance(node, ast.ImportFrom) and node.module:
                    for prefix in forbidden_prefixes:
                        assert not node.module.startswith(prefix), (
                            f"monte_carlo imports from forbidden module: {node.module}"
                        )
