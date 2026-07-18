"""Trading strategies: base interface, breakout scanner, and opening-range breakout."""
from __future__ import annotations

from config.settings import Settings, get_settings
from strategy.base import Strategy


def make_strategy(settings: Settings | None = None) -> Strategy:
    """Instantiate the strategy selected by ``settings.strategy``."""
    s = settings or get_settings()
    name = s.strategy.lower()
    if name == "orb":
        from strategy.orb import OpeningRangeBreakout

        return OpeningRangeBreakout(s)
    if name == "breakout":
        from strategy.breakout import BreakoutScanner

        return BreakoutScanner(s)
    if name == "meanrev":
        from strategy.meanrev import MeanReversion

        return MeanReversion(s)
    raise ValueError(
        f"Unknown strategy '{s.strategy}' (expected 'orb', 'breakout', or 'meanrev')"
    )
