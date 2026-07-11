# polyvol — Polymarket 5-Minute Binary Market Volatility Harvesting

Research framework for the question:

> Does buying one side of a Polymarket 5-minute BTC/ETH binary when it gets
> cheap, then completing the pair when the other side gets cheap, produce
> positive expected value after realistic execution costs?

## The theory result you must not skip

The market price `p_t` of the YES share is (approximately) the conditional
probability that BTC finishes above the strike. If the market is efficient,
`p_t` is a **martingale**, and the optional stopping theorem says **every**
entry/exit timing rule has exactly zero expected value before costs, and
negative EV after fees and spread. This is not a modeling choice; it is
arithmetic.

The "guaranteed profit" framing hides where the money leaks: the hedge only
fails when the price never revisits your level, and in a binary that pins to
0/1, **a failed hedge is a near-certain 100% loss of the entry leg**. (If YES
must finish at $1 it must pass through your hedge trigger on the way; so
conditional on the hedge failing, your leg expires worthless.) The many small
locked-in wins are exactly offset by the rare total losses.

Therefore the ONLY viable edge hypothesis is: real Polymarket paths are
**not** martingales at second-to-minute horizons — retail overreaction /
thin books create excess mean reversion — and that excess exceeds
`spread + taker fees`. That is an empirical question, and this repo is built
to answer it: same strategy engine, run once on a martingale null and once on
real tapes; the edge is the difference.

## Verified market facts (fetched from docs.polymarket.com, 2026-07)

* Fee formula: `fee = shares × feeRate × p × (1−p)`, **taker only**.
  Crypto feeRate = **0.07** → max **$0.0175/share at 50c**, ~$0.0168 at 40c,
  ~$0.0033 at 5c. (The "2c above 50 / 5c below" numbers you were using are
  wrong — real fees are smaller and peak at 50c.)
* **Makers pay zero** and earn 20% of taker-fee rebates on crypto markets.
  This asymmetry is the single biggest strategy design lever.
* Fee params are per-market: verify via CLOB `getClobMarketInfo(conditionID)`.
* These dynamic fees were introduced specifically **to kill strategies like
  this one** (latency/oscillation arbitrage near 50c).

## Data plan (what's free, what isn't)

| Need | Source | Cost | Notes |
|---|---|---|---|
| Market metadata, token IDs, strike, resolution | Gamma API `/markets` | Free, no auth | `polyvol/data/polymarket_api.py::find_short_duration_crypto_markets` |
| Tick-level executed trades | Data API `/trades` | Free, no auth | The backbone. Every fill: ts, price, size, side, outcome |
| Price history bars | CLOB `/prices-history` | Free | ~1-min fidelity → useless for 5-min markets; ignore |
| Live order book depth | CLOB `/book` + WebSocket | Free | Record it YOURSELF starting now (`BookRecorder`) |
| Historical order book depth | Tardis.dev | Free 1st-of-month samples; paid full | Only needed for high-fidelity fill simulation |
| On-chain fills | Polygon CTF Exchange `OrderFilled` via HyperSync/Goldsky/Dune | Free tiers | Redundant with Data API trades; useful for verification |

No API keys are required for anything read-only. Keys/wallet only matter when
you eventually place orders.

## Repo layout

```
polyvol/
  fees.py                 documented fee model (verified formula)
  synthetic.py            martingale null: GBM → binary probability paths
  strategy.py             entry/hedge engine, taker + maker execution modes
  backtest.py             parameter-grid runner + analytics
  reconstruct.py          trade tape → 1s YES paths, effective-spread estimator
  data/polymarket_api.py  Gamma/Data/CLOB clients + live book recorder
scripts/
  run_synthetic.py        Experiment 1 (runs anywhere, no network)
  run_real_backtest.py    Experiment 2 (run locally; hits Polymarket APIs)
output/                   CSVs + figures
```

## Experiment 1 results (20,000 synthetic markets, σ_ann = 45%)

Median intra-market high-low range: **65c** — the model reproduces the
"swings way past 10c" behavior you described, from nothing but efficient
pricing. Big swings are NOT evidence of exploitable inefficiency.

Touch probabilities (your Q3) are high — buy at 40c with ≥60s left and the
price revisits 45c **82%** of the time, 50c **74%** of the time. And yet:

| Mode | entry=40c, target=5c | completion | EV/trade |
|---|---|---|---|
| Zero cost (sanity) | | 81% | **≈ $0.000** (martingale confirmed) |
| Taker (1c half-spread + fees) | | 81% | **−$0.049** |
| Maker upper bound (no fees/spread) | | 81% | **−$0.036** |

Every cell of the 4×3 grid is negative in both modes (−2.7c to −5.2c per
trade). The maker mode is negative despite zero costs because it models
gap-through adverse selection: your resting bid fills precisely when price
trades through it. Failed hedges lose the full entry stake essentially 100%
of the time, exactly as theory predicts.

**Interpretation:** the strategy as posed has a cost hurdle of roughly
**3–5 cents per pair** that real-market mean reversion must overcome. That is
the number Experiment 2 has to beat.

## Roadmap

1. **Run Experiment 2 locally** (`scripts/run_real_backtest.py`). First check:
   is real EV at 40c/5c better than the synthetic −4.9c? By how much?
2. **Calibrate σ from real data** (realized vol of reconstructed paths) and
   re-run the null so the comparison is apples-to-apples.
3. **Start the book recorder today.** A week of `BookRecorder` on live 5-min
   markets ≈ 2,000 markets of real depth → upgrade the fill simulator from
   spread-model to book-walk (partial fills, average fill price, impact).
4. **Variance-reduction test for mean reversion** independent of the
   strategy: regress 10s-ahead price changes on the previous 10s change,
   conditioned on time remaining and |p−0.5|. If the coefficient isn't
   significantly negative, stop — no strategy variant will save it.
5. If (4) shows real reversion: redesign around **maker-only execution**
   (zero fee + rebate income), which is where any surviving edge lives.
6. Position sizing only after 1–5: size = f(book depth at level, bankroll,
   Kelly on the empirical PnL distribution). Premature before real fills.

## Honest failure modes this design guards against

* survivorship: discovery pulls ALL resolved markets in the window, not
  winners
* look-ahead: strategy sees only prices up to the current second
* fantasy fills: taker mode charges spread + exact documented fee; maker mode
  is explicitly labeled an upper bound
* fee fantasy: fee params re-fetched per market from the CLOB
* multiple testing: a 4×3 grid over thousands of markets WILL produce a
  lucky cell; demand t-stats that survive Bonferroni (~|t| > 3) and validate
  out-of-sample on a later date range
