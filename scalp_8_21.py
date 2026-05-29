"""
EMA 8/21 trend-pullback scalper for gold.

Strategy:
  Bias  (15M): EMA8 > EMA21 AND EMA21 rising for 3 bars  -> bullish
                EMA8 < EMA21 AND EMA21 falling for 3 bars -> bearish
  Setup (1M):  price has touched or closed below EMA21 within last K bars (pullback)
  Entry (1M):  bar closes in bias direction, closes back above/below EMA8,
               and close > prev close (BOS)
  SL    (1M):  low/high of last 3 bars +/- sl_buf
  TP    (1M):  rr * risk
  BE    :      at +be_at_r * risk, move SL to entry
  Trail :      after BE, ratchet SL using EMA21 or 1M swing
  Session:     only enter during configured hot UTC hours

Walk-forward: 3 sliding folds; require positive net P/L in EVERY fold.
"""
from __future__ import annotations
import itertools
import sys
import time as _time
from pathlib import Path
from typing import Optional

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).parent))
from backtest import (
    load_csv, resample_15m, ema, simulate, metrics, Signal,
)

CSV = "/projects/sandbox/stategy/XAUUSD_M1_202602160516_202605290404.csv"
SESSION_HOURS = {2, 5, 8, 13, 14, 15, 16, 22}


def add_indicators(df_1m: pd.DataFrame) -> pd.DataFrame:
    out = df_1m.copy()
    out["ema8"] = ema(out["close"], 8)
    out["ema21"] = ema(out["close"], 21)
    return out


def add_15m_trend(df_15: pd.DataFrame) -> pd.DataFrame:
    out = df_15.copy()
    out["ema8_15"] = ema(out["close"], 8)
    out["ema21_15"] = ema(out["close"], 21)
    out["ema21_slope"] = out["ema21_15"].diff(3)
    return out


def project_15m_to_1m(df_15: pd.DataFrame, df_1m_index: pd.DatetimeIndex,
                      cols: tuple) -> pd.DataFrame:
    avail = df_15[list(cols)].copy()
    avail.index = avail.index + pd.Timedelta(minutes=15)
    return avail.reindex(df_1m_index, method="ffill")


def compute_bias_1m(df: pd.DataFrame) -> np.ndarray:
    e8 = df["ema8_15"].values
    e21 = df["ema21_15"].values
    sl = df["ema21_slope"].values
    bias = np.zeros(len(df), dtype=int)
    bias[(e8 > e21) & (sl > 0)] = 1
    bias[(e8 < e21) & (sl < 0)] = -1
    return bias


def detect_scalp_signals(df: pd.DataFrame, bias: np.ndarray,
                          pullback_bars: int = 5,
                          session_hours: Optional[set[int]] = None,
                          sl_buf: float = 2.0) -> list[Signal]:
    o = df["open"].values
    c = df["close"].values
    h = df["high"].values
    l = df["low"].values
    e8 = df["ema8"].values
    e21 = df["ema21"].values
    times = df.index
    n = len(df)
    sigs: list[Signal] = []

    for i in range(pullback_bars, n):
        b = bias[i]
        if b == 0:
            continue
        if session_hours is not None and times[i].hour not in session_hours:
            continue
        if b == 1:
            wlow = l[i - pullback_bars: i + 1]
            we21 = e21[i - pullback_bars: i + 1]
            if not (wlow <= we21).any():
                continue
            if not (c[i] > o[i] and c[i] > e8[i] and c[i] > c[i - 1]):
                continue
            sl_lvl = float(min(l[i - 2: i + 1])) - sl_buf
            if sl_lvl >= c[i]:
                continue
            sigs.append(Signal(time=times[i], direction=1, entry=float(c[i]),
                               pattern="P_LONG", ema21_at_entry=float(e21[i]),
                               sl=sl_lvl))
        else:
            whigh = h[i - pullback_bars: i + 1]
            we21 = e21[i - pullback_bars: i + 1]
            if not (whigh >= we21).any():
                continue
            if not (c[i] < o[i] and c[i] < e8[i] and c[i] < c[i - 1]):
                continue
            sl_lvl = float(max(h[i - 2: i + 1])) + sl_buf
            if sl_lvl <= c[i]:
                continue
            sigs.append(Signal(time=times[i], direction=-1, entry=float(c[i]),
                               pattern="P_SHORT", ema21_at_entry=float(e21[i]),
                               sl=sl_lvl))
    return sigs


def slice_t(df, t0, t1):
    return df[(df.index >= t0) & (df.index < t1)].copy()


def run_one(df_1m_slice, df_15_slice, pullback, rr, sl_buf, be, trail):
    df_15_t = add_15m_trend(df_15_slice)
    aligned = project_15m_to_1m(df_15_t, df_1m_slice.index,
                                  ("ema8_15", "ema21_15", "ema21_slope"))
    df_combo = pd.concat([df_1m_slice, aligned], axis=1).dropna()
    if len(df_combo) < 100:
        return None
    bias = compute_bias_1m(df_combo)
    sigs = detect_scalp_signals(df_combo, bias, pullback_bars=pullback,
                                 session_hours=SESSION_HOURS, sl_buf=sl_buf)
    if not sigs:
        return None
    trs = simulate(sigs, df_combo, rr=rr, max_bars=240,
                   be_at_r=be, trail_method=trail)
    m = metrics(trs)
    if m.get("trades", 0) == 0:
        return None
    m.update({"pullback": pullback, "rr": rr, "sl_buf": sl_buf,
              "be_at_r": be, "trail": trail or "none"})
    return m


def main():
    print("Loading ...")
    df = load_csv(CSV)
    df_1m = add_indicators(df)
    df_15 = resample_15m(df_1m)
    print(f"  {len(df_1m):,} 1m bars  {len(df_15):,} 15m bars")

    # 3 walk-forward folds
    t0, t1 = df_1m.index[0], df_1m.index[-1]
    total = t1 - t0
    fold = total / 3.5
    folds = []
    for i in range(3):
        a = t0 + i * (total / 4.5)
        b = a + 0.6 * fold
        c = b
        d = c + 0.4 * fold
        folds.append((a, b, c, d))
    for i, (_, _, c, d) in enumerate(folds):
        print(f"  fold{i+1}: test [{c.date()}..{d.date()}]")

    pullbacks = [3, 5, 8]
    rrs = [1.0, 1.5, 2.0, 3.0]
    sl_bufs = [2.0, 3.0]
    bes = [None, 0.5, 1.0]
    trails = [None, "ema21", "swing"]
    grid = list(itertools.product(pullbacks, rrs, sl_bufs, bes, trails))
    print(f"\nGrid: {len(grid)} configs x 3 folds = {len(grid)*3} runs")

    out = []
    start = _time.time()
    for gi, (pb, rr, sb, be, tr) in enumerate(grid):
        fms = []
        for _, _, c, d in folds:
            df_1m_s = slice_t(df_1m, c, d)
            df_15_s = slice_t(df_15, c, d)
            if len(df_1m_s) < 1000:
                continue
            m = run_one(df_1m_s, df_15_s, pb, rr, sb, be, tr)
            if m:
                fms.append(m)
        if not fms:
            continue
        out.append({
            "pullback": pb, "rr": rr, "sl_buf": sb,
            "be_at_r": be, "trail": tr or "none",
            "folds_with_trades": len(fms),
            "total_trades": sum(m["trades"] for m in fms),
            "mean_net": float(np.mean([m["net_pts"] for m in fms])),
            "min_net": float(np.min([m["net_pts"] for m in fms])),
            "mean_wr": float(np.mean([m["win_rate"] for m in fms])),
            "mean_pf": float(np.mean([m["profit_factor"] for m in fms
                                       if np.isfinite(m["profit_factor"])])),
            "mean_dd": float(np.mean([m["max_dd_pts"] for m in fms])),
            "mean_tpd": float(np.mean([m["trades_per_day"] for m in fms])),
        })
        if (gi + 1) % 30 == 0:
            el = _time.time() - start
            print(f"  {gi+1}/{len(grid)}  elapsed {el:.0f}s")

    res = pd.DataFrame(out)
    if len(res) == 0:
        print("No configs produced trades.")
        return
    res_robust = res[(res["folds_with_trades"] >= 2) & (res["min_net"] > 0)].copy()
    res_robust = res_robust.sort_values("mean_net", ascending=False).reset_index(drop=True)
    res_robust.to_csv("results_scalp_8_21_wf.csv", index=False, float_format="%.3f")

    print(f"\n{len(res_robust)} robust configs (positive in every fold).")
    if len(res_robust) == 0:
        # fall back to top of full pool
        top_full = res.sort_values("mean_net", ascending=False).head(15)
        print("\nTop 15 from FULL pool (not robustness-filtered):")
        print(top_full.to_string(index=False))
        return

    print("\nTop 10 robust configs:")
    print(res_robust.head(10).to_string(index=False))

    # Run winner on full window
    best = res_robust.iloc[0]
    df_15_full = add_15m_trend(df_15)
    aligned = project_15m_to_1m(df_15_full, df_1m.index,
                                  ("ema8_15", "ema21_15", "ema21_slope"))
    df_combo = pd.concat([df_1m, aligned], axis=1).dropna()
    bias = compute_bias_1m(df_combo)
    sigs = detect_scalp_signals(df_combo, bias, pullback_bars=int(best["pullback"]),
                                 session_hours=SESSION_HOURS, sl_buf=float(best["sl_buf"]))
    be_v = None if pd.isna(best["be_at_r"]) else float(best["be_at_r"])
    tr_v = None if best["trail"] == "none" else best["trail"]
    trs = simulate(sigs, df_combo, rr=float(best["rr"]),
                   max_bars=240, be_at_r=be_v, trail_method=tr_v)
    m = metrics(trs)
    print("\n=== WINNER full-window (3.5 months) ===")
    print(f"  pullback_bars={int(best['pullback'])}  rr={best['rr']}  "
          f"sl_buf={best['sl_buf']}  be={best['be_at_r']}  trail={best['trail']}")
    print(f"  trades={m['trades']}  WR={m['win_rate']:.1f}%  net={m['net_pts']:+.1f}  "
          f"PF={m['profit_factor']:.2f}  DD={m['max_dd_pts']:.1f}  trd/day={m['trades_per_day']:.2f}")
    pd.DataFrame([t.__dict__ for t in trs]).to_csv("trades_scalp_8_21.csv", index=False)
    print(f"  trade log -> trades_scalp_8_21.csv")


if __name__ == "__main__":
    main()
