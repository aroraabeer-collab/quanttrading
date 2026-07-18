from backtest.costs import IntradayCostModel, brokerage_per_order


def test_brokerage_is_capped_at_flat_rate():
    # 0.03% of ₹1,00,000 = ₹30 > ₹20 flat -> capped at 20.
    assert brokerage_per_order(100_000) == 20.0
    # 0.03% of ₹50,000 = ₹15 < ₹20 -> percentage wins.
    assert brokerage_per_order(50_000) == 15.0 or abs(brokerage_per_order(50_000) - 15.0) < 1e-9


def test_round_trip_equals_sum_of_side_costs():
    model = IntradayCostModel(slippage_bps=3.0)
    notional = 100_000
    rt = model.round_trip(notional)
    sides = model.side_cost(notional, "buy") + model.side_cost(notional, "sell")
    assert abs(rt.total - sides) < 1e-6


def test_stt_only_on_sell_and_stamp_only_on_buy():
    model = IntradayCostModel(slippage_bps=0.0)
    buy = model.side_cost(100_000, "buy")
    sell = model.side_cost(100_000, "sell")
    # Sell carries STT (0.025%) which dwarfs the buy-side stamp (0.003%).
    assert sell > buy


def test_per_side_fee_fraction_matches_statutory_round_trip():
    model = IntradayCostModel(slippage_bps=5.0)
    notional = 200_000
    rt = model.round_trip(notional)
    reconstructed = model.per_side_fee_fraction(notional) * 2 * notional
    assert abs(reconstructed - (rt.total - rt.slippage)) < 1e-6


def test_cost_floor_is_material_for_scalping():
    # A realistic scalp cost floor should be tens of bps — the reason scalping is hard.
    model = IntradayCostModel(slippage_bps=3.0)
    frac = model.round_trip(100_000).total_fraction
    assert 0.001 < frac < 0.01  # between 10 and 100 bps
