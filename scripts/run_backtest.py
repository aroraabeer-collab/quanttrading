"""Run the intraday breakout backtest over cached Nifty 50 bars.

    uv run scripts/run_backtest.py [--resolution 5] [--no-report]
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))  # project root on path

from backtest.engine import run_backtest
from backtest.metrics import summary, tearsheet
from config.settings import get_settings
from config.universe import nifty50_symbols
from data.cache import read_bars
from strategy import make_strategy


def main() -> None:
    settings = get_settings()
    parser = argparse.ArgumentParser(description="Backtest the Nifty 50 breakout scanner.")
    parser.add_argument("--resolution", default=settings.bar_resolution)
    parser.add_argument("--no-report", action="store_true", help="Skip the HTML tearsheet.")
    args = parser.parse_args()

    bars = {}
    for sym in nifty50_symbols():
        df = read_bars(sym, args.resolution)
        if df is not None and not df.empty:
            bars[sym] = df
    if not bars:
        raise SystemExit(
            f"No cached bars at {args.resolution}m. Run: uv run scripts/download_data.py"
        )
    print(f"Loaded {len(bars)} symbols from cache. Strategy: {settings.strategy}")

    pf = run_backtest(bars, make_strategy(settings), settings)
    summary(pf, settings)
    if not args.no_report:
        tearsheet(pf)


if __name__ == "__main__":
    main()
