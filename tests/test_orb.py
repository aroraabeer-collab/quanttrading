import pandas as pd

from strategy.orb import OpeningRangeBreakout

IST = "Asia/Kolkata"


def _day_bars(day: str, closes, highs, volumes):
    idx = pd.date_range(f"{day} 09:15", periods=len(closes), freq="5min", tz=IST)
    return pd.DataFrame(
        {
            "open": closes,
            "high": highs,
            "low": [c - 0.2 for c in closes],
            "close": closes,
            "volume": volumes,
        },
        index=idx,
    )


def test_scan_fires_on_or_breakout():
    orb = OpeningRangeBreakout()
    # First 6 bars (09:15–09:40) form the opening range with high 100.
    # Bars 7–8 (09:45, 09:50) break above it.
    closes = [99.5, 99.6, 99.7, 99.6, 99.8, 99.7, 100.6, 100.8]
    highs = [100.0] * 6 + [100.7, 100.9]
    volumes = [10_000.0] * 8
    bars = _day_bars("2026-01-05", closes, highs, volumes)
    assert orb.scan(bars) is True


def test_scan_rejects_before_breakout_window():
    orb = OpeningRangeBreakout()
    # Only the opening-range bars exist (still 09:15–09:40) — no entry yet.
    closes = [99.5, 99.6, 99.7, 99.6, 99.8, 99.7]
    highs = [100.0] * 6
    bars = _day_bars("2026-01-05", closes, highs, [10_000.0] * 6)
    assert orb.scan(bars) is False


def test_scan_rejects_without_breakout():
    orb = OpeningRangeBreakout()
    closes = [99.5, 99.6, 99.7, 99.6, 99.8, 99.7, 99.9, 99.8]  # never exceeds OR high 100
    highs = [100.0] * 6 + [99.95, 99.9]
    bars = _day_bars("2026-01-05", closes, highs, [10_000.0] * 8)
    assert orb.scan(bars) is False


def test_entry_signals_at_most_one_per_day():
    orb = OpeningRangeBreakout()
    # Full day of 5-min bars with two separate breakout bars; only the first counts.
    idx = pd.date_range("2026-01-05 09:15", "2026-01-05 15:30", freq="5min", tz=IST)
    n = len(idx)
    close = pd.Series(99.5, index=idx)
    high = pd.Series(100.0, index=idx)
    vol = pd.Series(10_000.0, index=idx)
    # Two breakouts, both after 09:45 (in the entry window).
    close.iloc[8] = 101.0   # 09:55
    close.iloc[20] = 102.0  # 10:55
    df_close = close.to_frame("X")
    df_high = high.to_frame("X")
    df_vol = vol.to_frame("X")
    signals = orb.entry_signals(df_close, df_high, df_vol)
    assert signals["X"].sum() == 1
    assert signals["X"].iloc[8]  # the first breakout is the one taken


def test_orb_uses_trailing_stop():
    assert OpeningRangeBreakout().exit_rules.trail is True
    assert OpeningRangeBreakout().one_trade_per_day is True
