"""NSE market-hours clock.

Uses pandas-market-calendars for the NSE trading calendar (holidays), with a
fallback to fixed hours (09:15–15:30 IST) if the calendar isn't available.
"""
from __future__ import annotations

from datetime import date, time

import pandas as pd

from config.settings import Settings, get_settings

IST = "Asia/Kolkata"
OPEN_TIME = time(9, 15)
CLOSE_TIME = time(15, 30)


class MarketClock:
    def __init__(self, settings: Settings | None = None) -> None:
        s = settings or get_settings()
        self.square_off_time = _parse_time(s.square_off_time)
        self._cal = _load_calendar()

    def now(self) -> pd.Timestamp:
        return pd.Timestamp.now(tz=IST)

    def is_trading_day(self, d: date | None = None) -> bool:
        d = d or self.now().date()
        if self._cal is None:
            return d.weekday() < 5  # Mon–Fri fallback
        return not self._cal.schedule(start_date=d, end_date=d).empty

    def is_open(self, now: pd.Timestamp | None = None) -> bool:
        now = now or self.now()
        if not self.is_trading_day(now.date()):
            return False
        return OPEN_TIME <= now.timetz().replace(tzinfo=None) <= CLOSE_TIME

    def past_square_off(self, now: pd.Timestamp | None = None) -> bool:
        now = now or self.now()
        return now.timetz().replace(tzinfo=None) >= self.square_off_time


def _parse_time(hhmm: str) -> time:
    h, m = hhmm.split(":")
    return time(int(h), int(m))


def _load_calendar():
    try:
        import pandas_market_calendars as mcal

        for name in ("NSE", "XNSE"):
            try:
                return mcal.get_calendar(name)
            except Exception:  # noqa: BLE001 — try the next alias
                continue
    except Exception:  # noqa: BLE001 — library missing / import error
        return None
    return None
