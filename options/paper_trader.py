"""Live paper trader for the index short strangle (volatility risk premium).

One idempotent step per run: if flat, sell a ~1-SD strangle on the nearest Nifty
expiry at **real live option prices**; if in a position, mark it to market from
live quotes and close on a stop-loss or at expiry. State persists between runs.

This validates the model-based backtest against real fills — no real money.
"""
from __future__ import annotations

import json
from datetime import date
from math import sqrt
from pathlib import Path

import pandas as pd

from config.settings import STATE_DIR
from options.data import NIFTY_LOT, OptionsData, atm_strike
from options.pricing import intrinsic

STATE_FILE = STATE_DIR / "options_paper.json"


def _cost(premium_points: float) -> float:
    """Round-trip options cost for a 1-lot strangle (brokerage + STT on premium)."""
    return 2 * 2 * 25.0 + 0.001 * premium_points * NIFTY_LOT


class OptionsPaperTrader:
    def __init__(
        self, data: OptionsData, initial_capital: float = 1_000_000,
        sd_width: float = 1.0, stop_mult: float = 2.0, target_dte: int = 25,
        vix_min: float = 13.0, state_file: Path | None = None,
    ) -> None:
        self.d = data
        self.sd_width = sd_width
        self.stop_mult = stop_mult
        self.target_dte = target_dte
        self.vix_min = vix_min   # only sell when implied vol is rich enough (validated: Sharpe 1.04->1.40)
        self.state_file = state_file or STATE_FILE
        self.state = self._load(initial_capital)

    def _load(self, cap):
        if self.state_file.exists():
            return json.loads(self.state_file.read_text())
        return {"realized_pnl": 0.0, "position": None, "history": []}

    def _save(self):
        STATE_DIR.mkdir(parents=True, exist_ok=True)
        self.state_file.write_text(json.dumps(self.state, indent=2, default=str))

    def mark(self) -> tuple[float, float]:
        """Current (unrealized, realized) P&L in ₹ from live quotes — no state change.

        Used by the display/daemon so it can show P&L even when it isn't the moment
        to trade (e.g. between managed steps or just after market close).
        """
        realized = self.state["realized_pnl"]
        pos = self.state["position"]
        if not pos:
            return 0.0, realized
        q = self.d.p.quote([pos["ce_symbol"], pos["pe_symbol"]])
        ce = q.get(pos["ce_symbol"], pos["ce_entry"])
        pe = q.get(pos["pe_symbol"], pos["pe_entry"])
        unreal = (pos["premium"] - (ce + pe)) * NIFTY_LOT
        return unreal, realized

    # --- one step -----------------------------------------------------------
    def step(self, today: date | None = None) -> dict:
        today = today or date.today()
        pos = self.state["position"]
        log = {"time": str(today), "action": None, "detail": {}}
        if pos is None:
            self._enter(today, log)
        else:
            self._manage(today, pos, log)
        self._save()
        return log

    def _enter(self, today, log):
        chain = self.d.live_chain(strikecount=25, target_dte=self.target_dte)
        spot, vix, expiry, opts = chain["spot"], chain["vix"], chain["expiry"], chain["options"]
        if vix < self.vix_min:
            log["action"] = "wait"
            log["detail"] = {"reason": f"VIX {vix:.1f} < {self.vix_min} — premium too cheap to sell"}
            return
        dte = max((expiry - today).days, 1)
        move = spot * (vix / 100.0) * sqrt(dte / 365.0) * self.sd_width
        kc_t, kp_t = atm_strike(spot + move), atm_strike(spot - move)

        ce = self._pick(opts, "CE", kc_t)
        pe = self._pick(opts, "PE", kp_t)
        if ce is None or pe is None:
            log["action"] = "wait"
            log["detail"] = {"reason": "strikes not found in chain"}
            return
        premium = ce["ltp"] + pe["ltp"]
        self.state["position"] = {
            "entry_date": str(today), "expiry": str(expiry), "dte": dte, "spot_in": spot, "vix": vix,
            "ce_strike": ce["strike"], "ce_symbol": ce["symbol"], "ce_entry": ce["ltp"],
            "pe_strike": pe["strike"], "pe_symbol": pe["symbol"], "pe_entry": pe["ltp"],
            "premium": premium,
        }
        log["action"] = "SELL strangle"
        log["detail"] = {
            "expiry": str(expiry), "spot": spot, "vix": vix,
            "short": f"{ce['strike']}CE @ {ce['ltp']:.1f} + {pe['strike']}PE @ {pe['ltp']:.1f}",
            "premium_collected": round(premium * NIFTY_LOT), "dte": dte,
        }

    def _manage(self, today, pos, log):
        expiry = pd.to_datetime(pos["expiry"]).date()
        q = self.d.p.quote([pos["ce_symbol"], pos["pe_symbol"]])
        ce_now = q.get(pos["ce_symbol"], pos["ce_entry"])
        pe_now = q.get(pos["pe_symbol"], pos["pe_entry"])
        cur_val = ce_now + pe_now
        mtm = (pos["premium"] - cur_val) * NIFTY_LOT

        reason = None
        if today >= expiry:
            spot = self.d.live_chain(strikecount=1)["spot"]  # settle at current index level
            payoff = intrinsic(spot, pos["ce_strike"], "CE") + intrinsic(spot, pos["pe_strike"], "PE")
            realized = (pos["premium"] - payoff) * NIFTY_LOT - _cost(pos["premium"])
            reason = "expiry"
        elif mtm <= -self.stop_mult * pos["premium"] * NIFTY_LOT:
            realized = mtm - _cost(pos["premium"])
            reason = "stop-loss"

        if reason:
            self.state["realized_pnl"] += realized
            self.state["history"].append({**pos, "exit_date": str(today), "reason": reason,
                                          "pnl": round(realized)})
            self.state["position"] = None
            log["action"] = f"CLOSE ({reason})"
            log["detail"] = {"pnl": round(realized), "total_realized": round(self.state["realized_pnl"])}
        else:
            max_profit = pos["premium"] * NIFTY_LOT
            log["action"] = "HOLD"
            log["detail"] = {
                "profit_so_far": round(mtm),
                "max_profit_at_expiry": round(max_profit),
                "pct_captured": round(mtm / max_profit * 100) if max_profit else 0,
                "buyback_cost_now": round(cur_val * NIFTY_LOT),
                "expiry": pos["expiry"],
            }

    @staticmethod
    def _pick(opts: pd.DataFrame, typ: str, target: int):
        sub = opts[opts["type"] == typ]
        if sub.empty:
            return None
        row = sub.iloc[(sub["strike"] - target).abs().argmin()]
        return {"strike": int(row["strike"]), "symbol": row["symbol"], "ltp": float(row["ltp"])}
