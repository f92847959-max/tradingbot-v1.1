"""Inter-market correlation engine (Phase 12).

Public API: CorrelationSnapshot, AssetFetcher, compute_snapshot.
"""
from correlation.snapshot import CorrelationSnapshot
from correlation.correlation_calculator import compute_snapshot

__all__ = ["CorrelationSnapshot", "AssetFetcher", "compute_snapshot"]


def __getattr__(name: str):
    if name == "AssetFetcher":
        from correlation.asset_fetcher import AssetFetcher

        return AssetFetcher
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
