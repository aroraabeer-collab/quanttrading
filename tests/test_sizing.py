from portfolio.sizing import size_trade


def test_size_trade_floors_to_whole_shares():
    # 10% of ₹10,00,000 = ₹1,00,000 budget; ₹950 price -> 105 shares.
    assert size_trade(nav=1_000_000, price=950, capital_per_trade=0.10) == 105


def test_size_trade_zero_when_unaffordable():
    assert size_trade(nav=1_000, price=5_000, capital_per_trade=0.10) == 0


def test_size_trade_guards_bad_inputs():
    assert size_trade(nav=0, price=100, capital_per_trade=0.10) == 0
    assert size_trade(nav=1_000_000, price=0, capital_per_trade=0.10) == 0
