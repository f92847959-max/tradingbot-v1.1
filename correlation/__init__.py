"""Inter-market correlation engine (Phase 12).

Public API: CorrelationSnapshot, AssetFetcher, compute_snapshot.
"""
from correlation.snapshot import CorrelationSnapshot
from correlation.asset_fetcher import AssetFetcher

__all__ = ["CorrelationSnapshot", "AssetFetcher"]
