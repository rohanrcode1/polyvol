"""Volatility-harvesting pair strategy engine.

Strategy: buy the cheap side when it first trades at/below `entry`, then try
to buy the opposite side so that total pair cost + fees < $1 (a completed
hedge = riskless $1 claim). If the hedge never completes, hold the naked leg
to resolution (payoff 0 or 1).

Execution modes
---------------
taker : cross the spread on both legs. Entry fills at ask = mid + half_spread,
        hedge fills at the opposite side's ask. Pay the documented taker fee
        fee = rate * p * (1-p) per share on each leg. This is the
        CONSERVATIVE / realistic-floor mode.
maker : rest limit orders. Entry fills at exactly `entry` when the mid trades
        through it; hedge fills at the limit when the mid trades through.
        Zero fees, no spread paid. This is an OPTIMISTIC UPPER BOUND: it
        ignores queue position, partial fills, and the adverse selection of
        being filled precisely when informed flow hits you. Real maker
        performance sits below this line, sometimes far below.

Prices are the YES mid. The complement book gives:
    NO ask ~= (1 - YES bid) + half_spread_no
We model a symmetric half-spread on both books.
"""

from __future__ import annotations

from dataclasses import dataclass, asdict

import numpy as np

from .fees import taker_fee_per_share, CRYPTO_FEE_RATE


@dataclass
class Params:
    entry: float = 0.40        # buy the cheap side when its price <= entry
    target: float = 0.05       # required GROSS profit per pair to hedge
    warmup_s: float = 15.0     # never trade in the first N seconds
    min_tr_s: float = 60.0     # require >= N seconds remaining at entry
    half_spread: float = 0.01  # per-book half spread (taker mode)
    fee_rate: float = CRYPTO_FEE_RATE
    mode: str = "taker"        # "taker" | "maker"
    enter_both_sides: bool = True  # enter whichever side gets cheap first


def run_path(prices: np.ndarray, outcome: int, p: Params, dt: float = 1.0):
    """Simulate one market. Returns a trade record dict or None (no entry).

    prices : YES mid per dt step. outcome : 1 if YES wins.
    """
    n = len(prices)
    horizon = (n - 1) * dt
    t = np.arange(n) * dt
    tr = horizon - t  # seconds remaining

    yes = prices
    no = 1.0 - prices

    # ---- entry -------------------------------------------------------
    ok_time = (t >= p.warmup_s) & (tr >= p.min_tr_s)
    if p.mode == "taker":
        yes_entry_px = yes + p.half_spread   # buy at ask
        no_entry_px = no + p.half_spread
    else:
        yes_entry_px = yes                   # limit fills at mid touch
        no_entry_px = no

    yes_hit = ok_time & (yes_entry_px <= p.entry)
    no_hit = ok_time & (no_entry_px <= p.entry) if p.enter_both_sides \
        else np.zeros(n, dtype=bool)

    any_hit = yes_hit | no_hit
    if not any_hit.any():
        return None
    i0 = int(any_hit.argmax())

    if yes_hit[i0]:
        side = "YES"
        entry_px = float(min(yes_entry_px[i0], p.entry)) if p.mode == "maker" \
            else float(yes_entry_px[i0])
        entry_px = min(entry_px, p.entry) if p.mode == "maker" else entry_px
        hedge_mid = no          # we will be buying NO
        leg_payoff = outcome    # YES pays `outcome`
    else:
        side = "NO"
        entry_px = float(min(no_entry_px[i0], p.entry)) if p.mode == "maker" \
            else float(no_entry_px[i0])
        hedge_mid = yes
        leg_payoff = 1 - outcome

    if p.mode == "maker":
        entry_px = p.entry  # limit price
        entry_fee = 0.0
    else:
        entry_fee = taker_fee_per_share(entry_px, p.fee_rate)

    # ---- hedge -------------------------------------------------------
    # Complete the pair when the opposite side is cheap enough that gross
    # pair profit >= target.
    hedge_limit = 1.0 - entry_px - p.target
    if p.mode == "taker":
        hedge_px_series = hedge_mid + p.half_spread
    else:
        hedge_px_series = hedge_mid

    can_hedge = np.zeros(n, dtype=bool)
    can_hedge[i0 + 1:] = hedge_px_series[i0 + 1:] <= hedge_limit
    completed = bool(can_hedge.any())

    rec = dict(
        side=side, entry_idx=i0, entry_t=float(t[i0]),
        entry_tr=float(tr[i0]), entry_px=entry_px, entry_fee=entry_fee,
        completed=completed, **asdict(p),
    )

    if completed:
        j = int(can_hedge.argmax())
        hedge_px = hedge_limit if p.mode == "maker" else float(hedge_px_series[j])
        hedge_fee = 0.0 if p.mode == "maker" \
            else taker_fee_per_share(hedge_px, p.fee_rate)
        pnl = 1.0 - entry_px - hedge_px - entry_fee - hedge_fee
        rec.update(hedge_t=float(t[j]), hedge_px=hedge_px,
                   hedge_fee=hedge_fee,
                   time_to_hedge=float(t[j] - t[i0]), pnl=float(pnl))
    else:
        pnl = float(leg_payoff) - entry_px - entry_fee
        rec.update(hedge_t=np.nan, hedge_px=np.nan, hedge_fee=0.0,
                   time_to_hedge=np.nan, pnl=float(pnl))
    return rec
