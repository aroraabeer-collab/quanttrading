"""Live paper trading for the index short strangle. Run daily.

    uv run scripts/run_options_paper.py

If flat, it sells a ~1-SD Nifty strangle at live prices; if in a trade, it marks
to market and closes on the 2x stop-loss or at expiry. Simulated — no real money.
Refresh the Fyers token first (uv run scripts/fyers_auth.py).
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))  # project root on path

from live.clock import MarketClock
from options.data import OptionsData
from options.paper_trader import OptionsPaperTrader


def main() -> None:
    clock = MarketClock()
    market_open = clock.is_open()
    trader = OptionsPaperTrader(OptionsData(), sd_width=1.0, stop_mult=2.0)
    log = trader.step()

    if market_open:
        print("\n🟢 Market OPEN — prices are live.")
    else:
        print("\n🔴 Market CLOSED — prices below are last-traded, NOT live.")
        print("   P&L won't move until the market opens (Mon–Fri, 9:15 AM–3:30 PM IST).")

    print(f"\n[{log['time']}]  {log['action']}")
    for k, v in log["detail"].items():
        print(f"    {k}: {v}")

    st = trader.state
    hist = st["history"]
    print("\n" + "=" * 52)
    print("PAPER TRACK RECORD (this is what you're validating)")
    print("=" * 52)
    if hist:
        wins = [h for h in hist if h["pnl"] > 0]
        print(f"  Completed cycles: {len(hist)}   Win rate: {len(wins)/len(hist)*100:.0f}%  "
              f"(backtest said ~78%)")
        print(f"  Realized P&L:     ₹{st['realized_pnl']:,.0f}")
        print("  Recent closes:")
        for h in hist[-5:]:
            print(f"    {h.get('exit_date','?')}  {h['ce_strike']}CE/{h['pe_strike']}PE  "
                  f"₹{h['pnl']:>8,.0f}  ({h['reason']})")
    else:
        print("  No completed cycles yet — first strangle is still open.")
        print("  ▶ Watch for: a full expiry cycle, and a stop-loss trigger.")
    pos = st["position"]
    if pos:
        max_p = pos["premium"] * 75
        print(f"\n  OPEN: short {pos['ce_strike']}CE + {pos['pe_strike']}PE, expiry {pos['expiry']}")
        if log["action"] == "HOLD":
            det = log["detail"]
            print(f"    Profit so far:      ₹{det['profit_so_far']:,.0f}   "
                  f"({det['pct_captured']}% of max)")
            print(f"    Max profit (if it expires in range):  ₹{det['max_profit_at_expiry']:,.0f}")
            print(f"    Buy-back cost now:  ₹{det['buyback_cost_now']:,.0f}")
        else:
            print(f"    Max profit if it expires in range: ₹{max_p:,.0f}")


if __name__ == "__main__":
    main()
