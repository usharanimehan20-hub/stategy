import pandas as pd, numpy as np
from backtest import (load_csv, classify_bias, simulate, metrics, MA_COMBOS,
                      add_bias_indicators, add_entry_indicators, ema, Signal)
from sweep_bb_rejection import resample, project_bias, cooldown

df = add_entry_indicators(load_csv("xau_1m_duka_18mo.csv"))
for n in (5, 8, 13, 21, 34):
    df[f"e{n}"] = ema(df["close"], n)
tr = pd.concat([(df["high"]-df["low"]), (df["high"]-df["close"].shift(1)).abs(),
                (df["low"]-df["close"].shift(1)).abs()], axis=1).max(axis=1)
df["atr14"] = tr.rolling(14).mean(); df["atr_ratio"] = df["atr14"]/df["atr14"].rolling(100).mean()
df15 = add_bias_indicators(resample(df, "15min"))
biases = {"15M_ribbon": project_bias(classify_bias(df15, MA_COMBOS["ribbon_only"]), df.index, 15),
          "15M_4MA": project_bias(classify_bias(df15, MA_COMBOS["ribbon_ema55_ema100"]), df.index, 15)}
RIBS = {"rib_5-34": (5, 8, 13, 21, 34), "rib_5-21(no34)": (5, 8, 13, 21)}


def add_bb(p, m=2.0):
    sma = df["close"].rolling(p).mean(); sd = df["close"].rolling(p).std()
    return (sma + m*sd).values, (sma - m*sd).values


def detect(bias, ribset, bbu, bbl, atrmax, buf=3.0):
    o=df["open"].values; c=df["close"].values; h=df["high"].values; l=df["low"].values
    ar=df["atr_ratio"].values; tm=df.index
    es=[df[f"e{n}"].values for n in ribset]
    s=[]
    for i in range(2,len(df)):
        b=bias.iloc[i]
        if b==0 or pd.isna(bbu[i]): continue
        if atrmax is not None and (pd.isna(ar[i]) or ar[i]>atrmax): continue
        rmax=max(e[i] for e in es); rmin=min(e[i] for e in es)
        if pd.isna(rmax): continue
        if b==1:
            reject = l[i]<=bbl[i] and c[i]>bbl[i]   # BB rejection (primary)
            if reject and c[i]>o[i] and c[i]>rmax:   # + close above whole ribbon
                sl=float(min(l[i-2:i+1]))-buf
                if sl<c[i]: s.append(Signal(time=tm[i],direction=1,entry=float(c[i]),pattern="bbr",ema21_at_entry=0.0,sl=sl))
        else:
            reject = h[i]>=bbu[i] and c[i]<bbu[i]
            if reject and c[i]<o[i] and c[i]<rmin:
                sl=float(max(h[i-2:i+1]))+buf
                if sl>c[i]: s.append(Signal(time=tm[i],direction=-1,entry=float(c[i]),pattern="bbr",ema21_at_entry=0.0,sl=sl))
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


print("BB REJECTION (primary) + close above EMA ribbon | 18mo real data\n")
print(f"{'config':<52}{'trd':>5}{'WR':>6}{'net':>8}{'PF':>6}{'DD':>6}{'losemo':>8}{'rob':>6}")
bbcache={p:add_bb(p) for p in (23,30)}
for blab,bias in biases.items():
    for rlab,ribset in RIBS.items():
        for bbp in (23,30):
            bbu,bbl=bbcache[bbp]
            for atrmax in (None,1.5):
                sg=detect(bias,ribset,bbu,bbl,atrmax)
                if len(sg)<30: continue
                for rr in (1.5,2.0,3.0):
                    r=ev(sg,rr)
                    if r is None: continue
                    trd,wr,net,pf,dd,lm,nm,rob=r
                    flag="  <==WORKS" if (net>200 and pf>1.1 and lm<=nm*0.4) else ""
                    print(f"{blab:<11}{rlab:<16}BB{bbp} ATR<{str(atrmax):<4} RR{rr}|{trd:>5}{wr:>5.0f}%{net:>+8.0f}{pf:>6.2f}{dd:>6.0f}{lm:>4}/{nm}{str(rob):>6}{flag}")
