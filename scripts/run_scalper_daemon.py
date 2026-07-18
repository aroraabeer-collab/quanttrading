"""Autonomous share-scalper paper daemon — a learning tool.

Continuously buys small dips / sells small rips across a few liquid stocks during
market hours, applying the real intraday cost model. Each line shows:

    GROSS (before costs)  −  COSTS  =  NET

Watch NET sink below GROSS as trades pile up — that's the transaction-cost drain
that makes high-frequency scalping a loser. Paper money only.

    python scripts/run_scalper_daemon.py      # venv active; Ctrl+C to stop
"""
from __future__ import annotations

import json
import sys
import time
import traceback
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))  # project root on path

from config.settings import STATE_DIR, get_settings
from config.universe import fyers_symbol
from data.fyers_provider import FyersProvider
from data.interfaces import ProviderError
from execution.paper_broker import PaperBroker
from live.clock import MarketClock
from live.scalper import ScalperPaperTrader

LOG = STATE_DIR / "scalper_log.jsonl"
BROKER_STATE = STATE_DIR / "scalper_state.json"
SYMBOLS = [fyers_symbol(t) for t in
           ["RELIANCE", "HDFCBANK", "ICICIBANK", "INFY", "TCS", "SBIN", "ITC", "AXISBANK"]]
POLL_OPEN, POLL_CLOSED, POLL_RETRY = 60, 300, 120


def _summary(broker: PaperBroker):
    net = broker.realized_pnl                        # already after costs
    costs = sum(f.cost for f in broker.fills)
    return net + costs, costs, net, len(broker.fills)  # gross, costs, net, n_fills


def main() -> None:
    clock = MarketClock()
    broker = PaperBroker(initial_cash=1_000_000, slippage_bps=3.0, segment="intraday")
    broker.load_state(BROKER_STATE)
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    print("Share-scalper paper daemon running (LEARNING TOOL — this approach loses). Ctrl+C to stop.\n")
    while True:
        try:
            get_settings.cache_clear()  # pick up a refreshed token
            now = clock.now()
            if not clock.is_open(now):
                print(f"{now:%Y-%m-%d %H:%M:%S}  🔴 market closed — scalper idle")
                time.sleep(POLL_CLOSED)
                continue

            scalper = ScalperPaperTrader(FyersProvider(), broker, SYMBOLS)
            log = scalper.step(now)
            broker.save_state(BROKER_STATE)

            gross, costs, net, n = _summary(broker)
            with open(LOG, "a") as f:
                f.write(json.dumps({"ts": now.isoformat(timespec="seconds"), "trades": n,
                                    "gross": round(gross), "costs": round(costs), "net": round(net)}) + "\n")
            print(f"{now:%H:%M:%S}  🟢 {log['buys']}buy/{log['sells']}sell  "
                  f"open:{len(broker.positions())}  fills:{n}  |  "
                  f"GROSS ₹{gross:,.0f}  −  COSTS ₹{costs:,.0f}  =  NET ₹{net:,.0f}")
            time.sleep(POLL_OPEN)

        except KeyboardInterrupt:
            print("\nScalper stopped.")
            break
        except ProviderError as e:
            msg = str(e).lower()
            if any(k in msg for k in ("-15", "-16", "authenticate", "valid token")):
                print("⚠  Token expired — run: python scripts/fyers_auth.py  (auto-resumes)")
                time.sleep(POLL_RETRY)
            else:
                print("provider error:", str(e)[:120])
                time.sleep(POLL_OPEN)
        except Exception:  # noqa: BLE001 — a scalper daemon must not die on transient errors
            traceback.print_exc()
            time.sleep(POLL_OPEN)


if __name__ == "__main__":
    main()
