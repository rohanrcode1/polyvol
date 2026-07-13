"""Polymarket data layer v2 (all READ endpoints free, no auth).

KEY FIX vs v1: 5-minute up/down markets are NOT discoverable by paging
/markets ordered by endDate -- descending order starts at far-future markets
("...by Dec 31, 2027") and never reaches recently-closed 5-min windows.

Instead, slugs are DETERMINISTIC:

    {asset}-updown-{interval}-{window_start_unix}

where window_start_unix is aligned to the interval (divisible by 300 for 5m,
900 for 15m). So discovery = generate timestamps, GET /events?slug=... each.
288 slugs per asset per day for 5m markets. No scanning, no cursors.

Outcome labels on these markets are ["Up", "Down"] (NOT Yes/No).
Index 0 = Up. We treat Up as the "YES" side everywhere downstream.
"""

from __future__ import annotations

import json
import time
from pathlib import Path

import pandas as pd
import requests

GAMMA = "https://gamma-api.polymarket.com"
DATA = "https://data-api.polymarket.com"
CLOB = "https://clob.polymarket.com"

UA = {"User-Agent": "polyvol-research/0.2"}

INTERVAL_SECONDS = {"5m": 300, "15m": 900, "1h": 3600, "4h": 14400}


# ---------------------------------------------------------------- discovery
def updown_slugs(asset: str = "btc", interval: str = "5m",
                 days_back: float = 2.0, end_unix: int | None = None):
    """Deterministic slugs for every window in the range (oldest first)."""
    step = INTERVAL_SECONDS[interval]
    now = int(time.time()) if end_unix is None else int(end_unix)
    end_aligned = now - (now % step)          # exclude the live window
    start = end_aligned - int(days_back * 86400)
    start -= start % step
    return [(ts, f"{asset}-updown-{interval}-{ts}")
            for ts in range(start, end_aligned, step)]


def fetch_updown_markets(
    assets=("btc",),
    interval: str = "5m",
    days_back: float = 2.0,
    end_unix: int | None = None,
    sleep_s: float = 0.05,
    verbose: bool = True,
) -> pd.DataFrame:
    """Metadata for every resolved up/down window via direct slug lookups.

    ~288 requests / asset / day for 5m => a couple of minutes for a two-day,
    two-asset pull. Safe to re-run. NOTE: the Data API only retains trades
    for these markets for a limited lookback; pull recent windows.
    """
    step = INTERVAL_SECONDS[interval]
    sess = requests.Session()
    rows, misses = [], 0
    for asset in assets:
        slugs = updown_slugs(asset, interval, days_back, end_unix)
        for i, (ts, slug) in enumerate(slugs):
            try:
                r = sess.get(f"{GAMMA}/events", params={"slug": slug},
                             headers=UA, timeout=30)
                if r.status_code != 200:
                    misses += 1
                    continue
                evs = r.json()
                if not evs or not evs[0].get("markets"):
                    misses += 1
                    continue
                m = evs[0]["markets"][0]
                row = _extract_market_row(m)
                # authoritative timing from the slug, not Gamma createdAt
                row["window_start"] = pd.to_datetime(ts, unit="s", utc=True)
                row["window_end"] = pd.to_datetime(ts + step, unit="s",
                                                   utc=True)
                row["asset"] = asset
                row["gamma_slug"] = slug
                rows.append(row)
            except requests.RequestException as e:
                if verbose:
                    print(f"  {slug}: {e}")
            if verbose and i and i % 50 == 0:
                print(f"  {asset} {interval}: {i}/{len(slugs)} windows, "
                      f"{len(rows)} found, {misses} missing")
            time.sleep(sleep_s)
    df = pd.DataFrame(rows)
    if df.empty:
        return df
    return (df.dropna(subset=["condition_id"])
              .drop_duplicates("condition_id")
              .sort_values("window_start")
              .reset_index(drop=True))


def _extract_market_row(m: dict) -> dict:
    def _j(x):
        return json.loads(x) if isinstance(x, str) else x

    token_ids = _j(m.get("clobTokenIds")) or []
    outcomes = _j(m.get("outcomes")) or []
    prices = _j(m.get("outcomePrices")) or []
    return dict(
        condition_id=m.get("conditionId"),
        question=m.get("question"),
        slug=m.get("slug"),
        outcome_labels=json.dumps(outcomes),          # e.g. ["Up","Down"]
        up_token=token_ids[0] if token_ids else None,
        down_token=token_ids[1] if len(token_ids) > 1 else None,
        # index 0 = Up. 1.0 => Up won, 0.0 => Down won (once resolved).
        outcome_up=(float(prices[0]) if prices else None),
        closed=m.get("closed"),
        fees_enabled=m.get("feesEnabled"),
        volume=m.get("volumeNum") or m.get("volume"),
    )


# ------------------------------------------------------------------ trades
def fetch_trades(condition_id: str, page_size: int = 500,
                 max_pages: int = 200,
                 sess: requests.Session | None = None) -> pd.DataFrame:
    """All executed fills for one market from the Data API."""
    sess = sess or requests.Session()
    out = []
    for page in range(max_pages):
        try:
            r = sess.get(
                f"{DATA}/trades",
                params=dict(market=condition_id, limit=page_size,
                            offset=page * page_size, takerOnly="true"),
                headers=UA, timeout=30,
            )
            if r.status_code >= 400:
                break
            batch = r.json()
        except (requests.RequestException, ValueError):
            break
        if not batch:
            break
        out.extend(batch)
        if len(batch) < page_size:
            break
        time.sleep(0.1)
    df = pd.DataFrame(out)
    if df.empty:
        return df
    df["ts"] = pd.to_datetime(df["timestamp"], unit="s", utc=True)
    df["price"] = df["price"].astype(float)
    df["size"] = df["size"].astype(float)
    return df.sort_values("ts").reset_index(drop=True)


def fetch_fee_params(condition_id: str) -> dict:
    r = requests.get(f"{CLOB}/markets/{condition_id}", headers=UA, timeout=30)
    r.raise_for_status()
    return r.json()


# -------------------------------------------------------------- live book
class BookRecorder:
    """Poll the CLOB order book and append snapshots to parquet.

    NOTE: before building weeks of recording infrastructure, check the
    HuggingFace dataset `aliplayer1/polymarket-crypto-updown` -- it already
    contains markets/prices/ticks/spot/orderbook tables for crypto up-down
    markets across 5m/15m/1h/4h timeframes, refreshed automatically.
    """

    def __init__(self, out_dir: str = "book_snapshots"):
        self.out_dir = Path(out_dir)
        self.out_dir.mkdir(parents=True, exist_ok=True)

    def snapshot(self, token_id: str) -> dict:
        r = requests.get(f"{CLOB}/book", params=dict(token_id=token_id),
                         headers=UA, timeout=10)
        r.raise_for_status()
        return r.json()

    def record(self, token_id: str, seconds: int = 330, interval: float = 1.0):
        rows = []
        t_end = time.time() + seconds
        while time.time() < t_end:
            t0 = time.time()
            try:
                b = self.snapshot(token_id)
                rows.append(dict(ts=t0,
                                 bids=json.dumps(b.get("bids", [])),
                                 asks=json.dumps(b.get("asks", []))))
            except requests.RequestException:
                pass
            time.sleep(max(0.0, interval - (time.time() - t0)))
        df = pd.DataFrame(rows)
        path = self.out_dir / f"{token_id[:16]}_{int(time.time())}.parquet"
        df.to_parquet(path)
        return path
