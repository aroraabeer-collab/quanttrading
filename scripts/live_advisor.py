"""REAL-MONEY advisor — prints the exact iron condor to place. Never trades.

    python scripts/live_advisor.py            # show today's ticket (or a refusal)
    python scripts/live_advisor.py --record   # after you place it, log your ACTUAL fills

You place every order yourself in the Fyers app. This tool only advises, enforces
the risk limits, and records what you actually got filled at.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))  # project root on path

from config.settings import get_settings
from live.clock import MarketClock
from options.advisor import LiveCondorAdvisor, format_ticket
from options.data import OptionsData
from options.real_ledger import RealLedger


def main() -> None:
    p = argparse.ArgumentParser(description="Live iron-condor advisor (manual execution).")
    p.add_argument("--record", action="store_true",
                   help="Record the ACTUAL credit you were filled at, after placing.")
    p.add_argument("--credit", type=float, help="₹ credit actually received (with --record).")
    args = p.parse_args()

    s = get_settings()
    ledger = RealLedger()
    st = ledger.stats()

    print(f"\n💰 REAL MONEY · account ₹{s.live_account:,.0f} · max risk/trade "
          f"{s.live_max_risk_pct*100:.0f}% · {s.live_max_lots} lot max")
    if st["trades"]:
        print(f"   Live record: {st['trades']} trades · {st['win_rate']:.0f}% win · "
              f"realized ₹{st['realized']:,.0f} (best ₹{st['best']:,.0f} / worst ₹{st['worst']:,.0f})")

    open_pos = ledger.open_position()
    if open_pos:
        print(f"\n⚠  You already have an OPEN position (entered {open_pos['entry_date']}, "
              f"expiry {open_pos['expiry']}). Manage it with scripts/live_monitor.py.")
        print("   One position at a time — do not stack trades.\n")
        return

    clock = MarketClock()
    if not clock.is_open():
        print("🔴 Market closed — prices aren't live. Run during 9:15–15:30 IST.\n")
        return

    advisor = LiveCondorAdvisor(OptionsData(), s, realized_pnl=ledger.realized_pnl())
    ticket = advisor.advise()
    print(format_ticket(ticket, s))

    if args.record:
        if not ticket.ok:
            print("Nothing to record — the advisor refused this trade.\n")
            return
        credit = args.credit
        if credit is None:
            credit = float(input("Actual credit received (₹): ").strip())
        ledger.record_entry(ticket.legs, credit, str(ticket.expiry),
                            ticket.max_loss, ticket.net_premium)
        slip = ticket.net_premium - credit
        print(f"\n✅ Recorded. Model said ₹{ticket.net_premium:,.0f}, you got ₹{credit:,.0f} "
              f"(slippage ₹{slip:,.0f}).")
        print("   Now monitor it: python scripts/live_monitor.py\n")


if __name__ == "__main__":
    main()
