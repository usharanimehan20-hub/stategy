import pandas as pd, numpy as np
from backtest import (load_csv, classify_bias, simulate, metrics, MA_COMBOS,
                      add_bias_indicators, add_entry_indicators, wma, Signal)
from sweep_bb_rejection import resample, project_bias, add_bb, cooldown

df = add_entry_indicators(load_csv("xau_1m_duka_18mo.csv"))
df["wma34"] = wma(df["close"], 34); df["wma64"] = wma(df["close"], 64)
df["body"] = (df["close"] - df["open"]).abs(); df["avg_body"] = df["body"].rolling(20).mean()
tr = pd.concat([(df["high"]-df["low"]), (df["high"]-df["close"].shift(1)).abs(),
                (df["low"]-df["close"].shift(1)).abs()], axis=1).max(axis=1)
df["atr14"] = tr.rolling(14).mean(); df["atr_ratio"] = df["atr14"] / df["atr14"].rolling(100).mean()
df15 = add_bias_indicators(resample(df, "15min")); df30 = add_bias_indicators(resample(df, "30min"))
bias15 = project_bias(classify_bias(df15, MA_COMBOS["ribbon_only"]), df.index, 15)
bias30 = project_bias(classify_bias(df30, MA_COMBOS["ribbon_only"]), df.index, 30)
LNY = set(range(8, 17))


def detect(dfb, bias, smult, buf, ses, atrmax):
    o = dfb["open"].values; c = dfb["close"].values; h = dfb["high"].values; l = dfb["low"].values
    bbl = dfb["bb_low"].values; bbu = dfb["bb_up"].values
    w34 = dfb["wma34"].values; w64 = dfb["wma64"].values
    bd = dfb["body"].values; ab = dfb["avg_body"].values; ar = dfb["atr_ratio"].values; tm = dfb.index
    s = []
    for i in range(3, len(dfb)):
        b = bias.iloc[i]
        if b == 0:
            continue
        if ses is not None and tm[i].hour not in ses:
            continue
        if pd.isna(bbl[i]) or pd.isna(w64[i]) or pd.isna(ab[i]):
            continue
        if atrmax is not None and (pd.isna(ar[i]) or ar[i] > atrmax):
            continue
        strong = bd[i] >= smult * ab[i]
        if b == 1:
            if (l[i] <= bbl[i]) and c[i] > bbl[i] and c[i] > o[i] and strong and c[i] > w34[i] and c[i] > w64[i]:
                sl = float(min(l[i-2:i+1])) - buf
                if sl < c[i]:
                    s.append(Signal(time=tm[i], direction=1, entry=float(c[i]), pattern="c1", ema21_at_entry=0.0, sl=sl))
        else:
            if (h[i] >= bbu[i]) and c[i] < bbu[i] and c[i] < o[i] and strong and c[i] < w34[i] and c[i] < w64[i]:
                sl = float(max(h[i-2:i+1])) + buf
                if sl > c[i]:
                    s.append(Signal(time=tm[i], direction=-1, entry=float(c[i]), pattern="c1", ema21_at_entry=0.0, sl=sl))
    return s


def ev(sigs, rr):
    trs = cooldown(simulate(sigs, df, rr=rr, max_bars=240), 2, 1)
    m = metrics(trs)
    if m["trades"] < 30:
        return None
    tdf = pd.DataFrame({"t": [t.entry_time for t in trs], "p": [t.pnl_points for t in trs]})
    tdf["mo"] = pd.to_datetime(tdf["t"]).dt.to_period("M"); mon = tdf.groupby("mo")["p"].sum()
    return m["trades"], m["win_rate"], m["net_pts"], m["profit_factor"], m["max_dd_pts"], int((mon < 0).sum()), len(mon)


dfb = add_bb(df, 30, 1.5)
for col in ("wma34", "wma64", "body", "avg_body", "atr_ratio"):
    dfb[col] = df[col]

print("Config 1 + refinements on 18mo real data:\n")
print(f"{'variant':<34}{'trd':>5}{'WR':>6}{'net':>8}{'PF':>6}{'DD':>6}{'lose_mo':>9}")
for blab, bias in [("15M", bias15), ("30M", bias30)]:
    for atrmax in [None, 1.5, 1.2]:
        for ses_l, ses in [("all", None), ("LNY", LNY)]:
            for rr in [2.0, 3.0]:
                sg = detect(dfb, bias, 1.5, 3.0, ses, atrmax)
                if len(sg) < 30:
                    continue
                r = ev(sg, rr)
                if r is None:
                    continue
                t, wr, net, pf, dd, lm, nm = r
                flag = "  <== WORKS" if (net > 150 and lm <= nm * 0.4 and pf > 1.10) else ""
                print(f"b{blab} ATR<{str(atrmax):<4} {ses_l:<3} RR{rr} |{t:>5}{wr:>5.0f}%{net:>+8.0f}{pf:>6.2f}{dd:>6.0f}{lm:>5}/{nm}{flag}")
