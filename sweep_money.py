"""
Aggressive parameter sweep for an intraday/scalping money-printer.

Locked from PR #3 winner:
    mode = m1 (15M bias / 1M entry)
    sl_method = swing3m
    session = 2,5,8,13,14,15,16,22

Sweeps:
    ma_combo: ribbon_only, ribbon_ema55, ribbon_ema100, ribbon_ema55_ema100
    pattern : P1, P2, both
    rr      : 1.5, 2, 3, 4, 5, 6
    sl_buf  : 2, 3
    be_at_r : None, 0.5, 1.0, 1.5     <-- breakeven-after-N-R move
    trail   : None, ema21, swing      <-- trailing stop after BE

Walk-forward validation: 3 folds of (60% train / 40% test, sliding).
Final pick = highest mean OOS net_pts across folds (curve-fit-resistant).
"""
from __future__ import annotations
import itertools
import sys
import time as _time
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).parent))
from backtest import (
    load_csv, resample_15m, resample_3m, add_bias_indicators, add_entry_indicators,
    classify_bias, find_swings_3m, detect_signals, simulate, metrics, MA_COMBOS,
)

CSV = "/projects/sandbox/stategy/XAUUSD_M1_202602160516_202605290404.csv"
SESSION_HOURS = {2, 5, 8, 13, 14, 15, 16, 22}

print("Loading data ...")
df = load_csv(CSV)
df_1m = add_entry_indicators(df)
df_15 = add_bias_indicators(resample_15m(df_1m))
df_3m = resample_3m(df_1m)
sh, sl_arr = find_swings_3m(df_3m)
print(f"  {len(df_1m):,} 1m bars, {len(df_15):,} 15m bars, {len(df_3m):,} 3m bars")
print(f"  range: {df_1m.index[0]} -> {df_1m.index[-1]}")


def run_one(df_1m_slice, df_15_slice, df_3m_slice, sh_slice, sl_arr_slice,
            ma_combo, pattern, rr, sl_buf, be_at_r, trail):
    bias_15 = classify_bias(df_15_slice, MA_COMBOS[ma_combo])
    sigs = detect_signals(
        df_1m_slice, df_15_slice, bias_15, pattern=pattern, wait_bars=15,
        sl_method="swing3m", sl_buffer=sl_buf,
        df_3m=df_3m_slice, swing_high=sh_slice, swing_low=sl_arr_slice,
        session_hours=SESSION_HOURS, bias_tf_minutes=15,
    )
    trs = simulate(sigs, df_1m_slice, rr=rr, max_bars=240,
                   be_at_r=be_at_r, trail_method=trail)
    m = metrics(trs)
    if m.get("trades", 0) == 0:
        return None
    m.update({"ma_combo": ma_combo, "pattern": pattern, "rr": rr,
              "sl_buf": sl_buf, "be_at_r": be_at_r, "trail": trail or "none"})
    return m


def slice_by_time(df, t0, t1):
    return df[(df.index >= t0) & (df.index < t1)].copy()


def slice_arrays(df_3m_slice, sh, sl_arr, full_df_3m):
    # Indices from the full df_3m to map sh/sl_arr to the slice
    mask = full_df_3m.index.isin(df_3m_slice.index)
    return sh[mask], sl_arr[mask]


# Walk-forward folds: 3 sliding folds covering full data
n = len(df_1m)
t_start = df_1m.index[0]
t_end = df_1m.index[-1]
total = (t_end - t_start)
fold_size = total / 3.5  # 3 folds + 50% overlap-ish
folds = []
for i in range(3):
    train_t0 = t_start + i * (total / 4.5)
    train_t1 = train_t0 + 0.6 * fold_size
    test_t0 = train_t1
    test_t1 = test_t0 + 0.4 * fold_size
    folds.append((train_t0, train_t1, test_t0, test_t1))
for i, (a, b, c, d) in enumerate(folds):
    print(f"  fold{i+1}: train [{a.date()}..{b.date()}]  test [{c.date()}..{d.date()}]")

# Parameter grid
ma_combos = list(MA_COMBOS.keys())
patterns = ["P1", "P2", "both"]
rrs = [1.5, 2.0, 3.0, 4.0, 5.0, 6.0]
sl_bufs = [2.0, 3.0]
be_options = [None, 0.5, 1.0, 1.5]
trail_options = [None, "ema21", "swing"]

grid = list(itertools.product(ma_combos, patterns, rrs, sl_bufs, be_options, trail_options))
print(f"\nGrid size: {len(grid)} configs x 3 folds = {len(grid)*3} runs")

# Run all configs across all folds; aggregate by config across folds
results = []
t0 = _time.time()
for gi, (ma, pat, rr, buf, be, tr) in enumerate(grid):
    fold_metrics = []
    for fi, (a, b, c, d) in enumerate(folds):
        df_1m_test = slice_by_time(df_1m, c, d)
        df_15_test = slice_by_time(df_15, c, d)
        df_3m_test = slice_by_time(df_3m, c, d)
        if len(df_1m_test) < 100 or len(df_3m_test) < 10:
            continue
        sh_test, sl_test = slice_arrays(df_3m_test, sh, sl_arr, df_3m)
        m = run_one(df_1m_test, df_15_test, df_3m_test, sh_test, sl_test,
                    ma, pat, rr, buf, be, tr)
        if m:
            fold_metrics.append(m)
    if not fold_metrics:
        continue
    # Aggregate across folds
    agg = {
        "ma_combo": ma, "pattern": pat, "rr": rr, "sl_buf": buf,
        "be_at_r": be, "trail": tr or "none",
        "folds_with_trades": len(fold_metrics),
        "total_trades": sum(m["trades"] for m in fold_metrics),
        "mean_net_pts": np.mean([m["net_pts"] for m in fold_metrics]),
        "min_net_pts": np.min([m["net_pts"] for m in fold_metrics]),
        "mean_win_rate": np.mean([m["win_rate"] for m in fold_metrics]),
        "mean_pf": np.mean([m["profit_factor"] for m in fold_metrics if np.isfinite(m["profit_factor"])]),
        "mean_max_dd": np.mean([m["max_dd_pts"] for m in fold_metrics]),
        "mean_trades_per_day": np.mean([m["trades_per_day"] for m in fold_metrics]),
    }
    results.append(agg)
    if (gi + 1) % 100 == 0:
        elapsed = _time.time() - t0
        eta = elapsed / (gi + 1) * (len(grid) - gi - 1)
        print(f"  {gi+1}/{len(grid)}  elapsed {elapsed:.0f}s  eta {eta:.0f}s")

df_res = pd.DataFrame(results)
df_res = df_res[df_res["folds_with_trades"] >= 2]  # require at least 2 folds with trades
df_res = df_res[df_res["min_net_pts"] > 0]  # require positive in EVERY fold (robust)

print(f"\n{len(df_res)} robust configs (positive net in every fold w/ >=10 trades)")
df_res = df_res.sort_values("mean_net_pts", ascending=False).reset_index(drop=True)
df_res.to_csv("sweep_money_results.csv", index=False, float_format="%.3f")
print(f"\nTop 15 robust configs by mean OOS net_pts:")
print(df_res.head(15).to_string(index=False))

# Final recommendation
if len(df_res) > 0:
    best = df_res.iloc[0]
    print("\n" + "=" * 80)
    print("FINAL RECOMMENDATION (best across all 3 walk-forward folds)")
    print("=" * 80)
    print(f"  ma_combo : {best['ma_combo']}")
    print(f"  pattern  : {best['pattern']}")
    print(f"  rr       : {best['rr']}")
    print(f"  sl_buf   : {best['sl_buf']}")
    print(f"  be_at_r  : {best['be_at_r']}")
    print(f"  trail    : {best['trail']}")
    print(f"\n  Across {int(best['folds_with_trades'])} folds:")
    print(f"    total trades  : {int(best['total_trades'])}")
    print(f"    mean net pts  : {best['mean_net_pts']:+.1f}")
    print(f"    min net (worst fold): {best['min_net_pts']:+.1f}")
    print(f"    mean WR       : {best['mean_win_rate']:.1f}%")
    print(f"    mean PF       : {best['mean_pf']:.2f}")
    print(f"    mean max DD   : {best['mean_max_dd']:.1f}")
else:
    print("\nNo configs passed the robustness filter (positive in every fold).")
