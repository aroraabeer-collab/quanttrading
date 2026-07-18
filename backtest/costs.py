"""Indian **intraday** (equity MIS) transaction-cost model.

Every scalp is a round trip (buy + sell, same day). Costs are the reason most
high-frequency retail strategies fail, so we model each component explicitly
rather than hand-waving a single number.

Rates below are standard NSE intraday equity charges (subject to change by
exchange/SEBI/government — update here in one place). Brokerage assumes Fyers'
intraday plan: ₹20 per executed order or 0.03% of turnover, whichever is lower.

References for the schedule: NSE/SEBI charge circulars and broker cost pages.
"""
from __future__ import annotations

from dataclasses import dataclass

# --- Statutory / exchange rates (fractions of turnover unless noted) ---
STT_SELL = 0.00025          # Securities Transaction Tax: 0.025% on SELL side only
EXCHANGE_TXN = 0.0000297    # NSE transaction charge: ~0.00297%, both sides
SEBI_TURNOVER = 0.000001    # SEBI: ₹10 per crore = 0.0001%, both sides
STAMP_BUY = 0.00003         # Stamp duty: 0.003% on BUY side only
GST_RATE = 0.18             # GST: 18% on (brokerage + exchange txn + SEBI)

# --- Delivery (positional / CNC) equity rates ---
STT_DELIVERY = 0.001        # 0.1% on BOTH buy and sell (delivery)
STAMP_DELIVERY_BUY = 0.00015  # 0.015% on BUY side only
DP_CHARGE_PER_SELL = 13.5   # ₹ flat depository charge per scrip on the sell side
# Fyers charges ZERO brokerage on equity delivery.

# --- Broker (Fyers intraday) ---
BROKERAGE_FLAT = 20.0       # ₹ per executed order
BROKERAGE_PCT = 0.0003      # 0.03% of order value
BROKERAGE_MIN_OF = "min"    # whichever is lower


def brokerage_per_order(order_value: float) -> float:
    """₹ brokerage for one order = min(₹20, 0.03% of value)."""
    return min(BROKERAGE_FLAT, BROKERAGE_PCT * order_value)


@dataclass
class CostBreakdown:
    """Round-trip cost of one scalp, in ₹, at a given notional."""

    notional: float
    brokerage: float
    stt: float
    exchange_txn: float
    sebi: float
    stamp: float
    gst: float
    slippage: float

    @property
    def total(self) -> float:
        return (
            self.brokerage + self.stt + self.exchange_txn
            + self.sebi + self.stamp + self.gst + self.slippage
        )

    @property
    def total_fraction(self) -> float:
        """Total round-trip cost as a fraction of notional."""
        return self.total / self.notional if self.notional else 0.0

    def as_dict(self) -> dict[str, float]:
        return {
            "brokerage": self.brokerage,
            "stt": self.stt,
            "exchange_txn": self.exchange_txn,
            "sebi": self.sebi,
            "stamp": self.stamp,
            "gst": self.gst,
            "slippage": self.slippage,
            "total": self.total,
            "total_bps": self.total_fraction * 1e4,
        }


class IntradayCostModel:
    def __init__(self, slippage_bps: float) -> None:
        self.slippage_bps = slippage_bps

    def round_trip(self, notional: float) -> CostBreakdown:
        """Cost of buying then selling ~``notional`` worth of stock, same day."""
        brokerage = 2 * brokerage_per_order(notional)          # buy + sell orders
        stt = STT_SELL * notional                               # sell side only
        exchange_txn = EXCHANGE_TXN * notional * 2              # both sides
        sebi = SEBI_TURNOVER * notional * 2                     # both sides
        stamp = STAMP_BUY * notional                            # buy side only
        gst = GST_RATE * (brokerage + exchange_txn + sebi)
        slippage = (self.slippage_bps / 1e4) * notional * 2     # per side
        return CostBreakdown(
            notional=notional,
            brokerage=brokerage,
            stt=stt,
            exchange_txn=exchange_txn,
            sebi=sebi,
            stamp=stamp,
            gst=gst,
            slippage=slippage,
        )

    def side_cost(self, value: float, side: str) -> float:
        """₹ cost of a single order (``side`` = 'buy' or 'sell').

        Consistent with :meth:`round_trip` (buy + sell side costs sum to it).
        Used by the paper broker to charge each simulated fill.
        """
        side = side.lower()
        brokerage = brokerage_per_order(value)
        exchange_txn = EXCHANGE_TXN * value
        sebi = SEBI_TURNOVER * value
        stt = STT_SELL * value if side == "sell" else 0.0
        stamp = STAMP_BUY * value if side == "buy" else 0.0
        gst = GST_RATE * (brokerage + exchange_txn + sebi)
        slippage = (self.slippage_bps / 1e4) * value
        return brokerage + exchange_txn + sebi + stt + stamp + gst + slippage

    def per_side_fee_fraction(self, notional: float) -> float:
        """Symmetric per-transaction fee fraction for vectorbt's ``fees=``.

        vectorbt charges the same ``fees`` on entry and exit; we halve the
        round-trip statutory+broker cost (slippage is passed separately) so the
        modelled round-trip total matches this cost model.
        """
        rt = self.round_trip(notional)
        cost_ex_slippage = rt.total - rt.slippage
        return (cost_ex_slippage / notional) / 2 if notional else 0.0

    def slippage_fraction(self) -> float:
        """Per-side slippage as a fraction, for vectorbt's ``slippage=``."""
        return self.slippage_bps / 1e4


class DeliveryCostModel:
    """Positional/delivery (CNC) equity costs — free brokerage, but 0.1% STT
    on both sides. Used by the ML factor backtest, which rebalances infrequently.
    """

    def __init__(self, slippage_bps: float) -> None:
        self.slippage_bps = slippage_bps

    def side_cost(self, value: float, side: str) -> float:
        """₹ cost of one delivery order (``side`` = 'buy' or 'sell')."""
        side = side.lower()
        exchange_txn = EXCHANGE_TXN * value
        sebi = SEBI_TURNOVER * value
        stt = STT_DELIVERY * value  # both sides
        stamp = STAMP_DELIVERY_BUY * value if side == "buy" else 0.0
        dp = DP_CHARGE_PER_SELL if side == "sell" else 0.0
        gst = GST_RATE * (exchange_txn + sebi)  # brokerage is zero on delivery
        slippage = (self.slippage_bps / 1e4) * value
        return exchange_txn + sebi + stt + stamp + dp + gst + slippage

    def rebalance_cost(self, buy_value: float, sell_value: float, n_sells: int) -> float:
        """Total ₹ cost of a rebalance given buy/sell notional and #scrips sold."""
        cost = self.side_cost(buy_value, "buy") + self.side_cost(sell_value, "sell")
        cost += DP_CHARGE_PER_SELL * max(0, n_sells - 1)  # side_cost already added one
        return cost
