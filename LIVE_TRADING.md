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

**Automated (recommended)** — one command watches all day and pings you:
```bash
python scripts/fyers_auth.py                      # 1. refresh token (each morning)
python scripts/run_live_daemon.py --mode alert    # 2. leave it running
#    → macOS notification when it's time to place or close
#    → you click in the Fyers app; it auto-detects and records your real fills
```

**Manual (if you prefer step-by-step):**
```bash
python scripts/live_advisor.py               # see the ticket — or a refusal
python scripts/live_advisor.py --record      # log your ACTUAL fill
python scripts/live_monitor.py               # check it (--watch to poll)
python scripts/live_monitor.py --close 1850  # record the exit
```

### Daemon modes
| Mode | What it does |
|---|---|
| `shadow` | Decides and logs only — silent. Builds the validation record. **Default.** |
| `alert` | Also fires a macOS notification when action is due. **Run this.** |
| `auto` | Would place real orders — **refused**: needs a registered Algo-ID (see below). |

Decisions are logged to `state/decisions.jsonl` — after a few weeks that's your
evidence for whether the automation actually makes the right calls.

## What this software will NOT do

- **It never places an order.** Verified: the only broker calls in the whole
  codebase are `optionchain`, `history`, `quotes`, `positions` — all read-only.
  Every trade is your click, your decision.
- **It can't predict.** ~78–84% win rate means roughly **1 in 5 trades loses**,
  and losses are bigger than wins. That's the deal you're accepting.

## If you want true auto-execution later

Automated order placement has required a **SEBI-registered Algo-ID** since April
2026. Running an unregistered algo risks regulatory action and broker suspension.
To unlock it properly:

1. **Request algo-trading registration through Fyers** (they file for the Algo-ID)
2. Set `QT_LIVE_ALGO_ID` in `.env`
3. Implement `FyersBroker(Broker)` against the existing interface in
   `execution/interfaces.py` and wire it into the daemon's `auto` mode
4. **Run `shadow` mode first** — only trust it with orders once the decision log
   shows it consistently made the right calls

Until step 1 is done, `--mode auto` refuses to start, by design.

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
