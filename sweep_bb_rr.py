"""
Improve RR on the PR#7 refined BB foundation WITHOUT killing the ~46% WR.

Foundation (locked, proven):
  30M ribbon bias + 5M BB(30,1.5) + pullback(3) touch + bias-dir close
  + pullback SL (3pt) + ATR<1.5 + London/NY + 2-loss/1h cooldown.

We sweep EXIT management only:
  - fixed RR target (2,3,4,5)
  - scale-out: TP1 partial close (at R, fraction) then BE + trail the runner
Report WR, net, PF, DD, losing months, max consec loss, and EFFECTIVE RR
(avg win / avg loss) so we can see the real reward:risk.
"""
from __future__ import annotations
import time
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


def add_bb(df, period, mult):
    out = df.copy()
    sma = out["close"].rolling(period).mean(); std = out["close"].rolling(period).std()
    out["bb_up"] = sma + mult * std; out["bb_low"] = sma - mult * std
    return out


def detect(df, bias, pb, sl_buf, ses, atr_max):
    o, c, h, l = df["open"].values, df["close"].values, df["high"].values, df["low"].values
    bbu, bbl = df["bb_up"].values, df["bb_low"].values
    atr_r = df["atr_ratio"].values
    times = df.index
    sigs = []
    for i in range(pb + 1, len(df)):
        b = bias.iloc[i]
        if b == 0 or (ses is not None and times[i].hour not in ses):
            continue
        if pd.isna(bbu[i]) or (atr_max is not None and (pd.isna(atr_r[i]) or atr_r[i] > atr_max)):
            continue
        if b == 1:
            if not (l[i - pb:i + 1] <= bbl[i - pb:i + 1]).any(): continue
            if not (c[i] > o[i] and c[i] > c[i - 1]): continue
            sl_lvl = float(min(l[i - pb:i + 1])) - sl_buf
            if sl_lvl >= c[i]: continue
        else:
            if not (h[i - pb:i + 1] >= bbu[i - pb:i + 1]).any(): continue
            if not (c[i] < o[i] and c[i] < c[i - 1]): continue
            sl_lvl = float(max(h[i - pb:i + 1])) + sl_buf
            if sl_lvl <= c[i]: continue
        sigs.append(Signal(time=times[i], direction=int(b), entry=float(c[i]),
                           pattern="bb", ema21_at_entry=0.0, sl=sl_lvl))
    return sigs


def cooldown(trades, n_loss=2, hours=1):
    if not trades: return trades
    out = []; consec = 0; cd = None
    for t in trades:
        if cd is not None and t.entry_time < cd: continue
        out.append(t)
        if t.pnl_points < 0:
            consec += 1
            if consec >= n_loss:
                cd = t.exit_time + pd.Timedelta(hours=hours); consec = 0
        else: consec = 0
    return out


def evaluate(trades):
    m = metrics(trades)
    if m.get("trades", 0) < 50: return None
    pnls = np.array([t.pnl_points for t in trades])
    wins = pnls[pnls > 0]; losses = pnls[pnls < 0]
    avg_win = wins.mean() if len(wins) else 0.0
    avg_loss = abs(losses.mean()) if len(losses) else 1e-9
    eff_rr = avg_win / avg_loss if avg_loss > 0 else 0.0
    tdf = pd.DataFrame({"t": [t.entry_time for t in trades], "p": pnls})
    tdf["month"] = pd.to_datetime(tdf["t"]).dt.to_period("M")
    monthly = tdf.groupby("month")["p"].sum()
    los = (pnls < 0).astype(int); mcl = cur = 0
    for lv in los:
        if lv: cur += 1; mcl = max(mcl, cur)
        else: cur = 0
    return {"trades": m["trades"], "wr": m["win_rate"], "net": m["net_pts"], "pf": m["profit_factor"],
            "dd": m["max_dd_pts"], "avg_win": avg_win, "avg_loss": avg_loss, "eff_rr": eff_rr,
            "losing_months": int((monthly < 0).sum()), "n_months": len(monthly),
            "worst_month": float(monthly.min()), "mcl": mcl}


def main():
    t0 = time.time()
    df = add_entry_indicators(load_csv("XAUUSD_M5_202412300555_202605292355.csv"))
    df = add_atr_ratio(df)
    df30 = add_bias_indicators(resample(df, "30min"))
    bias = project_bias(classify_bias(df30, MA_COMBOS["ribbon_only"]), df.index, 30)
    dfb = add_bb(df, 30, 1.5); dfb["atr_ratio"] = df["atr_ratio"]
    sigs = detect(dfb, bias, 3, 3.0, LONDON_NY, 1.5)
    print(f"Foundation generated {len(sigs):,} signals. setup {time.time()-t0:.1f}s\n")

    # exit-management configs (signals fixed; only exits vary)
    configs = []
    # baseline fixed RR
    for rr in [1.5, 2.0, 3.0, 4.0, 5.0]:
        configs.append(("fixed", dict(rr=rr)))
    # scale-out: TP1 partial -> BE+trail runner to big RR
    for rr in [3.0, 4.0, 5.0]:
        for tp1 in [1.0, 1.5]:
            for frac in [0.5, 0.7]:
                for trail in ["swing", "ema21", None]:
                    configs.append(("scaleout",
                                    dict(rr=rr, tp1_at_r=tp1, tp1_close_frac=frac, trail_method=trail)))
    # pure BE+trail (no partial) at big RR
    for rr in [3.0, 4.0, 5.0]:
        for trail in ["swing", "ema21"]:
            configs.append(("be+trail", dict(rr=rr, be_at_r=1.0, trail_method=trail)))

    rows = []
    for kind, kw in configs:
        trs = cooldown(simulate(sigs, df, max_bars=48, **kw), 2, 1)
        ev = evaluate(trs)
        if ev is None: continue
        label = kind + " " + " ".join(f"{k}={v}" for k, v in kw.items())
        rows.append({"label": label, **ev})

    dfr = pd.DataFrame(rows)
    dfr.to_csv("results_bb_rr.csv", index=False, float_format="%.3f")

    print("=== By NET P/L (best money) ===")
    for _, r in dfr.sort_values("net", ascending=False).head(12).iterrows():
        print(f"  {r['label']:<54} trd={r['trades']:>4} WR={r['wr']:4.1f}% net={r['net']:+6.0f} "
              f"PF={r['pf']:.2f} effRR={r['eff_rr']:.2f} DD={r['dd']:4.0f} lm={r['losing_months']}/{r['n_months']} wm={r['worst_month']:+5.0f} mcl={r['mcl']}")

    print("\n=== By EFFECTIVE RR (best reward:risk), with WR>=40% and net>200 ===")
    good = dfr[(dfr["wr"] >= 40) & (dfr["net"] > 200)]
    for _, r in good.sort_values("eff_rr", ascending=False).head(12).iterrows():
        print(f"  {r['label']:<54} trd={r['trades']:>4} WR={r['wr']:4.1f}% net={r['net']:+6.0f} "
              f"PF={r['pf']:.2f} effRR={r['eff_rr']:.2f} DD={r['dd']:4.0f} lm={r['losing_months']}/{r['n_months']} wm={r['worst_month']:+5.0f} mcl={r['mcl']}")

    print(f"\nTotal {time.time()-t0:.1f}s")


if __name__ == "__main__":
    main()
