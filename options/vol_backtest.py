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
    regime_veto=None,                 # optional RegimeVeto: skip hostile regimes
) -> VolResult:
    df = pd.concat([spot.rename("S"), vix.rename("V")], axis=1).dropna()
    S, V, idx = df["S"].to_numpy(), df["V"].to_numpy(), df.index
    n = len(df)
    rows = []
    nifty_s, vix_s = df["S"], df["V"]
    for i in range(0, n - hold_days, hold_days):
        if vix_min is not None and V[i] < vix_min:
            continue  # implied vol too cheap — sit out this cycle
        if regime_veto is not None and i >= 55:
            # Point-in-time check — only data up to entry, no lookahead.
            if regime_veto.check(nifty_s.iloc[: i + 1], vix_s.iloc[: i + 1]):
                continue
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
    equity = trades["pnl"].cumsum() if not trades.empty else pd.Series(dtype=float)
    stats = _stats(trades, hold_days, span_days=n)
    return VolResult(trades, equity, stats)


def run_vol_backtest_reentry(
    spot: pd.Series,
    vix: pd.Series,
    hold_days: int = 21,
    sd_width: float = 1.0,
    wing_sd: float | None = None,
    stop_mult: float | None = None,
    profit_target: float | None = None,
    vix_min: float | None = None,
    cooldown_days: int = 1,
) -> VolResult:
    """Event-driven variant: **redeploys capital as soon as a trade exits.**

    `run_vol_backtest` enters only on fixed `hold_days` slots, so an early exit
    leaves capital idle until the next slot — which unfairly penalises taking
    profit early. Here the next position opens `cooldown_days` after the previous
    one closes, so faster cycling actually earns its extra cycles.

    Stats are annualised by **actual elapsed time**, not an assumed cycle count.
    """
    df = pd.concat([spot.rename("S"), vix.rename("V")], axis=1).dropna()
    S, V, idx = df["S"].to_numpy(), df["V"].to_numpy(), df.index
    n = len(df)
    rows: list[dict] = []
    days_in_market = 0

    i = 0
    while i < n - 1:
        if vix_min is not None and V[i] < vix_min:
            i += 1                       # wait for premium to be worth selling
            continue
        exp_i = min(i + hold_days, n - 1)
        T0 = (idx[exp_i] - idx[i]).days / 365.0
        if exp_i <= i or T0 <= 0:
            break

        S0, sig0 = S[i], V[i] / 100.0
        move = S0 * sig0 * np.sqrt(T0)
        Kc, Kp = _round_strike(S0 + sd_width * move), _round_strike(S0 - sd_width * move)
        wings, n_legs = None, 2
        if wing_sd is not None:
            wings = (_round_strike(S0 + wing_sd * move), _round_strike(S0 - wing_sd * move))
            n_legs = 4
        prem = _leg_value(S0, Kc, Kp, T0, sig0, wings)
        prem_rs = prem * LOT

        exit_i, exit_val, reason = exp_i, None, "expiry"
        if stop_mult is not None or profit_target is not None:
            for d in range(i + 1, exp_i):
                Td = (idx[exp_i] - idx[d]).days / 365.0
                cur = _leg_value(S[d], Kc, Kp, Td, V[d] / 100.0, wings)
                mtm = (prem - cur) * LOT
                if stop_mult is not None and mtm <= -stop_mult * prem_rs:
                    exit_i, exit_val, reason = d, cur, "stop"
                    break
                if profit_target is not None and mtm >= profit_target * prem_rs:
                    exit_i, exit_val, reason = d, cur, "target"
                    break
        if exit_val is None:
            exit_val = _leg_settle(S[exp_i], Kc, Kp, wings)

        cost = _cost(prem, n_legs)
        pnl = (prem - exit_val) * LOT - cost
        held = exit_i - i
        days_in_market += held
        rows.append({
            "entry": idx[i].date(), "exit": idx[exit_i].date(),
            "spot_in": S0, "spot_out": S[exit_i], "vix": V[i],
            "Kc": Kc, "Kp": Kp, "premium": prem_rs, "pnl": pnl,
            "cost": cost, "reason": reason, "held": held,
        })
        i = exit_i + cooldown_days       # ← redeploy instead of waiting for a slot

    trades = pd.DataFrame(rows)
    equity = trades["pnl"].cumsum() if not trades.empty else pd.Series(dtype=float)
    return VolResult(trades, equity, _stats_reentry(trades, n, days_in_market))


def _stats_reentry(t: pd.DataFrame, span_days: int, days_in_market: int) -> dict:
    """Annualised by real elapsed time, so variants with different trade counts
    are directly comparable."""
    if t.empty:
        return {"trades": 0, "win_rate": 0.0, "sharpe": float("nan")}
    years = max(span_days / TRADING_YEAR, 1e-9)
    pnl = t["pnl"]
    wins, losses = pnl[pnl > 0], pnl[pnl <= 0]
    ret = pnl / MARGIN_PER_LOT
    trades_per_yr = len(t) / years
    sharpe = (ret.mean() / ret.std() * np.sqrt(trades_per_yr)) if ret.std() > 0 else float("nan")
    eq = pnl.cumsum()
    return {
        "trades": len(t),
        "trades_per_yr": trades_per_yr,
        "win_rate": len(wins) / len(t) * 100,
        "avg_win": wins.mean() if len(wins) else 0.0,
        "avg_loss": losses.mean() if len(losses) else 0.0,
        "worst_loss": pnl.min(),
        "total_pnl": pnl.sum(),
        "ann_return_pct": (pnl.sum() / MARGIN_PER_LOT) / years * 100,
        "sharpe": sharpe,
        "max_dd": (eq - eq.cummax()).min(),
        "avg_days_held": t["held"].mean(),
        "utilization_pct": days_in_market / span_days * 100,
        "total_costs": t["cost"].sum(),
    }


def _stats(t: pd.DataFrame, hold_days: int, span_days: int | None = None) -> dict:
    if t.empty:  # e.g. a vix_min so high that nothing ever qualified
        return {"cycles": 0, "win_rate": 0.0, "avg_win": 0.0, "avg_loss": 0.0,
                "worst_loss": 0.0, "best_win": 0.0, "total_pnl": 0.0, "avg_pnl": 0.0,
                "sharpe": float("nan"), "max_dd": 0.0, "ann_return_pct": 0.0}
    pnl = t["pnl"]
    wins, losses = pnl[pnl > 0], pnl[pnl <= 0]
    # Annualise by how many cycles ACTUALLY happened. Using a fixed
    # TRADING_YEAR/hold_days inflates Sharpe whenever cycles are skipped
    # (e.g. by the VIX filter) — which silently overstated earlier results.
    if span_days:
        cycles_per_yr = len(t) / max(span_days / TRADING_YEAR, 1e-9)
    else:
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
