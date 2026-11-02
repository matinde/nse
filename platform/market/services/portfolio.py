"""Turn a person's buy and sell rows into open holdings and realized profit."""

from decimal import Decimal


def combine_trades(trades):
    """Apply trades in date order.

    Each trade is a dict with id, code, side ("buy" or "sell"), shares, and price.
    Returns (positions, error). positions maps a code to shares still held,
    remaining cost, and profit already realized on sells. error is set when a
    sell is larger than the shares held at that moment.
    """
    ordered = sorted(trades, key=lambda trade: (trade["trade_date"], trade["id"] if trade["id"] is not None else 10**12))
    positions = {}
    for trade in ordered:
        code = trade["code"]
        shares = int(trade["shares"])
        price = Decimal(trade["price"])
        state = positions.setdefault(
            code,
            {"shares": 0, "cost": Decimal("0"), "realized": Decimal("0")},
        )
        if trade["side"] == "buy":
            state["shares"] += shares
            state["cost"] += price * shares
            continue
        if shares > state["shares"]:
            return positions, (
                f"Cannot sell {shares} {code}. Only {state['shares']} "
                f"{'share is' if state['shares'] == 1 else 'shares are'} held on {trade['trade_date']}."
            )
        average = state["cost"] / state["shares"]
        state["realized"] += (price - average) * shares
        state["cost"] -= average * shares
        state["shares"] -= shares
        if state["shares"] == 0:
            state["cost"] = Decimal("0")
    return positions, None


def held_intervals(trades, as_of):
    """Periods when each stock was held, from the buy that opened it to the sell that closed it.

    A position still open runs through as_of.
    """
    ordered = sorted(
        trades,
        key=lambda trade: (trade["trade_date"], trade["id"] if trade["id"] is not None else 10**12),
    )
    grouped = {}
    for trade in ordered:
        grouped.setdefault(trade["code"], []).append(trade)
    spans = []
    for code, rows in grouped.items():
        shares = 0
        opened = None
        for trade in rows:
            before = shares
            if trade["side"] == "buy":
                shares += int(trade["shares"])
            else:
                shares = max(0, shares - int(trade["shares"]))
            if before <= 0 and shares > 0:
                opened = trade["trade_date"]
            elif before > 0 and shares <= 0 and opened is not None:
                spans.append((code, opened, trade["trade_date"]))
                opened = None
        if opened is not None and shares > 0:
            spans.append((code, opened, as_of))
    return spans
