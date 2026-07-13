"""Spot-lag test: how long does the Polymarket book stay stale after a
Binance move?

This is the LAST candidate edge family in these markets, and the one the
dynamic fee structure was built to defend. The ticks table carries the
Binance spot price observed at each trade, so we can measure predictability
directly without knowing the strike:

    d_mid[t -> t+k] = alpha + gamma_k * spot_return[t-1 -> t] + eps

for k = 1..15 seconds, pooled across markets (Up-token mid; Up delta is
always positive, so gamma_k > 0 at k >= 1 means the book has NOT yet
incorporated a spot move that is 1+ seconds old => a predictability window.

gamma_k ~ 0 for all k >= 1 means the book reprices within a second and the
latency race is already won by faster players.

Inference: one gamma per market, t-test across markets (clustered).

Usage:
  python scripts/spot_lag_test.py --hf data/hf --asset BTC
"""

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import numpy as np
import pandas as pd

HORIZON = 300
LAGS = [0, 1, 2, 3, 5, 10, 15]


def build_joint_series(hf_dir: Path, asset: str):
    """Per market: 1s grid of (up_mid, spot). Spot comes from the tick
    stream's attached Binance price, forward-filled."""
    import duckdb
    con = duckdb.connect()
    tick_glob = str(hf_dir / "data" / "ticks" / f"crypto={asset}" /
                    "timeframe=5-minute" / "*.parquet")
    bbo_path = str(hf_dir / "bbo_5m.parquet")

    spot = con.sql(f"""
        SELECT t.market_id,
               CAST(t.timestamp_ms / 1000 AS BIGINT)
                   - b.window_start AS sec,
               last(t.spot_price_usdt ORDER BY t.timestamp_ms) AS spot
        FROM read_parquet('{tick_glob}') t
        JOIN (SELECT DISTINCT market_id, window_start
              FROM read_parquet('{bbo_path}')) b USING (market_id)
        WHERE t.spot_price_usdt > 0
        GROUP BY 1, 2
    """).df()

    bbo = pd.read_parquet(bbo_path,
                          columns=["market_id", "crypto", "sec",
                                   "up_bid", "up_ask"])
    bbo = bbo[bbo.crypto == asset]
    bbo["mid"] = (bbo.up_bid + bbo.up_ask) / 2.0

    out = []
    spot_g = dict(tuple(spot.groupby("market_id", sort=False)))
    for mid_id, g in bbo.groupby("market_id", sort=False):
        sg = spot_g.get(mid_id)
        if sg is None or len(sg) < 30:
            continue
        grid = pd.DataFrame(index=range(HORIZON + 1))
        grid["mid"] = g.set_index("sec")["mid"] \
            .reindex(grid.index).ffill()
        grid["spot"] = sg.set_index("sec")["spot"] \
            .reindex(grid.index).ffill()
        if grid["mid"].notna().sum() < 150 or grid["spot"].notna().sum() < 100:
            continue
        out.append((mid_id, grid["mid"].to_numpy(),
                    grid["spot"].to_numpy()))
    print(f"{len(out)} {asset} markets with joint mid+spot coverage")
    return out


def per_market_gammas(mid: np.ndarray, spot: np.ndarray):
    """gamma_k for each lag: slope of mid change [t, t+k] on spot log-return
    [t-1, t]. Skips the final pin (last 15s)."""
    t = np.arange(2, HORIZON - max(LAGS) - 15)
    r = np.log(spot[t] / spot[t - 1])
    res = {}
    ok0 = np.isfinite(r)
    if ok0.sum() < 30 or np.nanstd(r) < 1e-9:
        return None
    for k in LAGS:
        dmid = mid[t + k] - mid[t] if k > 0 else mid[t] - mid[t - 1]
        ok = ok0 & np.isfinite(dmid)
        x, y = r[ok], dmid[ok]
        if len(x) < 30 or x.std() < 1e-12:
            res[k] = np.nan
            continue
        res[k] = float(np.cov(x, y, ddof=1)[0, 1] / np.var(x, ddof=1))
    return res


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--hf", default="data/hf")
    ap.add_argument("--asset", default="BTC")
    args = ap.parse_args()

    joint = build_joint_series(Path(args.hf), args.asset)
    if not joint:
        sys.exit("no joint series -- check paths / asset")

    gam = [g for g in (per_market_gammas(m, s) for _, m, s in joint)
           if g is not None]
    df = pd.DataFrame(gam)

    print(f"\n=== spot -> mid predictive slope gamma_k "
          f"({len(df)} markets, clustered t) ===")
    print("k=0 is contemporaneous (sanity: should be strongly positive).")
    print("k>=1 positive & significant = the book lags spot by >= k seconds.")
    rows = []
    for k in LAGS:
        b = df[k].dropna()
        t = b.mean() / (b.std(ddof=1) / np.sqrt(len(b)))
        rows.append(dict(lag_s=k, mean_gamma=b.mean(), t=t, n=len(b)))
    print(pd.DataFrame(rows).to_string(
        index=False, float_format=lambda x: f"{x:+.3f}"))

    print("\nInterpretation: gamma_k is 'cents of Up-mid move per 1.0 of "
          "spot log-return still to come at lag k'. Economic value of the "
          "window ~ gamma_k x typical 1s |spot return| x how often you can "
          "capture it, minus taker fee (~1.7c) and spread. If gamma decays "
          "to ~0 by k=1-2s, the race is already won by faster players.")


if __name__ == "__main__":
    main()
