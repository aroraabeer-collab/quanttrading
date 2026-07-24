"""The event veto must block premium-selling into known binary events."""
from datetime import date, timedelta

from config.settings import get_settings
from options.event_veto import (TIER_ENTRY, TIER_HARD, EventVeto, MarketEvent,
                                load_events)


def _settings(**over):
    base = {"live_event_veto": True, "event_entry_buffer_days": 3}
    return get_settings().model_copy(update={**base, **over})


def _veto(events, **over):
    return EventVeto(_settings(**over), events=events)


ENTRY = date(2026, 7, 20)
EXPIRY = date(2026, 8, 12)


def test_hard_event_inside_window_vetoes():
    v = _veto([MarketEvent(date(2026, 8, 1), "Union Budget", TIER_HARD)])
    reason = v.check(ENTRY, EXPIRY)
    assert reason and "Union Budget" in reason


def test_hard_event_after_expiry_is_fine():
    v = _veto([MarketEvent(EXPIRY + timedelta(days=5), "Union Budget", TIER_HARD)])
    assert v.check(ENTRY, EXPIRY) is None


def test_entry_event_within_buffer_vetoes_entry():
    v = _veto([MarketEvent(ENTRY + timedelta(days=2), "RBI MPC", TIER_ENTRY)])
    reason = v.check(ENTRY, EXPIRY)
    assert reason and "RBI MPC" in reason


def test_entry_event_beyond_buffer_allows_entry():
    # RBI meeting 10 days out — you can enter now and manage through it.
    v = _veto([MarketEvent(ENTRY + timedelta(days=10), "RBI MPC", TIER_ENTRY)])
    assert v.check(ENTRY, EXPIRY) is None


def test_disabled_via_settings():
    v = _veto([MarketEvent(date(2026, 8, 1), "Union Budget", TIER_HARD)],
              live_event_veto=False)
    assert v.check(ENTRY, EXPIRY) is None


def test_budget_is_auto_generated_each_year():
    events = load_events(today=date(2026, 7, 20))
    budgets = [e for e in events if e.name == "Union Budget"]
    assert any(e.date == date(2027, 2, 1) for e in budgets)
    assert all(e.tier == TIER_HARD for e in budgets)


def test_advisor_refuses_on_event(monkeypatch):
    """End-to-end: the advisor's Gate 1.5 turns an event into a refusal."""
    from test_advisor import FakeChain
    from options.advisor import LiveCondorAdvisor

    chain = FakeChain()                      # expiry ~25 days out
    event_day = date.today() + timedelta(days=10)
    monkeypatch.setattr("options.event_veto.load_events",
                        lambda today=None: [MarketEvent(event_day, "Union Budget", TIER_HARD)])
    t = LiveCondorAdvisor(chain, _settings(live_account=150_000)).advise()
    assert not t.ok
    assert "EVENT VETO" in t.reason and "Union Budget" in t.reason
