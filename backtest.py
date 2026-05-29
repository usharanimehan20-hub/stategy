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


def resample_1h(df: pd.DataFrame) -> pd.DataFrame:
    """Resample any-TF OHLC to 1-hour OHLC (used for HTF-confluence filter)."""
    agg = {"open": "first", "high": "max", "low": "min", "close": "last"}
    return df.resample("1h", label="left", closed="left").agg(agg).dropna()


def build_htf_bias_aligned(df_low: pd.DataFrame, bias_index: pd.DatetimeIndex,
                           htf: str = "1h") -> pd.Series:
    """
    Build a HTF (default 1H) bias series and align it to `bias_index` (the 15M
    or 30M setup index) using as-of/forward-fill. The 1H bias of a bar at time T
    is only available from T+1H onward, so we shift before reindexing.
    Returns an int Series of {-1,0,+1} the same length as bias_index.
    """
    if htf != "1h":
        raise ValueError(f"unsupported htf: {htf}")
    df_h = add_bias_indicators(resample_1h(df_low))
    bias_h = classify_bias(df_h, ("wma34", "wma64", "ema55", "ema100"))
    # Availability shift: 1H bar starting at T closes at T+1H.
    bias_avail = bias_h.copy()
    bias_avail.index = bias_avail.index + pd.Timedelta(hours=1)
    aligned = bias_avail.reindex(bias_index, method="ffill").fillna(0).astype(int)
    return aligned


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
                   bias_tf_minutes: int = 15,
                   bias_1h_aligned: Optional[pd.Series] = None,
                   ma_sep_min: Optional[float] = None,
                   max_ext_pts: Optional[float] = None,
                   body_frac_min: Optional[float] = None) -> list[Signal]:
    """
    Candle Theory — setup on 15M, entry trigger on 1M.

    Optional filters (default None/off, fully backward compatible):
      bias_1h_aligned : Series of 1H bias aligned to df_15.index. When provided
                        require bias_1h == bias_15 at setup time (HTF confluence).
      ma_sep_min      : Require |ema55 - ema100| >= ma_sep_min on the setup
                        15M (or bias-TF) candle.
      max_ext_pts     : At the 1M entry trigger require
                        |entry_price - ema21| <= max_ext_pts.
      body_frac_min   : For the setup candle require
                        |close-open|/(high-low) >= body_frac_min.

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

    # Optional HTF (1H) bias array, aligned to df_15.index. None = filter off.
    bias_1h_arr = bias_1h_aligned.values if bias_1h_aligned is not None else None

    # Optional MA-separation arrays from the bias-TF dataframe.
    ema55_15 = df_15["ema55"].values if "ema55" in df_15.columns else None
    ema100_15 = df_15["ema100"].values if "ema100" in df_15.columns else None

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

        # F1: HTF (1H) confluence — 1H bias must agree with 15M bias at setup time.
        if bias_1h_arr is not None and int(bias_1h_arr[i]) != b:
            continue

        # F2: MA separation — avoid chop where ema55 and ema100 are entwined.
        if ma_sep_min is not None and ema55_15 is not None and ema100_15 is not None:
            if abs(float(ema55_15[i]) - float(ema100_15[i])) < ma_sep_min:
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

        # F4: setup-candle body strength (filter doji-like or choppy setups).
        if body_frac_min is not None:
            rng = float(h15[i] - l15[i])
            if rng <= 0:
                continue
            body_frac = abs(float(c15[i] - o15[i])) / rng
            if body_frac < body_frac_min:
                continue

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
                # F3: extension filter — don't chase price that has already
                # stretched far from the EMA21 mean.
                if max_ext_pts is not None:
                    if abs(float(c1[j]) - float(e21_1[j])) > max_ext_pts:
                        break  # first valid trigger is too extended -> skip setup
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
             max_bars: int = 240,
             be_at_r: Optional[float] = None,
             trail_method: Optional[str] = None) -> list[Trade]:
    """
    Walk-forward simulator with optional breakeven move and trailing stop.

    Parameters:
        be_at_r: If set, when unrealized profit reaches this many R (R = initial risk),
                 slide SL to entry (breakeven). Common values: 1.0, 1.5.
        trail_method: After BE move, trail SL using:
                      - "ema21" : SL clamped to current EMA21 +/- 1pt buffer
                      - "swing" : SL clamped to most recent 1M 3-bar fractal swing
                      - None    : no trail (just BE if be_at_r set)
    Conservative tie-breaking: same-bar SL+TP -> SL wins.
    """
    trades: list[Trade] = []
    h = df_1m["high"].values
    l = df_1m["low"].values
    c = df_1m["close"].values
    e21 = df_1m["ema21"].values if "ema21" in df_1m.columns else None
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

        be_target = None
        if be_at_r is not None:
            be_target = sig.entry + be_at_r * risk if sig.direction == 1 else sig.entry - be_at_r * risk
        be_moved = False

        outcome = "EOD"
        exit_price = sig.entry
        exit_time = sig.time
        bars_held = 0
        end_idx = min(i0 + 1 + max_bars, len(df_1m))

        for j in range(i0 + 1, end_idx):
            bar_h, bar_l = h[j], l[j]
            bars_held += 1

            # 1) BE move
            if be_target is not None and not be_moved:
                if (sig.direction == 1 and bar_h >= be_target) or (sig.direction == -1 and bar_l <= be_target):
                    sl = sig.entry
                    be_moved = True

            # 2) Trail update (only after BE)
            if trail_method and be_moved and e21 is not None:
                if trail_method == "ema21":
                    if sig.direction == 1:
                        sl = max(sl, float(e21[j]) - 1.0)
                    else:
                        sl = min(sl, float(e21[j]) + 1.0)
                elif trail_method == "swing" and j >= 2:
                    if sig.direction == 1:
                        if l[j - 1] < l[j - 2] and l[j - 1] < bar_l:
                            sl = max(sl, float(l[j - 1]) - 1.0)
                    else:
                        if h[j - 1] > h[j - 2] and h[j - 1] > bar_h:
                            sl = min(sl, float(h[j - 1]) + 1.0)

            # 3) Exits
            if sig.direction == 1:
                hit_sl = bar_l <= sl
                hit_tp = bar_h >= tp
            else:
                hit_sl = bar_h >= sl
                hit_tp = bar_l <= tp

            if hit_sl:
                outcome = "BE" if be_moved and abs(sl - sig.entry) < 1e-6 else "SL"
                exit_price = sl
                exit_time = times[j]
                break
            if hit_tp:
                outcome = "TP"
                exit_price = tp
                exit_time = times[j]
                break
        else:
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
               patterns=("P1", "P2", "both"),
               bias_1h_aligned: Optional[pd.Series] = None,
               ma_sep_min: Optional[float] = None,
               max_ext_pts: Optional[float] = None,
               body_frac_min: Optional[float] = None) -> pd.DataFrame:
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
                    bias_1h_aligned=bias_1h_aligned,
                    ma_sep_min=ma_sep_min,
                    max_ext_pts=max_ext_pts,
                    body_frac_min=body_frac_min,
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


def build_engine_inputs(df: pd.DataFrame, mode: str, sl_method: str,
                        htf_confluence: bool = False,
                        verbose: bool = True) -> dict:
    """
    From a raw OHLC dataframe, build everything the engine needs:
        df_lower, df_15, df_3m, swing_high/low, wait_bars, max_bars,
        bias_tf_minutes, bias_1h_aligned (or None).
    Used by both the CLI here and the sweep_filters.py script so that IS / OOS
    slices share the same construction logic.

    Returns a dict of inputs plus the (possibly downgraded) sl_method.
    """
    iv = detect_interval_minutes(df)
    if mode == "auto":
        mode = "m1" if iv < 5 else "m15"
    if verbose:
        print(f"  mode={mode}  sl_method={sl_method}  bars={len(df):,}  iv={iv:.0f}min")

    df_3m = None
    swing_high = swing_low = None
    bias_tf_minutes = 15
    df_1m = None  # base 1M frame, if any

    if mode == "m1":
        df_1m = add_entry_indicators(df)
        df_15 = add_bias_indicators(resample_15m(df_1m))
        df_lower = df_1m
        wait_bars = 15
        max_bars = 240
        if sl_method == "swing3m":
            df_3m = resample_3m(df_1m)
            swing_high, swing_low = find_swings_3m(df_3m)
        elif sl_method == "swing15m":
            df_3m = df_lower
            swing_high, swing_low = find_swings_3m(df_lower)
    elif mode == "m30_15":
        bias_tf_minutes = 30
        if iv < 5:
            df_1m = add_entry_indicators(df)
            df_15 = add_entry_indicators(resample_15m(df_1m))
            df_30 = add_bias_indicators(resample_30m(df_1m))
        else:
            df_15 = add_entry_indicators(df)
            df_30 = add_bias_indicators(resample_30m(df_15))
        df_lower = df_15
        df_15 = df_30
        wait_bars = 2
        max_bars = 32
        if sl_method == "swing3m":
            if iv < 5:
                df_3m = resample_3m(df_1m)
                swing_high, swing_low = find_swings_3m(df_3m)
            else:
                if verbose:
                    print("  WARNING: swing3m unavailable with M15 input; using swing15m")
                sl_method = "swing15m"
        if sl_method == "swing15m":
            df_3m = df_lower
            swing_high, swing_low = find_swings_3m(df_lower)
    else:  # m15
        df_15 = add_bias_indicators(add_entry_indicators(df))
        df_lower = df_15
        wait_bars = 1
        max_bars = 16
        if sl_method == "swing3m":
            if verbose:
                print("  WARNING: swing3m unavailable in m15 mode; using ema21")
            sl_method = "ema21"
        if sl_method == "swing15m":
            df_3m = df_15
            swing_high, swing_low = find_swings_3m(df_15)

    bias_1h_aligned = None
    if htf_confluence:
        if iv >= 60:
            if verbose:
                print("  WARNING: --htf-confluence requested but data interval >=60min; skipping")
        else:
            bias_1h_aligned = build_htf_bias_aligned(df, df_15.index, htf="1h")
            if verbose:
                nz = int((bias_1h_aligned != 0).sum())
                print(f"  HTF (1H) bias aligned: nonzero={nz:,}/{len(bias_1h_aligned):,}")

    return {
        "mode": mode,
        "sl_method": sl_method,
        "df_lower": df_lower,
        "df_15": df_15,
        "df_3m": df_3m,
        "swing_high": swing_high,
        "swing_low": swing_low,
        "wait_bars": wait_bars,
        "max_bars": max_bars,
        "bias_tf_minutes": bias_tf_minutes,
        "bias_1h_aligned": bias_1h_aligned,
    }


def run_single_config(eng: dict, *, ma_combo: str, pattern: str, rr: float,
                      sl_buf: float, session_hours: Optional[set[int]] = None,
                      ma_sep_min: Optional[float] = None,
                      max_ext_pts: Optional[float] = None,
                      body_frac_min: Optional[float] = None) -> dict:
    """
    Run one specific config end-to-end (signals + simulate + metrics) using the
    pre-built engine inputs `eng` from build_engine_inputs().
    """
    ma_cols = MA_COMBOS[ma_combo]
    bias_15 = classify_bias(eng["df_15"], ma_cols)
    sigs = detect_signals(
        eng["df_lower"], eng["df_15"], bias_15,
        pattern=pattern, wait_bars=eng["wait_bars"],
        sl_method=eng["sl_method"], sl_buffer=sl_buf,
        df_3m=eng["df_3m"], swing_high=eng["swing_high"], swing_low=eng["swing_low"],
        session_hours=session_hours,
        bias_tf_minutes=eng["bias_tf_minutes"],
        bias_1h_aligned=eng["bias_1h_aligned"],
        ma_sep_min=ma_sep_min, max_ext_pts=max_ext_pts, body_frac_min=body_frac_min,
    )
    trs = simulate(sigs, eng["df_lower"], rr=rr, max_bars=eng["max_bars"])
    return metrics(trs)


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

    # ---- New optional entry filters (default OFF for backward compat) ----
    ap.add_argument("--htf-confluence", action="store_true", default=False,
                    help="Require 1H bias agreement with bias-TF (e.g. 15M) "
                         "bias at setup time.")
    ap.add_argument("--ma-sep-min", type=float, default=None,
                    help="Min |ema55 - ema100| (gold pts) on the setup candle.")
    ap.add_argument("--max-ext-pts", type=float, default=None,
                    help="Max |entry_price - ema21| (pts) at the 1M entry "
                         "trigger. Filters chases.")
    ap.add_argument("--body-frac-min", type=float, default=None,
                    help="Min |close-open|/(high-low) for the setup candle "
                         "(e.g. 0.5 = body must be at least half of range).")

    # ---- Train/test split (used by --report-oos here, mirrored by sweep) ----
    ap.add_argument("--train-frac", type=float, default=0.7,
                    help="Chronological in-sample fraction when --report-oos.")
    ap.add_argument("--report-oos", action="store_true", default=False,
                    help="Split data at --train-frac, run matrix on IS, "
                         "re-run top config on OOS, print both side by side.")
    args = ap.parse_args()

    print(f"Loading {args.csv} ...")
    df = load_csv(args.csv, tz=args.tz)
    if args.start:
        df = df[df.index >= pd.Timestamp(args.start)]
    if args.end:
        df = df[df.index <= pd.Timestamp(args.end)]
    iv = detect_interval_minutes(df)
    print(f"  {len(df):,} bars from {df.index[0]} to {df.index[-1]}  median interval={iv:.0f}min")

    session_hours = None
    if args.session:
        session_hours = {int(x.strip()) for x in args.session.split(",") if x.strip()}
        print(f"  session filter: hours {sorted(session_hours)}")

    if args.quick:
        rr_grid, buf_grid, pats = (1.0, 2.0, 3.0), (2.0,), ("both",)
    else:
        rr_grid, buf_grid, pats = (1.0, 1.5, 2.0, 3.0, 4.0, 5.0), (2.0, 3.0), ("P1", "P2", "both")

    # Decide which slice to use as the matrix domain.
    if args.report_oos:
        n = len(df)
        split = int(n * args.train_frac)
        df_is = df.iloc[:split]
        df_oos = df.iloc[split:]
        print(f"  IS slice : {df_is.index[0]} -> {df_is.index[-1]}  ({len(df_is):,} bars)")
        print(f"  OOS slice: {df_oos.index[0]} -> {df_oos.index[-1]}  ({len(df_oos):,} bars)")
        df_for_matrix = df_is
    else:
        df_for_matrix = df

    print("Building engine inputs ...")
    eng = build_engine_inputs(df_for_matrix, mode=args.mode,
                              sl_method=args.sl_method,
                              htf_confluence=args.htf_confluence,
                              verbose=True)
    # Effective sl_method may have been downgraded inside build_engine_inputs.
    args.sl_method = eng["sl_method"]
    mode = eng["mode"]

    n_configs = len(MA_COMBOS) * len(pats) * len(rr_grid) * len(buf_grid)
    print(f"Running matrix ({n_configs} configs) ...")
    res = run_matrix(eng["df_lower"], eng["df_15"],
                     wait_bars=eng["wait_bars"], max_bars=eng["max_bars"],
                     sl_method=eng["sl_method"], df_3m=eng["df_3m"],
                     swing_high=eng["swing_high"], swing_low=eng["swing_low"],
                     session_hours=session_hours,
                     bias_tf_minutes=eng["bias_tf_minutes"],
                     rr_grid=rr_grid, buf_grid=buf_grid, patterns=pats,
                     bias_1h_aligned=eng["bias_1h_aligned"],
                     ma_sep_min=args.ma_sep_min,
                     max_ext_pts=args.max_ext_pts,
                     body_frac_min=args.body_frac_min)
    res["mode"] = mode
    res["sl_method"] = args.sl_method
    res.to_csv(args.out, index=False, float_format="%.3f")
    print(f"\nSaved {len(res)} configs -> {args.out}")
    print("\nTop 15 by net points:")
    print(res.head(15).to_string(index=False))

    best = res.iloc[0]
    sigs = detect_signals(
        eng["df_lower"], eng["df_15"],
        classify_bias(eng["df_15"], MA_COMBOS[best["ma_combo"]]),
        pattern=best["pattern"], wait_bars=eng["wait_bars"],
        sl_method=eng["sl_method"], sl_buffer=best["sl_buf"],
        df_3m=eng["df_3m"], swing_high=eng["swing_high"], swing_low=eng["swing_low"],
        session_hours=session_hours,
        bias_tf_minutes=eng["bias_tf_minutes"],
        bias_1h_aligned=eng["bias_1h_aligned"],
        ma_sep_min=args.ma_sep_min, max_ext_pts=args.max_ext_pts,
        body_frac_min=args.body_frac_min,
    )
    trs = simulate(sigs, eng["df_lower"], rr=best["rr"], max_bars=eng["max_bars"])
    pd.DataFrame([t.__dict__ for t in trs]).to_csv(args.trades_out, index=False)
    print(f"Best config trade log -> {args.trades_out}")

    # ---- Optional OOS verification of top-1 IS config ----
    if args.report_oos:
        print("\n" + "=" * 70)
        print("OOS verification of top-1 IS config")
        print("=" * 70)
        eng_oos = build_engine_inputs(df_oos, mode=args.mode,
                                      sl_method=args.sl_method,
                                      htf_confluence=args.htf_confluence,
                                      verbose=True)
        oos_m = run_single_config(
            eng_oos,
            ma_combo=best["ma_combo"], pattern=best["pattern"],
            rr=float(best["rr"]), sl_buf=float(best["sl_buf"]),
            session_hours=session_hours,
            ma_sep_min=args.ma_sep_min, max_ext_pts=args.max_ext_pts,
            body_frac_min=args.body_frac_min,
        )
        print(f"\nConfig: ma_combo={best['ma_combo']}  pattern={best['pattern']}  "
              f"rr={best['rr']}  sl_buf={best['sl_buf']}")
        print(f"  IS : trades={int(best['trades'])}  WR={best['win_rate']:.1f}%  "
              f"net={best['net_pts']:.1f}  PF={best['profit_factor']:.2f}  "
              f"DD={best['max_dd_pts']:.1f}")
        if oos_m.get("trades", 0) > 0:
            print(f"  OOS: trades={oos_m['trades']}  WR={oos_m['win_rate']:.1f}%  "
                  f"net={oos_m['net_pts']:.1f}  PF={oos_m['profit_factor']:.2f}  "
                  f"DD={oos_m['max_dd_pts']:.1f}")
        else:
            print("  OOS: no trades")


if __name__ == "__main__":
    main()
