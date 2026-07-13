"""Ingest the aliplayer1/polymarket-crypto-updown HuggingFace dataset.

DO NOT use `datasets.load_dataset()` on this repo -- it is ~29 GB / 9.5B rows
and load_dataset pulls everything. The data is Hive-partitioned by
crypto/timeframe, so we grab ONLY the partitions we need.

Two modes:

  download  -- snapshot_download with allow_patterns (recommended: local
               copy, fast repeated backtests). BTC+ETH 5-minute ticks +
               orderbook + markets is a small fraction of the full 29 GB.
  probe     -- remote DuckDB queries over hf:// to check date coverage and
               row counts BEFORE downloading anything.

Requires:  pip install huggingface_hub duckdb
(no HF account/token needed for public datasets)

Data traps handled here:
  * end_ts in `markets` is Gamma's endDate (~+24h), NOT the window close.
    True window = slug timestamp .. +300s. We derive window_start from the
    slug and fall back to flooring start_ts to the 300s grid.
  * resolution == -1 means unknown -> filtered out.
  * fee_rate_bps == -1 means unknown -> fetch live params from the CLOB for
    anything you plan to trade.

Usage:
  python scripts/hf_ingest.py probe
  python scripts/hf_ingest.py download --assets BTC ETH --out data/hf
  python scripts/hf_ingest.py build   --assets BTC ETH --out data/hf
"""

import argparse
import re
import sys
from pathlib import Path

REPO = "aliplayer1/polymarket-crypto-updown"
TF = "5-minute"


def probe():
    import duckdb
    con = duckdb.connect()
    con.sql("INSTALL httpfs; LOAD httpfs;")
    base = f"hf://datasets/{REPO}/data"
    print("markets coverage by asset/timeframe (resolved only):")
    con.sql(f"""
        SELECT crypto, timeframe, count(*) AS n_markets,
               to_timestamp(min(start_ts)) AS first,
               to_timestamp(max(start_ts)) AS last
        FROM '{base}/markets.parquet'
        WHERE resolution IN (0, 1)
        GROUP BY 1, 2 ORDER BY 1, 2
    """).show()
    print("orderbook BBO rows for BTC 5-minute (may take a minute):")
    con.sql(f"""
        SELECT count(*) AS rows,
               to_timestamp(min(ts_ms) / 1000) AS first,
               to_timestamp(max(ts_ms) / 1000) AS last
        FROM '{base}/orderbook/crypto=BTC/timeframe={TF}/*.parquet'
    """).show()


def download(assets, out: Path):
    from huggingface_hub import snapshot_download
    patterns = ["data/markets.parquet"]
    for a in assets:
        patterns += [
            f"data/ticks/crypto={a}/timeframe={TF}/*",
            f"data/orderbook/crypto={a}/timeframe={TF}/*",
        ]
    path = snapshot_download(repo_id=REPO, repo_type="dataset",
                             allow_patterns=patterns,
                             local_dir=str(out))
    print(f"downloaded selected partitions to {path}")


def build(assets, out: Path):
    """Consolidate raw partitions into two backtest-ready tables:

    markets_5m.parquet   one row per resolved window, true window bounds
    bbo_5m.parquet       1-second UP-side best bid/ask per market
                         (Down book folded in via complement: a Down quote
                          at q is an Up quote at 1-q with bid/ask swapped)
    """
    import duckdb
    con = duckdb.connect()
    d = out / "data"
    asset_list = ",".join(f"'{a}'" for a in assets)

    con.sql(f"""
        CREATE TABLE markets AS
        SELECT *,
            COALESCE(
                TRY_CAST(regexp_extract(slug, '(\\d+)$', 1) AS BIGINT),
                start_ts - (start_ts % 300)
            ) AS window_start,
            COALESCE(
                TRY_CAST(regexp_extract(slug, '(\\d+)$', 1) AS BIGINT),
                start_ts - (start_ts % 300)
            ) + 300 AS window_close
        FROM '{d}/markets.parquet'
        WHERE resolution IN (0, 1) AND timeframe = '{TF}'
          AND crypto IN ({asset_list})
    """)
    n = con.sql("SELECT count(*) FROM markets").fetchone()[0]
    con.sql(f"COPY markets TO '{out}/markets_5m.parquet' (FORMAT PARQUET)")
    print(f"markets_5m.parquet: {n} resolved windows")

    # fold both tokens' BBO into UP terms, snap to a 1s grid per market,
    # forward-fill within the window
    con.sql(f"""
        CREATE TABLE bbo AS
        WITH raw AS (
            SELECT o.market_id, o.ts_ms,
                CASE WHEN o.outcome = 'Up' THEN o.best_bid
                     ELSE 1.0 - o.best_ask END AS up_bid,
                CASE WHEN o.outcome = 'Up' THEN o.best_ask
                     ELSE 1.0 - o.best_bid END AS up_ask,
                CASE WHEN o.outcome = 'Up' THEN o.best_bid_size
                     ELSE o.best_ask_size END AS up_bid_sz,
                CASE WHEN o.outcome = 'Up' THEN o.best_ask_size
                     ELSE o.best_bid_size END AS up_ask_sz,
                m.window_start, m.window_close, m.resolution, m.crypto
            FROM read_parquet('{d}/orderbook/*/*/*.parquet',
                              hive_partitioning = true) o
            JOIN markets m USING (market_id)
            WHERE o.ts_ms / 1000 BETWEEN m.window_start AND m.window_close
        )
        SELECT market_id, crypto, resolution, window_start,
               CAST(ts_ms / 1000 AS BIGINT) - window_start AS sec,
               last(up_bid  ORDER BY ts_ms) AS up_bid,
               last(up_ask  ORDER BY ts_ms) AS up_ask,
               last(up_bid_sz ORDER BY ts_ms) AS up_bid_sz,
               last(up_ask_sz ORDER BY ts_ms) AS up_ask_sz
        FROM raw
        GROUP BY 1, 2, 3, 4, 5
    """)
    n = con.sql("SELECT count(*) FROM bbo").fetchone()[0]
    nm = con.sql("SELECT count(DISTINCT market_id) FROM bbo").fetchone()[0]
    con.sql(f"COPY bbo TO '{out}/bbo_5m.parquet' (FORMAT PARQUET)")
    print(f"bbo_5m.parquet: {n:,} second-level BBO rows across {nm} markets")
    print("NOTE: BBO coverage starts when the collector's WebSocket capture "
          "began -- older markets have ticks but no book. Check the probe "
          "dates before assuming full-history coverage.")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("cmd", choices=["probe", "download", "build"])
    ap.add_argument("--assets", nargs="+", default=["BTC", "ETH"])
    ap.add_argument("--out", default="data/hf")
    args = ap.parse_args()
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    if args.cmd == "probe":
        probe()
    elif args.cmd == "download":
        download(args.assets, out)
    else:
        build(args.assets, out)


if __name__ == "__main__":
    main()
