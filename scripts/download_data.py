"""Backfill intraday bars for the Nifty 50 into the parquet cache.

    uv run scripts/download_data.py --days 60 --resolution 5
"""
from __future__ import annotations

import argparse
import sys
from datetime import date, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))  # project root on path

from config.settings import get_settings
from config.universe import universe_symbols
from data.cache import write_bars
from data.fyers_provider import FyersProvider


def main() -> None:
    settings = get_settings()
    parser = argparse.ArgumentParser(description="Backfill NSE bars into the cache.")
    parser.add_argument("--days", type=int, default=60, help="Lookback window in calendar days.")
    parser.add_argument(
        "--resolution",
        default=settings.bar_resolution,
        help="Bar size in minutes (Fyers code, e.g. 1/3/5/15) or 'D' for daily.",
    )
    parser.add_argument(
        "--universe", default=settings.universe, help="nifty50 or nifty200."
    )
    args = parser.parse_args()

    end = date.today()
    start = end - timedelta(days=args.days)
    symbols = universe_symbols(args.universe)
    provider = FyersProvider()

    print(f"Downloading {len(symbols)} symbols @ {args.resolution}m, {start} -> {end}")
    ok = 0
    for i, sym in enumerate(symbols, 1):
        try:
            df = provider.history([sym], start, end, args.resolution)[sym]
        except Exception as exc:  # noqa: BLE001 — keep going on per-symbol failures
            print(f"  [{i:>2}/{len(symbols)}] {sym}: FAILED ({exc})")
            continue
        if df.empty:
            print(f"  [{i:>2}/{len(symbols)}] {sym}: no data")
            continue
        write_bars(sym, args.resolution, df)
        ok += 1
        print(f"  [{i:>2}/{len(symbols)}] {sym}: {len(df)} bars -> cached")
    print(f"Done. {ok}/{len(symbols)} symbols cached.")


if __name__ == "__main__":
    main()
