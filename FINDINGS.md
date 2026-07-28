# Findings — What Works and What Doesn't (Indian Markets)

A rigorous, honest record of every strategy tested in this project, so we don't
re-learn the same lessons. **Headline: of nine strategies, eight were rejected;
one has a real edge.**

## The scorecard

| # | Strategy | Horizon | Verdict | Key number |
|---|----------|---------|---------|-----------|
| 1 | Breakout scalping (naive) | Intraday | ❌ Loses | −83% / 8 months |
| 2 | Breakout + VWAP/time filters | Intraday | ❌ Loses | −25% |
| 3 | Opening-range breakout + trailing | Intraday | ❌ Loses | −28% |
| 4 | Mean-reversion (fade to VWAP) | Intraday | ❌ Loses | −64%, fat tails |
| 5 | Regime-filtered ORB (breadth) | Intraday | ❌ Loses | −0.10%/trade EV |
| 6 | ML factor model (ensemble) | Positional | ⚠️ = Market beta | +19% but < passive |
| 7 | Long-short market-neutral | Positional | ❌ No alpha | ≈ 0 after costs |
| 8 | Min-variance / HRP portfolios | Positional | ⚠️ Marginal | Sharpe 1.54 vs 1.50, less return |
| **9** | **Index option selling (VRP)** | **Monthly** | **✅ REAL EDGE** | **78% win, Sharpe 1.04** |
| 10 | Composite indicators (MA+RSI+MACD+BB) | Intraday | ❌ Loses | −59% net (−3.6% gross) |
| 11 | Hybrid: technical/vol regime veto on #9 | Filter | ❌ No help | Sharpe 0.88→0.79, bigger DD |

## The one lesson that explains 1–8, 10, 11

**Price-based strategies don't beat passive.** Price is the most-arbitraged data
on earth; no way of slicing/weighting/timing it manufactures returns that aren't
there. Every price model either lost to costs (intraday) or merely reproduced
market beta (positional). Proven **nine different ways** now.

- **#10 (composite indicators):** ports NSE-QUANT-TRADER's MA+RSI+MACD+BB weighted
  score. Gross −3.6% (48.6% win — a coin flip: no signal even before costs), net
  **−59%** after honest intraday costs. Buy-and-hold (−0.2%) beat it by 58 points.
  Fusing four indicators just gives four ways to generate edgeless, cost-bleeding
  trades. (`strategy/composite.py`)
- **#11 (hybrid ensemble — the veto test):** the honest way to "combine models" is
  options-edge-trades + technical/vol signals as veto-only filters. Backtested a
  regime veto (MA-stretch + momentum + VIX-spike ensemble) on the options
  strategy: it **hurt** — Sharpe 0.88→0.79, total ₹161k→₹144k, and a *bigger*
  drawdown (skipped good trades, missed the bad ones). The technical/vol signals
  don't predict hostile cycles. **Shipped OFF by default.** (`options/regime_veto.py`)

**Corollary:** you cannot ensemble your way to an edge. Averaging negative-
expectancy signals yields a negative-expectancy ensemble. The only signals that
help the options edge are **VIX≥13** (validated) and the **event calendar**
(principled) — both veto-only.

## The one edge (#9): index option selling

Retail overpays for options; sellers are paid the difference. Over 5.4 years,
India VIX ran **26% above** realized volatility on average — that gap is the edge.

- **Strategy:** sell a ~1-SD NIFTY strangle, 2× premium stop-loss, **take profit at
  50% of credit** (see the cycling study below).
- **Result (model-based, 1 lot, 5.4 yr):** 78% win rate, +₹2.93L, **Sharpe 1.04**,
  worst single loss −₹37k. Best risk-adjusted result in the project.
- **Why not stocks:** tested a 178-stock basket → Sharpe 0.06, −56% drawdown.
  Single-stock gap risk + correlations spiking to 1 in crashes. Index is superior.
- **The catch:** avg loss ≈ 2× avg win, worst ≈ 5× avg win. High win rate, fat
  tail. Only viable with strict tail discipline (stops, defined risk, sizing).
- **Caveat:** backtest is Black-Scholes at VIX (Fyers has no expired-option data).
  It ignores skew (understates premium edge = conservative) but real crash gaps /
  slippage could make a live loss *worse* than −₹37k.

Reports: `reports/options_report.html`, `reports/pnl_report.html`.

## Capital cycling: take profit at 50% (the biggest single improvement)

An earlier test concluded profit-taking *hurt* (Sharpe 0.61). **That test was
wrong** — `run_vol_backtest` only enters on fixed 21-day slots, so exiting at day
8 left capital **idle for 13 days**. It paid the cost of early exit and never
received the benefit. `run_vol_backtest_reentry` fixes this by redeploying as
soon as a trade closes. Over 5.4 yrs, 1 lot, stop 2×, VIX≥13:

| variant | trades/yr | win% | annual % | Sharpe | avg days held |
|---|---|---|---|---|---|
| hold to expiry | 9.9 | 74% | 21.9% | 0.64 | 19.4 |
| take 25% | 26.3 | 92% | 21.7% | 0.60 | 6.2 |
| **take 50%** | **16.6** | **91%** | **38.4%** | **1.08** | **10.8** |
| take 75% | 12.9 | 80% | 16.4% | 0.38 | 14.4 |

**Taking 50% nearly doubles annualised return and lifts Sharpe from 0.64 → 1.08**,
while holding positions for *half* the time. Extra costs (₹10.1k vs ₹6.1k) are far
outweighed by the extra cycles. Adopted as the default (`live_profit_target`).

## ⚠️ Correction to earlier numbers

`_stats` annualised Sharpe using a **fixed** `TRADING_YEAR / hold_days`, regardless
of how many cycles actually occurred — so any run that *skipped* cycles (the VIX
filter) had its Sharpe inflated. Now fixed to annualise by real elapsed time:

- Stop-loss strangle, no VIX filter: **Sharpe 1.04** — unchanged, was always correct
- With VIX≥13 filter: previously reported **1.40**, actually **1.16** (still an
  improvement, just smaller than claimed)

Also note the re-entry engine enters as soon as VIX crosses 13, so it sells
thinner premium more often (26% of entries at VIX<14, vs 16% for slot-based).
Its lower absolute baseline is realistic, not a bug — but it means **the honest
hold-to-expiry baseline is ~0.64 Sharpe, not ~1.0**.

## Current status: paper validation (do this before real money)

The live paper trader (`scripts/run_options_paper.py`) sells the real strangle at
live Fyers prices. **We are validating the model against real fills — zero real
money.**

**What to watch for over the next ~2–3 months:**
1. At least **2–3 complete expiry cycles**.
2. At least **one stop-loss trigger** — and whether the strategy recovers after.
3. Whether the **realized win rate** tracks the backtest's ~78%.

**Daily-ish routine (run a few times a week, and near each expiry):**
```bash
uv run scripts/fyers_auth.py          # refresh Fyers token (expires daily)
uv run scripts/run_options_paper.py   # manage position + show track record
```

## Path to real money (only after validation)

Not now. When the paper record holds up, the responsible first step is **small,
manual, human-in-the-loop**: the tool tells you the strangle; you place it in the
Fyers app, 1 lot, defined-risk, money you can lose entirely. Full automation
additionally requires a **SEBI-registered Algo-ID** (mandatory since Apr 2026),
a real-order `FyersBroker` adapter, and hard risk kill-switches.

## Architecture (all tested, 36 unit tests)

Broker-agnostic data + execution interfaces · Fyers integration (rate-limit
backoff, daily OAuth) · intraday + positional + options backtest engines · honest
India cost models (intraday, delivery, options) · ML factor pipeline (walk-forward,
ensemble) · risk-based portfolios (PyPortfolioOpt) · options pricing + vol-premium
backtest · live paper traders for both equities and options.

> Research/educational. Not investment advice. Past simulation ≠ future results.
