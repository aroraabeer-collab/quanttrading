"""Fyers implementation of :class:`DataProvider` (fyers-apiv3).

Provides chunked intraday history, latest quotes, and a simple polling live feed.
Auth uses the daily access token from settings (see scripts/fyers_auth.py).
"""
from __future__ import annotations

import time
from datetime import date, timedelta

import pandas as pd

from config.settings import get_settings
from data.interfaces import DataProvider, ProviderError, QuoteCallback

# Fyers intraday history allows a limited window per request; chunk conservatively.
_MAX_CHUNK_DAYS = 90
IST = "Asia/Kolkata"


class FyersProvider(DataProvider):
    def __init__(self, poll_seconds: float = 5.0) -> None:
        self._poll_seconds = poll_seconds
        self._settings = get_settings()
        try:
            from fyers_apiv3 import fyersModel
        except ImportError as exc:  # pragma: no cover
            raise ProviderError("fyers-apiv3 is not installed") from exc

        s = self._settings
        if not s.fyers_app_id or not s.fyers_access_token:
            raise ProviderError(
                "Missing Fyers credentials. Set FYERS_APP_ID and FYERS_ACCESS_TOKEN "
                "in .env (run scripts/fyers_auth.py to refresh the daily token)."
            )
        self._fyers = fyersModel.FyersModel(
            client_id=s.fyers_app_id,
            token=s.fyers_access_token,
            is_async=False,
            log_path="",
        )

    # --- history -----------------------------------------------------------
    def history(
        self,
        symbols: list[str],
        start: date,
        end: date,
        interval: str = "5",
    ) -> dict[str, pd.DataFrame]:
        out: dict[str, pd.DataFrame] = {}
        for sym in symbols:
            out[sym] = self._history_one(sym, start, end, interval)
        return out

    def _history_one(
        self, symbol: str, start: date, end: date, interval: str
    ) -> pd.DataFrame:
        frames: list[pd.DataFrame] = []
        # Daily data allows ~1yr per request; intraday is limited to ~100 days.
        chunk_days = 360 if interval.upper() == "D" else _MAX_CHUNK_DAYS
        chunk_start = start
        while chunk_start <= end:
            chunk_end = min(chunk_start + timedelta(days=chunk_days), end)
            resp = self._history_request(symbol, interval, chunk_start, chunk_end)
            candles = resp.get("candles", [])
            if candles:
                frames.append(_candles_to_df(candles))
            chunk_start = chunk_end + timedelta(days=1)
            time.sleep(0.35)  # stay under Fyers' per-minute quota
        if not frames:
            return _empty_bars()
        df = pd.concat(frames)
        return df[~df.index.duplicated(keep="last")].sort_index()

    def _history_request(self, symbol, interval, range_from, range_to, retries=5):
        """One history request with exponential backoff on 429 rate limits."""
        data = {
            "symbol": symbol,
            "resolution": interval,
            "date_format": "1",
            "range_from": range_from.isoformat(),
            "range_to": range_to.isoformat(),
            "cont_flag": "1",
        }
        delay = 1.0
        for attempt in range(retries):
            resp = self._fyers.history(data=data)
            if resp.get("s") == "ok":
                return resp
            if resp.get("code") == 429:  # rate limited — back off and retry
                time.sleep(delay)
                delay = min(delay * 2, 30)
                continue
            raise ProviderError(f"Fyers history failed for {symbol}: {resp}")
        raise ProviderError(f"Fyers history rate-limited for {symbol} after {retries} retries")

    # --- quotes ------------------------------------------------------------
    def quote(self, symbols: list[str]) -> dict[str, float]:
        prices: dict[str, float] = {}
        # Fyers quotes endpoint accepts a comma-separated batch (cap ~50).
        for batch in _chunks(symbols, 50):
            resp = self._fyers.quotes(data={"symbols": ",".join(batch)})
            if resp.get("s") != "ok":
                raise ProviderError(f"Fyers quotes failed: {resp}")
            for item in resp.get("d", []):
                sym = item.get("n")
                lp = item.get("v", {}).get("lp")
                if sym is not None and lp is not None:
                    prices[sym] = float(lp)
        return prices

    # --- positions (READ-ONLY) ---------------------------------------------
    def positions(self) -> list[dict]:
        """Current open broker positions. **Read-only — never places orders.**

        Lets the live daemon detect that you actually placed (or closed) a trade,
        and record your real fills. Reading positions needs no Algo-ID; only
        automated *order placement* does.
        """
        resp = self._fyers.positions()
        if resp.get("s") != "ok":
            raise ProviderError(f"Fyers positions failed: {resp}")
        out = []
        for p in resp.get("netPositions", []):
            qty = int(p.get("netQty") or 0)
            if qty == 0:
                continue  # squared off
            out.append({
                "symbol": p.get("symbol"),
                "qty": qty,
                "avg_price": float(p.get("netAvg") or 0.0),
            })
        return out

    # --- live feed (polling) ----------------------------------------------
    def subscribe(self, symbols: list[str], callback: QuoteCallback) -> None:
        """Poll quotes on an interval and invoke ``callback`` per symbol.

        Simple and robust; a true WebSocket tick feed (fyers_apiv3.FyersWebsocket)
        is a future enhancement. Blocks until interrupted.
        """
        while True:
            ts = pd.Timestamp.now(tz=IST)
            for sym, price in self.quote(symbols).items():
                callback(sym, price, ts)
            time.sleep(self._poll_seconds)


def _candles_to_df(candles: list[list]) -> pd.DataFrame:
    df = pd.DataFrame(
        candles, columns=["epoch", "open", "high", "low", "close", "volume"]
    )
    df.index = pd.to_datetime(df["epoch"], unit="s", utc=True).dt.tz_convert(IST)
    df.index.name = "timestamp"
    return df.drop(columns=["epoch"])


def _empty_bars() -> pd.DataFrame:
    idx = pd.DatetimeIndex([], name="timestamp", tz=IST)
    return pd.DataFrame(
        {c: pd.Series(dtype="float64") for c in ["open", "high", "low", "close", "volume"]},
        index=idx,
    )


def _chunks(seq: list[str], n: int):
    for i in range(0, len(seq), n):
        yield seq[i : i + n]
