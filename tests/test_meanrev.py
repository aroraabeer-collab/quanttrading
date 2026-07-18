import pandas as pd

from strategy.meanrev import MeanReversion

IST = "Asia/Kolkata"


def _bars(closes, volumes=None):
    n = len(closes)
    idx = pd.date_range("2026-01-05 09:45", periods=n, freq="5min", tz=IST)  # inside MR window
    volumes = volumes or [10_000.0] * n
    return pd.DataFrame(
        {
            "open": closes,
            "high": [c + 0.1 for c in closes],
            "low": [c - 0.1 for c in closes],
            "close": closes,
            "volume": volumes,
        },
        index=idx,
    )


def test_scan_fires_on_dip_then_tickup():
    mr = MeanReversion()
    # VWAP builds ~99.7; dip to 99.0 (>0.4% below), then tick up to 99.1 -> entry.
    closes = [100.0, 100.1, 99.9, 100.0, 99.0, 99.1]
    assert mr.scan(_bars(closes)) is True


def test_scan_rejects_without_tickup():
    mr = MeanReversion()
    # Still falling on the last bar (no reversal) -> no entry (avoid falling knife).
    closes = [100.0, 100.1, 99.9, 100.0, 99.4, 99.2]
    assert mr.scan(_bars(closes)) is False


def test_scan_rejects_when_not_stretched():
    mr = MeanReversion()
    # Price basically at VWAP -> not a dip.
    closes = [100.0, 100.0, 100.0, 100.0, 99.98, 100.0]
    assert mr.scan(_bars(closes)) is False


def test_meanrev_is_not_one_trade_per_day():
    mr = MeanReversion()
    assert mr.one_trade_per_day is False
    assert mr.exit_rules.trail is False
