"""
Gold (XAUUSD) — Multi-MA Bias + Candle Theory Backtester
=========================================================

Strategy: see STRATEGY.md

Usage:
    python3 backtest.py --csv path/to/xauusd_1m.csv
    python3 backtest.py --csv path/to/xauusd_1m.csv --tz UTC
    python3 backtest.py --csv path/to/xauusd_1m.csv --quick   # smaller matrix

CSV expected columns (case-insensitive):
    timestamp (or time/date/datetime), open, high, low, close

The 15-minute bias series is built internally by resampling the 1-min data.
"""

from __future__ import annotations
import argparse
import itertools
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

import numpy as np
import pandas as pd


# ---------------------------------------------------------------------------
# 1. Data loading
# ---------------------------------------------------------------------------

def load_csv(path: str, tz: Optional[str] = None) -> pd.DataFrame:
    """
    Load OHLC CSV with flexible format. Supports:
      - Comma-separated with timestamp column
      - MetaTrader TSV with <DATE> <TIME> <OPEN> <HIGH> <LOW> <CLOSE> ...
      - Either separate date/time or single timestamp
    """
    # Auto-detect separator: try tab first (MetaTrader), then comma
    with open(path, "r") as fh:
        first = fh.readline()
    sep = "\t" if "\t" in first else ","
    df = pd.read_csv(path, sep=sep)

    # Strip angle brackets and lowercase
    df.columns = [c.strip().strip("<>").lower() for c in df.columns]

    # Build timestamp
    if "timestamp" in df.columns:
        df["timestamp"] = pd.to_datetime(df["timestamp"])
    elif "datetime" in df.columns:
        df["timestamp"] = pd.to_datetime(df["datetime"])
    elif "date" in df.columns and "time" in df.columns:
        # MetaTrader format: 2026.02.16 + 05:16:00
        date_str = df["date"].astype(str).str.replace(".", "-", regex=False)
        df["timestamp"] = pd.to_datetime(date_str + " " + df["time"].astype(str))
    elif "date" in df.columns:
        df["timestamp"] = pd.to_datetime(df["date"])
    else:
        raise ValueError(f"Could not derive a timestamp from columns: {df.columns.tolist()}")

    # OHLC columns are already lowercased without brackets
    missing = {"open", "high", "low", "close"} - set(df.columns)
    if missing:
        raise ValueError(f"Missing required columns: {missing}")

    df = df[["timestamp", "open", "high", "low", "close"]].copy()
    df = df.sort_values("timestamp").drop_duplicates("timestamp").reset_index(drop=True)
    df = df.set_index("timestamp")

    if tz:
        if df.index.tz is None:
            df.index = df.index.tz_localize(tz)
        else:
            df.index = df.index.tz_convert(tz)

    return df


def resample_15m(df_1m: pd.DataFrame) -> pd.DataFrame:
    """Resample 1-min OHLC to 15-min OHLC."""
    agg = {"open": "first", "high": "max", "low": "min", "close": "last"}
    df_15 = df_1m.resample("15min", label="left", closed="left").agg(agg).dropna()
    return df_15


def resample_30m(df: pd.DataFrame) -> pd.DataFrame:
    """Resample any-TF OHLC to 30-min OHLC."""
    agg = {"open": "first", "high": "max", "low": "min", "close": "last"}
    return df.resample("30min", label="left", closed="left").agg(agg).dropna()


# ---------------------------------------------------------------------------
# 2. Indicators
# ---------------------------------------------------------------------------

def wma(s: pd.Series, length: int) -> pd.Series:
    weights = np.arange(1, length + 1, dtype=float)
    return s.rolling(length).apply(lambda x: np.dot(x, weights) / weights.sum(), raw=True)


def ema(s: pd.Series, length: int) -> pd.Series:
    return s.ewm(span=length, adjust=False).mean()


def add_bias_indicators(df_15: pd.DataFrame) -> pd.DataFrame:
    out = df_15.copy()
    out["wma34"] = wma(out["close"], 34)
    out["wma64"] = wma(out["close"], 64)
    out["ema55"] = ema(out["close"], 55)
    out["ema100"] = ema(out["close"], 100)
    return out


def add_entry_indicators(df_1m: pd.DataFrame) -> pd.DataFrame:
    out = df_1m.copy()
    out["ema8"] = ema(out["close"], 8)
    out["ema21"] = ema(out["close"], 21)
    return out


# ---------------------------------------------------------------------------
# 3. Bias classification
# ---------------------------------------------------------------------------

# MA combos to test
MA_COMBOS = {
    "ribbon_only":          ("wma34", "wma64"),
    "ribbon_ema55":         ("wma34", "wma64", "ema55"),
    "ribbon_ema100":        ("wma34", "wma64", "ema100"),
    "ribbon_ema55_ema100":  ("wma34", "wma64", "ema55", "ema100"),  # full setup
}


def classify_bias(df_15: pd.DataFrame, ma_cols: tuple[str, ...]) -> pd.Series:
    """
    Returns a series of {1, -1, 0} per 15M bar:
        +1 = bullish (close strictly above all MAs in combo)
        -1 = bearish (close strictly below all MAs in combo)
         0 = mixed / no bias

    Bias **persists** until invalidated by an opposite-direction qualifying close.
    """
    close = df_15["close"]
    above = pd.concat([close > df_15[c] for c in ma_cols], axis=1).all(axis=1)
    below = pd.concat([close < df_15[c] for c in ma_cols], axis=1).all(axis=1)

    raw = pd.Series(0, index=df_15.index, dtype=int)
    raw[above] = 1
    raw[below] = -1

    # Persist last non-zero bias
    bias = raw.replace(0, np.nan).ffill().fillna(0).astype(int)
    return bias


def project_bias_to_1m(bias_15: pd.Series, df_1m: pd.DataFrame) -> pd.Series:
    """
    For each 1-min bar, the active bias = bias of the LAST CLOSED 15M bar.
    A 15M bar at time T closes at T+15min, so its bias is available from T+15min onwards.
    """
    bias_avail = bias_15.copy()
    bias_avail.index = bias_avail.index + pd.Timedelta(minutes=15)
    aligned = bias_avail.reindex(df_1m.index, method="ffill").fillna(0).astype(int)
    return aligned


# ---------------------------------------------------------------------------
# 4. Entry detection (Candle Theory)
# ---------------------------------------------------------------------------

@dataclass
class Signal:
    time: pd.Timestamp
    direction: int       # +1 long, -1 short
    entry: float         # entry price (close of confirmation candle)
    pattern: str         # "P1" or "P2"
    ema21_at_entry: float
    sl: float = 0.0      # pre-computed SL level (raw, before buffer is added)


def resample_3m(df_1m: pd.DataFrame) -> pd.DataFrame:
    """Resample 1-min OHLC to 3-min OHLC."""
    agg = {"open": "first", "high": "max", "low": "min", "close": "last"}
    return df_1m.resample("3min", label="left", closed="left").agg(agg).dropna()


def find_swings_3m(df_3m: pd.DataFrame) -> tuple[np.ndarray, np.ndarray]:
    """
    Find 3-bar fractal swing highs/lows on 3-minute data.
    A swing high at bar i: high[i] > high[i-1] AND high[i] > high[i+1].
    Returns two boolean arrays aligned with df_3m: (swing_high, swing_low).
    Bar i's swing status is only confirmed once bar i+1 has closed.
    """
    h = df_3m["high"].values
    l = df_3m["low"].values
    n = len(df_3m)
    sh = np.zeros(n, dtype=bool)
    sl = np.zeros(n, dtype=bool)
    for i in range(1, n - 1):
        if h[i] > h[i - 1] and h[i] > h[i + 1]:
            sh[i] = True
        if l[i] < l[i - 1] and l[i] < l[i + 1]:
            sl[i] = True
    return sh, sl


def latest_swing_sl(entry_time: pd.Timestamp, direction: int,
                    df_3m: pd.DataFrame, sh: np.ndarray, sl: np.ndarray,
                    buffer_pts: float, lookback_bars: int = 10) -> Optional[float]:
    """
    Find the most recent confirmed 3M swing high/low strictly before entry_time
    within the last `lookback_bars` 3M bars (default 10 bars = 30 min, what a
    screen-trader actually sees as the relevant structure).

    For long: SL = swing_low - buffer. For short: SL = swing_high + buffer.

    Confirmation lag: a swing at 3M bar i is only confirmed once bar i+1 closes,
    so we require the swing bar's index <= position(entry_time) - 2.

    Fallback: if no confirmed fractal swing in the lookback window, use the
    extreme low/high of the lookback window itself (Donchian-style).
    """
    pos = df_3m.index.searchsorted(entry_time, side="right") - 1
    confirmed_max_idx = pos - 1
    lookback_min_idx = max(0, pos - lookback_bars)
    if confirmed_max_idx < lookback_min_idx:
        return None

    if direction == 1:
        # Look for fractal swing low in the lookback window
        idxs = np.where(sl[lookback_min_idx: confirmed_max_idx + 1])[0]
        if len(idxs) > 0:
            last = lookback_min_idx + idxs[-1]
            return float(df_3m["low"].iloc[last]) - buffer_pts
        # Fallback: lowest low in the lookback window
        return float(df_3m["low"].iloc[lookback_min_idx: pos + 1].min()) - buffer_pts
    else:
        idxs = np.where(sh[lookback_min_idx: confirmed_max_idx + 1])[0]
        if len(idxs) > 0:
            last = lookback_min_idx + idxs[-1]
            return float(df_3m["high"].iloc[last]) + buffer_pts
        return float(df_3m["high"].iloc[lookback_min_idx: pos + 1].max()) + buffer_pts


def detect_signals(df_1m: pd.DataFrame, df_15: pd.DataFrame,
                   bias_15: pd.Series, pattern: str = "both",
                   wait_bars: int = 15,
                   sl_method: str = "ema21",
                   sl_buffer: float = 2.0,
                   df_3m: Optional[pd.DataFrame] = None,
                   swing_high: Optional[np.ndarray] = None,
                   swing_low: Optional[np.ndarray] = None,
                   session_hours: Optional[set[int]] = None,
                   bias_tf_minutes: int = 15) -> list[Signal]:
    """
    Candle Theory — setup on 15M, entry trigger on 1M.

    For each completed 15M bar (the "setup candle"):
        Pattern 1 (long bias):  setup is GREEN (close>open)
                                during next 15M window watch 1-min bars
                                first 1M with (close>open) AND (close>prev_1M_close) -> ENTRY
        Pattern 2 (long bias):  setup is RED (close<open)
                                during next 15M window watch 1-min bars
                                a 1M HIGH must first break the setup candle's HIGH
                                then first 1M with (close>open) AND (close>prev_1M_close) -> ENTRY
                                (break and body-close can be the same 1M bar)
        Bearish bias = mirror.

    `wait_bars` = number of 1-min bars after setup-candle close during which the
                  setup remains armed. Default 15 = exactly the next 15M window.
    """
    o15 = df_15["open"].values
    c15 = df_15["close"].values
    h15 = df_15["high"].values
    l15 = df_15["low"].values
    t15 = df_15.index

    bias_arr = bias_15.values

    o1 = df_1m["open"].values
    c1 = df_1m["close"].values
    h1 = df_1m["high"].values
    l1 = df_1m["low"].values
    e21_1 = df_1m["ema21"].values
    t1 = df_1m.index
    pos1 = {t: i for i, t in enumerate(t1)}

    signals: list[Signal] = []

    for i in range(len(df_15) - 1):
        b = int(bias_arr[i])
        if b == 0:
            continue

        is_green = c15[i] > o15[i]
        is_red = c15[i] < o15[i]

        is_p1 = (b == 1 and is_green) or (b == -1 and is_red)
        is_p2 = (b == 1 and is_red) or (b == -1 and is_green)

        if pattern == "P1" and not is_p1:
            continue
        if pattern == "P2" and not is_p2:
            continue
        if pattern == "both" and not (is_p1 or is_p2):
            continue
        which = "P1" if is_p1 else "P2"

        # Setup-candle closes at t15[i] + bias_tf_minutes; entry window is the next bias bar
        setup_close = t15[i] + pd.Timedelta(minutes=bias_tf_minutes)
        start_idx = pos1.get(setup_close)
        if start_idx is None:
            continue
        end_idx = min(start_idx + wait_bars, len(df_1m))

        # For P2, find the high/low break first
        scan_start = start_idx
        if which == "P2":
            target = h15[i] if b == 1 else l15[i]
            broke_at = None
            for j in range(start_idx, end_idx):
                if (b == 1 and h1[j] > target) or (b == -1 and l1[j] < target):
                    broke_at = j
                    break
            if broke_at is None:
                continue
            scan_start = broke_at  # break and body-close may be same bar

        # First 1M body close in bias direction with BOS (close vs prev close)
        for j in range(max(scan_start, 1), end_idx):
            body_ok = (b == 1 and c1[j] > o1[j]) or (b == -1 and c1[j] < o1[j])
            bos_ok = (b == 1 and c1[j] > c1[j - 1]) or (b == -1 and c1[j] < c1[j - 1])
            if body_ok and bos_ok:
                # Session filter (entry hour)
                if session_hours is not None and t1[j].hour not in session_hours:
                    break  # setup expired this window if hour disallowed
                # Pre-compute SL based on chosen method
                if sl_method == "swing3m":
                    sl_lvl = latest_swing_sl(t1[j], b, df_3m, swing_high, swing_low, sl_buffer)
                    if sl_lvl is None:
                        break
                    # Validity check: SL must be on correct side of entry
                    if (b == 1 and sl_lvl >= c1[j]) or (b == -1 and sl_lvl <= c1[j]):
                        break
                else:  # "ema21"
                    sl_lvl = (e21_1[j] - sl_buffer) if b == 1 else (e21_1[j] + sl_buffer)
                signals.append(Signal(
                    time=t1[j], direction=b, entry=float(c1[j]),
                    pattern=which, ema21_at_entry=float(e21_1[j]),
                    sl=float(sl_lvl),
                ))
                break  # one entry per setup
    return signals


# ---------------------------------------------------------------------------
# 5. Trade simulation
# ---------------------------------------------------------------------------

@dataclass
class Trade:
    entry_time: pd.Timestamp
    exit_time: pd.Timestamp
    direction: int
    pattern: str
    entry: float
    sl: float
    tp: float
    exit_price: float
    pnl_points: float
    bars_held: int
    outcome: str  # "TP", "SL", "EOD"


def simulate(signals: list[Signal], df_1m: pd.DataFrame,
             rr: float,
             spread_pts: float = 0.3,
             max_bars: int = 240) -> list[Trade]:
    """
    For each signal, use the pre-computed `sig.sl`, derive TP from RR x risk.
    Walk forward bar-by-bar; if same bar hits both, assume SL first (conservative).
    No pyramiding: skip new signals while a position is open.
    """
    trades: list[Trade] = []
    h = df_1m["high"].values
    l = df_1m["low"].values
    times = df_1m.index
    pos_to_idx = {t: i for i, t in enumerate(times)}

    busy_until = -1
    for sig in signals:
        i0 = pos_to_idx.get(sig.time)
        if i0 is None or i0 < busy_until:
            continue

        sl = sig.sl
        if sig.direction == 1:
            if sl >= sig.entry:
                continue
            risk = sig.entry - sl
            tp = sig.entry + rr * risk
        else:
            if sl <= sig.entry:
                continue
            risk = sl - sig.entry
            tp = sig.entry - rr * risk

        outcome = "EOD"
        exit_price = sig.entry
        exit_time = sig.time
        bars_held = 0

        for j in range(i0 + 1, min(i0 + 1 + max_bars, len(df_1m))):
            bar_h, bar_l = h[j], l[j]
            bars_held += 1
            if sig.direction == 1:
                hit_sl = bar_l <= sl
                hit_tp = bar_h >= tp
            else:
                hit_sl = bar_h >= sl
                hit_tp = bar_l <= tp

            if hit_sl and hit_tp:
                outcome = "SL"
                exit_price = sl
                exit_time = times[j]
                break
            if hit_sl:
                outcome = "SL"
                exit_price = sl
                exit_time = times[j]
                break
            if hit_tp:
                outcome = "TP"
                exit_price = tp
                exit_time = times[j]
                break
        else:
            # Didn't hit either within max_bars; close at last close
            j = min(i0 + max_bars, len(df_1m) - 1)
            exit_price = df_1m["close"].iloc[j]
            exit_time = times[j]

        if sig.direction == 1:
            pnl = exit_price - sig.entry - spread_pts
        else:
            pnl = sig.entry - exit_price - spread_pts

        trades.append(Trade(
            entry_time=sig.time, exit_time=exit_time, direction=sig.direction,
            pattern=sig.pattern, entry=sig.entry, sl=sl, tp=tp,
            exit_price=exit_price, pnl_points=pnl, bars_held=bars_held,
            outcome=outcome,
        ))
        busy_until = pos_to_idx.get(exit_time, i0 + bars_held) + 1

    return trades


# ---------------------------------------------------------------------------
# 6. Metrics
# ---------------------------------------------------------------------------

def metrics(trades: list[Trade]) -> dict:
    if not trades:
        return {"trades": 0}
    pnl = np.array([t.pnl_points for t in trades])
    wins = pnl[pnl > 0]
    losses = pnl[pnl <= 0]
    gross_w = wins.sum() if len(wins) else 0.0
    gross_l = -losses.sum() if len(losses) else 0.0

    # Equity curve & drawdown
    eq = np.cumsum(pnl)
    peak = np.maximum.accumulate(eq)
    dd = peak - eq
    max_dd = dd.max() if len(dd) else 0.0

    days = (trades[-1].exit_time - trades[0].entry_time).total_seconds() / 86400
    tpd = len(trades) / max(days, 1e-9)

    return {
        "trades": len(trades),
        "win_rate": len(wins) / len(trades) * 100,
        "net_pts": pnl.sum(),
        "avg_trade_pts": pnl.mean(),
        "profit_factor": (gross_w / gross_l) if gross_l > 0 else float("inf"),
        "max_dd_pts": max_dd,
        "trades_per_day": tpd,
        "tp_rate": sum(1 for t in trades if t.outcome == "TP") / len(trades) * 100,
        "sl_rate": sum(1 for t in trades if t.outcome == "SL") / len(trades) * 100,
        "p1_share": sum(1 for t in trades if t.pattern == "P1") / len(trades) * 100,
        "p2_share": sum(1 for t in trades if t.pattern == "P2") / len(trades) * 100,
    }


# ---------------------------------------------------------------------------
# 7. Matrix runner
# ---------------------------------------------------------------------------

def run_matrix(df_lower: pd.DataFrame, df_15: pd.DataFrame,
               wait_bars: int, max_bars: int,
               sl_method: str = "ema21",
               df_3m: Optional[pd.DataFrame] = None,
               swing_high: Optional[np.ndarray] = None,
               swing_low: Optional[np.ndarray] = None,
               session_hours: Optional[set[int]] = None,
               bias_tf_minutes: int = 15,
               rr_grid=(1.0, 1.5, 2.0, 3.0, 4.0, 5.0),
               buf_grid=(2.0, 3.0),
               patterns=("P1", "P2", "both")) -> pd.DataFrame:
    """
    df_lower: timeframe used for entry trigger (1M for Mode A, 15M for Mode B).
    df_15:    15M bars carrying bias MAs.
    wait_bars: how many df_lower bars after a 15M setup-candle close to wait
               for an entry trigger. (15 for Mode A, 1 for Mode B.)
    max_bars: max df_lower bars to hold a trade before timing out.
    sl_method: "ema21" (legacy) or "swing3m" (most recent 3-min swing high/low).
    """
    rows = []
    for combo_name, ma_cols in MA_COMBOS.items():
        bias_15 = classify_bias(df_15, ma_cols)

        for pat in patterns:
            for buf in buf_grid:
                sigs = detect_signals(
                    df_lower, df_15, bias_15, pattern=pat, wait_bars=wait_bars,
                    sl_method=sl_method, sl_buffer=buf,
                    df_3m=df_3m, swing_high=swing_high, swing_low=swing_low,
                    session_hours=session_hours,
                    bias_tf_minutes=bias_tf_minutes,
                )
                for rr in rr_grid:
                    trs = simulate(sigs, df_lower, rr=rr, max_bars=max_bars)
                    m = metrics(trs)
                    m.update({"ma_combo": combo_name, "pattern": pat,
                              "rr": rr, "sl_buf": buf})
                    rows.append(m)
    df = pd.DataFrame(rows)
    cols = ["ma_combo", "pattern", "rr", "sl_buf",
            "trades", "win_rate", "tp_rate", "sl_rate",
            "net_pts", "avg_trade_pts", "profit_factor", "max_dd_pts",
            "trades_per_day", "p1_share", "p2_share"]
    return df[cols].sort_values("net_pts", ascending=False).reset_index(drop=True)


# ---------------------------------------------------------------------------
# 8. CLI
# ---------------------------------------------------------------------------

def detect_interval_minutes(df: pd.DataFrame) -> float:
    """Median bar interval in minutes (robust to weekend gaps)."""
    diffs = df.index.to_series().diff().dt.total_seconds().dropna() / 60
    return float(diffs.median())


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--csv", required=True, help="Path to OHLC CSV (M1 or M15)")
    ap.add_argument("--mode", choices=("auto", "m1", "m15", "m30_15"), default="auto",
                    help="m1 = bias 15M, entry 1M; "
                         "m15 = bias 15M, entry 15M; "
                         "m30_15 = bias 30M, entry 15M; "
                         "auto detects m1/m15 from data interval.")
    ap.add_argument("--sl-method", choices=("ema21", "swing3m", "swing15m"), default="swing3m",
                    help="SL placement: ema21 / swing3m (1M data needed) / swing15m")
    ap.add_argument("--session", default=None,
                    help="Comma-separated allowed entry hours (UTC of the data), "
                         "e.g. '2,5,8,13,14,15,16,22'. If omitted, no filter.")
    ap.add_argument("--tz", default=None, help="Optional timezone localization")
    ap.add_argument("--quick", action="store_true",
                    help="Use a smaller matrix for fast smoke test")
    ap.add_argument("--start", default=None,
                    help="Optional ISO date to slice data from (e.g. 2026-02-16)")
    ap.add_argument("--end", default=None, help="Optional ISO date to slice data to")
    ap.add_argument("--out", default="results.csv")
    ap.add_argument("--trades-out", default="trades_best.csv")
    args = ap.parse_args()

    print(f"Loading {args.csv} ...")
    df = load_csv(args.csv, tz=args.tz)
    if args.start:
        df = df[df.index >= pd.Timestamp(args.start)]
    if args.end:
        df = df[df.index <= pd.Timestamp(args.end)]
    iv = detect_interval_minutes(df)
    print(f"  {len(df):,} bars from {df.index[0]} to {df.index[-1]}  median interval={iv:.0f}min")

    mode = args.mode
    if mode == "auto":
        mode = "m1" if iv < 5 else "m15"
    print(f"  mode = {mode}  sl_method = {args.sl_method}")

    df_3m = None
    swing_high = swing_low = None
    bias_tf_minutes = 15

    if mode == "m1":
        df_1m = add_entry_indicators(df)
        df_15 = add_bias_indicators(resample_15m(df_1m))
        df_lower = df_1m
        wait_bars = 15
        max_bars = 240
        if args.sl_method == "swing3m":
            df_3m = resample_3m(df_1m)
            swing_high, swing_low = find_swings_3m(df_3m)
            print(f"  3M bars: {len(df_3m):,}  swings: highs={swing_high.sum():,} lows={swing_low.sum():,}")
        elif args.sl_method == "swing15m":
            df_3m = df_lower  # use 1M for swing detection (rare; default to swing3m)
            swing_high, swing_low = find_swings_3m(df_lower)
        print(f"  {len(df_15):,} 15-min bars (resampled)")
    elif mode == "m30_15":
        # Bias on 30M, candle theory + entry on 15M
        bias_tf_minutes = 30
        if iv < 5:  # M1 input -> resample to 15M and 30M
            df_1m = add_entry_indicators(df)
            df_15 = add_entry_indicators(resample_15m(df_1m))  # ema8/21 on 15M
            df_30 = add_bias_indicators(resample_30m(df_1m))
            print(f"  resampled: {len(df_15):,} 15M bars, {len(df_30):,} 30M bars (from 1M)")
        else:  # M15 input -> resample to 30M
            df_15 = add_entry_indicators(df)
            df_30 = add_bias_indicators(resample_30m(df_15))
            print(f"  {len(df_15):,} 15M bars (input), {len(df_30):,} 30M bars (resampled)")
        df_lower = df_15
        df_15 = df_30  # bias container is now 30M (variable kept named df_15 in engine)
        wait_bars = 2  # next 30M = 2 15M bars
        max_bars = 32  # ~8 hours of 15M

        if args.sl_method == "swing3m":
            if iv < 5:
                df_3m = resample_3m(df_1m)
                swing_high, swing_low = find_swings_3m(df_3m)
                print(f"  3M swings: highs={swing_high.sum():,} lows={swing_low.sum():,}")
            else:
                print("  WARNING: 3M swing not available with M15 input; falling back to swing15m")
                args.sl_method = "swing15m"
        if args.sl_method == "swing15m":
            df_3m = df_lower  # reuse the swing helper on 15M data
            swing_high, swing_low = find_swings_3m(df_lower)
            print(f"  15M swings: highs={swing_high.sum():,} lows={swing_low.sum():,}")
    else:  # m15
        df_15 = add_bias_indicators(add_entry_indicators(df))
        df_lower = df_15
        wait_bars = 1
        max_bars = 16
        if args.sl_method == "swing3m":
            print("  WARNING: swing3m not available in m15 mode (no sub-15M data); falling back to ema21")
            args.sl_method = "ema21"
        if args.sl_method == "swing15m":
            df_3m = df_15
            swing_high, swing_low = find_swings_3m(df_15)

    session_hours = None
    if args.session:
        session_hours = {int(x.strip()) for x in args.session.split(",") if x.strip()}
        print(f"  session filter: hours {sorted(session_hours)}")

    if args.quick:
        rr_grid, buf_grid, pats = (1.0, 2.0, 3.0), (2.0,), ("both",)
    else:
        rr_grid, buf_grid, pats = (1.0, 1.5, 2.0, 3.0, 4.0, 5.0), (2.0, 3.0), ("P1", "P2", "both")

    print(f"Running matrix ({len(MA_COMBOS) * len(pats) * len(rr_grid) * len(buf_grid)} configs) ...")
    res = run_matrix(df_lower, df_15, wait_bars=wait_bars, max_bars=max_bars,
                     sl_method=args.sl_method, df_3m=df_3m,
                     swing_high=swing_high, swing_low=swing_low,
                     session_hours=session_hours,
                     bias_tf_minutes=bias_tf_minutes,
                     rr_grid=rr_grid, buf_grid=buf_grid, patterns=pats)
    res["mode"] = mode
    res["sl_method"] = args.sl_method
    res.to_csv(args.out, index=False, float_format="%.3f")
    print(f"\nSaved {len(res)} configs -> {args.out}")
    print("\nTop 15 by net points:")
    print(res.head(15).to_string(index=False))

    best = res.iloc[0]
    ma_cols = MA_COMBOS[best["ma_combo"]]
    bias_15 = classify_bias(df_15, ma_cols)
    sigs = detect_signals(df_lower, df_15, bias_15,
                          pattern=best["pattern"], wait_bars=wait_bars,
                          sl_method=args.sl_method, sl_buffer=best["sl_buf"],
                          df_3m=df_3m, swing_high=swing_high, swing_low=swing_low,
                          session_hours=session_hours,
                          bias_tf_minutes=bias_tf_minutes)
    trs = simulate(sigs, df_lower, rr=best["rr"], max_bars=max_bars)
    pd.DataFrame([t.__dict__ for t in trs]).to_csv(args.trades_out, index=False)
    print(f"Best config trade log -> {args.trades_out}")


if __name__ == "__main__":
    main()
