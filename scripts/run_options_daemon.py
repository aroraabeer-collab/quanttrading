"""Background daemon for the options paper trade — runs continuously.

During market hours it manages the strangle in real time (stop / expiry / entry)
and logs a P&L snapshot every minute. Outside hours it idles. When the Fyers
token expires each morning it pauses and **auto-resumes** once you re-auth
(`uv run scripts/fyers_auth.py`) — no restart needed.

    uv run scripts/run_options_daemon.py      # leave running; Ctrl+C to stop

Feeds the floating widget (`scripts/pnl_widget.py`), which reads the P&L log.
"""
from __future__ import annotations

import json
import sys
import time
import traceback
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))  # project root on path

from config.settings import STATE_DIR, get_settings
from data.interfaces import ProviderError
from live.clock import MarketClock
from options.data import OptionsData
from options.paper_trader import OptionsPaperTrader

LOG = STATE_DIR / "pnl_log.jsonl"
STATUS = STATE_DIR / "daemon_status.json"
POLL_OPEN, POLL_CLOSED, POLL_RETRY = 60, 300, 120


def _write_status(rec: dict) -> None:
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    STATUS.write_text(json.dumps({"updated": datetime.now().isoformat(timespec="seconds"), **rec}))


def _log(unreal: float, realized: float, market_open: bool, note: str) -> None:
    rec = {"ts": datetime.now().isoformat(timespec="seconds"),
           "unrealized": round(unreal), "realized": round(realized),
           "total": round(unreal + realized), "market_open": market_open, "note": note}
    with open(LOG, "a") as f:
        f.write(json.dumps(rec) + "\n")
    _write_status(rec)


def main() -> None:
    clock = MarketClock()
    print("Options paper daemon running. Ctrl+C to stop.\n")
    while True:
        try:
            get_settings.cache_clear()          # pick up a refreshed token from .env
            now = clock.now()
            is_open = clock.is_open(now)
            trader = OptionsPaperTrader(OptionsData(), vix_min=13.0)

            action = trader.step()["action"] if is_open else "market closed"
            unreal, realized = trader.mark()
            _log(unreal, realized, is_open, action)
            print(f"{now:%Y-%m-%d %H:%M:%S}  {'🟢OPEN ' if is_open else '🔴CLOSED'}  "
                  f"{action:<16} unrealized ₹{unreal:,.0f}  total ₹{unreal+realized:,.0f}")
            time.sleep(POLL_OPEN if is_open else POLL_CLOSED)

        except KeyboardInterrupt:
            print("\nDaemon stopped.")
            break
        except ProviderError as e:
            msg = str(e).lower()
            if any(k in msg for k in ("-15", "-16", "authenticate", "valid token")):
                print("⚠  Token expired — run: python scripts/fyers_auth.py  (auto-resumes)")
                _write_status({"note": "token expired — run fyers_auth.py", "market_open": True})
                time.sleep(POLL_RETRY)
            else:
                print("provider error:", msg[:120])
                time.sleep(POLL_OPEN)
        except Exception:  # noqa: BLE001 — daemon must never die on a transient error
            traceback.print_exc()
            time.sleep(POLL_OPEN)


if __name__ == "__main__":
    main()
