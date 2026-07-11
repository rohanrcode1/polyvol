"""Experiment 1: the martingale null.

Generates 20,000 synthetic 5-minute markets (efficient-market price paths),
then runs the full strategy grid in both execution modes. This establishes
the baseline every real-data result must be compared against:

  * touch probabilities (Q3: "if I buy at 40c, how often does 45c/50c print
    before expiry?") are HIGH -- and yet
  * expected value is ~0 pre-cost and NEGATIVE post-cost,

because the rare failed hedges are exactly severe enough to eat the many
small locked-in wins. That is what a martingale guarantees. A real edge
requires real Polymarket paths to mean-revert more than this null.

Run:  python scripts/run_synthetic.py
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

from polyvol.synthetic import simulate_paths, touch_probability_matrix
from polyvol.strategy import Params
from polyvol.backtest import run_grid, summarize, equity_metrics

OUT = Path(__file__).resolve().parents[1] / "output"
OUT.mkdir(exist_ok=True)

N_MARKETS = 20_000
SIGMA_ANN = 0.45  # ~45% annualized BTC vol; re-calibrate from real data

pd.set_option("display.width", 200)
pd.set_option("display.float_format", lambda x: f"{x:,.4f}")


def main():
    print(f"Simulating {N_MARKETS:,} five-minute markets "
          f"(driftless GBM, sigma_ann={SIGMA_ANN})...")
    prices, outcomes = simulate_paths(N_MARKETS, sigma_ann=SIGMA_ANN, seed=42)
    rng_range = (prices.max(axis=1) - prices.min(axis=1))
    print(f"  YES-win rate: {outcomes.mean():.3f}")
    print(f"  median intra-market high-low range: {np.median(rng_range)*100:.1f}c "
          f"(p25={np.percentile(rng_range,25)*100:.1f}c, "
          f"p75={np.percentile(rng_range,75)*100:.1f}c)")

    # ---------------- Q3: touch probability matrix -------------------
    print("\n=== Touch probabilities: P(YES revisits entry+delta | bought at "
          "entry with >= T sec left) ===")
    tp = pd.DataFrame(touch_probability_matrix(prices))
    piv = tp.pivot_table(index=["entry", "min_tr_s"], columns="delta",
                         values="p_touch")
    print(piv.to_string())
    tp.to_csv(OUT / "touch_probabilities.csv", index=False)

    # ---------------- Q1/Q2: strategy grid ---------------------------
    grid = dict(entry=[0.30, 0.35, 0.40, 0.45],
                target=[0.02, 0.05, 0.10])

    results = {}
    for mode, hs in [("taker", 0.01), ("maker", 0.0)]:
        base = Params(mode=mode, half_spread=hs, min_tr_s=60, warmup_s=15)
        trades = run_grid(prices, outcomes, base, grid)
        summ = summarize(trades, N_MARKETS)
        results[mode] = (trades, summ)
        print(f"\n=== {mode.upper()} mode "
              f"(half-spread={hs*100:.0f}c, crypto taker fee curve) ===")
        cols = ["entry", "target", "n_entries", "completion_rate",
                "avg_time_to_hedge_s", "avg_pnl_completed", "avg_pnl_failed",
                "ev_per_trade", "t_stat", "worst"]
        print(summ[cols].to_string(index=False))
        summ.to_csv(OUT / f"grid_summary_{mode}.csv", index=False)

    # ---------------- zero-cost sanity check (martingale => EV ~ 0) --
    base = Params(mode="taker", half_spread=0.0, fee_rate=0.0)
    trades0 = run_grid(prices, outcomes, base, dict(entry=[0.40], target=[0.05]))
    print("\n=== Sanity check: zero spread, zero fees (entry=40c, target=5c) ===")
    print(f"  EV per trade: {trades0.pnl.mean():+.5f}  "
          f"(martingale predicts ~0; t={trades0.pnl.mean()/(trades0.pnl.std()/np.sqrt(len(trades0))):.2f})")

    # ---------------- figure -----------------------------------------
    fig, axes = plt.subplots(1, 3, figsize=(16, 4.5))

    ax = axes[0]
    for i in range(8):
        ax.plot(np.arange(prices.shape[1]), prices[i], lw=0.9)
    ax.set(title="Sample synthetic 5-min market paths",
           xlabel="seconds", ylabel="YES price", ylim=(0, 1))

    ax = axes[1]
    t, _ = results["taker"]
    sel = t[(t.entry == 0.40) & (t.target == 0.05)]
    ax.hist(sel[sel.completed].pnl, bins=40, alpha=0.7, label="hedged")
    ax.hist(sel[~sel.completed].pnl, bins=40, alpha=0.7, label="unhedged tail")
    ax.set(title="PnL distribution (taker, entry=40c, target=5c)",
           xlabel="PnL per pair ($)")
    ax.legend()

    ax = axes[2]
    for mode, marker in [("taker", "o"), ("maker", "s")]:
        _, s = results[mode]
        s5 = s[s.target == 0.05]
        ax.plot(s5.entry, s5.ev_per_trade, marker=marker, label=mode)
    ax.axhline(0, color="k", lw=0.8)
    ax.set(title="EV per trade vs entry threshold (target=5c)",
           xlabel="entry threshold", ylabel="EV per trade ($)")
    ax.legend()

    fig.tight_layout()
    fig.savefig(OUT / "synthetic_results.png", dpi=130)
    print(f"\nSaved: {OUT/'synthetic_results.png'}, grid CSVs, touch CSV")

    # ---------------- equity metrics for one config ------------------
    m = equity_metrics(sel.pnl.values)
    print(f"\nEquity metrics (taker, 40c/5c): per-trade Sharpe="
          f"{m['sharpe']:.3f}, max drawdown=${m['max_dd']:.2f} "
          f"(1 share/market)")


if __name__ == "__main__":
    main()
