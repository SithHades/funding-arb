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
