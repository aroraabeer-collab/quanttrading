"""Weighted composite indicator strategy (ports NSE-QUANT-TRADER's approach).

Fuses Moving-Average, RSI, MACD and Bollinger-Band signals into one weighted
score in [-1, +1], and goes long when the score crosses a threshold. Exactly the
kind of technical-indicator composite that retail systems favour — reproduced
here so it can be tested against this project's HONEST intraday cost model rather
than a frictionless backtest.

Each sub-signal returns +1 (bullish) / 0 / -1 (bearish); the weighted sum is the
composite score.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

# Default weights (as such systems typically set them — trend-following tilt).
DEFAULT_WEIGHTS = {"ma": 0.30, "rsi": 0.20, "macd": 0.30, "bb": 0.20}


def _ma_signal(close: pd.DataFrame, fast: int = 20, slow: int = 50) -> pd.DataFrame:
    f, s = close.ewm(span=fast).mean(), close.ewm(span=slow).mean()
    return np.sign(f - s)


def _rsi_signal(close: pd.DataFrame, window: int = 14,
                lo: float = 30, hi: float = 70) -> pd.DataFrame:
    delta = close.diff()
    gain = delta.clip(lower=0).ewm(alpha=1 / window).mean()
    loss = (-delta.clip(upper=0)).ewm(alpha=1 / window).mean()
    rsi = 100 - 100 / (1 + gain / loss.replace(0, np.nan))
    sig = pd.DataFrame(0.0, index=close.index, columns=close.columns)
    sig[rsi < lo] = 1.0     # oversold -> bullish
    sig[rsi > hi] = -1.0    # overbought -> bearish
    return sig


def _macd_signal(close: pd.DataFrame, fast: int = 12, slow: int = 26,
                 signal: int = 9) -> pd.DataFrame:
    macd = close.ewm(span=fast).mean() - close.ewm(span=slow).mean()
    return np.sign(macd - macd.ewm(span=signal).mean())


def _bb_signal(close: pd.DataFrame, window: int = 20, k: float = 2.0) -> pd.DataFrame:
    mid = close.rolling(window).mean()
    sd = close.rolling(window).std()
    sig = pd.DataFrame(0.0, index=close.index, columns=close.columns)
    sig[close < mid - k * sd] = 1.0    # below lower band -> bullish (mean-revert)
    sig[close > mid + k * sd] = -1.0   # above upper band -> bearish
    return sig


def composite_score(close: pd.DataFrame, weights: dict | None = None) -> pd.DataFrame:
    """Weighted composite indicator score in [-1, +1], per bar per symbol."""
    w = weights or DEFAULT_WEIGHTS
    score = (w["ma"] * _ma_signal(close)
             + w["rsi"] * _rsi_signal(close)
             + w["macd"] * _macd_signal(close)
             + w["bb"] * _bb_signal(close))
    return score / sum(w.values())


def composite_entries(close: pd.DataFrame, threshold: float = 0.5,
                      weights: dict | None = None) -> pd.DataFrame:
    """Boolean long-entry matrix: score crosses up through `threshold`."""
    score = composite_score(close, weights)
    return (score >= threshold) & (score.shift(1) < threshold)
