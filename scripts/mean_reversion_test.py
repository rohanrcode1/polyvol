"""The definitive, strategy-agnostic edge test (roadmap step 4).

Question: do real 5-minute binary paths mean-revert at short horizons?

Method: for each market path, take NON-OVERLAPPING 10-second steps and
regress the next 10s price change on the previous 10s price change:

    dp[t, t+10] = alpha + beta * dp[t-10, t] + eps

  beta < 0  => mean reversion (dips bounce)   -> strategy could work
  beta = 0  => martingale                     -> strategy is dead (proven)
  beta > 0  => momentum                       -> strategy is worse than dead

Inference is clustered by market: one beta per market, then a t-test across
markets (immune to within-market autocorrelation). Also bucketed by
time-remaining and |p - 0.5| so a localized pocket of reversion can't hide
in the pooled number.

Interpretation guide: the strategy needs reversion worth >= ~3-5c per pair
(the cost hurdle from the synthetic run). A beta of -0.1 on a typical 5c
swing recovers only ~0.5c -- statistically interesting, economically dead.

Usage:
  python scripts/mean_reversion_test.py --cache output/real      # real data
  python scripts/mean_reversion_test.py --synthetic              # self-test
                                        (must print beta ~ 0 on GBM paths)
"""

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import numpy as np
import pandas as pd

from polyvol.reconstruct import yes_price_series, paths_matrix

STEP_S = 10          # horizon of both the lag and the lead return
T_MIN, T_MAX = 15, 285   # ignore the very open and the terminal pin


def per_market_beta(path: np.ndarray, dt: float = 1.0):
    """OLS beta of lead return on lag return, non-overlapping steps."""
    idx = np.arange(T_MIN + STEP_S, T_MAX - STEP_S, STEP_S)
    lag = path[idx] - path[idx - STEP_S]
    lead = path[idx + STEP_S] - path[idx]
    keep = np.isfinite(lag) & np.isfinite(lead)
    lag, lead = lag[keep], lead[keep]
    if len(lag) < 5 or lag.std() < 1e-6:
        return np.nan
    return float(np.cov(lag, lead, ddof=1)[0, 1] / np.var(lag, ddof=1))


def bucketed_betas(paths: np.ndarray):
    """Pooled beta split by time-remaining and distance-from-50c buckets."""
    rows = []
    tr_buckets = [(240, 285), (180, 240), (120, 180), (60, 120), (15, 60)]
    horizon = paths.shape[1] - 1
    for tr_lo, tr_hi in tr_buckets:
        t_lo, t_hi = horizon - tr_hi, horizon - tr_lo
        idx = np.arange(max(t_lo, STEP_S), min(t_hi, horizon - STEP_S), STEP_S)
        if len(idx) == 0:
            continue
        lag = paths[:, idx] - paths[:, idx - STEP_S]
        lead = paths[:, idx + STEP_S] - paths[:, idx]
        level = paths[:, idx]
        for lo, hi, name in [(0.0, 0.15, "near 50c (|p-.5|<.15)"),
                             (0.15, 0.35, "mid    (.15-.35)"),
                             (0.35, 0.50, "extreme(>.35)")]:
            m = (np.abs(level - 0.5) >= lo) & (np.abs(level - 0.5) < hi) \
                & np.isfinite(lag) & np.isfinite(lead)
            if m.sum() < 200:
                continue
            x, y = lag[m], lead[m]
            if x.std() < 1e-9:
                continue
            b = np.cov(x, y, ddof=1)[0, 1] / np.var(x, ddof=1)
            # crude SE (pooled; clustered version is the headline number)
            resid = y - b * x
            se = resid.std(ddof=2) / (x.std(ddof=1) * np.sqrt(len(x)))
            rows.append(dict(time_remaining=f"{tr_lo}-{tr_hi}s",
                             level_bucket=name, n=int(m.sum()),
                             beta=b, t=b / se))
    return pd.DataFrame(rows)


def load_real_paths(cache: Path):
    mkts = None
    for p in [cache / "markets.parquet", cache / "markets.csv"]:
        if p.exists():
            mkts = pd.read_parquet(p) if p.suffix == ".parquet" \
                else pd.read_csv(p)
            break
    if mkts is None:
        sys.exit(f"no markets table in {cache}")
    for c in ("window_start", "window_end"):
        mkts[c] = pd.to_datetime(mkts[c], utc=True)
    series = []
    for _, m in mkts.iterrows():
        f = cache / f"trades_{m.condition_id[:12]}.parquet"
        if not f.exists():
            f = f.with_suffix(".csv")
            if not f.exists():
                continue
        tr = pd.read_parquet(f) if f.suffix == ".parquet" else pd.read_csv(f)
        if tr.empty:
            continue
        tr["ts"] = pd.to_datetime(tr["ts"], utc=True)
        series.append(yes_price_series(tr, m.window_start, m.window_end))
    print(f"loaded {len(series)} cached market paths from {cache}")
    return paths_matrix(series)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--cache", default="output/real")
    ap.add_argument("--synthetic", action="store_true",
                    help="self-test on martingale paths (expect beta ~ 0)")
    args = ap.parse_args()

    from polyvol.synthetic import simulate_paths

    if args.synthetic:
        paths, _ = simulate_paths(5000, sigma_ann=0.45, seed=7)
        label = "SYNTHETIC self-test (excess beta should be ~0)"
    else:
        paths = load_real_paths(Path(args.cache))
        label = f"REAL ({paths.shape[0]} markets)"

    def estimate(p):
        b = np.array([per_market_beta(x) for x in p])
        return b[np.isfinite(b)]

    betas = estimate(paths)

    # IMPORTANT: the raw estimator has a small-sample NEGATIVE bias
    # (~ -1/n_steps per market), so it reports spurious "mean reversion"
    # even on perfect martingales. We cancel it by running the identical
    # estimator on 5000 matched synthetic martingale paths and testing the
    # EXCESS: real beta minus null beta.
    null_paths, _ = simulate_paths(5000, sigma_ann=0.45, seed=123)
    null_betas = estimate(null_paths)

    mean_b, mean_0 = betas.mean(), null_betas.mean()
    excess = mean_b - mean_0
    se = np.sqrt(betas.var(ddof=1) / len(betas)
                 + null_betas.var(ddof=1) / len(null_betas))
    t = excess / se

    print(f"\n=== 10s-lag autocorrelation of price changes: {label} ===")
    print(f"markets used            : {len(betas)}")
    print(f"raw mean beta           : {mean_b:+.4f}  "
          f"(biased -- do not interpret alone)")
    print(f"martingale-null beta    : {mean_0:+.4f}  (same estimator bias)")
    print(f"EXCESS beta vs null     : {excess:+.4f}")
    print(f"t-stat (two-sample)     : {t:+.2f}")
    print(f"verdict                 : "
          f"{'MEAN REVERSION beyond null' if (excess < 0 and t < -3) else 'MOMENTUM beyond null' if (excess > 0 and t > 3) else 'consistent with MARTINGALE (no edge)'}")

    print("\n--- pooled beta by time-remaining x price-level bucket ---")
    bt = bucketed_betas(paths)
    if not bt.empty:
        print(bt.to_string(index=False,
                           float_format=lambda x: f"{x:+.4f}"))
    print("\nEconomic bar: the pair strategy needs reversion worth >= 3-5c "
          "per round trip. beta * (typical 10s move) is the recoverable "
          "amount; with 1-3c moves, |beta| must exceed ~1 -- i.e. massive.")


if __name__ == "__main__":
    main()
