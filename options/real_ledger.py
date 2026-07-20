"""Ledger of REAL money trades — actual fills, not model prices.

This is the live-validation data paper trading never produced: what you actually
got filled at, real slippage vs the model, and your realized win rate against the
backtest's 78–84%. It also feeds the advisor's drawdown halt.

Files (both gitignored): state/live_position.json, state/real_fills.jsonl
"""
from __future__ import annotations

import json
from datetime import date, datetime

from config.settings import STATE_DIR

POSITION = STATE_DIR / "live_position.json"
FILLS = STATE_DIR / "real_fills.jsonl"


class RealLedger:
    # --- open position ------------------------------------------------------
    def open_position(self) -> dict | None:
        if not POSITION.exists():
            return None
        return json.loads(POSITION.read_text()) or None

    def record_entry(self, legs: list[dict], actual_credit: float, expiry: str,
                     max_loss: float, model_credit: float = 0.0) -> dict:
        """Record what you ACTUALLY got filled at when you placed the condor."""
        STATE_DIR.mkdir(parents=True, exist_ok=True)
        pos = {
            "entry_date": str(date.today()),
            "expiry": expiry,
            "legs": legs,
            "credit": actual_credit,          # ₹ actually received
            "model_credit": model_credit,     # ₹ the advisor predicted
            "slippage": model_credit - actual_credit,
            "max_loss": max_loss,
        }
        POSITION.write_text(json.dumps(pos, indent=2, default=str))
        self._append({"event": "ENTRY", **pos})
        return pos

    def record_exit(self, actual_debit: float, reason: str) -> dict:
        """Record closing the position. P&L = credit received − debit paid."""
        pos = self.open_position()
        if not pos:
            raise RuntimeError("No open live position to close.")
        pnl = pos["credit"] - actual_debit
        rec = {"event": "EXIT", "exit_date": str(date.today()), "reason": reason,
               "debit": actual_debit, "pnl": pnl, "entry_date": pos["entry_date"],
               "expiry": pos["expiry"]}
        self._append(rec)
        POSITION.write_text(json.dumps({}))   # flat
        return rec

    # --- stats --------------------------------------------------------------
    def closed_trades(self) -> list[dict]:
        if not FILLS.exists():
            return []
        return [json.loads(l) for l in FILLS.read_text().splitlines()
                if l.strip() and json.loads(l).get("event") == "EXIT"]

    def realized_pnl(self) -> float:
        return sum(t["pnl"] for t in self.closed_trades())

    def stats(self) -> dict:
        trades = self.closed_trades()
        if not trades:
            return {"trades": 0, "wins": 0, "win_rate": 0.0, "realized": 0.0,
                    "best": 0.0, "worst": 0.0}
        pnls = [t["pnl"] for t in trades]
        wins = [p for p in pnls if p > 0]
        return {
            "trades": len(pnls),
            "wins": len(wins),
            "win_rate": len(wins) / len(pnls) * 100,
            "realized": sum(pnls),
            "best": max(pnls),
            "worst": min(pnls),
        }

    @staticmethod
    def _append(rec: dict) -> None:
        STATE_DIR.mkdir(parents=True, exist_ok=True)
        rec = {"ts": datetime.now().isoformat(timespec="seconds"), **rec}
        with open(FILLS, "a") as f:
            f.write(json.dumps(rec, default=str) + "\n")
