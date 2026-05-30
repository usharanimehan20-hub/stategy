"""
Dukascopy 1-minute OHLC downloader for XAUUSD.

Downloads hourly .bi5 tick files, decompresses (LZMA), parses 20-byte records,
aggregates to 1-minute BID OHLC, and writes a CSV compatible with backtest.load_csv.

Usage:
  python3.12 dukascopy_dl.py --symbol XAUUSD --start 2024-12-30 --end 2026-05-29 --out xau_1m_duka.csv
  python3.12 dukascopy_dl.py --symbol XAUUSD --start 2026-05-29 --end 2026-05-29 --out _oneday.csv  # validate
"""
from __future__ import annotations
import argparse, lzma, struct, io, sys, time
from datetime import datetime, timedelta, timezone
from concurrent.futures import ThreadPoolExecutor
import urllib.request
import pandas as pd
import numpy as np

BASE = "https://datafeed.dukascopy.com/datafeed"
# price scale: XAUUSD has 3 decimals -> divide int price by 1000
POINT = {"XAUUSD": 1000.0}


def hour_url(symbol, dt):
    # Dukascopy months are 0-indexed
    return f"{BASE}/{symbol}/{dt.year}/{dt.month-1:02d}/{dt.day:02d}/{dt.hour:02d}h_ticks.bi5"


def fetch_hour(symbol, dt, retries=2):
    """Download one hour, aggregate ticks to 1-min BID OHLC IN-WORKER (memory-light).
    Returns (dt, list_of[(minute_epoch_sec, o, h, l, c)]) or (dt, None) on error."""
    url = hour_url(symbol, dt)
    for attempt in range(retries + 1):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
            with urllib.request.urlopen(req, timeout=30) as r:
                raw = r.read()
            if not raw:
                return dt, []  # empty hour (market closed)
            data = lzma.decompress(raw)
            scale = POINT.get(symbol, 100000.0)
            base_sec = int(dt.replace(minute=0, second=0, microsecond=0).timestamp())
            # bin ticks into minute buckets
            bars = {}  # minute_index(0-59) -> [o,h,l,c]
            n = len(data)
            for off in range(0, n, 20):
                ms, ask_i, bid_i, av, bv = struct.unpack(">IIIff", data[off:off + 20])
                price = bid_i / scale
                minute = ms // 60000
                b = bars.get(minute)
                if b is None:
                    bars[minute] = [price, price, price, price]
                else:
                    if price > b[1]: b[1] = price
                    if price < b[2]: b[2] = price
                    b[3] = price
            out = [(base_sec + m * 60, v[0], v[1], v[2], v[3]) for m, v in bars.items()]
            return dt, out
        except urllib.error.HTTPError as e:
            if e.code == 404:
                return dt, []  # no data this hour
            if attempt == retries:
                return dt, None  # error
            time.sleep(0.5)
        except Exception:
            if attempt == retries:
                return dt, None
            time.sleep(0.5)
    return dt, None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--symbol", default="XAUUSD")
    ap.add_argument("--start", required=True)
    ap.add_argument("--end", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--workers", type=int, default=24)
    args = ap.parse_args()

    start = datetime.fromisoformat(args.start).replace(tzinfo=timezone.utc)
    end = datetime.fromisoformat(args.end).replace(tzinfo=timezone.utc) + timedelta(days=1)
    hours = []
    cur = start
    while cur < end:
        # skip typical weekend gap (Sat all day, Sun before 22:00 UTC, Fri after 21:00)
        wd = cur.weekday()  # Mon=0..Sun=6
        if wd == 5:  # Saturday
            cur += timedelta(hours=1); continue
        if wd == 6 and cur.hour < 22:  # Sunday before open
            cur += timedelta(hours=1); continue
        if wd == 4 and cur.hour >= 21:  # Friday after close
            cur += timedelta(hours=1); continue
        hours.append(cur)
        cur += timedelta(hours=1)

    print(f"{args.symbol}: {len(hours)} hours to fetch {args.start}..{args.end}", flush=True)
    t0 = time.time()
    all_bars = []
    errors = 0
    done = 0
    with ThreadPoolExecutor(max_workers=args.workers) as ex:
        futs = [ex.submit(fetch_hour, args.symbol, h) for h in hours]
        for fut in futs:
            dt, bars = fut.result()
            done += 1
            if bars is None:
                errors += 1
            elif bars:
                all_bars.extend(bars)
            if done % 1000 == 0:
                print(f"  {done}/{len(hours)}  bars={len(all_bars):,}  errors={errors}  {time.time()-t0:.0f}s", flush=True)

    if not all_bars:
        print("No bars downloaded."); sys.exit(1)

    df = pd.DataFrame(all_bars, columns=["sec", "open", "high", "low", "close"])
    df = df.drop_duplicates(subset="sec").sort_values("sec")
    df["timestamp"] = pd.to_datetime(df["sec"], unit="s")
    df = df[["timestamp", "open", "high", "low", "close"]]
    df.to_csv(args.out, index=False)
    print(f"Wrote {len(df):,} 1-min bars -> {args.out}  ({df['timestamp'].iloc[0]} .. {df['timestamp'].iloc[-1]})  errors={errors}  {time.time()-t0:.0f}s", flush=True)


if __name__ == "__main__":
    main()
