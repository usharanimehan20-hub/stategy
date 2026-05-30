"""Confirm Config 1 (strong+reject+ribbon) winner: monthly P/L for RR2 and RR3."""
import pandas as pd, numpy as np
from backtest import (load_csv, classify_bias, simulate, metrics, MA_COMBOS,
                      add_bias_indicators, add_entry_indicators)
from sweep_bb_rejection import (resample, project_bias, add_bb, add_ribbon_body,
                                detect, cooldown)

df = add_entry_indicators(load_csv("XAUUSD_M1_202602160516_202605290404.csv"))
df = add_ribbon_body(df)
df15 = add_bias_indicators(resample(df, "15min"))
bias = project_bias(classify_bias(df15, MA_COMBOS["ribbon_only"]), df.index, 15)
dfb = add_bb(df, 30, 1.5)
for col in ("wma34", "wma64", "body", "avg_body"):
    dfb[col] = df[col]
sigs = detect(dfb, bias, "strong_reject_ribbon", 1.5, 3.0, None)
print(f"Config 1 signals: {len(sigs)}  (long={sum(1 for s in sigs if s.direction==1)}, "
      f"short={sum(1 for s in sigs if s.direction==-1)})")


def report(rr, name):
    trs = cooldown(simulate(sigs, df, rr=rr, max_bars=240), 2, 1)
    m = metrics(trs)
    pnls = np.array([t.pnl_points for t in trs])
    wins = pnls[pnls > 0]; losses = pnls[pnls < 0]
    eff = wins.mean() / abs(losses.mean()) if len(losses) else 0
    tdf = pd.DataFrame({"t": [t.entry_time for t in trs], "p": pnls})
    tdf["month"] = pd.to_datetime(tdf["t"]).dt.to_period("M")
    mon = tdf.groupby("month").agg(trades=("p", "count"), net=("p", "sum"),
                                   wr=("p", lambda x: (x > 0).mean() * 100)).round(1)
    print(f"\n===== {name} =====")
    print(f"trades={m['trades']} WR={m['win_rate']:.1f}% net={m['net_pts']:+.0f} PF={m['profit_factor']:.2f} "
          f"effRR={eff:.2f} DD={m['max_dd_pts']:.0f} avg_win=+{wins.mean():.1f} avg_loss={losses.mean():.1f} "
          f"tpd={m['trades_per_day']:.2f}")
    print(mon.to_string())
    print(f"losing months {(mon['net']<0).sum()}/{len(mon)}  worst {mon['net'].min():+.0f}")
    pd.DataFrame([t.__dict__ for t in trs]).to_csv(f"trades_rejection_rr{rr}.csv", index=False)


report(2.0, "CONFIG 1 RR2.0  (balanced: decent WR + good RR)")
report(3.0, "CONFIG 1 RR3.0  (high RR)")
report(1.5, "CONFIG 1 RR1.5  (high WR)")
