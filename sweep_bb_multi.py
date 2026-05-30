"""
Test two user ideas on the refined BB strategy foundation:
  1. Switch BB timeframe 5M -> 3M
  2. Use MULTIPLE BB settings (an extreme "outer" band for the touch,
     optionally a snap-back-inside confirmation) -> should improve WR.

Foundation (refined, proven): 30M ribbon bias + ATR<1.5 + London+NY + RR1.5
                              + pullback SL + 2-loss/1h cooldown.

Walk-forward + full-window + monthly stability reported.
"""
from __future__ import annotations
import sys, time, itertools
import pandas as pd, numpy as np
from backtest import (load_csv, classify_bias, simulate, metrics, MA_COMBOS, Signal,
                      add_bias_indicators, add_entry_indicators)

LONDON_NY = set(range(8, 17))


def resample(df, rule):
    agg = {"open": "first", "high": "max", "low": "min", "close": "last"}
    return df[["open", "high", "low", "close"]].resample(rule, label="left", closed="left").agg(agg).dropna()


def project_bias(b, idx, src_tf):
    a = b.copy(); a.index = a.index + pd.Timedelta(minutes=src_tf)
    return a.reindex(idx, method="ffill").fillna(0).astype(int)


def add_atr_ratio(df):
    out = df.copy()
    tr = pd.concat([(out["high"] - out["low"]),
                    (out["high"] - out["close"].shift(1)).abs(),
                    (out["low"] - out["close"].shift(1)).abs()], axis=1).max(axis=1)
    out["atr14"] = tr.rolling(14).mean()
    out["atr_ratio"] = out["atr14"] / out["atr14"].rolling(100).mean()
    return out


def add_bands(df, period, m_inner, m_outer):
    out = df.copy()
    sma = out["close"].rolling(period).mean()
    std = out["close"].rolling(period).std()
    out["bb_up_in"] = sma + m_inner * std
    out["bb_low_in"] = sma - m_inner * std
    out["bb_up_out"] = sma + m_outer * std
    out["bb_low_out"] = sma - m_outer * std
    return out


def detect(df, bias, pb, sl_buf, ses, atr_max, entry_style):
    """entry_style: 'touch_outer' or 'snapback' (touch outer, close back inside inner)."""
    o, c, h, l = df["open"].values, df["close"].values, df["high"].values, df["low"].values
    bui, bli = df["bb_up_in"].values, df["bb_low_in"].values
    buo, blo = df["bb_up_out"].values, df["bb_low_out"].values
    atr_r = df["atr_ratio"].values
    times = df.index
    sigs = []
    for i in range(pb + 1, len(df)):
        b = bias.iloc[i]
        if b == 0:
            continue
        if ses is not None and times[i].hour not in ses:
            continue
        if pd.isna(buo[i]) or pd.isna(bli[i]):
            continue
        if atr_max is not None and (pd.isna(atr_r[i]) or atr_r[i] > atr_max):
            continue
        if b == 1:
            touched = (l[i - pb:i + 1] <= blo[i - pb:i + 1]).any()
            if not touched:
                continue
            if not (c[i] > o[i] and c[i] > c[i - 1]):
                continue
            if entry_style == "snapback" and not (c[i] > bli[i]):
                continue
            sl_lvl = float(min(l[i - pb:i + 1])) - sl_buf
            if sl_lvl >= c[i]:
                continue
        else:
            touched = (h[i - pb:i + 1] >= buo[i - pb:i + 1]).any()
            if not touched:
                continue
            if not (c[i] < o[i] and c[i] < c[i - 1]):
                continue
            if entry_style == "snapback" and not (c[i] < bui[i]):
                continue
            sl_lvl = float(max(h[i - pb:i + 1])) + sl_buf
            if sl_lvl <= c[i]:
                continue
        sigs.append(Signal(time=times[i], direction=int(b), entry=float(c[i]),
                           pattern="bb", ema21_at_entry=0.0, sl=sl_lvl))
    return sigs


def cooldown(trades, n_loss=2, hours=1):
    if not trades:
        return trades
    out = []; consec = 0; cd = None
    for t in trades:
        if cd is not None and t.entry_time < cd:
            continue
        out.append(t)
        if t.pnl_points < 0:
            consec += 1
            if consec >= n_loss:
                cd = t.exit_time + pd.Timedelta(hours=hours); consec = 0
        else:
            consec = 0
    return out


def evaluate(trades):
    m = metrics(trades)
    if m.get("trades", 0) < 50:
        return None
    tdf = pd.DataFrame([{"t": t.entry_time, "p": t.pnl_points} for t in trades])
    tdf["month"] = pd.to_datetime(tdf["t"]).dt.to_period("M")
    monthly = tdf.groupby("month")["p"].sum()
    pnls = np.array([t.pnl_points for t in trades])
    losses = (pnls < 0).astype(int); mcl = cur = 0
    for lv in losses:
        if lv: cur += 1; mcl = max(mcl, cur)
        else: cur = 0
    return {"trades": m["trades"], "wr": m["win_rate"], "net": m["net_pts"],
            "pf": m["profit_factor"], "dd": m["max_dd_pts"], "tpd": m["trades_per_day"],
            "losing_months": int((monthly < 0).sum()), "n_months": len(monthly),
            "worst_month": float(monthly.min()), "max_consec_loss": mcl}


def wf_folds(idx):
    t0, t1 = idx[0], idx[-1]; total = t1 - t0; f = total / 3.5
    return [(t0 + i * (total / 4.5) + 0.6 * f, t0 + i * (total / 4.5) + 1.0 * f) for i in range(3)]


def run(df_entry, tf_min, bias_src, bias_tf, atr_ratio_arr, label, configs):
    """configs: list of dicts with period, m_inner, m_outer, pb, rr, atr_max, style."""
    df_entry = df_entry.copy()
    df_entry["atr_ratio"] = atr_ratio_arr
    bias = project_bias(bias_src, df_entry.index, bias_tf)
    folds = wf_folds(df_entry.index)
    rows = []
    for cfg in configs:
        dfb = add_bands(df_entry, cfg["period"], cfg["m_inner"], cfg["m_outer"])
        dfb["atr_ratio"] = df_entry["atr_ratio"]
        sigs = detect(dfb, bias, cfg["pb"], 3.0, LONDON_NY, cfg["atr_max"], cfg["style"])
        if not sigs:
            continue
        trs = cooldown(simulate(sigs, df_entry, rr=cfg["rr"], max_bars=int(48 * 5 / tf_min)), 2, 1)
        full = evaluate(trs)
        if full is None:
            continue
        # walk-forward robustness
        fold_nets = []
        for a, bnd in folds:
            fs = [s for s in sigs if a <= s.time < bnd]
            if not fs:
                fold_nets = None; break
            ft = cooldown(simulate(fs, df_entry, rr=cfg["rr"], max_bars=int(48 * 5 / tf_min)), 2, 1)
            fm = metrics(ft)
            fold_nets.append(fm["net_pts"] if fm["trades"] else 0)
        robust = fold_nets is not None and all(n > 0 for n in fold_nets)
        rows.append({**cfg, "robust": robust, **full})
    dfr = pd.DataFrame(rows)
    print(f"\n===== {label} =====")
    if len(dfr) == 0:
        print("  no valid configs")
        return dfr
    show = dfr.sort_values(["losing_months", "net"], ascending=[True, False]).head(12)
    for _, r in show.iterrows():
        print(f"  BB({r['period']},{r['m_inner']}/{r['m_outer']}) pb{r['pb']} RR{r['rr']} "
              f"ATR<{r['atr_max']} {r['style']:<9} | trd={r['trades']:>4} WR={r['wr']:4.1f}% "
              f"net={r['net']:+6.0f} PF={r['pf']:.2f} DD={r['dd']:4.0f} "
              f"lm={r['losing_months']}/{r['n_months']} wm={r['worst_month']:+5.0f} mcl={r['max_consec_loss']} rob={r['robust']}")
    return dfr


def main():
    t0 = time.time()
    # ---- M5 (17 months) ----
    df5 = add_entry_indicators(load_csv("XAUUSD_M5_202412300555_202605292355.csv"))
    df5 = add_atr_ratio(df5)
    df30_from5 = add_bias_indicators(resample(df5, "30min"))
    bias30_5 = classify_bias(df30_from5, MA_COMBOS["ribbon_only"])

    # ---- M1 -> 3M and 5M (3.5 months, apples to apples) ----
    df1 = add_entry_indicators(load_csv("XAUUSD_M1_202602160516_202605290404.csv"))
    df3 = add_entry_indicators(resample(df1, "3min")); df3 = add_atr_ratio(df3)
    df5b = add_entry_indicators(resample(df1, "5min")); df5b = add_atr_ratio(df5b)
    df30_from1 = add_bias_indicators(resample(df1, "30min"))
    bias30_1 = classify_bias(df30_from1, MA_COMBOS["ribbon_only"])

    print(f"Loaded. M5(17mo)={len(df5):,}  M3(3.5mo)={len(df3):,}  M5b(3.5mo)={len(df5b):,}  setup {time.time()-t0:.1f}s")

    # IDEA 2: multiple BB settings (outer extreme band) on M5 17mo
    multi_cfgs = []
    for m_out in [2.0, 2.5, 3.0]:
        for m_in in [1.0, 1.5]:
            for style in ["touch_outer", "snapback"]:
                for rr in [1.5, 2.0]:
                    multi_cfgs.append({"period": 30, "m_inner": m_in, "m_outer": m_out,
                                       "pb": 3, "rr": rr, "atr_max": 1.5, "style": style})
    run(df5, 5, bias30_5, 30, df5["atr_ratio"].values,
        "M5 (17mo) MULTI-BAND: outer touch + optional snapback", multi_cfgs)

    # IDEA 1: 3M vs 5M on same 3.5-month window (single band, refined config)
    single_cfgs = [{"period": 30, "m_inner": 1.5, "m_outer": m, "pb": 3, "rr": rr,
                    "atr_max": 1.5, "style": "touch_outer"}
                   for m in [1.5, 2.0, 2.5] for rr in [1.5, 2.0]]
    run(df3, 3, bias30_1, 30, df3["atr_ratio"].values,
        "M3 (3.5mo) single-band refined", single_cfgs)
    run(df5b, 5, bias30_1, 30, df5b["atr_ratio"].values,
        "M5 (3.5mo) single-band refined  [same window as M3]", single_cfgs)

    # IDEA 1+2 combined: 3M multi-band
    run(df3, 3, bias30_1, 30, df3["atr_ratio"].values,
        "M3 (3.5mo) MULTI-BAND", multi_cfgs)

    print(f"\nTotal time {time.time()-t0:.1f}s")


if __name__ == "__main__":
    main()
