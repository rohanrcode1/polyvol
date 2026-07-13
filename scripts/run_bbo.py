from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from polyvol.strategy_bbo import run_bbo_backtest

df = run_bbo_backtest("data/hf/bbo_5m.parquet")

print()
print("=== BBO BACKTEST RESULTS ===")
print(f"Rows: {len(df)}")

if len(df):
    print(f"Completion rate: {df['completed'].mean():.2%}")
    print(f"Mean PnL:        {df['pnl'].mean():.4f}")
    print(f"Median PnL:      {df['pnl'].median():.4f}")
    print(f"Total PnL:       {df['pnl'].sum():.4f}")

    print()
    print("By completion status:")
    print(df.groupby("completed")["pnl"].agg(["count", "mean", "median"]))
else:
    print("No trades generated.")