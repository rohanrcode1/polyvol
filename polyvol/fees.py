"""Polymarket fee model.

Verified against docs.polymarket.com/trading/fees (fetched 2026-07-11):

    fee (USDC) = C * feeRate * p * (1 - p)

where C = shares traded, p = share price. Taker-only. Makers pay ZERO.
Category rates: Crypto = 0.07 (highest), Sports = 0.03, Geopolitics = 0.

Crypto examples per share:
    p = 0.50 -> $0.0175
    p = 0.40 -> $0.0168
    p = 0.10 -> $0.0063
    p = 0.05 -> $0.0033

NOTE: fee params are per-market and can change. Before trusting any backtest
number, fetch live params via CLOB `getClobMarketInfo(conditionID)` ->
info["fd"] = {"r": feeRate, "e": exponent, "to": taker_only} and plug them in.
"""

CRYPTO_FEE_RATE = 0.07


def taker_fee_per_share(price: float, fee_rate: float = CRYPTO_FEE_RATE) -> float:
    """USDC fee per share for a taker fill at `price`."""
    p = min(max(price, 0.0), 1.0)
    return fee_rate * p * (1.0 - p)


def maker_fee_per_share(price: float, fee_rate: float = 0.0) -> float:
    """Makers are never charged fees (per current docs)."""
    return 0.0
