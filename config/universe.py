"""Trading universe: Nifty 50 constituents in Fyers symbol format.

Fyers cash-equity symbols use the form ``NSE:<SYMBOL>-EQ``.

CAVEAT — survivorship bias: this is the *current* index membership, hardcoded.
Backtests over history using this fixed list overstate returns (today's winners
were not all in the index in the past, and dropped names are missing). This is
acceptable for a first framework; point-in-time index membership is a documented
future refinement (see plan "Out of scope").
"""
from __future__ import annotations

# Underlying NSE tickers (cash segment). Update as index membership changes.
NIFTY_50_TICKERS: list[str] = [
    "ADANIENT", "ADANIPORTS", "APOLLOHOSP", "ASIANPAINT", "AXISBANK",
    "BAJAJ-AUTO", "BAJFINANCE", "BAJAJFINSV", "BEL", "BHARTIARTL",
    "BPCL", "BRITANNIA", "CIPLA", "COALINDIA", "DRREDDY",
    "EICHERMOT", "GRASIM", "HCLTECH", "HDFCBANK", "HDFCLIFE",
    "HEROMOTOCO", "HINDALCO", "HINDUNILVR", "ICICIBANK", "INDUSINDBK",
    "INFY", "ITC", "JSWSTEEL", "KOTAKBANK", "LT",
    "M&M", "MARUTI", "NESTLEIND", "NTPC", "ONGC",
    "POWERGRID", "RELIANCE", "SBILIFE", "SBIN", "SHRIRAMFIN",
    "SUNPHARMA", "TATACONSUM", "TATAMOTORS", "TATASTEEL", "TCS",
    "TECHM", "TITAN", "TRENT", "ULTRACEMCO", "WIPRO",
]

# Nifty 50 index symbol on Fyers (used as the backtest benchmark).
NIFTY_50_INDEX = "NSE:NIFTY50-INDEX"


def fyers_symbol(ticker: str) -> str:
    """Convert an NSE ticker to a Fyers cash-equity symbol."""
    return f"NSE:{ticker}-EQ"


def nifty50_symbols() -> list[str]:
    """Nifty 50 constituents as Fyers ``NSE:<SYMBOL>-EQ`` symbols."""
    return [fyers_symbol(t) for t in NIFTY_50_TICKERS]


def nifty200_symbols() -> list[str]:
    """Nifty 200 constituents as Fyers ``NSE:<SYMBOL>-EQ`` symbols."""
    from config.universe_nifty200 import NIFTY_200_TICKERS

    return [fyers_symbol(t) for t in NIFTY_200_TICKERS]


def universe_symbols(name: str = "nifty50") -> list[str]:
    """Active trading universe by name ('nifty50' or 'nifty200')."""
    name = name.lower()
    if name == "nifty200":
        return nifty200_symbols()
    if name == "nifty50":
        return nifty50_symbols()
    raise ValueError(f"Unknown universe '{name}' (expected 'nifty50' or 'nifty200')")
