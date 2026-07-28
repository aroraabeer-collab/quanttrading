"""Regime veto mechanism — it's OFF by default (backtested to hurt), but when
enabled it must correctly flag hostile regimes and stay silent in calm ones."""
import numpy as np
import pandas as pd

from config.settings import get_settings
from options.regime_veto import RegimeVeto


def _settings(**over):
    base = {"live_regime_veto": True, "regime_trend_z": 2.0,
            "regime_momentum_mult": 2.0, "regime_vix_spike": 0.25}
    return get_settings().model_copy(update={**base, **over})


def _series(values):
    idx = pd.bdate_range("2026-01-01", periods=len(values))
    return pd.Series(values, index=idx)


def test_off_by_default():
    # The shipped default must be OFF — the backtest showed it hurts.
    assert get_settings().live_regime_veto is False


def test_calm_range_bound_market_is_not_vetoed():
    rng = np.random.default_rng(0)
    nifty = _series(24000 + np.cumsum(rng.normal(0, 30, 80)))   # gentle chop
    vix = _series(np.full(80, 14.0) + rng.normal(0, 0.3, 80))
    assert RegimeVeto(_settings()).check(nifty, vix) is None


def test_strong_trend_is_vetoed():
    # Calm base, then a sharp breakout: stretched far from MA AND large vs vol.
    nifty = _series(np.concatenate([np.full(60, 24000.0),
                                    np.linspace(24000, 27000, 20)]))  # +12.5% burst
    vix = _series(np.full(80, 14.0))
    reason = RegimeVeto(_settings()).check(nifty, vix)
    assert reason and "trending" in reason.lower()


def test_vix_spike_is_vetoed():
    rng = np.random.default_rng(1)
    nifty = _series(24000 + np.cumsum(rng.normal(0, 20, 80)))
    vix = _series(np.concatenate([np.full(75, 13.0), [13, 15, 17, 19, 20]]))  # +54% in 5d
    reason = RegimeVeto(_settings()).check(nifty, vix)
    assert reason and "vix" in reason.lower()


def test_disabled_never_vetoes():
    nifty = _series(np.linspace(23000, 26000, 80))
    vix = _series(np.full(80, 14.0))
    assert RegimeVeto(_settings(live_regime_veto=False)).check(nifty, vix) is None


def test_too_little_history_does_not_block():
    nifty = _series([24000, 24100, 24050])
    vix = _series([14, 14, 14])
    assert RegimeVeto(_settings()).check(nifty, vix) is None
