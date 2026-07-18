"""Rebalance the ML factor model in paper-trading mode (positional, delivery).

    uv run scripts/run_ml_paper.py [--top-k 20] [--horizon 5]

Run this on your rebalance schedule (e.g. weekly). It trains on cached daily
bars, picks the top-K names, and rebalances the paper portfolio to equal weight
at current live quotes. State persists between runs. Refresh data + token first:

    uv run scripts/fyers_auth.py
    uv run scripts/download_data.py --resolution D --days 1825 --universe nifty200
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))  # project root on path

from config.settings import get_settings
from data.fyers_provider import FyersProvider
from execution.paper_broker import PaperBroker
from live.ml_trader import MLPaperTrader


def main() -> None:
    s = get_settings()
    p = argparse.ArgumentParser(description="ML factor model — paper rebalance.")
    p.add_argument("--top-k", type=int, default=20)
    p.add_argument("--horizon", type=int, default=5)
    args = p.parse_args()

    provider = FyersProvider()
    broker = PaperBroker(
        initial_cash=s.initial_capital, slippage_bps=s.slippage_bps, segment="delivery"
    )
    resumed = broker.load_state()
    print(f"{'Resumed' if resumed else 'Fresh'} paper account — cash ₹{broker.cash():,.0f}")

    trader = MLPaperTrader(provider, broker, s, top_k=args.top_k, horizon=args.horizon)
    log = trader.rebalance()

    print(f"\nRebalance @ {log['time'].strftime('%Y-%m-%d %H:%M')}  |  NAV ₹{log['nav']:,.0f}")
    print(f"Target top-{args.top_k}: {', '.join(t.split(':')[1].replace('-EQ','') for t in log['targets'])}")
    if log["trades"]:
        print(f"\n{len(log['trades'])} orders:")
        for side, sym, qty in log["trades"]:
            print(f"  {side:<4} {sym.split(':')[1].replace('-EQ',''):<14} x{qty}")
    else:
        print("\nAlready at target — no trades.")
    print(f"\nCash ₹{broker.cash():,.0f}  |  Positions: {len(broker.positions())}  "
          f"|  Realized P&L ₹{broker.realized_pnl:,.0f}")


if __name__ == "__main__":
    main()
