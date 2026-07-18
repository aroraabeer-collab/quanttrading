# quanttrading — Nifty 50 Momentum (India)

A broker-agnostic quant trading system for Indian markets. First build: an
**intraday breakout scanner** across the Nifty 50 — many small trades within the
hour, each entering on a short-term breakout and exiting on a small target/stop
(all squared off by end of day). Researched in a vectorized intraday backtester
with realistic Indian per-trade costs, then run live with **simulated (paper)
fills** fed by real-time Fyers data.

> ⚠️ Reality check: at many trades/hour, transaction costs (STT, brokerage,
> exchange fees, slippage) dominate P&L. The backtest models every cost per
> trade so results are honest — a scalping edge must clear that cost floor on
> *every* trade to be real.

Data access and order execution sit behind interfaces (`data/interfaces.py`,
`execution/interfaces.py`), so going live later = adding one `FyersBroker`
adapter, and adding F&O / stock futures = new symbols, not a rewrite.

## Setup

Requires [uv](https://docs.astral.sh/uv/). Python 3.12 is provisioned
automatically (pinned in `.python-version`).

```bash
uv sync                      # create venv + install deps
cp .env.example .env         # then fill in Fyers credentials
```

## Fyers authentication

1. Create an app at <https://myapi.fyers.in/dashboard/> to get `APP_ID` and
   `SECRET_ID`; set the redirect URI to match `FYERS_REDIRECT_URI`.
2. Put `FYERS_APP_ID`, `FYERS_SECRET_ID`, `FYERS_REDIRECT_URI` in `.env`.
3. Fyers access tokens **expire daily**. Regenerate before a session:

   ```bash
   uv run scripts/fyers_auth.py     # opens login, writes FYERS_ACCESS_TOKEN to .env
   ```

## Commands

Prefix everything with the uv path if `uv` isn't on your PATH:
`export PATH="$HOME/.local/bin:$PATH"`. All commands run from the project root.

> **If `uv run …` hangs (prints nothing / never starts):** its per-run rebuild is
> stuck. Skip it — activate the venv once and use plain `python`:
> ```bash
> source .venv/bin/activate
> python scripts/run_options_daemon.py      # e.g.
> ```
> (Or `uv run --no-sync scripts/…` to keep uv but skip the rebuild.)
> Everywhere below, `uv run python X` and `python X` (with the venv active) are interchangeable.

### One-time setup
```bash
uv sync                               # create venv + install all dependencies
cp .env.example .env                  # then paste your Fyers APP_ID / SECRET_ID
```

### Every day you trade (Fyers token expires daily)
```bash
uv run scripts/fyers_auth.py          # log in, refresh token → writes .env
```
> Run this once each morning, or whenever you see `Could not authenticate (-16)`.

### ⭐ The live options strategy (current focus) + widget
```bash
uv run scripts/run_options_paper.py   # one manual step: manage/enter the strangle + show track record
uv run scripts/run_options_daemon.py  # OR run continuously: auto-manages during market hours, logs P&L
uv run scripts/pnl_widget.py          # floating Apple-Stocks-style P&L card (reads the daemon's log)
```
Typical live setup — two Terminal tabs: the **daemon** in one, the **widget** in
the other. Stop either with `Ctrl+C`, or `pkill -f run_options_daemon.py` /
`pkill -f pnl_widget.py`.

### Research & backtests
```bash
uv run scripts/run_options.py                       # options-selling (vol risk premium) backtest
uv run scripts/download_data.py --resolution D --days 1825 --universe nifty200   # daily bars
uv run scripts/run_ml.py --universe nifty200 --top-k 20                          # ML factor model
uv run scripts/run_ml_paper.py --top-k 20                                        # ML equity paper rebalance
uv run scripts/run_backtest.py                      # intraday breakout backtest (early experiment)
uv run pytest -q                                     # 36 unit tests
```

## Layout

| Path          | Purpose                                                        |
| ------------- | -------------------------------------------------------------- |
| `config/`     | Settings (pydantic) + Nifty 50 / Nifty 200 universes           |
| `data/`       | `DataProvider` interface, Fyers provider (backoff), parquet cache |
| `options/`    | ⭐ Options: pricing, vol-premium backtest, live paper trader    |
| `ml/`         | Cross-sectional ML factor model + risk-based portfolios        |
| `strategy/`   | Intraday strategies (breakout, mean-reversion, ORB)            |
| `backtest/`   | Cost models (intraday/delivery/options), vectorbt engine       |
| `execution/`  | `Broker` interface + `PaperBroker`                             |
| `live/`       | NSE market clock, paper runners, options daemon                |
| `scripts/`    | All entrypoints (see Commands above)                           |

See **[FINDINGS.md](FINDINGS.md)** for the full scorecard of what works and what doesn't.

## Status & scope

The one strategy with a real edge is **index option selling** (see FINDINGS.md).
It's in **paper validation** — simulated fills, no real money. Everything price-based
(intraday + ML) was tested and shown not to beat passive.

> Research/educational software. Not investment advice. Paper trading only —
> no real orders are placed by this codebase.
