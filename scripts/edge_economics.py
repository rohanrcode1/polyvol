"""Convert the two statistical signals into cents-after-cost.

Both regressions found structure the martingale null can't produce:
  A) mean reversion in BBO mids, concentrated near 50c late in the window
  B) pending book adjustment ~1+ seconds after a spot move

Neither is money until it survives real asks, real bids, real sizes, and the
fee curve -- which peaks at exactly 50c, i.e. exactly where signal A lives.
This script runs both as honest taker backtests on the BBO table.

  fade     buy the side whose price just dropped >= D cents in 10s (near
           50c, late window), at the REAL ask; exit at the REAL bid after
           HOLD seconds (or resolution payoff if the window ends first);
           taker fee on both legs.

  spotmom  when the 1-second spot return exceeds a threshold, buy the
           direction side at the REAL ask one second LATER (honest reaction
           latency); exit at the real bid after HOLD seconds; fees both legs.

Inference is clustered by market. Results split into first-half / second-
half of the sample by date as a crude walk-forward check.

Remaining optimism even here: 1s resolution (bots eat good quotes in
milliseconds), top-of-book only, and possible collector clock skew between
the spot and book feeds (spotmom especially). Positive numbers here justify
live paper-capture with your own single-clock recorder -- not live money.

Usage:
  python scripts/edge_economics.py fade    --bbo data/hf/bbo_5m.parquet
  python scripts/edge_economics.py spotmom --hf data/hf --asset BTC
"""

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import numpy as np
import pandas as pd

from polyvol import fees as _fees

FEE_RATE = _fees.CRYPTO_FEE_RATE


def taker_fee_per_share(p):
    return _fees.taker_fee_per_share(p, FEE_RATE)

HORIZON = 300
MIN_SHARES = 20.0


# ------------------------------------------------------------------ common
def _clustered(trades: pd.DataFrame, keys):
    def _agg(g):
        per_mkt = g.groupby("market_id").pnl.mean()
        n_m = len(per_mkt)
        t = per_mkt.mean() / (per_mkt.std(ddof=1) / np.sqrt(n_m)) \
            if n_m > 2 and per_mkt.std(ddof=1) > 0 else np.nan
        return pd.Series(dict(n_trades=len(g), n_markets=n_m,
                              win_rate=(g.pnl > 0).mean(),
                              ev_cents=g.pnl.mean() * 100,
                              t_clustered=t))
    return trades.groupby(keys).apply(_agg, include_groups=False) \
        .reset_index()


def _load_bbo(bbo_path, asset=None):
    cols = ["market_id", "crypto", "resolution", "window_start", "sec",
            "up_bid", "up_ask", "up_bid_sz", "up_ask_sz"]
    bbo = pd.read_parquet(bbo_path, columns=cols)
    if asset:
        bbo = bbo[bbo.crypto == asset]
    out = {}
    for mid_id, g in bbo.groupby("market_id", sort=False):
        g = g[(g.sec >= 0) & (g.sec <= HORIZON)]
        gg = g.set_index("sec").reindex(range(HORIZON + 1)).ffill()
        if gg.up_ask.notna().sum() < 150:
            continue
        out[mid_id] = dict(
            bid=gg.up_bid.to_numpy(float), ask=gg.up_ask.to_numpy(float),
            bid_sz=gg.up_bid_sz.to_numpy(float),
            ask_sz=gg.up_ask_sz.to_numpy(float),
            res=int(g.resolution.iloc[0]),
            ws=int(g.window_start.iloc[0]))
    print(f"{len(out)} markets loaded")
    return out


def _exit_pnl(side, entry_px, i_exit, bid, ask, res):
    """Sell at the bid at i_exit if quotes exist; else resolution payoff."""
    if side == "UP":
        px = bid[i_exit]
        payoff = float(res)
    else:
        px = 1.0 - ask[i_exit]
        payoff = float(1 - res)
    if i_exit >= HORIZON or not np.isfinite(px):
        return payoff, 0.0
    return px, taker_fee_per_share(px)


# -------------------------------------------------------------------- fade
def run_fade(markets, drops=(0.03, 0.05, 0.08), hold=10, lookback=10,
             zone=0.15, tr_bands=((15, 120), (120, 285))):
    recs = []
    for mid_id, m in markets.items():
        bid, ask = m["bid"], m["ask"]
        mid = (bid + ask) / 2.0
        t_next = 0  # non-overlapping trades within a market
        for t in range(lookback + 15, HORIZON - 1):
            if t < t_next:
                continue
            tr = HORIZON - t
            if tr < 15:      # skip the terminal pin
                break
            if not np.isfinite(mid[t]) or not np.isfinite(mid[t - lookback]):
                continue
            if abs(mid[t] - 0.5) > zone:
                continue
            d = mid[t] - mid[t - lookback]
            for D in sorted(drops, reverse=True):
                if abs(d) < D:
                    continue
                if d < 0:   # UP dropped -> buy UP at ask
                    side, epx, esz = "UP", ask[t], m["ask_sz"][t]
                else:       # UP rose -> DOWN dropped -> buy DOWN
                    side, epx = "DOWN", 1.0 - bid[t]
                    esz = m["bid_sz"][t]
                if not np.isfinite(epx) or esz < MIN_SHARES or epx <= 0:
                    continue
                i_x = min(t + hold, HORIZON)
                xpx, xfee = _exit_pnl(side, epx, i_x, bid, ask, m["res"])
                pnl = xpx - epx - taker_fee_per_share(epx) - xfee
                band = next((f"tr {a}-{b}s" for a, b in tr_bands
                             if a <= tr < b), None)
                if band is None:
                    break
                recs.append(dict(market_id=mid_id, drop=D, band=band,
                                 side=side, pnl=pnl))
                t_next = t + hold
                break   # largest-threshold trade only, once per trigger
    df = pd.DataFrame(recs)
    if df.empty:
        print("no fade trades triggered")
        return df
    print("\n=== FADE: buy the dipped side at the real ask, exit at the "
          "real bid after hold ===")
    print(_clustered(df, ["drop", "band"]).to_string(
        index=False, float_format=lambda x: f"{x:+.3f}"))
    return df


# ----------------------------------------------------------------- spotmom
def _joint_spot(hf_dir: Path, asset: str, markets):
    import duckdb
    con = duckdb.connect()
    tick_glob = str(hf_dir / "data" / "ticks" / f"crypto={asset}" /
                    "timeframe=5-minute" / "*.parquet")
    ws_map = pd.DataFrame([(k, v["ws"]) for k, v in markets.items()],
                          columns=["market_id", "window_start"])
    con.register("wsmap", ws_map)
    spot = con.sql(f"""
        SELECT t.market_id,
               CAST(t.timestamp_ms / 1000 AS BIGINT) - w.window_start AS sec,
               last(t.spot_price_usdt ORDER BY t.timestamp_ms) AS spot
        FROM read_parquet('{tick_glob}') t
        JOIN wsmap w USING (market_id)
        WHERE t.spot_price_usdt > 0
        GROUP BY 1, 2
    """).df()
    for mid_id, g in spot.groupby("market_id", sort=False):
        if mid_id in markets:
            s = g.set_index("sec")["spot"] \
                .reindex(range(HORIZON + 1)).ffill()
            markets[mid_id]["spot"] = s.to_numpy(float)
    return {k: v for k, v in markets.items() if "spot" in v
            and np.isfinite(v["spot"]).sum() > 100}


def run_spotmom(markets, thresholds_bps=(2, 4, 8), hold=10, react=1):
    recs = []
    for mid_id, m in markets.items():
        bid, ask, spot = m["bid"], m["ask"], m["spot"]
        with np.errstate(all="ignore"):
            r = np.diff(np.log(spot), prepend=np.nan) * 1e4   # bps
        t_next = 0
        for t in range(16, HORIZON - react - 1):
            if t < t_next or not np.isfinite(r[t]):
                continue
            for th in sorted(thresholds_bps, reverse=True):
                if abs(r[t]) < th:
                    continue
                ta = t + react           # honest 1s reaction latency
                if r[t] > 0:             # spot up -> buy UP at ask
                    side, epx, esz = "UP", ask[ta], m["ask_sz"][ta]
                else:
                    side, epx = "DOWN", 1.0 - bid[ta]
                    esz = m["bid_sz"][ta]
                if not np.isfinite(epx) or esz < MIN_SHARES or epx <= 0.02 \
                        or epx >= 0.98:
                    break
                i_x = min(ta + hold, HORIZON)
                xpx, xfee = _exit_pnl(side, epx, i_x, bid, ask, m["res"])
                pnl = xpx - epx - taker_fee_per_share(epx) - xfee
                recs.append(dict(market_id=mid_id, thresh_bps=th,
                                 half=("H1" if m["ws"] < np.median(
                                     [x["ws"] for x in markets.values()])
                                     else "H2"),
                                 side=side, pnl=pnl))
                t_next = ta + hold
                break
    df = pd.DataFrame(recs)
    if df.empty:
        print("no spotmom trades triggered")
        return df
    print("\n=== SPOTMOM: buy direction side at real ask 1s AFTER the spot "
          "move, exit at real bid ===")
    print(_clustered(df, ["thresh_bps", "half"]).to_string(
        index=False, float_format=lambda x: f"{x:+.3f}"))
    print("\nH1/H2 = first/second half of sample by date (walk-forward "
          "check: an edge that only exists in H1 is regime noise).")
    return df


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("cmd", choices=["fade", "spotmom"])
    ap.add_argument("--bbo", default="data/hf/bbo_5m.parquet")
    ap.add_argument("--hf", default="data/hf")
    ap.add_argument("--asset", default="BTC")
    ap.add_argument("--hold", type=int, default=10)
    ap.add_argument("--fee-rate", type=float, default=_fees.CRYPTO_FEE_RATE,
                    help="0.07 = crypto taker. 0 = maker-fill approximation "
                         "(optimistic: ignores queue + adverse selection)")
    args = ap.parse_args()
    global FEE_RATE
    FEE_RATE = args.fee_rate

    if args.cmd == "fade":
        mkts = _load_bbo(args.bbo)
        df = run_fade(mkts, hold=args.hold)
    else:
        mkts = _load_bbo(Path(args.hf) / "bbo_5m.parquet", asset=args.asset)
        mkts = _joint_spot(Path(args.hf), args.asset, mkts)
        print(f"{len(mkts)} markets with joint spot")
        df = run_spotmom(mkts, hold=args.hold)

    if not df.empty:
        out = Path("output")
        out.mkdir(exist_ok=True)
        df.to_parquet(out / f"edge_{args.cmd}_trades.parquet")
        print(f"\nsaved per-trade records to output/edge_{args.cmd}"
              f"_trades.parquet")


if __name__ == "__main__":
    main()
