"""Bounce-free mean reversion test: BBO MIDPOINTS, not trade prints.

Why this exists: the trade-tape regression (mean_reversion_test.py) showed a
small negative excess beta (-0.021, t=-2.7), concentrated at extreme price
levels. But trade prints bounce between bid and ask, and bid-ask bounce
mechanically induces negative autocorrelation in trade-price changes even
when the true value is a perfect martingale (Roll 1984). The bounce is
strongest exactly where the negative betas showed up: extreme prices, where
the spread is largest relative to price and the 1c tick dominates.

Midpoint changes carry no bounce. If the negative excess beta survives on
mids, there is real reversion; if it vanishes, the trade-tape result was
microstructure noise and the martingale verdict is final.

Usage:
  python scripts/bbo_mid_reversion.py --bbo data/hf/bbo_5m.parquet
"""

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import numpy as np
import pandas as pd

from polyvol.synthetic import simulate_paths

STEP_S = 10
T_MIN, T_MAX = 15, 285
HORIZON = 300


def per_market_beta(path: np.ndarray):
    idx = np.arange(T_MIN + STEP_S, T_MAX - STEP_S, STEP_S)
    lag = path[idx] - path[idx - STEP_S]
    lead = path[idx + STEP_S] - path[idx]
    keep = np.isfinite(lag) & np.isfinite(lead)
    lag, lead = lag[keep], lead[keep]
    if len(lag) < 5 or lag.std() < 1e-6:
        return np.nan
    return float(np.cov(lag, lead, ddof=1)[0, 1] / np.var(lag, ddof=1))


def estimate(paths):
    b = np.array([per_market_beta(x) for x in paths])
    return b[np.isfinite(b)]


def bucketed(paths):
    rows = []
    for tr_lo, tr_hi in [(240, 285), (180, 240), (120, 180),
                         (60, 120), (15, 60)]:
        t_lo, t_hi = HORIZON - tr_hi, HORIZON - tr_lo
        idx = np.arange(max(t_lo, STEP_S), min(t_hi, HORIZON - STEP_S),
                        STEP_S)
        if len(idx) == 0:
            continue
        lag = paths[:, idx] - paths[:, idx - STEP_S]
        lead = paths[:, idx + STEP_S] - paths[:, idx]
        level = paths[:, idx]
        for lo, hi, name in [(0.0, 0.15, "near 50c"),
                             (0.15, 0.35, "mid"),
                             (0.35, 0.50, "extreme")]:
            m = (np.abs(level - 0.5) >= lo) & (np.abs(level - 0.5) < hi) \
                & np.isfinite(lag) & np.isfinite(lead)
            if m.sum() < 200:
                continue
            x, y = lag[m], lead[m]
            if x.std() < 1e-9:
                continue
            b = np.cov(x, y, ddof=1)[0, 1] / np.var(x, ddof=1)
            resid = y - b * x
            se = resid.std(ddof=2) / (x.std(ddof=1) * np.sqrt(len(x)))
            rows.append(dict(time_remaining=f"{tr_lo}-{tr_hi}s",
                             level=name, n=int(m.sum()), beta=b, t=b / se))
    return pd.DataFrame(rows)


def load_mid_paths(bbo_path: str):
    bbo = pd.read_parquet(bbo_path,
                          columns=["market_id", "sec", "up_bid", "up_ask"])
    bbo = bbo[(bbo.sec >= 0) & (bbo.sec <= HORIZON)]
    bbo["mid"] = (bbo.up_bid + bbo.up_ask) / 2.0
    # drop crossed/garbage quotes
    bbo.loc[(bbo.up_ask < bbo.up_bid) | (bbo.mid <= 0) | (bbo.mid >= 1),
            "mid"] = np.nan
    mats, dropped = [], 0
    for _, g in bbo.groupby("market_id", sort=False):
        s = g.set_index("sec")["mid"].reindex(range(HORIZON + 1)).ffill()
        if s.notna().sum() < 150:      # require decent coverage
            dropped += 1
            continue
        mats.append(s.to_numpy())
    print(f"{len(mats)} markets with adequate BBO coverage "
          f"({dropped} dropped for sparse books)")
    return np.vstack(mats)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--bbo", default="data/hf/bbo_5m.parquet")
    args = ap.parse_args()

    paths = load_mid_paths(args.bbo)
    betas = estimate(paths)

    null_paths, _ = simulate_paths(5000, sigma_ann=0.45, seed=123)
    null_betas = estimate(null_paths)

    excess = betas.mean() - null_betas.mean()
    se = np.sqrt(betas.var(ddof=1) / len(betas)
                 + null_betas.var(ddof=1) / len(null_betas))
    t = excess / se

    print(f"\n=== 10s autocorrelation on BBO MIDS ({len(betas)} markets) ===")
    print(f"raw mean beta        : {betas.mean():+.4f}")
    print(f"martingale-null beta : {null_betas.mean():+.4f}")
    print(f"EXCESS beta vs null  : {excess:+.4f}")
    print(f"t-stat (two-sample)  : {t:+.2f}")
    print(f"verdict              : "
          f"{'REAL mean reversion' if (excess < 0 and t < -3) else 'momentum' if (excess > 0 and t > 3) else 'MARTINGALE -- trade-tape reversion was bid-ask bounce'}")

    print("\n--- by time-remaining x level (mids) ---")
    bt = bucketed(paths)
    if not bt.empty:
        print(bt.to_string(index=False, float_format=lambda x: f"{x:+.4f}"))


if __name__ == "__main__":
    main()
