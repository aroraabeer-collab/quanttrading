"""Shared test fixtures: synthetic intraday bars and a fake data provider."""
from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

IST = "Asia/Kolkata"


@pytest.fixture(autouse=True)
def _isolate_paper_state(tmp_path, monkeypatch):
    """Ensure no test ever writes to the real paper-trading state directory."""
    monkeypatch.setattr("execution.paper_broker.STATE_DIR", tmp_path)


def session_index(day: str, resolution: int = 5) -> pd.DatetimeIndex:
    start = pd.Timestamp(f"{day} 09:15", tz=IST)
    end = pd.Timestamp(f"{day} 15:30", tz=IST)
    return pd.date_range(start, end, freq=f"{resolution}min")


def make_ohlcv(index: pd.DatetimeIndex, seed: int = 0) -> pd.DataFrame:
    """Gentle uptrend with periodic breakout bars (price jump + volume spike)."""
    rng = np.random.default_rng(seed)
    n = len(index)
    close = 100 + np.cumsum(rng.normal(0, 0.1, n))
    volume = rng.uniform(8_000, 12_000, n)
    for i in range(15, n, 10):  # inject clear breakouts past the lookback window
        close[i] = close[i - 1] * 1.012
        volume[i] *= 3.0
    open_ = np.r_[close[0], close[:-1]]
    high = np.maximum(open_, close) + 0.05
    low = np.minimum(open_, close) - 0.05
    return pd.DataFrame(
        {"open": open_, "high": high, "low": low, "close": close, "volume": volume},
        index=index,
    )


@pytest.fixture
def synthetic_bars() -> dict[str, pd.DataFrame]:
    idx = session_index("2026-01-05").append(session_index("2026-01-06"))
    return {
        "NSE:AAA-EQ": make_ohlcv(idx, seed=1),
        "NSE:BBB-EQ": make_ohlcv(idx, seed=2),
        "NSE:CCC-EQ": make_ohlcv(idx, seed=3),
    }


class FakeProvider:
    """DataProvider stand-in returning fixed bars and a settable quote map."""

    def __init__(self, bars: dict[str, pd.DataFrame]):
        self._bars = bars
        self.quotes: dict[str, float] = {
            s: float(df["close"].iloc[-1]) for s, df in bars.items()
        }

    def history(self, symbols, start, end, interval="5"):
        return {s: self._bars[s] for s in symbols if s in self._bars}

    def quote(self, symbols):
        return {s: self.quotes[s] for s in symbols if s in self.quotes}

    def subscribe(self, symbols, callback):  # pragma: no cover
        raise NotImplementedError
