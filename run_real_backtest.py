"""Experiment 2: real Polymarket data (run on YOUR machine -- needs internet
access to gamma-api / data-api / clob.polymarket.com; no API keys required).

Pipeline:
  1. discover resolved 5-minute BTC/ETH up-or-down markets (Gamma)
  2. pull the full trade tape per market (Data API -- free tick data)
  3. rebuild 1-second YES price paths + estimate the effective spread
  4. run the IDENTICAL grid the synthetic experiment ran
  5. compare EV against the martingale null:
        real EV > synthetic EV  by a margin bigger than costs
        => genuine mean-reversion edge. Otherwise: no edge.

Usage:
  python scripts/run_real_backtest.py --keyword "Bitcoin Up or Down" \
      --max-markets 500 --out output/real
"""

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import numpy as np
import pandas as pd

from polyvol.data.polymarket_api import (
    find_short_duration_crypto_markets, fetch_trades, fetch_fee_params)
from polyvol.reconstruct import (
    yes_price_series, estimate_half_spread, paths_matrix)
from polyvol.strategy import Params
from polyvol.backtest import run_grid, summarize


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--keyword", default="Bitcoin Up or Down")
    ap.add_argument("--max-markets", type=int, default=500)
    ap.add_argument("--out", default="output/real")
    args = ap.parse_args()
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)

    print("Discovering markets via Gamma...")
    mkts = find_short_duration_crypto_markets(keyword=args.keyword)
    if mkts.empty:
        sys.exit("No markets matched. Check the keyword / series slug against "
                 "the Polymarket UI (open a 5-min market and copy its title).")
    mkts = mkts.head(args.max_markets)
    mkts.to_parquet(out / "markets.parquet")
    print(f"  {len(mkts)} resolved 5-min markets")

    # Verify the live fee schedule on one market -- do NOT trust hardcoded fees
    try:
        info = fetch_fee_params(mkts.iloc[0].condition_id)
        print(f"  fee params sample: {info.get('fd', info)}")
    except Exception as e:  # noqa: BLE001
        print(f"  (fee param fetch failed: {e})")

    series, outcomes, spreads = [], [], []
    for _, m in mkts.iterrows():
        try:
            tr = fetch_trades(m.condition_id)
        except Exception as e:  # noqa: BLE001
            print(f"  skip {m.slug}: {e}")
            continue
        if tr.empty or m.outcome_yes is None:
            continue
        series.append(yes_price_series(tr, m.start_ts, m.end_ts))
        outcomes.append(int(round(m.outcome_yes)))
        spreads.append(estimate_half_spread(tr))
        tr.to_parquet(out / f"trades_{m.condition_id[:12]}.parquet")

    print(f"Reconstructed {len(series)} paths; "
          f"median effective half-spread ~ {np.median(spreads)*100:.1f}c")

    prices = paths_matrix(series)
    outcomes = np.array(outcomes)

    grid = dict(entry=[0.30, 0.35, 0.40, 0.45], target=[0.02, 0.05, 0.10])
    for mode, hs in [("taker", float(np.median(spreads))), ("maker", 0.0)]:
        base = Params(mode=mode, half_spread=hs)
        trades = run_grid(prices, outcomes, base, grid)
        summ = summarize(trades, len(series))
        print(f"\n=== REAL DATA / {mode.upper()} ===")
        print(summ.to_string(index=False))
        summ.to_csv(out / f"real_grid_{mode}.csv", index=False)
        trades.to_parquet(out / f"real_trades_{mode}.parquet")

    print("\nCompare ev_per_trade against output/grid_summary_*.csv from the "
          "synthetic run. The edge, if any, is the difference.")


if __name__ == "__main__":
    main()
