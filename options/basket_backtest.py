"""Diversified stock-option selling — does a basket beat the index alone?

Individual stocks lack an implied-vol index, so we proxy each stock's IV as its
own trailing realized volatility scaled by the **vol-risk-premium multiplier
measured on Nifty** (mean of India VIX ÷ Nifty realized vol). We then sell a
strangle on each stock (model-based, same engine) and aggregate an equal-weight
basket, comparing its risk-adjusted P&L to the single-index strangle.

Caveat: the proxy assumes stocks carry the index's VRP. It tests the
*diversification* benefit robustly; absolute per-name premium is approximate.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from options.vol_backtest import _stats, run_vol_backtest


def realized_vol(close: pd.Series, window: int = 20) -> pd.Series:
    """Trailing annualized realized volatility, in VIX-style percentage points."""
    return close.pct_change().rolling(window).std() * np.sqrt(252) * 100


def vrp_multiplier(nifty_close: pd.Series, vix: pd.Series, window: int = 20) -> float:
    """Mean ratio of implied (VIX) to realized vol on Nifty — the premium the
    market pays for insurance. Applied to stocks as their proxy-IV scaler."""
    rv = realized_vol(nifty_close, window)
    ratio = (vix / rv).replace([np.inf, -np.inf], np.nan).dropna()
    return float(ratio.mean())


def proxy_iv(close: pd.Series, mult: float, window: int = 20) -> pd.Series:
    """Per-stock proxy implied vol = trailing realized vol × VRP multiplier."""
    return realized_vol(close, window) * mult


def run_basket_backtest(
    stock_closes: dict[str, pd.Series],
    mult: float,
    hold_days: int = 21,
    sd_width: float = 1.0,
    stop_mult: float | None = 2.0,
    min_price: float = 100.0,
) -> tuple[dict, pd.DataFrame]:
    """Sell a stop-managed strangle on each stock; aggregate an equal-weight basket.

    Returns (basket_stats, per_cycle_returns_frame). Uses % returns (P&L /
    underlying notional) so names of different price/lot combine fairly.
    """
    per_name_ret = {}
    for sym, close in stock_closes.items():
        if close.dropna().empty or close.dropna().iloc[-1] < min_price:
            continue
        iv = proxy_iv(close, mult)
        try:
            res = run_vol_backtest(close, iv, hold_days=hold_days,
                                   sd_width=sd_width, stop_mult=stop_mult)
        except Exception:
            continue
        if res.trades.empty:
            continue
        per_name_ret[sym] = res.trades.set_index("entry")["ret"]

    if not per_name_ret:
        raise ValueError("No names produced trades.")

    # Align all names on the common cycle schedule; basket = equal-weight mean.
    R = pd.DataFrame(per_name_ret)
    basket_ret = R.mean(axis=1)  # equal-weight across available names each cycle

    # Build a trades-like frame so _stats works (pnl in "return units").
    fake = pd.DataFrame({"pnl": basket_ret.values})
    stats = _stats_from_returns(basket_ret, hold_days)
    stats["n_names"] = R.shape[1]
    return stats, R


def _stats_from_returns(ret: pd.Series, hold_days: int) -> dict:
    cycles_per_yr = 252 / hold_days
    wins, losses = ret[ret > 0], ret[ret <= 0]
    sharpe = ret.mean() / ret.std() * np.sqrt(cycles_per_yr) if ret.std() > 0 else float("nan")
    eq = ret.cumsum()
    dd = (eq - eq.cummax()).min()
    return {
        "cycles": len(ret),
        "win_rate": len(wins) / len(ret) * 100 if len(ret) else 0,
        "avg_win_pct": wins.mean() * 100 if len(wins) else 0,
        "avg_loss_pct": losses.mean() * 100 if len(losses) else 0,
        "worst_pct": ret.min() * 100,
        "total_ret_pct": ret.sum() * 100,
        "sharpe": sharpe,
        "max_dd_pct": dd * 100,
        "ann_ret_pct": ret.mean() * cycles_per_yr * 100,
    }
