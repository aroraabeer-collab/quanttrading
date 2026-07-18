"""Run the intraday breakout scanner in paper-trading mode on live Fyers data.

    uv run scripts/run_paper.py

Trades are simulated (PaperBroker) — no real orders are placed. Refresh the
Fyers token first with: uv run scripts/fyers_auth.py
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))  # project root on path

from config.settings import get_settings
from data.fyers_provider import FyersProvider
from execution.paper_broker import PaperBroker
from live.runner import PaperRunner
from strategy import make_strategy


def main() -> None:
    s = get_settings()
    provider = FyersProvider()
    broker = PaperBroker(initial_cash=s.initial_capital, slippage_bps=s.slippage_bps)
    runner = PaperRunner(provider, broker, make_strategy(s), s)
    runner.run()


if __name__ == "__main__":
    main()
