"""Positional backtest for the ML factor model.

Given per-rebalance predicted scores, hold the top-K names equal-weighted,
rebalance on schedule, and charge realistic *delivery* costs on turnover. Reports
out-of-sample **average daily net profit** (the chosen objective) plus supporting
metrics, and the **Information Coefficient** (rank-correlation of predictions with
realized forward returns) — the acid test of whether the model predicts anything.
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd

from backtest.costs import DeliveryCostModel
from backtest.engine import Panels
from config.settings import Settings, get_settings

TRADING_DAYS = 252


@dataclass
class FactorResult:
    equity: pd.Series
    daily_pnl: pd.Series
    daily_ret: pd.Series
    metrics: dict
    ic: float


def _build_weights(preds: dict[pd.Timestamp, pd.Series], symbols, top_k: int) -> pd.DataFrame:
    """Long-only: equal weight across the top-K names."""
    rows = {}
    for date, scores in preds.items():
        top = scores.sort_values(ascending=False).head(top_k).index
        w = pd.Series(0.0, index=symbols)
        if len(top):
            w[top] = 1.0 / len(top)
        rows[date] = w
    return pd.DataFrame(rows).T.sort_index()


def _build_ls_weights(preds: dict[pd.Timestamp, pd.Series], symbols, top_k: int) -> pd.DataFrame:
    """Dollar-neutral: long top-K (+0.5 gross), short bottom-K (-0.5 gross)."""
    rows = {}
    for date, scores in preds.items():
        s = scores.sort_values(ascending=False)
        longs, shorts = s.head(top_k).index, s.tail(top_k).index
        w = pd.Series(0.0, index=symbols)
        if len(longs):
            w[longs] += 0.5 / len(longs)
        if len(shorts):
            w[shorts] -= 0.5 / len(shorts)
        rows[date] = w
    return pd.DataFrame(rows).T.sort_index()


def _information_coefficient(
    preds: dict[pd.Timestamp, pd.Series], panels: Panels, horizon: int
) -> float:
    """Mean daily Spearman rank-corr between predicted scores and realized fwd return."""
    fwd = panels.close.shift(-horizon) / panels.close - 1
    ics = []
    for date, scores in preds.items():
        if date not in fwd.index:
            continue
        realized = fwd.loc[date].reindex(scores.index)
        pair = pd.concat([scores, realized], axis=1).dropna()
        if len(pair) >= 5:
            ics.append(pair.iloc[:, 0].corr(pair.iloc[:, 1], method="spearman"))
    return float(np.nanmean(ics)) if ics else float("nan")


def run_factor_backtest(
    panels: Panels,
    preds: dict[pd.Timestamp, pd.Series],
    horizon: int,
    top_k: int = 10,
    settings: Settings | None = None,
    long_short: bool = False,
) -> FactorResult:
    """Backtest predictions. ``long_short=True`` runs the dollar-neutral variant
    (long top-K, short bottom-K) that isolates the factor edge from market beta.
    """
    s = settings or get_settings()
    symbols = panels.close.columns
    weights_rebal = (
        _build_ls_weights(preds, symbols, top_k) if long_short
        else _build_weights(preds, symbols, top_k)
    )
    res = simulate_weights(panels, weights_rebal, s)
    res.ic = _information_coefficient(preds, panels, horizon)
    return res


def simulate_weights(
    panels: Panels, weights_rebal: pd.DataFrame, settings: Settings | None = None
) -> FactorResult:
    """Simulate any (rebalance_date x symbol) target-weight scheme with delivery
    costs on turnover. Shared by the ML factor and risk-based portfolio backtests.
    """
    s = settings or get_settings()
    close = panels.close
    symbols = close.columns
    start = weights_rebal.index.min()
    daily_idx = close.index[close.index >= start]
    W = weights_rebal.reindex(daily_idx).ffill().fillna(0.0)
    R = close.pct_change().reindex(daily_idx).fillna(0.0)

    # Yesterday's holdings earn today's return.
    gross = (W.shift(1) * R).sum(axis=1)

    # Delivery costs on rebalance turnover, expressed as a return drag.
    cost_model = DeliveryCostModel(s.slippage_bps)
    nav = s.initial_capital
    cost_drag = pd.Series(0.0, index=daily_idx)
    prev_w = pd.Series(0.0, index=symbols)
    for d in weights_rebal.index:
        if d not in cost_drag.index:
            continue
        new_w = weights_rebal.loc[d].reindex(symbols).fillna(0.0)
        delta = new_w - prev_w
        buy_value = float(delta[delta > 0].sum()) * nav
        sell_value = float(-delta[delta < 0].sum()) * nav
        n_sells = int((delta < 0).sum())
        cost_drag[d] += cost_model.rebalance_cost(buy_value, sell_value, n_sells) / nav
        prev_w = new_w

    net = gross - cost_drag
    equity = (1 + net).cumprod() * s.initial_capital
    daily_pnl = equity.diff().fillna(equity.iloc[0] - s.initial_capital)
    metrics = _metrics(net, equity, daily_pnl, s.initial_capital)
    return FactorResult(equity, daily_pnl, net, metrics, float("nan"))


def _metrics(net: pd.Series, equity: pd.Series, pnl: pd.Series, init: float) -> dict:
    ann_factor = np.sqrt(TRADING_DAYS)
    sharpe = net.mean() / net.std() * ann_factor if net.std() > 0 else float("nan")
    dd = (equity / equity.cummax() - 1).min()
    n_days = len(net)
    return {
        "total_return_pct": (equity.iloc[-1] / init - 1) * 100,
        "avg_daily_pnl": pnl.mean(),          # THE objective (₹)
        "avg_daily_ret_pct": net.mean() * 100,
        "ann_return_pct": (net.mean() * TRADING_DAYS) * 100,
        "sharpe": sharpe,
        "max_drawdown_pct": dd * 100,
        "pct_positive_days": (net > 0).mean() * 100,
        "oos_days": n_days,
    }
