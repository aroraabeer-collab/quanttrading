import numpy as np
import pandas as pd

from backtest.engine import build_panels
from ml.features import FEATURES, build_dataset
from ml.model import walk_forward_predict

IST = "Asia/Kolkata"


def _synthetic_daily(n_days=400, n_syms=12, seed=0):
    rng = np.random.default_rng(seed)
    idx = pd.bdate_range("2023-01-02", periods=n_days, tz=IST)
    bars = {}
    for k in range(n_syms):
        # Each stock a random walk; a couple have mild momentum for signal.
        drift = 0.0003 if k < 4 else 0.0
        ret = rng.normal(drift, 0.015, n_days)
        close = 100 * np.exp(np.cumsum(ret))
        vol = rng.uniform(1e5, 2e5, n_days)
        bars[f"NSE:S{k}-EQ"] = pd.DataFrame(
            {"open": close, "high": close * 1.01, "low": close * 0.99,
             "close": close, "volume": vol},
            index=idx,
        )
    return bars


def test_build_dataset_shape_and_columns():
    panels = build_panels(_synthetic_daily())
    data = build_dataset(panels, horizon=5)
    assert list(data.columns) == FEATURES + ["fwd_ret"]
    assert data.index.names == ["date", "symbol"]
    assert len(data) > 0
    assert not data.isna().any().any()
    # Ranked features must lie in [0, 1].
    assert data[FEATURES].to_numpy().min() >= 0.0
    assert data[FEATURES].to_numpy().max() <= 1.0


def test_walk_forward_produces_oos_predictions():
    panels = build_panels(_synthetic_daily())
    data = build_dataset(panels, horizon=5)
    preds = walk_forward_predict(data, horizon=5, oos_frac=0.3, rebalance_every=5)
    assert len(preds) > 0
    # Every prediction date is in the last 30% of history (out-of-sample).
    dates = data.index.get_level_values("date").unique().sort_values()
    oos_cutoff = dates[int(len(dates) * 0.7)]
    assert all(d >= oos_cutoff for d in preds)
    # Each prediction is a score per symbol.
    some = next(iter(preds.values()))
    assert isinstance(some, pd.Series) and len(some) > 0
