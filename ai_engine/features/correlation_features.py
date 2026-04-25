"""Correlation feature group (CORR-04)."""
from __future__ import annotations

from dataclasses import asdict, fields
from typing import List, Optional

import pandas as pd

from correlation.snapshot import CorrelationSnapshot


_FEATURE_NAMES: List[str] = [field.name for field in fields(CorrelationSnapshot)]


class CorrelationFeatures:
    """Broadcast a CorrelationSnapshot into feature columns."""

    def __init__(self) -> None:
        self._feature_names = list(_FEATURE_NAMES)

    def get_feature_names(self) -> List[str]:
        return list(self._feature_names)

    def calculate(
        self,
        df: pd.DataFrame,
        snapshot: Optional[CorrelationSnapshot] = None,
    ) -> pd.DataFrame:
        values = {name: 0.0 for name in self._feature_names}
        if snapshot is not None:
            values.update(asdict(snapshot))

        for name in self._feature_names:
            df[name] = float(values.get(name, 0.0))
        return df
