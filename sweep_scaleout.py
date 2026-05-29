"""Scale-out sweep targeting 70-75% WR with effective 1:3 RR."""
from __future__ import annotations
import itertools, sys, time as _time
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

print("Loading ...")
df = load_csv(CSV)
df_1m = add_entry_indicators(df)
df_15 = add_bias_indicators(resample_15m(df_1m))
df_3m = resample_3m(df_1m)
sh, sl_arr = find_swings_3m(df_3m)
print(f"  {len(df_1m):,} 1m, {len(df_15):,} 15m, {len(df_3m):,} 3m bars")


def slice_t(d, t0, t1):
    return d[(d.index >= t0) & (d.index < t1)].copy()


def slice_arr(df_3m_slice, sh_full, sl_full, full_3m):
    mask = full_3m.index.isin(df_3m_slice.index)
    return sh_full[mask], sl_full[mask]


t0, t1 = df_1m.index[0], df_1m.index[-1]
total = t1 - t0
fold = total / 3.5
folds = []
for i in range(3):
    a = t0 + i * (total / 4.5)
    b = a + 0.6 * fold
    c = b
    d_t = c + 0.4 * fold
    folds.append((a, b, c, d_t))
for i, (_, _, c, d_t) in enumerate(folds):
    print(f"  fold{i+1}: test [{c.date()}..{d_t.date()}]")


def run_one(d_1m, d_15, d_3m, sh_s, sl_s, ma, pat, rr, sl_buf, tp1, frac, trail):
    bias = classify_bias(d_15, MA_COMBOS[ma])
    sigs = detect_signals(
        d_1m, d_15, bias, pattern=pat, wait_bars=15,
        sl_method="swing3m", sl_buffer=sl_buf,
        df_3m=d_3m, swing_high=sh_s, swing_low=sl_s,
        session_hours=SESSION_HOURS, bias_tf_minutes=15,
    )
    if not sigs:
        return None
    trs = simulate(sigs, d_1m, rr=rr, max_bars=240,
                   tp1_at_r=tp1, tp1_close_frac=frac, trail_method=trail)
    m = metrics(trs)
    if m.get("trades", 0) == 0:
        return None
    m.update({"ma_combo": ma, "pattern": pat, "rr": rr, "sl_buf": sl_buf,
              "tp1": tp1, "frac": frac, "trail": trail or "none"})
    return m


ma_combos = ["ribbon_only", "ribbon_ema55", "ribbon_ema55_ema100"]
patterns = ["P1", "P2"]
rrs = [3.0, 4.0, 5.0]
sl_bufs = [2.0, 3.0]
tp1_options = [0.3, 0.5, 0.7, 1.0, 1.5]
frac_options = [0.3, 0.5, 0.7]
trail_options = [None, "ema21", "swing"]

grid = list(itertools.product(ma_combos, patterns, rrs, sl_bufs, tp1_options, frac_options, trail_options))
print(f"\nGrid: {len(grid)} configs x 3 folds = {len(grid)*3} runs")

results = []
start = _time.time()
for gi, (ma, pat, rr, sb, tp1, frac, tr) in enumerate(grid):
    fms = []
    for _, _, c, d_t in folds:
        d_1m = slice_t(df_1m, c, d_t)
        d_15 = slice_t(df_15, c, d_t)
        d_3m = slice_t(df_3m, c, d_t)
        if len(d_1m) < 1000:
            continue
        sh_s, sl_s = slice_arr(d_3m, sh, sl_arr, df_3m)
        m = run_one(d_1m, d_15, d_3m, sh_s, sl_s, ma, pat, rr, sb, tp1, frac, tr)
        if m:
            fms.append(m)
    if not fms:
        continue
    results.append({
        "ma_combo": ma, "pattern": pat, "rr": rr, "sl_buf": sb,
        "tp1": tp1, "frac": frac, "trail": tr or "none",
        "folds_with_trades": len(fms),
        "total_trades": sum(m["trades"] for m in fms),
        "mean_net": float(np.mean([m["net_pts"] for m in fms])),
        "min_net": float(np.min([m["net_pts"] for m in fms])),
        "mean_wr": float(np.mean([m["win_rate"] for m in fms])),
        "min_wr": float(np.min([m["win_rate"] for m in fms])),
        "mean_pf": float(np.mean([m["profit_factor"] for m in fms if np.isfinite(m["profit_factor"])])),
        "mean_dd": float(np.mean([m["max_dd_pts"] for m in fms])),
        "mean_avg": float(np.mean([m["avg_trade_pts"] for m in fms])),
        "mean_tpd": float(np.mean([m["trades_per_day"] for m in fms])),
    })
    if (gi + 1) % 100 == 0:
        el = _time.time() - start
        eta = el / (gi + 1) * (len(grid) - gi - 1)
        print(f"  {gi+1}/{len(grid)}  elapsed {el:.0f}s  eta {eta:.0f}s")

res = pd.DataFrame(results)
res_robust = res[(res["folds_with_trades"] >= 2) & (res["min_net"] > 0)].copy()
res_robust = res_robust.sort_values("mean_wr", ascending=False).reset_index(drop=True)
res_robust.to_csv("results_scaleout.csv", index=False, float_format="%.3f")
print(f"\n{len(res_robust)} robust configs (positive in every fold)")

target_wr = 70.0
target_pf = 1.5
hits = res_robust[(res_robust["mean_wr"] >= target_wr) & (res_robust["mean_pf"] >= target_pf)]
print(f"\nConfigs hitting target (mean WR >= {target_wr}% AND PF >= {target_pf}):")
if len(hits) > 0:
    print(hits.head(15).to_string(index=False))
else:
    print("  None.")

print(f"\nTop 15 robust by mean WR:")
print(res_robust.head(15).to_string(index=False))

print(f"\nTop 15 robust by mean net_pts:")
print(res_robust.sort_values("mean_net", ascending=False).head(15).to_string(index=False))
