import pandas as pd

from execution.paper_broker import PaperBroker
from live.runner import PaperRunner
from strategy.breakout import BreakoutScanner
from conftest import FakeProvider

IST = "Asia/Kolkata"


def _breakout_ending_bars(symbol: str) -> dict[str, pd.DataFrame]:
    """Bars whose final row breaks out on a volume surge (triggers scan())."""
    lb = BreakoutScanner().lookback
    n = lb + 1
    idx = pd.date_range("2026-01-05 09:15", periods=n, freq="5min", tz=IST)
    close = [100.0] * lb + [101.5]
    volume = [10_000.0] * lb + [40_000.0]
    df = pd.DataFrame(
        {
            "open": close,
            "high": [100.2] * lb + [101.6],
            "low": [99.8] * lb + [100.5],
            "close": close,
            "volume": volume,
        },
        index=idx,
    )
    return {symbol: df}


def _runner(bars):
    provider = FakeProvider(bars)
    broker = PaperBroker(initial_cash=1_000_000, slippage_bps=3.0)
    runner = PaperRunner(provider, broker, BreakoutScanner())
    runner.symbols = list(bars.keys())  # scan only our synthetic symbol
    return runner, broker, provider


def test_run_once_enters_on_breakout():
    sym = "NSE:AAA-EQ"
    runner, broker, _ = _runner(_breakout_ending_bars(sym))
    now = pd.Timestamp("2026-01-05 10:00", tz=IST)
    log = runner.run_once(now)
    assert log["entries"], "expected a breakout entry"
    assert sym in broker.positions()


def test_run_once_exits_on_target():
    sym = "NSE:AAA-EQ"
    runner, broker, provider = _runner(_breakout_ending_bars(sym))
    now = pd.Timestamp("2026-01-05 10:00", tz=IST)
    runner.run_once(now)  # enter
    # Price jumps well past the +0.4% target -> should exit on the next cycle.
    provider.quotes[sym] = 200.0
    log = runner.run_once(now + pd.Timedelta(minutes=5))
    reasons = [r for _, r, _ in log["exits"]]
    assert "target" in reasons


def test_square_off_blocks_new_entries():
    sym = "NSE:AAA-EQ"
    runner, broker, _ = _runner(_breakout_ending_bars(sym))
    after_cutoff = pd.Timestamp("2026-01-05 15:20", tz=IST)  # past 15:15 square-off
    log = runner.run_once(after_cutoff)
    assert not log["entries"]
