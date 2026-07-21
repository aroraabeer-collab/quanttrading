"""The paper trader must run the SAME validated rules as the backtest."""
import json
from datetime import date, timedelta
from types import SimpleNamespace

import pandas as pd

from options.data import NIFTY_LOT
from options.paper_trader import OptionsPaperTrader


def _trader(tmp_path, ce_now, pe_now, profit_target=0.50, stop_mult=2.0):
    """Open position with 125.2 pts credit; current leg prices drive the exit."""
    state = tmp_path / "paper.json"
    pos = {
        "entry_date": "2026-07-13", "expiry": str(date.today() + timedelta(days=10)),
        "dte": 10, "spot_in": 24211.0, "vix": 13.3,
        "ce_strike": 25000, "ce_symbol": "CE_SYM", "ce_entry": 53.0,
        "pe_strike": 23400, "pe_symbol": "PE_SYM", "pe_entry": 72.2,
        "premium": 125.2,
    }
    state.write_text(json.dumps({"realized_pnl": 0.0, "position": pos, "history": []}))
    data = SimpleNamespace(
        p=SimpleNamespace(quote=lambda syms: {"CE_SYM": ce_now, "PE_SYM": pe_now}),
        live_chain=lambda **kw: {"spot": 24211.0},
    )
    return OptionsPaperTrader(data, profit_target=profit_target, stop_mult=stop_mult,
                              state_file=state)


def test_closes_at_the_profit_target():
    # Buy-back cost halved -> ~50% of credit captured -> must close.
    t = _trader_at_pct(0.50)
    log = t.step()
    assert log["action"] == "CLOSE (profit-target)"
    assert t.state["position"] is None
    assert t.state["realized_pnl"] > 0


def test_holds_below_the_target():
    t = _trader_at_pct(0.25)
    log = t.step()
    assert log["action"] == "HOLD"
    assert t.state["position"] is not None


def test_still_stops_out_on_a_loss():
    # Legs tripled in value -> deep loss -> stop-loss fires, not profit target.
    t = _trader(_TMP[0], ce_now=53.0 * 4, pe_now=72.2 * 4)
    log = t.step()
    assert log["action"] == "CLOSE (stop-loss)"
    assert t.state["realized_pnl"] < 0


# --- helpers ---------------------------------------------------------------
_TMP: list = []


def _trader_at_pct(pct: float):
    """Set current leg prices so exactly `pct` of the credit is captured."""
    credit = 125.2
    remaining = credit * (1 - pct)          # what it'd cost to buy back now
    share = remaining / 2
    return _trader(_TMP[0], ce_now=share, pe_now=share, profit_target=0.50)


def setup_module(module):  # noqa: D103
    import tempfile
    from pathlib import Path
    _TMP.append(Path(tempfile.mkdtemp()))
