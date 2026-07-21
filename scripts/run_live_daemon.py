"""Autonomous live daemon — watches the market and tells you when to act.

It NEVER places an order. It applies every risk gate, detects your real position
(read-only), and fires a macOS notification when a trade or exit is due.

    python scripts/run_live_daemon.py                 # uses settings.live_mode
    python scripts/run_live_daemon.py --mode alert    # notify me when to act
    python scripts/run_live_daemon.py --mode shadow   # decide + log only

Refresh your token first: python scripts/fyers_auth.py
"""
from __future__ import annotations

import argparse
import sys
import time
import traceback
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))  # project root on path

from config.settings import get_settings
from data.interfaces import ProviderError
from live.auto_daemon import DECISIONS, LiveAutoDaemon
from live.clock import MarketClock
from options.data import OptionsData

POLL_OPEN, POLL_CLOSED, POLL_RETRY = 60, 300, 120


def main() -> None:
    p = argparse.ArgumentParser(description="Live options daemon (advises, never trades).")
    p.add_argument("--mode", choices=["shadow", "alert"],
                   help="Override settings.live_mode for this run.")
    args = p.parse_args()

    s = get_settings()
    if args.mode:
        s = s.model_copy(update={"live_mode": args.mode})

    clock = MarketClock()
    daemon = LiveAutoDaemon(OptionsData(), s)   # raises if mode='auto' without Algo-ID
    print(f"\n🤖 Live daemon running in {daemon.mode.upper()} mode — it will NOT place orders.")
    print(f"   Account ₹{s.live_account:,.0f} · max risk {s.live_max_risk_pct*100:.0f}%/trade "
          f"· halt at −{s.live_halt_drawdown*100:.0f}%")
    print(f"   Decisions logged to {DECISIONS}")
    print("   Ctrl+C to stop.\n")

    while True:
        try:
            get_settings.cache_clear()          # pick up a refreshed token
            now = clock.now()
            if not clock.is_open(now):
                print(f"{now:%Y-%m-%d %H:%M:%S}  🔴 market closed — idle")
                time.sleep(POLL_CLOSED)
                continue

            rec = daemon.cycle(now)
            extra = rec.get("reason", "")
            print(f"{now:%H:%M:%S}  {rec['decision'].upper():<9} "
                  f"{('₹' + format(rec['pnl'], ',')) if 'pnl' in rec else ''}  {extra[:70]}")
            time.sleep(POLL_OPEN)

        except KeyboardInterrupt:
            print("\nDaemon stopped.")
            break
        except ProviderError as e:
            msg = str(e).lower()
            if any(k in msg for k in ("-15", "-16", "authenticate", "valid token")):
                print("⚠  Token expired — run: python scripts/fyers_auth.py  (auto-resumes)")
                time.sleep(POLL_RETRY)
            else:
                print("provider error:", str(e)[:120])
                time.sleep(POLL_OPEN)
        except Exception:  # noqa: BLE001 — a watchdog must not die on transient errors
            traceback.print_exc()
            time.sleep(POLL_OPEN)


if __name__ == "__main__":
    main()
