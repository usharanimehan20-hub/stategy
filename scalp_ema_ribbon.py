import pandas as pd, numpy as np
from backtest import (load_csv, classify_bias, simulate, metrics, MA_COMBOS,
                      add_bias_indicators, add_entry_indicators, ema, Signal)
from sweep_bb_rejection import resample, project_bias, cooldown

# ---- data (18 months real Dukascopy 1-min) ----
df = add_entry_indicators(load_csv("xau_1m_duka_18mo.csv"))
RIBBON = [5, 8, 13, 21, 34]          # fast + reliable Fibonacci EMA ribbon on 1M
for n in RIBBON:
    df[f"e{n}"] = ema(df["close"], n)
df["rib_max"] = df[[f"e{n}" for n in RIBBON]].max(axis=1)
df["rib_min"] = df[[f"e{n}" for n in RIBBON]].min(axis=1)
# ATR ratio
tr = pd.concat([(df["high"]-df["low"]), (df["high"]-df["close"].shift(1)).abs(),
                (df["low"]-df["close"].shift(1)).abs()], axis=1).max(axis=1)
df["atr14"] = tr.rolling(14).mean(); df["atr_ratio"] = df["atr14"]/df["atr14"].rolling(100).mean()

df15 = add_bias_indicators(resample(df, "15min"))
biases = {"15M_ribbon": project_bias(classify_bias(df15, MA_COMBOS["ribbon_only"]), df.index, 15),
          "15M_4MA": project_bias(classify_bias(df15, MA_COMBOS["ribbon_ema55_ema100"]), df.index, 15)}


def add_bb(d, p, m=2.0):
    sma = d["close"].rolling(p).mean(); sd = d["close"].rolling(p).std()
    return sma, sma + m*sd, sma - m*sd


def detect(bias, atrmax, bbmid_up, bbmid_low, buf=3.0):
    o=df["open"].values; c=df["close"].values; h=df["high"].values; l=df["low"].values
    rmax=df["rib_max"].values; rmin=df["rib_min"].values; ar=df["atr_ratio"].values; tm=df.index
    bu = bbmid_up.values if bbmid_up is not None else None
    bl = bbmid_low.values if bbmid_low is not None else None
    s=[]
    for i in range(2,len(df)):
        b=bias.iloc[i]
        if b==0 or pd.isna(rmax[i]) or pd.isna(rmax[i-1]): continue
        if atrmax is not None and (pd.isna(ar[i]) or ar[i]>atrmax): continue
        if b==1:
            cross = c[i]>rmax[i] and c[i-1]<=rmax[i-1]   # first close above whole ribbon
            if cross and c[i]>o[i] and (bu is None or c[i]>bu[i]):
                sl=float(min(l[i-2:i+1]))-buf
                if sl<c[i]: s.append(Signal(time=tm[i],direction=1,entry=float(c[i]),pattern="rib",ema21_at_entry=0.0,sl=sl))
        else:
            cross = c[i]<rmin[i] and c[i-1]>=rmin[i-1]
            if cross and c[i]<o[i] and (bl is None or c[i]<bl[i]):
                sl=float(max(h[i-2:i+1]))+buf
                if sl>c[i]: s.append(Signal(time=tm[i],direction=-1,entry=float(c[i]),pattern="rib",ema21_at_entry=0.0,sl=sl))
    return s


def folds(idx):
    t0,t1=idx[0],idx[-1]; T=t1-t0; f=T/3.5
    return [(t0+i*(T/4.5)+0.6*f, t0+i*(T/4.5)+1.0*f) for i in range(3)]
FD=folds(df.index)


def ev(sigs,rr):
    trs=cooldown(simulate(sigs,df,rr=rr,max_bars=240),2,1); m=metrics(trs)
    if m["trades"]<30: return None
    td=pd.DataFrame({"t":[t.entry_time for t in trs],"p":[t.pnl_points for t in trs]})
    td["mo"]=pd.to_datetime(td["t"]).dt.to_period("M"); mon=td.groupby("mo")["p"].sum()
    fn=[]
    for a,b in FD:
        fs=[x for x in sigs if a<=x.time<b]; ft=cooldown(simulate(fs,df,rr=rr,max_bars=240),2,1); fm=metrics(ft)
        fn.append(fm["net_pts"] if fm["trades"] else 0)
    return m["trades"],m["win_rate"],m["net_pts"],m["profit_factor"],m["max_dd_pts"],int((mon<0).sum()),len(mon),all(x>0 for x in fn)


print("FAST EMA RIBBON (5,8,13,21,34) on 1M + 15M bias + ATR + BB(23/30) | 18mo real data\n")
print(f"{'config':<46}{'trd':>5}{'WR':>6}{'net':>8}{'PF':>6}{'DD':>6}{'losemo':>8}{'rob':>5}")
bbsets={"noBB":(None,None)}
for p in (23,30):
    mid,up,low=add_bb(df,p); bbsets[f"BB{p}"]=(up,low)
for blab,bias in biases.items():
    for atrmax in (None,1.5,2.0):
        for bblab,(bu,bl) in bbsets.items():
            sg=detect(bias,atrmax,bu,bl)
            if len(sg)<30: continue
            for rr in (1.5,2.0,3.0):
                r=ev(sg,rr)
                if r is None: continue
                trd,wr,net,pf,dd,lm,nm,rob=r
                flag="  <==WORKS" if (net>200 and pf>1.1 and lm<=nm*0.4) else ""
                print(f"{blab:<11} ATR<{str(atrmax):<4} {bblab:<5} RR{rr} |{trd:>5}{wr:>5.0f}%{net:>+8.0f}{pf:>6.2f}{dd:>6.0f}{lm:>4}/{nm}{str(rob):>6}{flag}")
