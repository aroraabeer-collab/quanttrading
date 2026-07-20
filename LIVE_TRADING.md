# Live Trading Rules — read this before every trade

**Account: ₹50,000 · 1 lot max · defined-risk iron condors only · manual execution**

> At this account size, **this is tuition, not income.** Expect ~₹500–1,500/month.
> The goal is to learn discipline with real skin in the game at a size where a bad
> trade hurts but does not end you. Do not scale up to chase returns.

## What you're trading and why

The one edge this project found is **selling index option premium** (VIX runs
~26% above realized volatility — you get paid for that gap). A ₹50k account can't
margin a naked strangle, so you trade a **tight iron condor**: sell a ~1-SD
strangle, buy protective wings ~100 points beyond each short.

**The wings are not optional.** They're what turns an account-ending loss into a
capped one. Without them, one gap can exceed your entire account.

## The rules (non-negotiable)

1. **Never place a naked position.** All four legs, every time.
2. **One position at a time.** Never stack trades.
3. **1 lot maximum.** Do not add lots — not to scale up, not to recover a loss.
4. **Only when the advisor says OK.** If it refuses, you skip the cycle. The
   refusal *is* the value — it's protecting you from a bad-sized trade.
5. **Take profit at 50% of credit.** Don't hold for the last rupee; that's where
   the tail lives.
6. **Cut at 75% of max loss.** Don't "wait for it to come back."
7. **Never widen a loser** or roll to avoid taking a loss. Take the loss.
8. **Halt at −20% of account (−₹10,000).** Stop trading entirely. Review, don't
   revenge-trade. The advisor enforces this automatically.
9. **Only sell when VIX ≥ 13.** Cheap premium isn't worth the tail.
10. **Record every real fill.** That's how we learn what actually happens vs the model.

## Pre-trade checklist (every single time)

- [ ] Token refreshed today (`python scripts/fyers_auth.py`)
- [ ] No position currently open
- [ ] Advisor returned a **ticket**, not a refusal
- [ ] Max loss shown is **≤ 12% of account** (~₹6,000)
- [ ] I can afford to lose this amount **entirely, today**, without it affecting my life
- [ ] I placed **all four legs** — including both BUY wings
- [ ] I recorded my **actual** credit (`--record`)

## The daily flow

```bash
python scripts/fyers_auth.py                 # 1. refresh token (each morning)
python scripts/live_advisor.py               # 2. see the ticket — or a refusal
#    → place all 4 legs yourself in the Fyers app
python scripts/live_advisor.py --record      # 3. log your ACTUAL fill
python scripts/live_monitor.py               # 4. check it (daily; --watch to poll)
python scripts/live_monitor.py --close 1850  # 5. record the exit when you close
```

## What this software will NOT do

- **It never places an order.** Every trade is your click, your decision.
- **It won't automate.** Automated order placement requires a SEBI-registered
  Algo-ID (mandatory since Apr 2026) — and a human brake is the point on a
  tail-risk strategy.
- **It can't predict.** ~78–84% win rate means roughly **1 in 5 trades loses**,
  and losses are bigger than wins. That's the deal you're accepting.

## Honest expectations

| | Reality |
|---|---|
| Win rate | ~78–84% (so ~1 in 5 loses) |
| Typical win | small — a fraction of the credit |
| Typical loss | **bigger than a typical win** |
| Worst case | the full capped max loss (~₹5–6k) |
| Monthly | ~₹500–1,500 — *if* it behaves like the backtest |
| Not validated | Zero completed paper cycles. This is backtest-validated only. |

**If you find yourself checking it every 10 minutes, or wanting to add lots after
a loss — stop trading. That instinct is what empties accounts, not the strategy.**

> Research/educational tooling. Not investment advice.
