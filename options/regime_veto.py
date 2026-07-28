"""Regime veto — an ENSEMBLE of technical signals, used veto-only.

The honest hybrid: the options edge is the only thing that trades; the technical
and volatility models are demoted to *reading conditions* and can only skip a
trade, never create one. Premium sellers get run over in two regimes:

  * **Strong trend** — a hard directional move breaches a strike. Detected when
    price is stretched far from its mean (MA) AND the recent move is large vs its
    own volatility (momentum). Both must agree, to avoid vetoing on noise.
  * **Vol expansion** — VIX rising fast means a move is *underway* (high VIX level
    is fine — that's rich premium; a rising VIX is the danger).

Each is a sub-signal; the veto fires if the trend pair agrees or vol is spiking.
This combines your MA/momentum/vol models exactly where they help — as filters.
"""
from __future__ import annotations

from datetime import date, timedelta
from math import sqrt

import pandas as pd

from config.settings import Settings, get_settings
from options.data import NIFTY_INDEX, OptionsData

VIX_INDEX = "NSE:INDIAVIX-INDEX"


def fetch_regime_series(data: OptionsData, lookback: int = 120):
    """Recent daily NIFTY + India VIX close series for the regime check."""
    end = date.today()
    start = end - timedelta(days=lookback)
    nifty = data.index_history(start, end, "D")["close"]
    vix = data.p.history([VIX_INDEX], start, end, "D")[VIX_INDEX]["close"]
    return nifty, vix


class RegimeVeto:
    def __init__(self, settings: Settings | None = None) -> None:
        self.s = settings or get_settings()

    def check(self, nifty: pd.Series, vix: pd.Series) -> str | None:
        """Veto reason if the regime is hostile to selling premium, else None."""
        s = self.s
        if not s.live_regime_veto:
            return None
        if len(nifty) < 55 or len(vix) < 7:
            return None  # not enough history to judge — don't block

        # --- Trend ensemble: stretch (MA) AND momentum must agree ---
        sma = nifty.rolling(50).mean().iloc[-1]
        sd = nifty.rolling(50).std().iloc[-1]
        z = (nifty.iloc[-1] - sma) / sd if sd else 0.0            # MA-stretch
        r20 = nifty.iloc[-1] / nifty.iloc[-21] - 1                 # 20-day return
        vol20 = nifty.pct_change().iloc[-20:].std() * sqrt(20)     # 20-day vol
        momentum = abs(r20) > s.regime_momentum_mult * vol20 if vol20 else False
        stretched = abs(z) > s.regime_trend_z
        if momentum and stretched:
            return (f"REGIME VETO — NIFTY trending hard (stretch z={z:+.1f}, "
                    f"20-day move {r20*100:+.1f}%). Premium sellers get run over in strong "
                    "trends; wait for range-bound conditions.")

        # --- Vol-expansion signal ---
        vix_roc = vix.iloc[-1] / vix.iloc[-6] - 1
        if vix_roc > s.regime_vix_spike:
            return (f"REGIME VETO — VIX spiking (+{vix_roc*100:.0f}% in 5 days, now "
                    f"{vix.iloc[-1]:.1f}). Volatility is expanding — a move is underway; "
                    "don't sell into it.")
        return None

    def check_live(self, data: OptionsData) -> str | None:
        """Fetch recent series and check — for the advisor/paper trader."""
        try:
            nifty, vix = fetch_regime_series(data)
        except Exception:  # noqa: BLE001 — never block trading on a data hiccup
            return None
        return self.check(nifty, vix)
