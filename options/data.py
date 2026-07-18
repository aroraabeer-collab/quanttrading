"""Fyers options data: symbol construction, expiry calendar, historical prices.

Fyers weekly NIFTY option symbols encode the expiry as ``YY<M><DD>`` where month
is ``1``–``9`` for Jan–Sep and ``O``/``N``/``D`` for Oct/Nov/Dec — e.g. the
14-Jul-2026 24050 call is ``NSE:NIFTY2671424050CE``. Monthly (last-of-month)
contracts use ``YY<MON>`` (e.g. ``NSE:NIFTY26JUL24000CE``).

We build candidate symbols and *validate them by fetching* — an invalid symbol
returns ``no_data``, so we never rely on guessing the calendar perfectly.
"""
from __future__ import annotations

from datetime import date, timedelta

import pandas as pd

from data.fyers_provider import FyersProvider

NIFTY_INDEX = "NSE:NIFTY50-INDEX"
NIFTY_LOT = 75  # contract multiplier (as of 2025+)
STRIKE_STEP = 50
_MONTH_CODE = {1: "1", 2: "2", 3: "3", 4: "4", 5: "5", 6: "6",
               7: "7", 8: "8", 9: "9", 10: "O", 11: "N", 12: "D"}


def weekly_symbol(expiry: date, strike: int, opt: str) -> str:
    yy = expiry.year % 100
    return f"NSE:NIFTY{yy:02d}{_MONTH_CODE[expiry.month]}{expiry.day:02d}{strike}{opt}"


def monthly_symbol(expiry: date, strike: int, opt: str) -> str:
    yy = expiry.year % 100
    return f"NSE:NIFTY{yy:02d}{expiry.strftime('%b').upper()}{strike}{opt}"


def atm_strike(spot: float) -> int:
    return int(round(spot / STRIKE_STEP) * STRIKE_STEP)


class OptionsData:
    def __init__(self, provider: FyersProvider | None = None) -> None:
        self.p = provider or FyersProvider()

    def index_history(self, start: date, end: date, interval: str = "D") -> pd.DataFrame:
        return self.p.history([NIFTY_INDEX], start, end, interval)[NIFTY_INDEX]

    def upcoming_expiries(self) -> list[date]:
        """Expiry dates from the live option chain (future only)."""
        oc = self.p._fyers.optionchain(
            data={"symbol": NIFTY_INDEX, "strikecount": 1, "timestamp": ""}
        )
        out = []
        for e in oc.get("data", {}).get("expiryData", []):
            try:
                out.append(pd.to_datetime(e["date"], format="%d-%m-%Y").date())
            except Exception:
                continue
        return sorted(out)

    def option_history(self, symbol: str, start: date, end: date, interval: str = "D") -> pd.DataFrame:
        """Historical bars for one option contract (empty frame if no data)."""
        try:
            return self.p.history([symbol], start, end, interval)[symbol]
        except Exception:
            return pd.DataFrame()

    def live_chain(self, strikecount: int = 20, target_dte: int | None = None) -> dict:
        """Live option chain. With ``target_dte`` set, picks the expiry closest to
        that many days out (matching the backtest's ~monthly hold); else nearest.

        Returns ``{expiry: date, spot: float, vix: float, options: DataFrame}``
        where options has columns [strike, type, ltp, symbol].
        """
        fy = self.p._fyers
        meta = fy.optionchain(data={"symbol": NIFTY_INDEX, "strikecount": 1, "timestamp": ""})
        exp_list = meta.get("data", {}).get("expiryData", [])
        if not exp_list:
            raise RuntimeError(f"No expiries in option chain: {meta}")
        today = date.today()
        if target_dte is None:
            chosen = exp_list[0]  # API returns them soonest-first
        else:
            def _dte(e):
                return abs((pd.to_datetime(e["date"], format="%d-%m-%Y").date() - today).days - target_dte)
            chosen = min(exp_list, key=_dte)
        oc = fy.optionchain(
            data={"symbol": NIFTY_INDEX, "strikecount": strikecount,
                  "timestamp": str(chosen.get("expiry", ""))}
        )
        nearest = chosen
        d = oc.get("data", {})
        rows, spot = [], None
        for o in d.get("optionsChain", []):
            if o.get("option_type") in ("CE", "PE"):
                rows.append({"strike": int(o["strike_price"]), "type": o["option_type"],
                             "ltp": float(o["ltp"]), "symbol": o["symbol"]})
            elif o.get("strike_price") in (-1, "-1"):
                spot = float(o.get("ltp"))
        return {
            "expiry": pd.to_datetime(nearest["date"], format="%d-%m-%Y").date(),
            "spot": spot,
            "vix": float(d.get("indiavixData", {}).get("ltp", 0) or 0),
            "options": pd.DataFrame(rows),
        }

    def resolve_option(self, expiry: date, strike: int, opt: str, near: date):
        """Return (symbol, history_df) for a contract, trying weekly then monthly
        format and a 1-day expiry fallback (holiday shifts). Empty df if none work.
        """
        start = near - timedelta(days=10)
        end = expiry + timedelta(days=2)
        for exp in (expiry, expiry - timedelta(days=1)):
            for builder in (weekly_symbol, monthly_symbol):
                sym = builder(exp, strike, opt)
                df = self.option_history(sym, start, end, "D")
                if not df.empty:
                    return sym, df
        return None, pd.DataFrame()
