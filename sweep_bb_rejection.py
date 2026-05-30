"""
Test 3 entry configs the user proposed.

Bias: 15M ribbon (close above WMA34 & WMA64 = bullish; below = bearish; persisted).
Drop to 1M for entry. Bullish shown; bearish is the mirror.

  Config 1 "strong+reject+ribbon":
     1M candle dips into/below the band and closes back out (rejection),
     the candle is STRONG (body >= mult x avg body of last 20),
     and closes above Ribbon 1 (close > WMA34 and > WMA64) -> enter.
  Config 2 "reject_only":
     1M candle rejects the band (dips into/below, closes back out, in bias dir) -> enter.
  Config 3 "ribbon_cross":
     1M close crosses above Ribbon 1 (prev close <= ribbon top, now close > both WMAs) -> enter.

SL: pullback swing low/high (last 3 bars) - buffer.  TP: fixed RR (swept).
Reports WR, net, PF, DD, monthly stability, max-consec-loss, walk-forward robustness.

NOTE: only ~3.5 months of 1M data exist, so monthly/fold samples are small.
"""
from __future__ import annotations
import time, itertools
import pandas as pd, numpy as np
from backtest import (load_csv, classify_bias, simulate, metrics, MA_COMBOS, Signal,
                      add_bias_indicators, add_entry_indicators, wma, ema)


def resample(df, rule):
    agg = {"open": "first", "high": "max", "low": "min", "close": "last"}
    return df[["open", "high", "low", "close"]].resample(rule, label="left", closed="left").agg(agg).dropna()


def project_bias(b, idx, src_tf):
    a = b.copy(); a.index = a.index + pd.Timedelta(minutes=src_tf)
    return a.reindex(idx, method="ffill").fillna(0).astype(int)


def add_bb(df, period, mult):
    out = df.copy()
    sma = out["close"].rolling(period).mean(); std = out["close"].rolling(period).std()
    out["bb_up"] = sma + mult * std; out["bb_low"] = sma - mult * std
    return out


def add_ribbon_body(df):
    out = df.copy()
    out["wma34"] = wma(out["close"], 34)
    out["wma64"] = wma(out["close"], 64)
    out["body"] = (out["close"] - out["open"]).abs()
    out["avg_body"] = out["body"].rolling(20).mean()
    return out


def detect(df, bias, config, strong_mult, sl_buf, ses):
    o = df["open"].values; c = df["close"].values
    h = df["high"].values; l = df["low"].values
    bbu = df["bb_up"].values; bbl = df["bb_low"].values
    w34 = df["wma34"].values; w64 = df["wma64"].values
    body = df["body"].values; avgbody = df["avg_body"].values
    times = df.index
    sigs = []
    for i in range(3, len(df)):
        b = bias.iloc[i]
        if b == 0:
            continue
        if ses is not None and times[i].hour not in ses:
            continue
        if pd.isna(bbl[i]) or pd.isna(w64[i]) or pd.isna(avgbody[i]):
            continue
        green = c[i] > o[i]
        red = c[i] < o[i]
        strong = body[i] >= strong_mult * avgbody[i]
        ribbon_top = max(w34[i], w64[i]); ribbon_bot = min(w34[i], w64[i])
        ok = False
        if b == 1:
            reject = (l[i] <= bbl[i]) and (c[i] > bbl[i]) and green
            above_ribbon = (c[i] > w34[i]) and (c[i] > w64[i])
            cross = (c[i] > ribbon_top) and (c[i - 1] <= max(w34[i - 1], w64[i - 1]))
            if config == "strong_reject_ribbon":
                ok = reject and strong and above_ribbon
            elif config == "reject_only":
                ok = reject
            elif config == "ribbon_cross":
                ok = cross and green
            if ok:
                sl_lvl = float(min(l[i - 2:i + 1])) - sl_buf
                if sl_lvl >= c[i]:
                    continue
                sigs.append(Signal(time=times[i], direction=1, entry=float(c[i]),
                                   pattern=config, ema21_at_entry=0.0, sl=sl_lvl))
        else:
            reject = (h[i] >= bbu[i]) and (c[i] < bbu[i]) and red
            below_ribbon = (c[i] < w34[i]) and (c[i] < w64[i])
            cross = (c[i] < ribbon_bot) and (c[i - 1] >= min(w34[i - 1], w64[i - 1]))
            if config == "strong_reject_ribbon":
                ok = reject and strong and below_ribbon
            elif config == "reject_only":
                ok = reject
            elif config == "ribbon_cross":
                ok = cross and red
            if ok:
                sl_lvl = float(max(h[i - 2:i + 1])) + sl_buf
                if sl_lvl <= c[i]:
                    continue
                sigs.append(Signal(time=times[i], direction=-1, entry=float(c[i]),
                                   pattern=config, ema21_at_entry=0.0, sl=sl_lvl))
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
    if m.get("trades", 0) < 30:
        return None
    pnls = np.array([t.pnl_points for t in trades])
    wins = pnls[pnls > 0]; losses = pnls[pnls < 0]
    eff_rr = (wins.mean() / abs(losses.mean())) if len(losses) else 0
    tdf = pd.DataFrame({"t": [t.entry_time for t in trades], "p": pnls})
    tdf["month"] = pd.to_datetime(tdf["t"]).dt.to_period("M")
    monthly = tdf.groupby("month")["p"].sum()
    los = (pnls < 0).astype(int); mcl = cur = 0
    for lv in los:
        if lv: cur += 1; mcl = max(mcl, cur)
        else: cur = 0
    return {"trades": m["trades"], "wr": m["win_rate"], "net": m["net_pts"], "pf": m["profit_factor"],
            "dd": m["max_dd_pts"], "eff_rr": eff_rr, "losing_months": int((monthly < 0).sum()),
            "n_months": len(monthly), "worst_month": float(monthly.min()), "mcl": mcl}


def wf_folds(idx):
    t0, t1 = idx[0], idx[-1]; total = t1 - t0; f = total / 3.5
    return [(t0 + i * (total / 4.5) + 0.6 * f, t0 + i * (total / 4.5) + 1.0 * f) for i in range(3)]


def main():
    t0 = time.time()
    df = add_entry_indicators(load_csv("XAUUSD_M1_202602160516_202605290404.csv"))
    df = add_ribbon_body(df)
    df15 = add_bias_indicators(resample(df, "15min"))
    biases = {
        "15M_ribbon": project_bias(classify_bias(df15, MA_COMBOS["ribbon_only"]), df.index, 15),
        "15M_4MA": project_bias(classify_bias(df15, MA_COMBOS["ribbon_ema55_ema100"]), df.index, 15),
    }
    LONDON_NY = set(range(8, 17))
    folds = wf_folds(df.index)
    print(f"M1 bars={len(df):,}  {df.index[0].date()}..{df.index[-1].date()}  setup {time.time()-t0:.1f}s\n")

    configs = ["strong_reject_ribbon", "reject_only", "ribbon_cross"]
    rows = []
    for cfg in configs:
        for bias_lbl, bias in biases.items():
            for bb_p, bb_m in [(20, 2.0), (30, 1.5)]:
                dfb = add_bb(df, bb_p, bb_m)
                for col in ("wma34", "wma64", "body", "avg_body"):
                    dfb[col] = df[col]
                for ses_lbl, ses in [("all", None), ("LNY", LONDON_NY)]:
                    sigs = detect(dfb, bias, cfg, 1.5, 3.0, ses)
                    if len(sigs) < 30:
                        continue
                    for rr in [1.5, 2.0, 3.0]:
                        trs = cooldown(simulate(sigs, df, rr=rr, max_bars=240), 2, 1)
                        ev = evaluate(trs)
                        if ev is None:
                            continue
                        # walk-forward
                        fnets = []
                        for a, bnd in folds:
                            fs = [s for s in sigs if a <= s.time < bnd]
                            if not fs:
                                fnets = None; break
                            ft = cooldown(simulate(fs, df, rr=rr, max_bars=240), 2, 1)
                            fm = metrics(ft)
                            fnets.append(fm["net_pts"] if fm["trades"] else 0)
                        robust = fnets is not None and all(n > 0 for n in fnets)
                        rows.append({"config": cfg, "bias": bias_lbl, "bb": f"{bb_p},{bb_m}",
                                     "ses": ses_lbl, "rr": rr, "robust": robust, **ev})

    dfr = pd.DataFrame(rows)
    dfr.to_csv("results_bb_rejection.csv", index=False, float_format="%.3f")
    for cfg in configs:
        sub = dfr[dfr["config"] == cfg].sort_values("net", ascending=False)
        print(f"\n===== {cfg}  (top 6 by net) =====")
        if len(sub) == 0:
            print("  no valid configs (too few signals)")
            continue
        for _, r in sub.head(6).iterrows():
            print(f"  bias={r['bias']:<10} BB({r['bb']}) {r['ses']:<3} RR{r['rr']} | "
                  f"trd={r['trades']:>4} WR={r['wr']:4.1f}% net={r['net']:+6.0f} PF={r['pf']:.2f} "
                  f"effRR={r['eff_rr']:.2f} DD={r['dd']:4.0f} lm={r['losing_months']}/{r['n_months']} "
                  f"mcl={r['mcl']} rob={r['robust']}")
    print(f"\nTotal {time.time()-t0:.1f}s")


if __name__ == "__main__":
    main()
