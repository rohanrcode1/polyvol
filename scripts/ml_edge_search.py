"""ML edge search over the BBO data: the exhaustive version of the filter
hunt, done honestly.

What this is: a gradient-boosted model that searches the full joint feature
space (price level, time remaining, momentum at several horizons, volatility,
spread, book imbalance) for ANY market state where a taker trade has positive
expected value NET OF COSTS.

The two design decisions that keep it honest:

1. THE LABEL IS AN EXECUTABLE RETURN. Not "does the mid go up" -- we already
   know the mids revert (beta to -0.59) and that it's uncapturable. The label
   is: buy UP at the real ask now, sell at the real bid in HOLD seconds, pay
   taker fees on both legs. A symmetric DOWN trade is the mirror (evaluated
   via the bottom of the prediction distribution).

2. PURGED WALK-FORWARD VALIDATION. Markets are sorted by start time and split
   into sequential folds; the model trains only on strictly earlier markets.
   Never random shuffle -- overlapping windows leak the answer.

The verdict metric is the DECILE TABLE: take the model's most confident 10%
of opportunities OUT OF SAMPLE and report their realized net EV with
market-clustered t-stats. If even the model's best decile is negative after
costs, the conditional-edge hypothesis is closed at this data resolution.

Interpreting outcomes:
  * top-decile OOS EV <= 0 everywhere  -> no hidden taker edge at 1s
  * top-decile OOS EV > 0 in ONE fold  -> regime noise; ignore
  * top-decile OOS EV > 0 in ALL folds with clustered t > 3
        -> candidate signal; next step is your own sub-second capture,
           NOT live money (this data still has 1s resolution and possible
           collector clock skew)

Self-test: --selftest fabricates martingale BBO data; the top decile must
come back ~ -costs (i.e. the pipeline must NOT hallucinate an edge on data
that has none).

Usage:
  python scripts/ml_edge_search.py --bbo data/hf/bbo_5m.parquet
  python scripts/ml_edge_search.py --selftest
Optional: pip install lightgbm (falls back to sklearn HistGradientBoosting).
"""

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import numpy as np
import pandas as pd

from polyvol.fees import taker_fee_per_share

HORIZON = 300
STRIDE = 5          # sample every 5s to reduce overlap
HOLD = 15           # exit after 15s
FOLDS = 4


# ------------------------------------------------------------- features
def build_dataset(bbo_path: str) -> pd.DataFrame:
    cols = ["market_id", "sec", "up_bid", "up_ask", "up_bid_sz",
            "up_ask_sz", "window_start"]
    bbo = pd.read_parquet(bbo_path, columns=cols)
    rows = []
    for mid_id, g in bbo.groupby("market_id", sort=False):
        g = g[(g.sec >= 0) & (g.sec <= HORIZON)]
        gg = g.set_index("sec").reindex(range(HORIZON + 1)).ffill()
        bid = gg.up_bid.to_numpy(float)
        ask = gg.up_ask.to_numpy(float)
        bsz = gg.up_bid_sz.to_numpy(float)
        asz = gg.up_ask_sz.to_numpy(float)
        mid = (bid + ask) / 2.0
        if np.isfinite(mid).sum() < 150:
            continue
        dmid = np.diff(mid, prepend=np.nan)
        ws = int(g.window_start.iloc[0])
        for t in range(35, HORIZON - HOLD - 15, STRIDE):
            if not (np.isfinite(ask[t]) and np.isfinite(bid[t + HOLD])):
                continue
            m = mid[t]
            if not np.isfinite(m) or m <= 0.03 or m >= 0.97:
                continue
            v30 = np.nanstd(dmid[t - 30:t])
            # label: buy UP at ask now, sell at bid in HOLD s, fees both legs
            y = (bid[t + HOLD] - taker_fee_per_share(bid[t + HOLD])
                 - ask[t] - taker_fee_per_share(ask[t]))
            # exact DOWN mirror: buy DOWN at (1-bid) now, sell at (1-ask) later
            y_dn = (bid[t] - taker_fee_per_share(1 - bid[t])
                    - ask[t + HOLD]
                    - taker_fee_per_share(1 - ask[t + HOLD]))
            rows.append(dict(
                market_id=mid_id, window_start=ws, t=t, label=y,
                label_dn=y_dn,
                mid=m, dist50=abs(m - 0.5), time_rem=HORIZON - t,
                ret1=mid[t] - mid[t - 1], ret5=mid[t] - mid[t - 5],
                ret10=mid[t] - mid[t - 10], ret30=mid[t] - mid[t - 30],
                vol30=v30, spread=ask[t] - bid[t],
                imb=np.log((bsz[t] + 1) / (asz[t] + 1)),
                exit_spread_proxy=ask[t] - bid[t],
            ))
    df = pd.DataFrame(rows).replace([np.inf, -np.inf], np.nan).dropna()
    print(f"dataset: {len(df):,} samples from "
          f"{df.market_id.nunique():,} markets")
    return df


FEATURES = ["mid", "dist50", "time_rem", "ret1", "ret5", "ret10", "ret30",
            "vol30", "spread", "imb"]


# ---------------------------------------------------------------- model
def get_model():
    try:
        from lightgbm import LGBMRegressor
        return LGBMRegressor(n_estimators=400, num_leaves=63,
                             learning_rate=0.05, verbose=-1)
    except ImportError:
        from sklearn.ensemble import HistGradientBoostingRegressor
        return HistGradientBoostingRegressor(max_iter=400,
                                             learning_rate=0.05)


def clustered_t(g: pd.DataFrame) -> float:
    per = g.groupby("market_id").realized.mean()
    if len(per) < 3 or per.std(ddof=1) == 0:
        return np.nan
    return per.mean() / (per.std(ddof=1) / np.sqrt(len(per)))


def walk_forward(df: pd.DataFrame):
    mkts = (df[["market_id", "window_start"]].drop_duplicates()
            .sort_values("window_start").market_id.to_numpy())
    fold_of = {m: min(i * FOLDS // len(mkts), FOLDS - 1)
               for i, m in enumerate(mkts)}
    df = df.assign(fold=df.market_id.map(fold_of))

    all_rows = []
    for f in range(1, FOLDS):
        train = df[df.fold < f]
        test = df[df.fold == f].copy()
        if len(train) < 5000 or len(test) < 2000:
            continue
        model = get_model()
        model.fit(train[FEATURES], train.label)
        test["pred"] = model.predict(test[FEATURES])
        # top decile = model's best BUY-UP opportunities;
        # bottom decile = best BUY-DOWN opportunities (mirror trade:
        # pnl_down ~= -(up move) - costs, computed exactly below)
        q_hi = test.pred.quantile(0.9)
        q_lo = test.pred.quantile(0.1)
        top = test[test.pred >= q_hi].copy()
        top["realized"] = top.label
        bot = test[test.pred <= q_lo].copy()
        bot["realized"] = bot.label_dn   # exact DOWN-trade net pnl
        for name, g in [("buy-UP top decile", top),
                        ("buy-DOWN bottom decile", bot),
                        ("all test samples", test.assign(realized=test.label))]:
            all_rows.append(dict(
                fold=f, bucket=name, n=len(g),
                ev_cents=g.realized.mean() * 100,
                t_clustered=clustered_t(g),
                corr=np.corrcoef(test.pred, test.label)[0, 1]
                if name == "all test samples" else np.nan))
    res = pd.DataFrame(all_rows)
    print("\n=== OUT-OF-SAMPLE decile economics (net of spread + fees) ===")
    print(res.to_string(index=False, float_format=lambda x: f"{x:+.3f}"))
    print("\nRead: 'ev_cents' is realized net EV per share of the model's "
          "chosen trades on unseen future markets. Positive in every fold "
          "with t>3 = candidate. Anything else = no hidden taker edge at "
          "this resolution.")

    # feature importance on the last model (permutation, small sample)
    try:
        from sklearn.inspection import permutation_importance
        samp = test.sample(min(20000, len(test)), random_state=0)
        imp = permutation_importance(model, samp[FEATURES], samp.label,
                                     n_repeats=3, random_state=0)
        order = np.argsort(-imp.importances_mean)
        print("\nfeature importance (permutation):")
        for i in order:
            print(f"  {FEATURES[i]:<10} {imp.importances_mean[i]:+.5f}")
    except Exception as e:  # noqa: BLE001
        print(f"(importance skipped: {e})")
    return res


# ------------------------------------------------------------- selftest
def make_martingale_bbo(path: str, n=1500):
    from polyvol.synthetic import simulate_paths
    prices, _ = simulate_paths(n, sigma_ann=0.45, seed=11)
    rows = []
    for i, p in enumerate(prices):
        for s in range(0, HORIZON + 1):
            m = min(max(p[s], 0.01), 0.99)
            rows.append(dict(market_id=f"m{i:05d}", sec=s,
                             up_bid=m - 0.01, up_ask=m + 0.01,
                             up_bid_sz=100.0, up_ask_sz=100.0,
                             window_start=1_700_000_000 + i * 300))
    pd.DataFrame(rows).to_parquet(path)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--bbo", default="data/hf/bbo_5m.parquet")
    ap.add_argument("--selftest", action="store_true")
    args = ap.parse_args()

    if args.selftest:
        print("SELF-TEST: martingale BBO -- top decile must be ~ -costs, "
              "NOT positive")
        make_martingale_bbo("/tmp/bbo_ml_selftest.parquet")
        df = build_dataset("/tmp/bbo_ml_selftest.parquet")
    else:
        df = build_dataset(args.bbo)
    walk_forward(df)


if __name__ == "__main__":
    main()
