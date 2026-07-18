"""Position sizing: convert a NAV budget into a whole-share quantity."""
from __future__ import annotations


def size_trade(nav: float, price: float, capital_per_trade: float) -> int:
    """Whole shares to buy for one scalp.

    Allocates ``capital_per_trade`` × NAV and floors to whole shares (NSE cash
    equities trade in integer quantities). Returns 0 if the budget can't afford
    a single share.
    """
    if price <= 0 or nav <= 0:
        return 0
    budget = capital_per_trade * nav
    return int(budget // price)
