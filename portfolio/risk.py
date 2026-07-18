"""Intraday risk gate — checked before any new entry reaches the broker.

Enforces: max concurrent positions, max trades per day, and a hard daily-loss
kill-switch (halt new entries once NAV drops past the limit vs the day's open).
Existing positions are still allowed to exit when trading is halted.
"""
from __future__ import annotations

from config.settings import Settings, get_settings


class RiskManager:
    def __init__(self, day_start_nav: float, settings: Settings | None = None) -> None:
        s = settings or get_settings()
        self.max_positions = s.max_concurrent_positions
        self.max_trades = s.max_trades_per_day
        self.daily_loss_limit = s.daily_loss_limit
        self.day_start_nav = day_start_nav
        self.trades_today = 0
        self.halted = False

    def loss_breached(self, nav: float) -> bool:
        return nav <= self.day_start_nav * (1 - self.daily_loss_limit)

    def can_enter(self, open_positions: int, nav: float) -> tuple[bool, str]:
        """Return (allowed, reason). Reason is empty when allowed."""
        if self.halted or self.loss_breached(nav):
            self.halted = True
            return False, "daily loss limit hit — trading halted"
        if self.trades_today >= self.max_trades:
            return False, "max trades/day reached"
        if open_positions >= self.max_positions:
            return False, "max concurrent positions reached"
        return True, ""

    def record_entry(self) -> None:
        self.trades_today += 1
