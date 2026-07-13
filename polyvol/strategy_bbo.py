"""Execution-realistic strategy engine driven by REAL best bid/ask series.

This replaces the modeled half-spread with the actual top-of-book from the
HF dataset's `orderbook` subset (built by scripts/hf_ingest.py build):

  * entry fills at the real best ASK of the cheap side, only if the
    displayed ask SIZE covers the order (no fantasy fills into 5-share
    quotes)
  * hedge fills at the real best ask of the opposite side under the same
    size constraint
  * taker fee = rate * p * (1-p) per share on each leg (crypto rate 0.07)

Still optimistic in one way: taking the full displayed size assumes nobody
beats you to it. Treat results as an upper bound on taker performance;
anything negative here is decisively dead.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd

from .fees import taker_fee_per_share, CRYPTO_FEE_RATE


@dataclass
class BBOParams:
    entry: float = 0.40
    target: float = 0.05
    warmup_s: float = 15.0
    min_tr_s: float = 60.0
    order_shares: float = 20.0     # require displayed size >= this
    fee_rate: float = CRYPTO_FEE_RATE


def run_path_bbo(up_bid, up_ask, up_bid_sz, up_ask_sz, outcome_up: int,
                 p: BBOParams, horizon_s: int = 300):
    """One market on real BBO arrays indexed by second [0..horizon].

    Down-side quotes come from the complement of the Up book:
        down_ask = 1 - up_bid   (size = up_bid_sz)
        down_bid = 1 - up_ask
    which is exact for a binary CLOB (selling Up at the bid == buying Down).
    """
    n = len(up_ask)
    t = np.arange(n, dtype=float)
    tr = horizon_s - t

    down_ask = 1.0 - up_bid
    down_ask_sz = up_bid_sz

    ok = (t >= p.warmup_s) & (tr >= p.min_tr_s) & np.isfinite(up_ask)

    up_entry = ok & (up_ask <= p.entry) & (up_ask_sz >= p.order_shares)
    dn_entry = ok & (down_ask <= p.entry) & (down_ask_sz >= p.order_shares)
    any_e = up_entry | dn_entry
    if not any_e.any():
        return None
    i0 = int(any_e.argmax())

    if up_entry[i0]:
        side, entry_px = "UP", float(up_ask[i0])
        hedge_ask, hedge_sz = down_ask, down_ask_sz
        leg_payoff = outcome_up
    else:
        side, entry_px = "DOWN", float(down_ask[i0])
        hedge_ask, hedge_sz = up_ask, up_ask_sz
        leg_payoff = 1 - outcome_up

    entry_fee = taker_fee_per_share(entry_px, p.fee_rate)

    lim = 1.0 - entry_px - p.target
    can = np.zeros(n, dtype=bool)
    can[i0 + 1:] = (np.nan_to_num(hedge_ask[i0 + 1:], nan=2.0) <= lim) \
        & (np.nan_to_num(hedge_sz[i0 + 1:]) >= p.order_shares)
    completed = bool(can.any())

    rec = dict(side=side, entry_t=float(t[i0]), entry_px=entry_px,
               entry_fee=entry_fee, completed=completed,
               entry=p.entry, target=p.target,
               order_shares=p.order_shares)
    if completed:
        j = int(can.argmax())
        hpx = float(hedge_ask[j])
        hfee = taker_fee_per_share(hpx, p.fee_rate)
        rec.update(hedge_t=float(t[j]), hedge_px=hpx,
                   time_to_hedge=float(t[j] - t[i0]),
                   pnl=1.0 - entry_px - hpx - entry_fee - hfee)
    else:
        rec.update(hedge_t=np.nan, hedge_px=np.nan, time_to_hedge=np.nan,
                   pnl=float(leg_payoff) - entry_px - entry_fee)
    return rec


def run_bbo_backtest(bbo_path: str, grid: dict | None = None,
                     horizon_s: int = 300) -> pd.DataFrame:
    """Run the grid over every market in a bbo_5m.parquet file."""
    from dataclasses import replace
    from itertools import product

    grid = grid or dict(entry=[0.30, 0.35, 0.40, 0.45],
                        target=[0.02, 0.05, 0.10])
    bbo = pd.read_parquet(bbo_path)
    recs = []
    keys = list(grid.keys())
    for mid, g in bbo.groupby("market_id"):
        g = g.set_index("sec").reindex(range(horizon_s + 1)).ffill()
        arrs = [g[c].to_numpy(dtype=float)
                for c in ("up_bid", "up_ask", "up_bid_sz", "up_ask_sz")]
        outcome = int(g["resolution"].dropna().iloc[0]) \
            if g["resolution"].notna().any() else None
        if outcome is None:
            continue
        for combo in product(*grid.values()):
            p = replace(BBOParams(), **dict(zip(keys, combo)))
            r = run_path_bbo(*arrs, outcome, p, horizon_s)
            if r is not None:
                r["market_id"] = mid
                recs.append(r)
    return pd.DataFrame(recs)
