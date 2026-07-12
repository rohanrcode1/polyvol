"""Grid backtester + performance analytics."""

from __future__ import annotations

from dataclasses import replace
from itertools import product

import numpy as np
import pandas as pd

from .strategy import Params, run_path


def run_grid(prices, outcomes, base: Params, grid: dict, dt: float = 1.0):
    """Run every parameter combination over every market path.

    grid example: {"entry": [0.35, 0.40], "target": [0.02, 0.05, 0.10]}
    Returns a tidy DataFrame with one row per (param combo, entered market).
    """
    keys = list(grid.keys())
    records = []
    for combo in product(*grid.values()):
        p = replace(base, **dict(zip(keys, combo)))
        for i in range(prices.shape[0]):
            rec = run_path(prices[i], int(outcomes[i]), p, dt)
            if rec is not None:
                rec["market_id"] = i
                records.append(rec)
    return pd.DataFrame(records)


def summarize(trades: pd.DataFrame, n_markets: int, group_keys=("entry", "target")):
    """Per-config summary answering the core research questions."""
    if trades.empty:
        return pd.DataFrame()

    def _agg(g: pd.DataFrame) -> pd.Series:
        comp = g[g.completed]
        fail = g[~g.completed]
        pnl = g.pnl.values
        return pd.Series(dict(
            n_entries=len(g),
            entry_rate=len(g) / n_markets,
            completion_rate=g.completed.mean(),
            avg_time_to_hedge_s=comp.time_to_hedge.mean(),
            avg_pnl_completed=comp.pnl.mean() if len(comp) else np.nan,
            avg_pnl_failed=fail.pnl.mean() if len(fail) else np.nan,
            ev_per_trade=pnl.mean(),
            pnl_std=pnl.std(ddof=1) if len(g) > 1 else np.nan,
            t_stat=(pnl.mean() / (pnl.std(ddof=1) / np.sqrt(len(g))))
            if len(g) > 1 and pnl.std(ddof=1) > 0 else np.nan,
            worst=pnl.min(), best=pnl.max(),
        ))

    return (trades.groupby(list(group_keys), sort=True)
            .apply(_agg, include_groups=False).reset_index())


def equity_metrics(pnl: np.ndarray):
    """Sharpe-per-trade and max drawdown of the cumulative PnL curve."""
    if len(pnl) < 2:
        return dict(sharpe=np.nan, max_dd=np.nan)
    eq = np.cumsum(pnl)
    peak = np.maximum.accumulate(eq)
    return dict(
        sharpe=pnl.mean() / pnl.std(ddof=1) if pnl.std(ddof=1) > 0 else np.nan,
        max_dd=float((peak - eq).max()),
    )
