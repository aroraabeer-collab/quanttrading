import numpy as np

from backtest.engine import build_panels, run_backtest
from strategy.breakout import BreakoutScanner


def test_build_panels_aligns_fields(synthetic_bars):
    panels = build_panels(synthetic_bars)
    assert list(panels.close.columns) == list(synthetic_bars.keys())
    assert panels.close.shape == panels.volume.shape
    assert not panels.close.empty


def test_backtest_runs_and_places_orders(synthetic_bars):
    pf = run_backtest(synthetic_bars, BreakoutScanner())
    # Engine produced a portfolio over the full bar history.
    assert len(pf.value()) == len(build_panels(synthetic_bars).close)
    # Our synthetic breakouts should have generated trades.
    assert int(np.asarray(pf.orders.count()).sum()) > 0
    # Total return must be a finite number (costs applied, no NaNs blowing up).
    assert np.isfinite(np.asarray(pf.total_return()).sum())
