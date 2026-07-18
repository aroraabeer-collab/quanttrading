"""Risk-based portfolio construction via PyPortfolioOpt.

Two documented allocators that target *risk-adjusted* outperformance of a naive
equal-weight benchmark — the exact weakness of our long-only ML book:

- **Minimum Variance** — the classic low-volatility portfolio (Ledoit-Wolf
  shrunk covariance for stability), long-only with a per-name cap.
- **Hierarchical Risk Parity (HRP)** — López de Prado's robust allocator that
  clusters correlated names and avoids inverting the covariance matrix.

Walk-forward: at each monthly rebalance, weights use only the *trailing* window,
so there is no lookahead.
"""
from __future__ import annotations

import warnings

import pandas as pd
import scipy.cluster.hierarchy as _sch

# Compat shim: newer scipy removed the private `_LINKAGE_METHODS` that older
# PyPortfolioOpt's HRPOpt checks against. Restore it so HRP works.
if not hasattr(_sch, "_LINKAGE_METHODS"):
    _sch._LINKAGE_METHODS = {
        m: i for i, m in enumerate(
            ["single", "complete", "average", "weighted", "centroid", "median", "ward"]
        )
    }

from pypfopt import EfficientFrontier, HRPOpt, expected_returns, risk_models

from backtest.engine import Panels
from config.settings import Settings, get_settings
from ml.factor_backtest import FactorResult, simulate_weights

warnings.filterwarnings("ignore")  # PyPortfolioOpt is chatty about solver details


def min_variance_weights(prices: pd.DataFrame, cap: float = 0.10) -> pd.Series:
    mu = expected_returns.mean_historical_return(prices)
    cov = risk_models.CovarianceShrinkage(prices).ledoit_wolf()
    ef = EfficientFrontier(mu, cov, weight_bounds=(0, cap))
    ef.min_volatility()
    return pd.Series(ef.clean_weights())


def hrp_weights(prices: pd.DataFrame) -> pd.Series:
    returns = prices.pct_change().dropna()
    hrp = HRPOpt(returns)
    hrp.optimize()
    return pd.Series(hrp.clean_weights())


def run_risk_portfolio(
    panels: Panels,
    method: str = "minvar",
    settings: Settings | None = None,
    lookback: int = 252,
    rebalance_every: int = 21,
    oos_frac: float = 0.35,
    cap: float = 0.10,
    restrict: pd.Index | None = None,
) -> FactorResult:
    """Backtest a monthly-rebalanced risk-based portfolio, walk-forward.

    ``restrict`` optionally limits the investable set at each rebalance (e.g. to
    the ML model's top names) — enabling the "ML selects, risk model weights"
    synthesis.
    """
    s = settings or get_settings()
    close = panels.close
    dates = close.index
    n = len(dates)
    oos_start = int(n * (1 - oos_frac))

    weights = {}
    for idx in range(oos_start, n, rebalance_every):
        t = dates[idx]
        window = close.iloc[max(0, idx - lookback):idx].dropna(axis=1)  # trailing, no lookahead
        if restrict is not None:
            keep = [c for c in window.columns if c in set(restrict)]
            window = window[keep]
        if window.shape[1] < 10 or len(window) < lookback * 0.8:
            continue
        w = min_variance_weights(window, cap) if method == "minvar" else hrp_weights(window)
        weights[t] = w.reindex(close.columns).fillna(0.0)

    if not weights:
        raise ValueError("No rebalance dates produced weights — check data/lookback.")
    W = pd.DataFrame(weights).T.sort_index()
    return simulate_weights(panels, W, s)


def equal_weight_backtest(
    panels: Panels, settings: Settings | None = None,
    rebalance_every: int = 21, oos_frac: float = 0.35,
) -> FactorResult:
    """Passive equal-weight benchmark over the same OOS window and cost model."""
    s = settings or get_settings()
    close = panels.close
    dates = close.index
    n = len(dates)
    weights = {}
    for idx in range(int(n * (1 - oos_frac)), n, rebalance_every):
        t = dates[idx]
        avail = close.iloc[max(0, idx - 21):idx].dropna(axis=1).columns
        if len(avail) == 0:
            continue
        weights[t] = pd.Series(1.0 / len(avail), index=avail).reindex(close.columns).fillna(0.0)
    W = pd.DataFrame(weights).T.sort_index()
    return simulate_weights(panels, W, s)
