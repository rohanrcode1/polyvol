"""Synthetic 5-minute binary market generator.

Model: BTC follows a driftless GBM with per-second volatility sig_s.
The market's YES mid-price is the fair probability that S_T > K given S_t,
with strike K = S_0 (markets open at ~50c):

    p_t = Phi( ln(S_t / K) / (sig_s * sqrt(tau)) ),   tau = seconds remaining

Properties this reproduces (and why it is the right NULL model):
  * opens at 50/50, resolves to exactly 0 or 1
  * swings of 10-30c inside 5 minutes are routine when S hovers near K
  * pins hard to 0/1 in the final seconds
  * p_t is a MARTINGALE. Under a martingale, EVERY entry/hedge timing rule
    has exactly zero expected value before costs (optional stopping theorem),
    and therefore negative EV after spread + taker fees.

So a real edge exists only if real Polymarket paths deviate from this model
(short-horizon overreaction / mean reversion) by MORE than execution costs.
The synthetic engine calibrates the cost hurdle; the real-data backtest
measures the deviation.
"""

from __future__ import annotations

import numpy as np
from scipy.stats import norm

SECONDS_PER_YEAR = 365 * 24 * 3600


def simulate_paths(
    n_markets: int,
    horizon_s: int = 300,
    dt: float = 1.0,
    sigma_ann: float = 0.45,
    seed: int = 0,
):
    """Simulate YES mid-price paths.

    Returns
    -------
    prices : (n_markets, n_steps + 1) YES mid-price, 1 column per dt
    outcomes : (n_markets,) 1 if YES wins else 0
    """
    rng = np.random.default_rng(seed)
    n_steps = int(round(horizon_s / dt))
    sig_s = sigma_ann / np.sqrt(SECONDS_PER_YEAR)  # per sqrt-second log-vol

    dW = rng.standard_normal((n_markets, n_steps)) * np.sqrt(dt)
    x = np.cumsum(sig_s * dW, axis=1)                      # ln(S_t / K)
    x = np.hstack([np.zeros((n_markets, 1)), x])

    tau = horizon_s - np.arange(n_steps + 1) * dt          # seconds remaining
    denom = sig_s * np.sqrt(np.maximum(tau, 1e-12))
    with np.errstate(divide="ignore", invalid="ignore"):
        prices = norm.cdf(x / denom)

    outcomes = (x[:, -1] > 0).astype(int)
    prices[:, -1] = outcomes                               # terminal pin
    return prices, outcomes


def touch_probability_matrix(
    prices: np.ndarray,
    entry_levels=(0.30, 0.35, 0.40, 0.45),
    deltas=(0.02, 0.05, 0.10),
    min_time_remaining_s=(240, 180, 120, 60, 30),
    dt: float = 1.0,
):
    """P(YES later trades >= entry + delta | YES first touched entry with
    >= T seconds remaining). Answers research question #3 directly.

    Returns list of dict rows.
    """
    n_markets, n_cols = prices.shape
    horizon = (n_cols - 1) * dt
    rows = []
    for e in entry_levels:
        below = prices <= e
        first_idx = np.where(below.any(axis=1), below.argmax(axis=1), -1)
        for min_tr in min_time_remaining_s:
            latest_idx = int((horizon - min_tr) / dt)
            valid = (first_idx >= 0) & (first_idx <= latest_idx)
            idxs = np.flatnonzero(valid)
            if len(idxs) == 0:
                continue
            for d in deltas:
                hits = 0
                for i in idxs:
                    j = first_idx[i]
                    if prices[i, j:].max() >= e + d:
                        hits += 1
                rows.append(
                    dict(entry=e, delta=d, min_tr_s=min_tr,
                         n=len(idxs), p_touch=hits / len(idxs))
                )
    return rows
