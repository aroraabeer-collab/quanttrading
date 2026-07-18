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

## The one lesson that explains 1–8

**Price-based strategies don't beat passive.** Price is the most-arbitraged data
on earth; no way of slicing/weighting/timing it manufactures returns that aren't
there. Every price model either lost to costs (intraday) or merely reproduced
market beta (positional). Proven ~7 different ways.

## The one edge (#9): index option selling

Retail overpays for options; sellers are paid the difference. Over 5.4 years,
India VIX ran **26% above** realized volatility on average — that gap is the edge.

- **Strategy:** sell a ~1-SD NIFTY strangle each month, 2× premium stop-loss.
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
