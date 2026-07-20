"""Monitor your REAL open iron condor. Alerts only — you place every order.

    python scripts/live_monitor.py                    # one check
    python scripts/live_monitor.py --watch            # re-check every 60s
    python scripts/live_monitor.py --close 1850       # record the exit (₹ debit paid)
"""
from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))  # project root on path

from config.settings import get_settings
from live.clock import MarketClock
from options.data import OptionsData
from options.live_monitor import LiveMonitor, format_status
from options.real_ledger import RealLedger


def main() -> None:
    p = argparse.ArgumentParser(description="Live condor monitor (alerts only).")
    p.add_argument("--watch", action="store_true", help="Re-check every 60 seconds.")
    p.add_argument("--close", type=float, metavar="DEBIT",
                   help="Record closing the position: ₹ debit you actually paid.")
    p.add_argument("--reason", default="manual", help="Why you closed (with --close).")
    args = p.parse_args()

    s = get_settings()
    ledger = RealLedger()

    if args.close is not None:
        rec = ledger.record_exit(args.close, args.reason)
        st = ledger.stats()
        print(f"\n✅ Closed. P&L on this trade: ₹{rec['pnl']:,.0f} ({args.reason})")
        print(f"   Live record: {st['trades']} trades · {st['win_rate']:.0f}% win · "
              f"realized ₹{st['realized']:,.0f}")
        print(f"   (backtest said ~78-84% win — this is your REAL number)\n")
        return

    clock = MarketClock()
    monitor = LiveMonitor(OptionsData(), ledger, s)
    while True:
        if not clock.is_open():
            print("🔴 Market closed — showing last-traded prices.")
        m = monitor.mark()
        print(format_status(m, monitor.alerts(m) if m else [], s))
        if not args.watch or m is None:
            break
        time.sleep(60)


if __name__ == "__main__":
    main()
