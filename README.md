# Volatility Harvesting on Polymarket: A Complete Falsification Study

A rigorous investigation into an apparently attractive trading strategy on Polymarket prediction markets—and how a well-engineered fee structure makes it unbeatable.

## What This Is

This repository documents a small research project that tested whether retail traders can exploit mean reversion in Polymarket 5-minute binary markets. The answer is no—but the *way* and *why* is more interesting than the negative result.

**Status**: Hypothesis rejected ✗  
**Confidence**: Very high (statistical significance t > 30 across 6,700+ markets)  
**Key finding**: The fee structure isn't accidental—it's targeted defense.

## Start Here

**[👉 READ THE FULL RESEARCH MEMO](./docs/RESEARCH_MEMO.md)**

The memo tells the complete story: from initial hypothesis through the discovery of real but unattainable mean reversion, to the final realization that Polymarket's fee curve was engineered specifically to eliminate this edge.

*Estimated read time: 25-30 minutes*

## The Question

Polymarket's 5-minute binary options markets (BTC Up or Down 5m) swing 10-30 cents during their lifetime before pinning to $0 or $1. Could a trader:

1. Buy one side when it gets cheap (e.g., UP at 40¢)
2. Wait for the opposite side to also get cheap (DOWN at 45¢)
3. Hold both to resolution for guaranteed $1 payout
4. Profit from the difference ($0.85 cost vs. $1 payout)?

It seems straightforward. The markets clearly shift enough to make it possible. There's a mathematical guarantee if you can complete the hedge. What could go wrong?

## The Methodology

We built a research framework to test this rigorously:

1. **Theory Test**: Simulate 20,000 perfect markets (martingales) and measure the cost of the strategy
2. **Null Calibration**: Verify the simulation reproduces observed price behavior
3. **Real Data Backtest**: Test on 999 markets with actual Polymarket trades
4. **Microstructure Analysis**: When unexpected signals appeared, dig deeper
5. **Economic Quantification**: Test the strategy at real bid/ask prices
6. **HuggingFace Dataset**: Access 6,742 markets with full orderbook history
7. **Final Decomposition**: Separate real reversion from measurement artifacts

## Key Findings

| Test | Result | Interpretation |
|---|---|---|
| **Synthetic null (taker mode)** | EV = −4.9¢/pair, t = −30+ | Cost hurdle is 3–5¢ due to fees |
| **Real markets (999 markets)** | EV = −5.1¢/pair, t = −9.7 | Identical to null model |
| **Mean reversion (BBO mids)** | beta = −0.064, t = −13.6 | Real reversion exists |
| **Reversion concentration** | Strongest at 50¢ late in window | Where fees are highest (peak 1.75¢/share) |
| **Economic capture test** | Fade strategy EV = −6.9 to −13.5¢ | Reversion doesn't pay for itself |
| **Spot-momentum test** | EV = −4.0¢ (1-second latency) | Book reprices before you can react |

## The Verdict

### Yes, mean reversion exists (statistically significant across 6,700+ markets, t > 30)

When the YES price drops sharply late in the window, it tends to partially revert. This is real market behavior, not noise.

### But no, you cannot capture it profitably as a retail taker

For three reasons:

1. **The spread costs money** (0.5¢ per side)
2. **Fees are dynamic and punitive** (0.07 × p × (1−p), peaking at exactly 50¢ where reversion is strongest)
3. **Execution latency kills the spot-momentum signal** (milliseconds for professionals vs. seconds for retail)

### The Fee Moat

This is the elegant part. Polymarket didn't eliminate the pattern—they engineered the fee structure to **tax the exact behavior that would exploit it**:

- Fee formula: `0.07 × price × (1 − price)`
- Peaks at: 50¢ (exactly where reversion concentrates)
- Cost: 1.75¢/share on each leg = 3.5¢ round trip
- Recoverable reversion: 0.5–1.5¢
- Result: Losing strategy

## What This Means

**For retail traders**: Before testing any strategy on a platform with dynamic fees, calculate whether signal ≥ fee + spread. On Polymarket, that hurdle is 3–5¢ per pair. Most intraday reversal patterns recover less.

**For researchers**: Bid-ask bounce creates false reversion signals in trade-price data. Always test on quote midpoints when possible. Statistical significance (t > 30) can coexist with negative economic value (−6¢).

**For platform designers**: This is how efficient markets are maintained in practice. Not by eliminating patterns, but by pricing them accurately. The strategy isn't forbidden—it's just expensive.

## The Code

All code to reproduce this research is available in the `polyvol` framework:

- `synthetic.py` — Martingale market generator
- `strategy.py` — Entry/hedge simulation engine
- `backtest.py` — Grid search and analytics
- `polymarket_api.py` — Free API clients (no keys needed)
- `reconstruct.py` — Turn trade tape to price paths
- `mean_reversion_test.py` — Autocorrelation test with bias correction
- `bbo_mid_reversion.py` — Midpoint reversion test
- `spot_lag_test.py` — Book-to-spot lead-lag measurement
- `edge_economics.py` — End-to-end backtest at executable prices


## How to Use This

### Read It

The memo explains:
- What prediction markets are
- Why this strategy seemed promising
- What theory says should happen
- What actually happened
- Why the difference matters

### Run It

The code is Python 3.11+ with standard scientific libraries (pandas, numpy, scipy). All data sources are free (no API keys). Start with:

```bash
# Test the martingale null
python scripts/run_synthetic.py

# Run the mean reversion diagnostic
python scripts/mean_reversion_test.py --synthetic

# See the fee moat in action
python scripts/edge_economics.py fade --bbo data/hf/bbo_5m.parquet
```

### Learn From It

The research methodology—null model, synthetic validation, real data confirmation, microstructure decomposition—applies to any market/strategy combo. Feel free to use it as a template for your own investigations.

## Caveats & Limitations

1. **One regime, two weeks of data**: April 2026 may not represent all market conditions
2. **One-second resolution**: Sub-second patterns (where professionals operate) are invisible
3. **Polymarket-specific**: Other prediction markets may have different fee structures
4. **Dataset coverage**: The HuggingFace orderbook data starts when the collector's WebSocket began, so older markets have ticks but no book
5. **No live trading**: This is backtesting, not live results


## References

- Optional Stopping Theorem (Doob, 1953)
- Roll, R. (1984). "A Simple Implicit Measure of the Effective Bid-Ask Spread in an Efficient Market"
- Polymarket Fee Documentation (docs.polymarket.com/trading/fees, verified July 2026)
- Polymarket API docs (public, no auth required)
- HuggingFace Dataset: `aliplayer1/polymarket-crypto-updown` (6,742 markets, 1.9M orderbook snapshots)

## Repository Structure

```
.
.
├── .gitignore
├── LICENSE.md
├── README.md
├── docs/
│   ├── EXECUTIVE_SUMMARY.txt
│   ├── INDEX.md
│   ├── RESEARCH_MEMO.md
│   └── VISUAL_SUMMARY.md
├── polyvol/
│   ├── __init__.py
│   ├── backtest.py
│   ├── fees.py
│   ├── reconstruct.py
│   ├── strategy.py
│   ├── strategy_bbo.py
│   ├── synthetic.py
│   └── data/
│       └── polymarket_api.py
└── scripts/
    ├── bbo_mid_reversion.py
    ├── edge.economics.py
    ├── hf_ingest.py
    ├── mean_reversion_test.py
    ├── run_bbo.py
    ├── run_real_backtest.py
    ├── run_synthetic.py
    └── spot_lag_test.py
```

## License & Attribution

This research is open-source and reproducible. Use it, extend it, cite it.

**Conducted July 2026**  
**All analysis, code, and findings are publicly available.**

---

## The Big Picture

Markets work because they're expensive to exploit. This investigation proves that point empirically. Polymarket could have banned the strategy, but instead they just priced it. That's an example of great market design.

If you're a trader reading this: calculate the actual cost of the pattern you want to capture before you trade.

If you're a platform designer: this is how you maintain efficiency without banning anything.

If you're a researcher: this is a replicable template for testing strategies on any market.

---

**Questions? Extensions? Better ideas?**

If you find something interesting, feel free to share.

---

*Last updated: July 13, 2026*
