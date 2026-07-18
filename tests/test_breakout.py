import numpy as np
import pandas as pd

from strategy.breakout import BreakoutScanner


def _bars(highs, closes, volumes):
    n = len(closes)
    idx = pd.date_range("2026-01-05 09:15", periods=n, freq="5min", tz="Asia/Kolkata")
    return pd.DataFrame(
        {
            "open": closes,
            "high": highs,
            "low": [c - 0.1 for c in closes],
            "close": closes,
            "volume": volumes,
        },
        index=idx,
    )


def test_scan_fires_on_breakout_with_volume(monkeypatch):
    scanner = BreakoutScanner()
    lb = scanner.lookback
    # Flat prior bars, then a final bar that breaks the high on a volume surge.
    highs = [100.0] * lb + [101.0]
    closes = [99.5] * lb + [100.9]
    volumes = [10_000.0] * lb + [30_000.0]
    assert scanner.scan(_bars(highs, closes, volumes)) is True


def test_scan_rejects_breakout_without_volume():
    scanner = BreakoutScanner()
    lb = scanner.lookback
    highs = [100.0] * lb + [101.0]
    closes = [99.5] * lb + [100.9]
    volumes = [10_000.0] * lb + [10_000.0]  # no surge
    assert scanner.scan(_bars(highs, closes, volumes)) is False


def test_scan_rejects_without_breakout():
    scanner = BreakoutScanner()
    lb = scanner.lookback
    highs = [100.0] * lb + [100.0]
    closes = [99.5] * lb + [99.6]  # below prior high
    volumes = [10_000.0] * lb + [30_000.0]
    assert scanner.scan(_bars(highs, closes, volumes)) is False


def test_scan_needs_enough_history():
    scanner = BreakoutScanner()
    short = _bars([100.0], [99.5], [10_000.0])
    assert scanner.scan(short) is False


def test_entry_signals_matrix_shape_and_dtype(synthetic_bars):
    scanner = BreakoutScanner()
    close = pd.DataFrame({s: df["close"] for s, df in synthetic_bars.items()})
    high = pd.DataFrame({s: df["high"] for s, df in synthetic_bars.items()})
    volume = pd.DataFrame({s: df["volume"] for s, df in synthetic_bars.items()})
    signals = scanner.entry_signals(close, high, volume)
    assert signals.shape == close.shape
    assert signals.to_numpy().dtype == np.bool_
    assert signals.to_numpy().sum() > 0  # our synthetic breakouts should trigger
