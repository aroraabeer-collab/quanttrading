"""Black-Scholes pricing for European index options (NIFTY).

Used to backtest option selling without expired-contract price data: we price
each contract at entry using India VIX as the implied vol, then settle against
the realized spot at expiry. This is the standard way to study the volatility
risk premium when historical option quotes aren't available.
"""
from __future__ import annotations

from math import erf, exp, log, sqrt

RISK_FREE = 0.065  # ~Indian short-term risk-free rate


def _norm_cdf(x: float) -> float:
    return 0.5 * (1.0 + erf(x / sqrt(2.0)))


def bs_price(S: float, K: float, T: float, sigma: float, opt: str, r: float = RISK_FREE) -> float:
    """European option price. ``opt`` is 'CE' (call) or 'PE' (put). T in years."""
    if T <= 0 or sigma <= 0:
        return max(0.0, S - K) if opt == "CE" else max(0.0, K - S)
    d1 = (log(S / K) + (r + 0.5 * sigma ** 2) * T) / (sigma * sqrt(T))
    d2 = d1 - sigma * sqrt(T)
    if opt == "CE":
        return S * _norm_cdf(d1) - K * exp(-r * T) * _norm_cdf(d2)
    return K * exp(-r * T) * _norm_cdf(-d2) - S * _norm_cdf(-d1)


def bs_delta(S: float, K: float, T: float, sigma: float, opt: str, r: float = RISK_FREE) -> float:
    if T <= 0 or sigma <= 0:
        return 0.0
    d1 = (log(S / K) + (r + 0.5 * sigma ** 2) * T) / (sigma * sqrt(T))
    return _norm_cdf(d1) if opt == "CE" else _norm_cdf(d1) - 1.0


def intrinsic(S: float, K: float, opt: str) -> float:
    return max(0.0, S - K) if opt == "CE" else max(0.0, K - S)
