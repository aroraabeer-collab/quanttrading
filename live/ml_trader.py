"""Positional paper trader for the ML factor model.

One rebalance cycle: load cached daily bars, train the ensemble on all history,
predict scores as-of the latest close, pick the top-K names, and rebalance the
paper portfolio to equal weight at current live quotes. Designed to be run on a
schedule (e.g. weekly) — it is idempotent and persists state between runs.

Honest framing: this tracks the market (it's ~beta, not proven alpha). It exists
to run a real end-to-end paper system, not because it beats passive indexing.
"""
from __future__ import annotations

import pandas as pd

from backtest.engine import build_panels
from config.settings import Settings, get_settings
from config.universe import universe_symbols
from data.cache import read_bars
from data.interfaces import DataProvider
from execution.interfaces import Broker, Side
from ml.features import FEATURES, build_dataset, build_features
from ml.model import make_ensemble


class MLPaperTrader:
    def __init__(
        self,
        provider: DataProvider,
        broker: Broker,
        settings: Settings | None = None,
        top_k: int = 20,
        horizon: int = 5,
    ) -> None:
        self.provider = provider
        self.broker = broker
        self.s = settings or get_settings()
        self.top_k = top_k
        self.horizon = horizon
        self.symbols = universe_symbols(self.s.universe)

    def _load_panels(self):
        bars = {}
        for sym in self.symbols:
            df = read_bars(sym, "D")
            if df is not None and not df.empty:
                bars[sym] = df
        if not bars:
            raise RuntimeError(
                f"No daily bars cached for {self.s.universe}. Run: "
                "uv run scripts/download_data.py --resolution D --days 1825 "
                f"--universe {self.s.universe}"
            )
        return build_panels(bars)

    def target_names(self) -> pd.Index:
        """Train on history, predict as-of the latest close, return top-K symbols."""
        panels = self._load_panels()
        data = build_dataset(panels, self.horizon)
        model = make_ensemble().fit(data[FEATURES].to_numpy(), data["fwd_ret"].to_numpy())

        feats = build_features(panels)
        last_date = feats.index.get_level_values("date").max()
        x_today = feats.xs(last_date, level="date")
        scores = pd.Series(model.predict(x_today[FEATURES].to_numpy()), index=x_today.index)
        return scores.sort_values(ascending=False).head(self.top_k).index

    def rebalance(self, now: pd.Timestamp | None = None) -> dict:
        now = now or pd.Timestamp.now(tz="Asia/Kolkata")
        targets = self.target_names()
        target_w = {sym: 1.0 / len(targets) for sym in targets}

        # Quote everything we might touch (current holdings + targets).
        universe = list(set(self.broker.positions()) | set(targets))
        quotes = self.provider.quote(universe)
        nav = self.broker.nav(quotes)
        log: dict = {"time": now, "nav": nav, "targets": list(targets), "trades": []}

        # 1) Exit names no longer in the target set.
        for sym, pos in list(self.broker.positions().items()):
            if sym not in target_w and sym in quotes:
                self.broker.place_order(sym, Side.SELL, pos.qty, quotes[sym], now)
                log["trades"].append(("SELL", sym, pos.qty))

        # 2) Rebalance toward target weights. Skip tiny drift to avoid cost-churn.
        min_trade_value = 0.005 * nav  # only trade adjustments worth >0.5% of NAV
        for sym, w in target_w.items():
            price = quotes.get(sym)
            if not price:
                continue
            target_qty = int((w * nav) // price)
            cur = self.broker.positions().get(sym)
            cur_qty = cur.qty if cur else 0
            diff = target_qty - cur_qty
            if abs(diff) * price < min_trade_value:
                continue  # negligible drift — leave it
            if diff > 0:
                self.broker.place_order(sym, Side.BUY, diff, price, now)
                log["trades"].append(("BUY", sym, diff))
            elif diff < 0:
                self.broker.place_order(sym, Side.SELL, -diff, price, now)
                log["trades"].append(("SELL", sym, -diff))

        if hasattr(self.broker, "save_state"):
            self.broker.save_state()
        return log
