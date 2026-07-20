"""Monitor for the REAL open iron condor. Alerts only — never places orders.

Marks all four legs from live quotes and tells you, in plain language, when to
act: take profit, cut before the loss caps out, or handle expiry. You place every
order yourself.
"""
from __future__ import annotations

import pandas as pd

from config.settings import Settings, get_settings
from options.data import NIFTY_LOT, OptionsData
from options.real_ledger import RealLedger


class LiveMonitor:
    def __init__(self, data: OptionsData, ledger: RealLedger | None = None,
                 settings: Settings | None = None) -> None:
        self.d = data
        self.ledger = ledger or RealLedger()
        self.s = settings or get_settings()

    def mark(self) -> dict | None:
        """Current P&L of the live condor from real quotes (None if flat)."""
        pos = self.ledger.open_position()
        if not pos:
            return None
        legs = pos["legs"]
        quotes = self.d.p.quote([leg["symbol"] for leg in legs])

        # Closing cost: buy back the shorts, sell the longs.
        shorts = sum(quotes.get(l["symbol"], l["ltp"]) for l in legs if l["action"].strip() == "SELL")
        longs = sum(quotes.get(l["symbol"], l["ltp"]) for l in legs if l["action"].strip() == "BUY")
        debit_to_close = (shorts - longs) * NIFTY_LOT
        pnl = pos["credit"] - debit_to_close

        expiry = pd.to_datetime(pos["expiry"]).date()
        dte = (expiry - pd.Timestamp.now(tz="Asia/Kolkata").date()).days
        return {
            "pnl": pnl,
            "credit": pos["credit"],
            "max_loss": pos["max_loss"],
            "debit_to_close": debit_to_close,
            "pct_of_credit": pnl / pos["credit"] * 100 if pos["credit"] else 0.0,
            "dte": dte,
            "expiry": str(expiry),
            "legs": legs,
        }

    def alerts(self, m: dict) -> list[str]:
        """Plain-language actions. Empty list = hold, do nothing."""
        out: list[str] = []
        target = self.s.live_profit_target
        if m["pnl"] >= target * m["credit"]:
            out.append(f"✅ TAKE PROFIT — you're at ₹{m['pnl']:,.0f} "
                       f"({m['pct_of_credit']:.0f}% of credit). Close all 4 legs. Don't get greedy.")
        if m["pnl"] <= -0.75 * m["max_loss"]:
            out.append(f"🛑 CUT IT — loss ₹{m['pnl']:,.0f} is near your ₹{m['max_loss']:,.0f} cap. "
                       "Close now; don't wait for the wings to absorb it.")
        if 0 <= m["dte"] <= 1:
            out.append(f"⏰ EXPIRY {m['expiry']} — close today. Do not carry it into settlement.")
        if m["dte"] < 0:
            out.append("⚠️  Past expiry — reconcile with your broker and record the exit.")
        return out


def format_status(m: dict | None, alerts: list[str], s: Settings | None = None) -> str:
    s = s or get_settings()
    if m is None:
        return "\nNo open live position. Run: python scripts/live_advisor.py\n"
    sign = "+" if m["pnl"] >= 0 else "−"
    lines = [
        "",
        "=" * 58,
        f"  LIVE CONDOR   ·   expiry {m['expiry']}   ·   {m['dte']} DTE",
        "=" * 58,
        f"  P&L now      : {sign}₹{abs(m['pnl']):,.0f}   ({m['pct_of_credit']:+.0f}% of credit)",
        f"  Credit taken : ₹{m['credit']:,.0f}   ← max profit",
        f"  Max loss     : ₹{m['max_loss']:,.0f}   ← capped by wings",
        f"  Close cost   : ₹{m['debit_to_close']:,.0f}   (buy back shorts, sell longs)",
        f"  Profit target: ₹{m['credit'] * s.live_profit_target:,.0f}",
        "",
    ]
    lines += ["  " + a for a in alerts] if alerts else ["  → HOLD. Nothing to do."]
    lines += ["=" * 58, ""]
    return "\n".join(lines)
