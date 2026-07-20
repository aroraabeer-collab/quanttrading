"""The risk gate is the safety-critical code here — it must REFUSE bad trades."""
from datetime import date, timedelta

import pandas as pd

from config.settings import get_settings
from options.advisor import LiveCondorAdvisor
from options.data import NIFTY_LOT


class FakeChain:
    """Synthetic option chain: price decays as you go further out of the money."""

    def __init__(self, spot: float = 24_000, vix: float = 15.0, dte: int = 25):
        self.spot, self.vix, self.dte = spot, vix, dte

    def live_chain(self, strikecount: int = 30, target_dte: int = 25) -> dict:
        rows = []
        for k in range(int(self.spot) - 2000, int(self.spot) + 2050, 50):
            ltp = max(2.0, 200 - abs(k - self.spot) * 0.15)
            for typ in ("CE", "PE"):
                rows.append({"strike": k, "type": typ, "ltp": ltp,
                             "symbol": f"NSE:NIFTYTEST{k}{typ}"})
        return {"expiry": date.today() + timedelta(days=self.dte), "spot": self.spot,
                "vix": self.vix, "options": pd.DataFrame(rows)}


def _settings(**over):
    return get_settings().model_copy(update=over)


def test_accepts_a_survivable_condor():
    s = _settings(live_account=50_000, live_wing_points=100, live_max_risk_pct=0.12)
    t = LiveCondorAdvisor(FakeChain(), s).advise()
    assert t.ok, t.reason
    assert len(t.legs) == 4                      # never naked
    assert t.net_premium > 0                     # it's a credit spread
    assert t.max_loss_pct <= 0.12                # within the risk limit
    # Max loss is capped by the wings: width x lot - credit
    assert abs(t.max_loss - (100 * NIFTY_LOT - t.net_premium)) < 1.0


def test_refuses_when_wings_too_wide_for_the_account():
    # 300pt wings => ~₹15.7k max loss => ~31% of a ₹50k account => must refuse.
    s = _settings(live_account=50_000, live_wing_points=300, live_max_risk_pct=0.12)
    t = LiveCondorAdvisor(FakeChain(), s).advise()
    assert not t.ok
    assert "max loss" in t.reason.lower()
    assert "%" in t.reason                       # tells the user the actual number


def test_refuses_when_vix_too_low():
    s = _settings(vix_min=13.0)
    t = LiveCondorAdvisor(FakeChain(vix=10.0), s).advise()
    assert not t.ok
    assert "vix" in t.reason.lower()


def test_halts_after_account_drawdown():
    s = _settings(live_account=50_000, live_halt_drawdown=0.20)
    # Down ₹11,000 = 22% => past the 20% halt.
    t = LiveCondorAdvisor(FakeChain(), s, realized_pnl=-11_000).advise()
    assert not t.ok
    assert "halt" in t.reason.lower()


def test_a_bigger_account_allows_the_same_trade():
    """Identical trade, larger account => same ₹ risk is now an acceptable %."""
    s = _settings(live_account=500_000, live_wing_points=300, live_max_risk_pct=0.12)
    t = LiveCondorAdvisor(FakeChain(), s).advise()
    assert t.ok, t.reason                        # sizing, not the strategy, was the problem
