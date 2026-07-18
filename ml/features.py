"""Feature engineering for the cross-sectional factor model.

Each feature is computed per stock over time, then **cross-sectionally ranked**
each day (percentile across the universe) so the model learns *relative*
attractiveness rather than market-wide moves. The label is the forward return
over a fixed horizon. Output is a tidy table indexed by (date, symbol).
"""
from __future__ import annotations

import pandas as pd

from backtest.engine import Panels

# Feature columns the model consumes (order-independent).
FEATURES = [
    "ret_1m", "ret_3m", "ret_6m", "mom_12_1",
    "rev_5d", "vol_20d", "dist_sma50", "vol_ratio", "rsi_14",
]


def _rsi(close: pd.DataFrame, window: int = 14) -> pd.DataFrame:
    delta = close.diff()
    gain = delta.clip(lower=0).rolling(window).mean()
    loss = (-delta.clip(upper=0)).rolling(window).mean()
    rs = gain / loss.replace(0, pd.NA)
    return 100 - 100 / (1 + rs)


def compute_features(panels: Panels) -> dict[str, pd.DataFrame]:
    close, volume = panels.close, panels.volume
    ret = close.pct_change()
    return {
        "ret_1m": close.pct_change(21),
        "ret_3m": close.pct_change(63),
        "ret_6m": close.pct_change(126),
        "mom_12_1": close.shift(21) / close.shift(252) - 1,   # 12-1 momentum
        "rev_5d": close.pct_change(5),                         # short-term reversal
        "vol_20d": ret.rolling(20).std(),
        "dist_sma50": close / close.rolling(50).mean() - 1,
        "vol_ratio": volume.rolling(5).mean() / volume.rolling(60).mean(),
        "rsi_14": _rsi(close, 14),
    }


def build_features(panels: Panels) -> pd.DataFrame:
    """Tidy (date, symbol) table of cross-sectionally ranked features (no label).

    Used both for training (joined with a label) and for live prediction, where
    the latest date has features but no known forward return yet.
    """
    feats = compute_features(panels)
    ranked = {name: df.rank(axis=1, pct=True) for name, df in feats.items()}
    cols = [ranked[name].stack().rename(name) for name in FEATURES]
    X = pd.concat(cols, axis=1)
    X.index.names = ["date", "symbol"]
    return X.dropna()


def build_dataset(panels: Panels, horizon: int = 5) -> pd.DataFrame:
    """Ranked features + forward-return label, for training. ``horizon`` in days."""
    X = build_features(panels)
    label = (panels.close.shift(-horizon) / panels.close - 1).stack().rename("fwd_ret")
    label.index.names = ["date", "symbol"]
    return X.join(label, how="inner").dropna()
