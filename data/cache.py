"""Parquet cache for historical intraday bars.

One parquet file per (symbol, resolution) so backtests reuse data instead of
re-hitting the Fyers API. Symbols are slugified for filesystem safety.
"""
from __future__ import annotations

import re
from pathlib import Path

import pandas as pd

from config.settings import CACHE_DIR

BAR_COLUMNS = ["open", "high", "low", "close", "volume"]


def _slug(symbol: str) -> str:
    """Filesystem-safe key for a Fyers symbol, e.g. NSE:RELIANCE-EQ -> NSE_RELIANCE-EQ."""
    return re.sub(r"[^A-Za-z0-9._-]", "_", symbol)


def cache_path(symbol: str, resolution: str) -> Path:
    return CACHE_DIR / f"{_slug(symbol)}__{resolution}m.parquet"


def write_bars(symbol: str, resolution: str, df: pd.DataFrame) -> Path:
    """Persist a bar DataFrame (index=DatetimeIndex, columns=BAR_COLUMNS)."""
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    path = cache_path(symbol, resolution)
    df.to_parquet(path)
    return path


def read_bars(symbol: str, resolution: str) -> pd.DataFrame | None:
    """Load cached bars, or None if not present."""
    path = cache_path(symbol, resolution)
    if not path.exists():
        return None
    return pd.read_parquet(path)


def load_panel(symbols: list[str], resolution: str, field: str = "close") -> pd.DataFrame:
    """Assemble a wide DataFrame (index=timestamp, columns=symbols) for one field.

    Only symbols with cached data are included; rows are the union of timestamps.
    """
    series: dict[str, pd.Series] = {}
    for sym in symbols:
        df = read_bars(sym, resolution)
        if df is not None and not df.empty and field in df.columns:
            series[sym] = df[field]
    if not series:
        return pd.DataFrame()
    return pd.DataFrame(series).sort_index()
