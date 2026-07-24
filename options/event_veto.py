"""Event-risk veto — don't sell premium into known binary events.

The strategy's blind spot: VIX rising before a scheduled event (Budget, RBI
policy, election results) reads as "premium is rich → sell", when it actually
means "a binary gap is coming → don't". This gate closes that hole.

Two tiers:
  * ``hard``  — veto if the event falls anywhere inside the trade window
                (entry → expiry). Budget-class events gap beyond priced vol.
  * ``entry`` — only veto *entering* within `event_entry_buffer_days` before the
                event; holding an existing position through it is allowed (the
                stop covers it). RBI/Fed-class events.

Event sources, merged:
  1. Auto-generated annuals (Union Budget, Feb 1).
  2. ``config/events.json`` — user-maintained schedule (VERIFY dates at
     rbi.org.in when the MPC calendar updates).
  3. ``state/event_flags.json`` — same schema, written by anything external
     (a human, a cron job, or an LLM news-checker). This is the pluggable
     "AI judgment" hook: whatever writes here can only ever REMOVE trades,
     never add them.
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import date
from pathlib import Path

from config.settings import PROJECT_ROOT, STATE_DIR, Settings, get_settings

EVENTS_FILE = PROJECT_ROOT / "config" / "events.json"
FLAGS_FILE = STATE_DIR / "event_flags.json"

TIER_HARD, TIER_ENTRY = "hard", "entry"


@dataclass(frozen=True)
class MarketEvent:
    date: date
    name: str
    tier: str = TIER_ENTRY


def _annual_events(year: int) -> list[MarketEvent]:
    return [MarketEvent(date(year, 2, 1), "Union Budget", TIER_HARD)]


def _from_file(path: Path) -> list[MarketEvent]:
    if not path.exists():
        return []
    try:
        raw = json.loads(path.read_text())
    except (json.JSONDecodeError, OSError):
        return []
    out = []
    for e in raw if isinstance(raw, list) else []:
        try:
            out.append(MarketEvent(date.fromisoformat(e["date"]), e["name"],
                                   e.get("tier", TIER_ENTRY)))
        except (KeyError, ValueError, TypeError):
            continue
    return out


def load_events(today: date | None = None) -> list[MarketEvent]:
    today = today or date.today()
    events = _annual_events(today.year) + _annual_events(today.year + 1)
    events += _from_file(EVENTS_FILE)   # user-maintained calendar
    events += _from_file(FLAGS_FILE)    # external/LLM flags (veto-only by design)
    return sorted({e for e in events if e.date >= today}, key=lambda e: e.date)


class EventVeto:
    def __init__(self, settings: Settings | None = None,
                 events: list[MarketEvent] | None = None) -> None:
        self.s = settings or get_settings()
        self._events = events

    def check(self, entry: date, expiry: date) -> str | None:
        """A veto reason string, or None if the window is clear."""
        if not self.s.live_event_veto:
            return None
        events = self._events if self._events is not None else load_events(entry)
        buffer_days = self.s.event_entry_buffer_days
        for ev in events:
            if ev.tier == TIER_HARD and entry <= ev.date <= expiry:
                return (f"EVENT VETO — {ev.name} ({ev.date}) falls inside this trade's "
                        f"window (expiry {expiry}). Binary-event gaps exceed priced vol; "
                        "skip this cycle or pick an expiry before the event.")
            if ev.tier == TIER_ENTRY and 0 <= (ev.date - entry).days <= buffer_days:
                return (f"EVENT VETO — {ev.name} ({ev.date}) is within {buffer_days} days. "
                        "Wait until after the event to enter; fresh premium into a "
                        "scheduled announcement is a bad trade.")
        return None
