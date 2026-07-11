"""Polymarket data layer (all READ endpoints are free, no auth, no API key).

Endpoints used
--------------
Gamma  https://gamma-api.polymarket.com   market/event discovery, metadata
Data   https://data-api.polymarket.com    executed trades (tick-level!) 
CLOB   https://clob.polymarket.com        price history, live order book

Data reality for 5-minute markets
---------------------------------
* /prices-history (CLOB) has ~1-minute minimum fidelity -> only ~5 points per
  5-minute market. Useless for this strategy. Do not rely on it.
* /trades (Data API) returns EVERY executed fill with timestamp, price, size,
  side, outcome. This is your free tick data and the backbone of the backtest.
* Historical ORDER BOOK DEPTH is NOT available free. Options:
    1. Record it yourself going forward (see BookRecorder below) - free.
    2. Tardis.dev - captures Polymarket CLOB book snapshots; free samples for
       the first day of each month, paid for continuous history.
    3. Reconstruct fills on-chain from CTF Exchange `OrderFilled` logs on
       Polygon (Envio HyperSync / Goldsky / Dune) - gives trades, not resting
       depth.
  Until you have book data, the backtest brackets reality between the taker
  (pessimistic) and maker (optimistic) execution modes.

Run this module on your own machine; this sandbox has no route to
polymarket.com domains.
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

UA = {"User-Agent": "polyvol-research/0.1"}


# ---------------------------------------------------------------- discovery
def find_short_duration_crypto_markets(
    keyword: str = "Bitcoin Up or Down",
    max_pages: int = 40,
    page_size: int = 100,
    closed: bool = True,
) -> pd.DataFrame:
    """Discover resolved short-duration crypto up/down markets via Gamma.

    Filters by question keyword, then keeps markets whose open->close window
    is <= 6 minutes. Verify the exact series slug in the Polymarket UI (the
    recurring series page URL) and tighten this filter accordingly.
    """
    rows = []
    for page in range(max_pages):
        r = requests.get(
            f"{GAMMA}/markets",
            params=dict(closed=str(closed).lower(), limit=page_size,
                        offset=page * page_size, order="endDate",
                        ascending="false"),
            headers=UA, timeout=30,
        )
        r.raise_for_status()
        batch = r.json()
        if not batch:
            break
        for m in batch:
            q = m.get("question", "")
            if keyword.lower() not in q.lower():
                continue
            rows.append(_extract_market_row(m))
        time.sleep(0.2)  # be polite
    df = pd.DataFrame(rows)
    if df.empty:
        return df
    dur = (df.end_ts - df.start_ts).dt.total_seconds()
    return df[dur.between(60, 360)].reset_index(drop=True)


def _extract_market_row(m: dict) -> dict:
    token_ids = m.get("clobTokenIds")
    if isinstance(token_ids, str):
        token_ids = json.loads(token_ids)
    outcomes = m.get("outcomes")
    if isinstance(outcomes, str):
        outcomes = json.loads(outcomes)
    prices = m.get("outcomePrices")
    if isinstance(prices, str):
        prices = json.loads(prices)
    return dict(
        condition_id=m.get("conditionId"),
        question=m.get("question"),
        slug=m.get("slug"),
        yes_token=token_ids[0] if token_ids else None,
        no_token=token_ids[1] if token_ids and len(token_ids) > 1 else None,
        start_ts=pd.to_datetime(m.get("startDate") or m.get("createdAt"),
                                utc=True),
        end_ts=pd.to_datetime(m.get("endDate"), utc=True),
        outcome_yes=(float(prices[0]) if prices else None),  # 1.0 / 0.0 once resolved
        fees_enabled=m.get("feesEnabled"),
        volume=m.get("volumeNum") or m.get("volume"),
    )


# ------------------------------------------------------------------ trades
def fetch_trades(condition_id: str, page_size: int = 500,
                 max_pages: int = 200) -> pd.DataFrame:
    """All executed fills for one market from the Data API (free tick data).

    Columns include: timestamp, price, size, side (BUY/SELL from taker's
    perspective), outcome (Yes/No), proxyWallet, transactionHash.
    """
    out = []
    for page in range(max_pages):
        r = requests.get(
            f"{DATA}/trades",
            params=dict(market=condition_id, limit=page_size,
                        offset=page * page_size, takerOnly="true"),
            headers=UA, timeout=30,
        )
        r.raise_for_status()
        batch = r.json()
        if not batch:
            break
        out.extend(batch)
        if len(batch) < page_size:
            break
        time.sleep(0.15)
    df = pd.DataFrame(out)
    if df.empty:
        return df
    df["ts"] = pd.to_datetime(df["timestamp"], unit="s", utc=True)
    df["price"] = df["price"].astype(float)
    df["size"] = df["size"].astype(float)
    return df.sort_values("ts").reset_index(drop=True)


def fetch_fee_params(condition_id: str) -> dict:
    """Live per-market fee params from the CLOB (rate / exponent / takerOnly)."""
    r = requests.get(f"{CLOB}/markets/{condition_id}", headers=UA, timeout=30)
    r.raise_for_status()
    return r.json()


# -------------------------------------------------------------- live book
class BookRecorder:
    """Poll the CLOB order book and append snapshots to parquet.

    Historical depth is not free, so start recording NOW while you backtest
    on trade data. A week of recordings of every 5-min BTC/ETH market gives
    you ~2,000 markets of real depth for the execution simulator.

    For production-grade capture use the CLOB WebSocket `market` channel
    (book + price_change events) instead of REST polling.
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
                rows.append(dict(
                    ts=t0,
                    bids=json.dumps(b.get("bids", [])),
                    asks=json.dumps(b.get("asks", [])),
                ))
            except requests.RequestException:
                pass
            time.sleep(max(0.0, interval - (time.time() - t0)))
        df = pd.DataFrame(rows)
        path = self.out_dir / f"{token_id[:16]}_{int(time.time())}.parquet"
        df.to_parquet(path)
        return path
