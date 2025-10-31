from decimal import ROUND_DOWN, Decimal


def to_base_amount_int(base_amount_tokens, size_decimals):
    """
    Convert a token amount (Decimal/float/str) to the integer amount expected by the API.
    - base_amount_tokens: amount in *tokens* (e.g. 0.123 SOL)
    - size_decimals: number of decimals the market supports (e.g. 3)
    Returns an int.
    """
    dec = Decimal(str(base_amount_tokens))
    scale = Decimal(10) ** int(size_decimals)
    # Round down to avoid sending a larger amount than intended
    scaled = (dec * scale).quantize(Decimal("1"), rounding=ROUND_DOWN)
    return int(scaled)


def calculate_current_price_from_position(
    sign, position, avg_entry_price, position_value, unrealized_pnl
):
    """
    Calculate the current price of an underlying asset based on position details.

    Parameters:
        sign (int): 1 for long, -1 for short.
        position (float): Position size.
        avg_entry_price (float): Average entry price.
        position_value (float): Current mark-to-market value of the position.
        unrealized_pnl (float): Unrealized profit or loss.

    Returns:
        float: The current price of the underlying asset.
    """
    position = float(position)
    avg_entry_price = float(avg_entry_price)
    position_value = float(position_value)
    unrealized_pnl = float(unrealized_pnl)

    current_price = position_value / position

    return current_price
