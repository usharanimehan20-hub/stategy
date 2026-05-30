"""Confirm the scale-out winner: monthly P/L + walk-forward vs PR#7 fixed RR1.5."""
import pandas as pd, numpy as np
from backtest import (load_csv, classify_bias, simulate, metrics, MA_COMBOS, Signal,
                      add_bias_indicators, add_entry_indicators)
from sweep_bb_rr import resample, project_bias, add_atr_ratio, add_bb, detect, cooldown

LONDON_NY = set(range(8, 17))
df = add_entry_indicators(load_csv("XAUUSD_M5_202412300555_202605292355.csv"))
df = add_atr_ratio(df)
df30 = add_bias_indicators(resample(df, "30min"))
bias = project_bias(classify_bias(df30, MA_COMBOS["ribbon_only"]), df.index, 30)
dfb = add_bb(df, 30, 1.5); dfb["atr_ratio"] = df["atr_ratio"]
sigs = detect(dfb, bias, 3, 3.0, LONDON_NY, 1.5)


def monthly_report(trs, name):
    m = metrics(trs)
    tdf = pd.DataFrame({"t": [t.entry_time for t in trs], "p": [t.pnl_points for t in trs]})
    tdf["month"] = pd.to_datetime(tdf["t"]).dt.to_period("M")
    monthly = tdf.groupby("month").agg(trades=("p", "count"), net=("p", "sum"),
                                        wr=("p", lambda x: (x > 0).mean() * 100)).round(1)
    pnls = np.array([t.pnl_points for t in trs])
    wins = pnls[pnls > 0]; losses = pnls[pnls < 0]
    eff_rr = (wins.mean() / abs(losses.mean())) if len(losses) else 0
    print(f"\n===== {name} =====")
    print(f"trades={m['trades']} WR={m['win_rate']:.1f}% net={m['net_pts']:+.0f} PF={m['profit_factor']:.2f} "
          f"effRR={eff_rr:.2f} DD={m['max_dd_pts']:.0f} avg_win=+{wins.mean():.1f} avg_loss={losses.mean():.1f}")
    print(monthly.to_string())
    print(f"losing months: {(monthly['net'] < 0).sum()}/{len(monthly)}  worst={monthly['net'].min():+.0f}")
    return trs


# Winner: scaleout rr5, tp1 1.5R close 70%, swing trail
win = cooldown(simulate(sigs, df, rr=5.0, tp1_at_r=1.5, tp1_close_frac=0.7,
                        trail_method="swing", max_bars=48), 2, 1)
monthly_report(win, "SCALE-OUT WINNER: rr5 / TP1@1.5R close70% / swing trail")
pd.DataFrame([t.__dict__ for t in win]).to_csv("trades_bb_scaleout_winner.csv", index=False)

# Old PR#7 for comparison
old = cooldown(simulate(sigs, df, rr=1.5, max_bars=48), 2, 1)
monthly_report(old, "PR#7 FIXED RR1.5 (for comparison)")

# Walk-forward on winner
t0, t1 = df.index[0], df.index[-1]; total = t1 - t0; f = total / 3.5
folds = [(t0 + i * (total / 4.5) + 0.6 * f, t0 + i * (total / 4.5) + 1.0 * f) for i in range(3)]
print("\n===== WALK-FORWARD (winner) =====")
ok = True
for i, (a, b) in enumerate(folds):
    fs = [s for s in sigs if a <= s.time < b]
    ft = cooldown(simulate(fs, df, rr=5.0, tp1_at_r=1.5, tp1_close_frac=0.7,
                           trail_method="swing", max_bars=48), 2, 1)
    fm = metrics(ft)
    print(f"  fold{i+1} [{a.date()}..{b.date()}]: trades={fm['trades']} WR={fm['win_rate']:.1f}% net={fm['net_pts']:+.0f} PF={fm['profit_factor']:.2f}")
    if fm["net_pts"] <= 0: ok = False
print(f"  ROBUST (positive every fold): {ok}")
