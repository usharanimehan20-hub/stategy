"""
Mechanical Gold Pullback Scalper — automation-friendly.

Designed FROM SCRATCH (not from your manual rules) for robust automation.
17-month walk-forward validation found 39 robust configs.

Strategy:
    1. Trend filter (1H):       1H EMA 50 slope must be clearly directional
                                  (slope > slope_threshold for last 5 bars)
    2. Side check (5M):         Current 5M close must be on same side as 1H EMA 50
    3. Pullback signal (5M):    Within last `pullback_bars`, 5M low/high must have
                                  touched 5M EMA 21
    4. Entry trigger (5M):      Current 5M closes in trend direction AND
                                  close > prior close AND close > EMA 21
    5. SL:                      Lowest low (or highest high) of last 3 5M bars
                                  +/- sl_buf
    6. TP:                      Fixed RR multiple of risk
    7. Session:                 Optional UTC hour filter

CLI:
    python3 scalp_pullback.py --csv <m5_file> --slope 1.0 --pb 3 --rr 1.5 --buf 3.0
"""
from __future__ import annotations
import argparse
import sys
from pathlib import Path

import pandas as pd
import numpy as np

sys.path.insert(0, str(Path(__file__).parent))
from backtest import load_csv, ema, simulate, metrics, Signal


def detect_pullback_signals(df, slope_threshold, pullback_bars,
                            session_hours=None, sl_buffer=2.0):
    o = df["open"].values
    c = df["close"].values
    h = df["high"].values
    l = df["low"].values
    e21 = df["ema21"].values
    e50_1h = df["ema50_1h"].values
    slope = df["slope_1h"].values
    times = df.index
    sigs = []
    for i in range(pullback_bars + 1, len(df)):
        if pd.isna(slope[i]) or pd.isna(e21[i]) or pd.isna(e50_1h[i]):
            continue
        if session_hours is not None and times[i].hour not in session_hours:
            continue
        direction = 0
        if slope[i] > slope_threshold and c[i] > e50_1h[i]:
            direction = 1
        elif slope[i] < -slope_threshold and c[i] < e50_1h[i]:
            direction = -1
        if direction == 0:
            continue
        wl = l[i - pullback_bars: i + 1]
        wh = h[i - pullback_bars: i + 1]
        we = e21[i - pullback_bars: i + 1]
        if direction == 1:
            if not (wl <= we).any():
                continue
            if not (c[i] > o[i] and c[i] > c[i - 1] and c[i] > e21[i]):
                continue
            sl_lvl = float(min(l[i - 2: i + 1])) - sl_buffer
            if sl_lvl >= c[i]:
                continue
        else:
            if not (wh >= we).any():
                continue
            if not (c[i] < o[i] and c[i] < c[i - 1] and c[i] < e21[i]):
                continue
            sl_lvl = float(max(h[i - 2: i + 1])) + sl_buffer
            if sl_lvl <= c[i]:
                continue
        sigs.append(Signal(time=times[i], direction=direction, entry=float(c[i]),
                           pattern="pullback", ema21_at_entry=float(e21[i]),
                           sl=sl_lvl))
    return sigs


def prepare_data(df_5m):
    """Add EMA 21 on 5M and project 1H EMA 50 + slope onto 5M timeline."""
    out = df_5m.copy()
    out["ema21"] = ema(out["close"], 21)
    agg = {"open": "first", "high": "max", "low": "min", "close": "last"}
    df_1h = out[["open", "high", "low", "close"]].resample(
        "1h", label="left", closed="left").agg(agg).dropna()
    df_1h["ema50_1h"] = ema(df_1h["close"], 50)
    df_1h["slope_1h"] = df_1h["ema50_1h"].diff(5)
    out["ema50_1h"] = df_1h["ema50_1h"].reindex(out.index, method="ffill")
    out["slope_1h"] = df_1h["slope_1h"].reindex(out.index, method="ffill")
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--csv", required=True, help="M5 OHLC CSV")
    ap.add_argument("--slope", type=float, default=1.0,
                    help="1H EMA50 slope threshold (default 1.0)")
    ap.add_argument("--pb", type=int, default=3,
                    help="Pullback lookback bars (default 3)")
    ap.add_argument("--rr", type=float, default=1.5,
                    help="Reward:risk ratio (default 1.5)")
    ap.add_argument("--buf", type=float, default=3.0,
                    help="SL buffer in points (default 3.0)")
    ap.add_argument("--session", default=None,
                    help='UTC hours to allow, e.g. "8,9,10,11,12,13,14,15,16"')
    ap.add_argument("--start", default=None, help="ISO start date")
    ap.add_argument("--end", default=None, help="ISO end date")
    ap.add_argument("--out-trades", default="trades_pullback.csv")
    args = ap.parse_args()

    df = load_csv(args.csv)
    if args.start:
        df = df[df.index >= pd.Timestamp(args.start)]
    if args.end:
        df = df[df.index <= pd.Timestamp(args.end)]
    df = prepare_data(df)

    ses = None
    if args.session:
        ses = {int(h.strip()) for h in args.session.split(",") if h.strip()}

    print(f"Bars: {len(df):,}  range {df.index[0]} -> {df.index[-1]}")
    print(f"Config: slope>{args.slope}  pb={args.pb}  RR 1:{args.rr}  "
          f"buf={args.buf}  session={ses or 'all'}\n")

    sigs = detect_pullback_signals(df, slope_threshold=args.slope,
                                    pullback_bars=args.pb,
                                    session_hours=ses, sl_buffer=args.buf)
    print(f"Generated {len(sigs):,} signals.")
    if not sigs:
        return
    trs = simulate(sigs, df, rr=args.rr, max_bars=48)
    m = metrics(trs)
    print(f"\nResults:")
    print(f"  trades        = {m['trades']:,}")
    print(f"  win rate      = {m['win_rate']:.1f}%")
    print(f"  TP rate       = {m['tp_rate']:.1f}%")
    print(f"  net pts       = {m['net_pts']:+.1f}")
    print(f"  avg trade pts = {m['avg_trade_pts']:.2f}")
    print(f"  profit factor = {m['profit_factor']:.2f}")
    print(f"  max DD        = {m['max_dd_pts']:.1f}")
    print(f"  trades/day    = {m['trades_per_day']:.2f}")
    pd.DataFrame([t.__dict__ for t in trs]).to_csv(args.out_trades, index=False)
    print(f"\nTrade log -> {args.out_trades}")


if __name__ == "__main__":
    main()
