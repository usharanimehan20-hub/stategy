"""
Refined 5M Bollinger Band scalper for gold — automation-ready.

Refinements applied to the original BB strategy:
  1. Bias TF moved 15M -> 30M (more stable, fewer false flips)
  2. ATR ratio filter: skip trades when 5M ATR(14) > 1.5x its 100-bar SMA
     (avoids strong-trend regimes that crush mean-reversion)
  3. Session filter: London + NY only (08:00-17:00 UTC)
  4. Cooldown: after 2 consecutive losing trades, skip 1 hour

Results on 17-month M5 dataset:
  trades=1010  WR=46.4%  net=+791  PF=1.18  max_DD=206
  losing months: 3 of 18  (worst -100)
  vs foundation: WR +8pp, P/L 2.7x, DD -80%, worst month -75%
"""
from __future__ import annotations
import argparse
from typing import Optional
import pandas as pd
import numpy as np
from backtest import (load_csv, classify_bias, simulate, metrics, MA_COMBOS, Signal,
                      add_bias_indicators, add_entry_indicators)


LONDON_NY = set(range(8, 17))


def project_bias(b: pd.Series, idx: pd.DatetimeIndex, src_tf_min: int) -> pd.Series:
    a = b.copy()
    a.index = a.index + pd.Timedelta(minutes=src_tf_min)
    return a.reindex(idx, method="ffill").fillna(0).astype(int)


def add_bb(df: pd.DataFrame, period: int = 30, mult: float = 1.5) -> pd.DataFrame:
    out = df.copy()
    sma = out["close"].rolling(period).mean()
    std = out["close"].rolling(period).std()
    out["bb_up"] = sma + mult * std
    out["bb_low"] = sma - mult * std
    return out


def add_atr_ratio(df: pd.DataFrame, atr_period: int = 14, ratio_window: int = 100) -> pd.DataFrame:
    out = df.copy()
    tr = pd.concat([(out["high"] - out["low"]),
                    (out["high"] - out["close"].shift(1)).abs(),
                    (out["low"] - out["close"].shift(1)).abs()], axis=1).max(axis=1)
    out["atr14"] = tr.rolling(atr_period).mean()
    out["atr_ratio"] = out["atr14"] / out["atr14"].rolling(ratio_window).mean()
    return out


def detect_bb_signals(df_bb, bias, pullback_bars=3, sl_buffer=3.0,
                      session_hours=None, atr_max=None):
    o, c, h, l = df_bb["open"].values, df_bb["close"].values, df_bb["high"].values, df_bb["low"].values
    bbu, bbl = df_bb["bb_up"].values, df_bb["bb_low"].values
    atr_r = df_bb["atr_ratio"].values if "atr_ratio" in df_bb.columns else None
    times = df_bb.index
    sigs = []
    for i in range(pullback_bars + 1, len(df_bb)):
        b = bias.iloc[i]
        if b == 0:
            continue
        if session_hours is not None and times[i].hour not in session_hours:
            continue
        if pd.isna(bbu[i]) or pd.isna(bbl[i]):
            continue
        if atr_max is not None and atr_r is not None:
            if pd.isna(atr_r[i]) or atr_r[i] > atr_max:
                continue
        if b == 1:
            if not (l[i - pullback_bars: i + 1] <= bbl[i - pullback_bars: i + 1]).any():
                continue
            if not (c[i] > o[i] and c[i] > c[i - 1]):
                continue
            sl_lvl = float(min(l[i - pullback_bars: i + 1])) - sl_buffer
            if sl_lvl >= c[i]:
                continue
        else:
            if not (h[i - pullback_bars: i + 1] >= bbu[i - pullback_bars: i + 1]).any():
                continue
            if not (c[i] < o[i] and c[i] < c[i - 1]):
                continue
            sl_lvl = float(max(h[i - pullback_bars: i + 1])) + sl_buffer
            if sl_lvl <= c[i]:
                continue
        sigs.append(Signal(time=times[i], direction=int(b), entry=float(c[i]),
                           pattern="bb", ema21_at_entry=0.0, sl=sl_lvl))
    return sigs


def apply_cooldown(trades, n_consec_losses=2, cooldown_hours=1):
    if not trades:
        return trades
    out = []
    consec = 0
    cd_until = None
    for t in trades:
        if cd_until is not None and t.entry_time < cd_until:
            continue
        out.append(t)
        if t.pnl_points < 0:
            consec += 1
            if consec >= n_consec_losses:
                cd_until = t.exit_time + pd.Timedelta(hours=cooldown_hours)
                consec = 0
        else:
            consec = 0
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--csv", required=True)
    ap.add_argument("--bb-period", type=int, default=30)
    ap.add_argument("--bb-mult", type=float, default=1.5)
    ap.add_argument("--pullback", type=int, default=3)
    ap.add_argument("--sl-buf", type=float, default=3.0)
    ap.add_argument("--rr", type=float, default=1.5)
    ap.add_argument("--atr-max", type=float, default=1.5)
    ap.add_argument("--cooldown-losses", type=int, default=2)
    ap.add_argument("--cooldown-hours", type=int, default=1)
    ap.add_argument("--bias-tf", type=int, default=30)
    ap.add_argument("--ma-combo", default="ribbon_only")
    ap.add_argument("--session", default="lny", choices=("all", "lny", "hot8"))
    ap.add_argument("--out-trades", default="trades_bb_refined.csv")
    args = ap.parse_args()

    df = load_csv(args.csv)
    df = add_entry_indicators(df)
    df = add_atr_ratio(df)
    df_bb = add_bb(df, args.bb_period, args.bb_mult)
    df_bb["atr14"] = df["atr14"]
    df_bb["atr_ratio"] = df["atr_ratio"]

    agg = {"open": "first", "high": "max", "low": "min", "close": "last"}
    rule = f"{args.bias_tf}min"
    df_bias = df[["open", "high", "low", "close"]].resample(rule, label="left", closed="left").agg(agg).dropna()
    df_bias = add_bias_indicators(df_bias)
    bias = project_bias(classify_bias(df_bias, MA_COMBOS[args.ma_combo]), df.index, args.bias_tf)

    if args.session == "all":
        ses = None
    elif args.session == "lny":
        ses = LONDON_NY
    else:
        ses = {2, 5, 8, 13, 14, 15, 16, 22}

    sigs = detect_bb_signals(df_bb, bias, args.pullback, args.sl_buf, ses, args.atr_max)
    print(f"Generated {len(sigs):,} signals")
    trs = simulate(sigs, df, rr=args.rr, max_bars=48)
    if args.cooldown_losses > 0 and args.cooldown_hours > 0:
        trs = apply_cooldown(trs, args.cooldown_losses, args.cooldown_hours)

    m = metrics(trs)
    print(f"\nResults:")
    print(f"  trades        = {m['trades']:,}")
    print(f"  win rate      = {m['win_rate']:.1f}%")
    print(f"  TP rate       = {m['tp_rate']:.1f}%")
    print(f"  net pts       = {m['net_pts']:+.1f}")
    print(f"  profit factor = {m['profit_factor']:.2f}")
    print(f"  max DD        = {m['max_dd_pts']:.1f}")
    print(f"  trades/day    = {m['trades_per_day']:.2f}")

    tdf = pd.DataFrame([{"entry_time": t.entry_time, "pnl": t.pnl_points} for t in trs])
    tdf["month"] = pd.to_datetime(tdf["entry_time"]).dt.to_period("M")
    monthly = tdf.groupby("month").agg(trades=("pnl", "count"), net=("pnl", "sum"),
                                        wr=("pnl", lambda x: (x > 0).mean() * 100)).round(2)
    print(f"\nMonthly P/L:\n{monthly.to_string()}")
    print(f"\nLosing months: {(monthly['net'] < 0).sum()} of {len(monthly)}")
    print(f"Worst: {monthly['net'].min():+.0f}  Best: {monthly['net'].max():+.0f}")
    pd.DataFrame([t.__dict__ for t in trs]).to_csv(args.out_trades, index=False)
    print(f"\nTrade log -> {args.out_trades}")


if __name__ == "__main__":
    main()
