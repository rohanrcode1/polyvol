"""Experiment 2 (v2): real Polymarket data via DETERMINISTIC slug discovery.

5-minute up/down market slugs are computable, not searchable:

    btc-updown-5m-{window_start_unix}    (window_start divisible by 300)
    eth-updown-5m-{window_start_unix}

so we generate the slugs for a recent time range and hit /events?slug= for
each. 288 windows per asset per day.

Usage (run on your machine):
  python scripts/run_real_backtest.py --assets btc eth --days 2 \
      --out output/real

Notes:
  * Pull RECENT days -- the Data API's trade retention for these
    high-churn markets is limited.
  * Markets/trades are cached in --out; re-runs skip fetched data.
  * Outcome index 0 = "Up" (our engine's YES side).
"""

import argparse
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import numpy as np
import pandas as pd
import requests

from polyvol.api.polymarket_api import (
    fetch_updown_markets, fetch_trades, fetch_fee_params)
from polyvol.reconstruct import (
    yes_price_series, estimate_half_spread, paths_matrix)
from polyvol.strategy import Params
from polyvol.backtest import run_grid, summarize


def save_table(df: pd.DataFrame, path: Path):
    try:
        df.to_parquet(path)
    except (ImportError, ValueError):
        csv_path = path.with_suffix(".csv")
        df.to_csv(csv_path, index=False)


def load_table(path: Path) -> pd.DataFrame | None:
    if path.exists():
        return pd.read_parquet(path)
    csv_path = path.with_suffix(".csv")
    if csv_path.exists():
        return pd.read_csv(csv_path)
    return None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--assets", nargs="+", default=["btc"],
                    choices=["btc", "eth", "sol", "xrp"])
    ap.add_argument("--interval", default="5m",
                    choices=["5m", "15m", "1h"])
    ap.add_argument("--days", type=float, default=2.0)
    ap.add_argument("--max-markets", type=int, default=1000)
    ap.add_argument("--out", default="output/real")
    args = ap.parse_args()
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)

    # ---------------- discovery (cached) ------------------------------
    mkts = load_table(out / "markets.parquet")
    if mkts is None or mkts.empty:
        print(f"Discovering {args.interval} windows for {args.assets} over "
              f"the last {args.days} day(s) via deterministic slugs...")
        mkts = fetch_updown_markets(assets=tuple(args.assets),
                                    interval=args.interval,
                                    days_back=args.days)
        if mkts.empty:
            sys.exit("No markets found. Sanity-check one slug in a browser: "
                     "https://gamma-api.polymarket.com/events?slug="
                     "btc-updown-5m-<recent unix ts divisible by 300>")
        save_table(mkts, out / "markets.parquet")
    # only resolved markets with a definite outcome
    mkts = mkts[mkts.outcome_up.isin([0.0, 1.0])].head(args.max_markets)
    print(f"{len(mkts)} resolved windows "
          f"(Up won {mkts.outcome_up.mean():.1%} -- should be near 50%)")

    # ---------------- verify live fee params on one market ------------
    try:
        info = fetch_fee_params(mkts.iloc[0].condition_id)
        print(f"fee params sample: "
              f"{ {k: info[k] for k in info if 'fee' in k.lower()} or info.get('fd', 'n/a') }")
    except Exception as e:  # noqa: BLE001
        print(f"(fee param fetch failed: {e})")

    # ---------------- trade tapes (cached per market) ------------------
    sess = requests.Session()
    series, outcomes, spreads, n_rows = [], [], [], 0
    t0 = time.time()
    for k, (_, m) in enumerate(mkts.iterrows()):
        cache = out / f"trades_{m.condition_id[:12]}.parquet"
        tr = load_table(cache)
        if tr is None:
            tr = fetch_trades(m.condition_id, sess=sess)
            if not tr.empty:
                save_table(tr, cache)
        if tr is None or tr.empty:
            continue
        if "ts" in tr and not pd.api.types.is_datetime64_any_dtype(tr["ts"]):
            tr["ts"] = pd.to_datetime(tr["ts"], utc=True)
        series.append(yes_price_series(tr, m.window_start, m.window_end))
        outcomes.append(int(round(m.outcome_up)))
        spreads.append(estimate_half_spread(tr))
        n_rows += len(tr)
        if k and k % 25 == 0:
            print(f"  {k}/{len(mkts)} markets, {n_rows:,} trade rows, "
                  f"{time.time()-t0:.0f}s")

    if not series:
        sys.exit("No trade tapes reconstructed. Likely cause: the Data API "
                 "no longer retains trades for these windows -- reduce "
                 "--days so you only request recent markets.")

    median_spread = float(np.median(spreads))
    print(f"\nReconstructed {len(series)} paths from {n_rows:,} trade rows; "
          f"median effective half-spread ~ {median_spread*100:.2f}c")

    prices = paths_matrix(series)
    outcomes = np.array(outcomes)

    # ---------------- identical grid to the synthetic run -------------
    grid = dict(entry=[0.30, 0.35, 0.40, 0.45], target=[0.02, 0.05, 0.10])
    for mode, hs in [("taker", median_spread), ("maker", 0.0)]:
        base = Params(mode=mode, half_spread=hs)
        trades = run_grid(prices, outcomes, base, grid)
        summ = summarize(trades, len(series))
        print(f"\n=== REAL DATA / {mode.upper()} ===")
        print(summ.to_string(index=False))
        summ.to_csv(out / f"real_grid_{mode}.csv", index=False)
        save_table(trades, out / f"real_trades_{mode}.parquet")

    print("\nNext: compare ev_per_trade against output/grid_summary_*.csv "
          "from the synthetic run (after re-calibrating sigma to these "
          "paths). The edge, if any, is the difference.")


if __name__ == "__main__":
    main()
