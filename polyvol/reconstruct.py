"""Turn a raw trade tape into a 1-second YES price path per market.

Also estimates the effective half-spread from the tape itself: taker BUYs
print at the ask, taker SELLs at the bid, so the average signed gap between
consecutive buy/sell prints is a live estimate of what crossing the book
actually cost. This keeps the execution simulator honest without full book
data.
"""

from __future__ import annotations

import numpy as np
import pandas as pd


def yes_price_series(trades: pd.DataFrame, start_ts, end_ts,
                     dt: str = "1s") -> pd.DataFrame:
    """1-second grid of YES trade price (last-observation-carried-forward).

    trades: output of fetch_trades(); needs ts, price, size, outcome, side.
    """
    t = trades.copy()
    # Normalize everything to YES terms: a NO print at q implies YES = 1 - q.
    is_no = t["outcome"].str.lower().isin(["no", "down"])
    t["yes_px"] = np.where(is_no, 1.0 - t["price"], t["price"])
    # Taker BUY of YES lifts the YES ask; taker SELL hits the YES bid.
    # A BUY of NO is economically a SELL of YES.
    buy = t["side"].str.upper().eq("BUY")
    t["yes_aggr"] = np.where(buy ^ is_no, 1, -1)  # +1 = at ask, -1 = at bid

    grid = pd.date_range(start_ts, end_ts, freq=dt)
    s = (t.set_index("ts")["yes_px"]
         .resample(dt).last().reindex(grid).ffill())
    out = pd.DataFrame({"yes_px": s})
    out["sec_remaining"] = (end_ts - out.index).total_seconds()
    return out


def estimate_half_spread(trades: pd.DataFrame) -> float:
    """Effective half-spread from bid/ask prints in the tape."""
    t = trades.copy()
    is_no = t["outcome"].str.lower().isin(["no", "down"])
    t["yes_px"] = np.where(is_no, 1.0 - t["price"], t["price"])
    buy = t["side"].str.upper().eq("BUY")
    t["aggr"] = np.where(buy ^ is_no, 1, -1)
    # consecutive opposite-aggressor prints straddle the spread
    px = t["yes_px"].values
    ag = t["aggr"].values
    gaps = []
    for i in range(1, len(t)):
        if ag[i] != ag[i - 1]:
            gaps.append(ag[i - 1] * (px[i - 1] - px[i]))
    gaps = [g for g in gaps if 0 <= g <= 0.10]
    return float(np.median(gaps) / 2) if gaps else 0.01


def paths_matrix(per_market_series: list[pd.DataFrame],
                 horizon_s: int = 300) -> np.ndarray:
    """Stack per-market 1s series into the (n_markets, horizon+1) matrix the
    backtester consumes. Markets missing early prints are back-filled at 0.5
    (their true opening state)."""
    n = len(per_market_series)
    m = np.full((n, horizon_s + 1), np.nan)
    for i, df in enumerate(per_market_series):
        v = df["yes_px"].values[-(horizon_s + 1):]
        m[i, -len(v):] = v
    # opening state ~ 0.5 before the first print
    first_nan = np.isnan(m)
    m[first_nan] = 0.5
    return m
