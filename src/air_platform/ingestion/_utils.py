"""Internal utilities shared across the ingestion package."""

from __future__ import annotations

from collections.abc import Sequence

import pandas as pd


def coerce_timestamps(values: Sequence[object], skip_nat: bool = False) -> list[pd.Timestamp]:
    """Convert a sequence of values to pd.Timestamp objects.

    Args:
        values:   Sequence of timestamps in any format pandas can parse.
        skip_nat: When True, silently drop values that cannot be parsed
                  (used when the input may contain null/NaT entries).
    """
    result: list[pd.Timestamp] = []
    for value in values:
        ts = pd.Timestamp(str(value))
        if skip_nat and pd.isna(ts):
            continue
        result.append(ts)
    return result
