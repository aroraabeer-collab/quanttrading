"""Volatility-risk-premium backtest — systematic NIFTY option selling.

For each monthly cycle we sell a ~1-SD short strangle (optionally with protective
wings = iron condor), priced with Black-Scholes using India VIX as the implied
vol. We mark the position to market daily along the realized spot path, so a
stop-loss and defined-risk wings behave realistically, then settle at expiry.

This isolates the core edge: premium is collected at *implied* vol (what buyers
overpay), P&L is settled at *realized* vol (how the market actually moved).
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd

from options.pricing import bs_price, intrinsic

TRADING_YEAR = 252
STRIKE_STEP = 50
LOT = 75
MARGIN_PER_LOT = 150_000.0  # approx SPAN+exposure margin to sell one NIFTY strangle


@dataclass
class VolResult:
    trades: pd.DataFrame          # per-cycle P&L and details
    equity: pd.Series             # cumulative ₹ P&L curve (1 lot)
    stats: dict


def _round_strike(x: float) -> int:
    return int(round(x / STRIKE_STEP) * STRIKE_STEP)


def _leg_value(S, Kc, Kp, T, sigma, wings):
    """Current value (to buy back) of the short structure per unit."""
    v = bs_price(S, Kc, T, sigma, "CE") + bs_price(S, Kp, T, sigma, "PE")
    if wings:
        Kcw, Kpw = wings
        v -= bs_price(S, Kcw, T, sigma, "CE") + bs_price(S, Kpw, T, sigma, "PE")
    return v


def _leg_settle(S, Kc, Kp, wings):
    v = intrinsic(S, Kc, "CE") + intrinsic(S, Kp, "PE")
    if wings:
        Kcw, Kpw = wings
        v -= intrinsic(S, Kcw, "CE") + intrinsic(S, Kpw, "PE")
    return v


def _cost(premium_value: float, n_legs: int) -> float:
    """Round-trip options cost: flat brokerage/exchange per leg + STT on premium."""
    return n_legs * 2 * 25.0 + 0.001 * premium_value * LOT


def run_vol_backtest(
    spot: pd.Series,
    vix: pd.Series,
    hold_days: int = 21,
    sd_width: float = 1.0,
    wing_sd: float | None = None,     # iron-condor wing distance in SDs (None = naked)
    stop_mult: float | None = None,   # stop-loss at this multiple of premium (None = to expiry)
    profit_target: float | None = None,  # take profit at this fraction of premium captured
    vix_min: float | None = None,     # only sell when VIX >= this (skip cheap-vol months)
) -> VolResult:
    df = pd.concat([spot.rename("S"), vix.rename("V")], axis=1).dropna()
    S, V, idx = df["S"].to_numpy(), df["V"].to_numpy(), df.index
    n = len(df)
    rows = []
    for i in range(0, n - hold_days, hold_days):
        if vix_min is not None and V[i] < vix_min:
            continue  # implied vol too cheap — sit out this cycle
        S0, sig0 = S[i], V[i] / 100.0
        Texp_days = (idx[i + hold_days] - idx[i]).days
        T0 = Texp_days / 365.0
        move = S0 * sig0 * np.sqrt(T0)
        Kc, Kp = _round_strike(S0 + sd_width * move), _round_strike(S0 - sd_width * move)
        wings = None
        n_legs = 2
        if wing_sd is not None:
            wings = (_round_strike(S0 + wing_sd * move), _round_strike(S0 - wing_sd * move))
            n_legs = 4
        prem = _leg_value(S0, Kc, Kp, T0, sig0, wings)   # premium collected (net)
        prem_rs = prem * LOT

        # Daily mark-to-market for stop-loss and/or early profit-taking.
        exit_val, exit_reason, exit_day = None, "expiry", hold_days
        if stop_mult is not None or profit_target is not None:
            for d in range(1, hold_days):
                Sd, sigd = S[i + d], V[i + d] / 100.0
                Td = (idx[i + hold_days] - idx[i + d]).days / 365.0
                cur = _leg_value(Sd, Kc, Kp, Td, sigd, wings)
                mtm_d = (prem - cur) * LOT
                if stop_mult is not None and mtm_d <= -stop_mult * prem_rs:
                    exit_val, exit_reason, exit_day = cur, "stop", d
                    break
                if profit_target is not None and mtm_d >= profit_target * prem_rs:
                    exit_val, exit_reason, exit_day = cur, "target", d
                    break
        if exit_val is None:
            exit_val = _leg_settle(S[i + hold_days], Kc, Kp, wings)

        gross = (prem - exit_val) * LOT
        pnl = gross - _cost(prem, n_legs)
        rows.append({
            "entry": idx[i].date(), "expiry": idx[i + hold_days].date(),
            "spot_in": S0, "spot_out": S[i + hold_days], "vix": V[i],
            "Kc": Kc, "Kp": Kp, "premium": prem_rs, "pnl": pnl,
            "ret": pnl / (S0 * LOT),   # P&L as fraction of underlying notional (comparable across names)
            "reason": exit_reason, "held": exit_day,
        })

    trades = pd.DataFrame(rows)
    equity = trades["pnl"].cumsum()
    stats = _stats(trades, hold_days)
    return VolResult(trades, equity, stats)


def _stats(t: pd.DataFrame, hold_days: int) -> dict:
    pnl = t["pnl"]
    wins, losses = pnl[pnl > 0], pnl[pnl <= 0]
    cycles_per_yr = TRADING_YEAR / hold_days
    ret = pnl / MARGIN_PER_LOT
    sharpe = ret.mean() / ret.std() * np.sqrt(cycles_per_yr) if ret.std() > 0 else float("nan")
    eq = pnl.cumsum()
    dd = (eq - eq.cummax()).min()
    return {
        "cycles": len(t),
        "win_rate": len(wins) / len(t) * 100 if len(t) else 0,
        "avg_win": wins.mean() if len(wins) else 0,
        "avg_loss": losses.mean() if len(losses) else 0,
        "worst_loss": pnl.min(),
        "best_win": pnl.max(),
        "total_pnl": pnl.sum(),
        "avg_pnl": pnl.mean(),
        "sharpe": sharpe,
        "max_dd": dd,
        "ann_return_pct": ret.mean() * cycles_per_yr * 100,
    }
