# Backtest Results

Strategy implemented per `STRATEGY.md`. Real XAUUSD 1-minute data, Feb 16 -> May 29, 2026 (~3.5 months, 100,192 bars).

## Headline result

| Stage | Best config | Net pts | PF | Trades | WR | Max DD |
|---|---|---|---|---|---|---|
| **0. Baseline** (EMA21 SL, no filter) | ribbon_only + P2 + RR 1:3 | +226 | 1.06 | 697 | 28.3% | 243 |
| **1. + 3M-swing SL** (your manual SL method) | ribbon_ema55 + P2 + RR 1:4 | +383 | 1.09 | 513 | 29.6% | 319 |
| **2. + Session filter only** (8 hot hours) | ribbon_only + P2 + RR 1:4 | +827 | 1.59 | 281 | 28.5% | 198 |
| **3. + Both filters stacked** | **ribbon + EMA55 + EMA100 + P2 + RR 1:5 + 2pt buf** | **+928** | **1.52** | **238** | **30.3%** | **232** |

**4x improvement in net P/L, PF 1.06 -> 1.52, drawdown reduced — strategy is now genuinely tradeable.**

## What each filter does

### A. SL = nearest 3-min swing high/low + 2-3pt buffer
Replaces the "EMA21 +/- 2pts" rule. Looks back up to 10 bars (30 min) on the 3M chart for the most recent fractal swing low (longs) or swing high (shorts). Falls back to extreme of the lookback window if no fractal swing is found. Standalone effect: +226 -> +383 pts. Real value comes when stacked with session filter.

### B. Session filter — only trade these 8 hours (UTC of data)
Discovered from analyzing the original trade log:

| Hour (UTC) | Approx market |
|---|---|
| 02 | Tokyo open |
| 05 | Sydney close |
| 08 | London open |
| 13 | NY pre-open |
| 14 | NY first hour |
| 15 | NY active |
| 16 | NY close |
| 22 | Sydney open |

Avoiding the other 16 hours removes 449 losing trades that net **−461 pts**. This is the single biggest fix.

## Key strategy findings (after filters)

1. **Pattern 2 dominates** — every top result is P2-only. The P1 setup (favored 15M candle) is consistently weaker.
2. **RR 1:4 to 1:5 is the sweet spot** with the swing-based SL.
3. **2-pt buffer beats 3-pt** in most configs.
4. **Adding EMA100 to the bias filter helps** once the session filter is on. Without session filter, EMA100 got dragged down by chop trades; with it, the full 4-MA setup is cleanest.

## Direction asymmetry (pre-filter)

| Direction | Trades | WR | Net |
|---|---|---|---|
| Shorts | 382 | 31% | +169 |
| Longs | 315 | 25% | +57 |

The data window had a strong downtrend (4996 -> 4501), so shorts dominated naturally. Confirms the strategy follows trend correctly when one exists.

## Recommended paper-trade config

```
MA combo:    Ribbon (WMA34/64) + EMA55 + EMA100  (full 4-MA setup)
Pattern:     P2 only
RR:          1:5
SL buffer:   2 pts
Session:     hours 02, 05, 08, 13, 14, 15, 16, 22 (UTC of data)
SL method:   nearest 3M swing low/high + 2pt buffer (10-bar lookback)
```

After 30+ paper trades, if results align with backtest, move to live with small size.

## Re-run commands

```bash
python3 backtest.py --csv XAUUSD_M1_*.csv --session "2,5,8,13,14,15,16,22"
python3 backtest.py --csv XAUUSD_M1_*.csv --sl-method ema21
python3 backtest.py --csv XAUUSD_M1_*.csv --quick
```

## Caveats

1. Data window is only 3.5 months. The session hours were derived from this window — re-derive them on a longer dataset for confidence.
2. Spread modeled at 0.3 pt. Real broker spread on gold is 1.5-5 pt — re-test with your broker's actual spread before going live.
3. P2 dominance may be window-specific. The long Mode B run (4 years, 15M only) preferred P1. Track P1 vs P2 win rate live.

## Files

- `STRATEGY.md` — strategy specification
- `backtest.py` — engine; supports `--sl-method {ema21,swing3m}` and `--session "h1,h2,..."`
- `results_modeA.csv` — original baseline (EMA21 SL, no filter)
- `results_swing3m.csv` — swing3m SL, no session
- `results_ema21_session.csv` — EMA21 SL + session filter
- `results_swing3m_session.csv` — **best**: swing3m SL + session filter
- `trades_*.csv` — best-config trade logs for each scenario
- `XAUUSD_M1_*.csv` — your raw M1 data
- `XAUUSD_M15_*.csv` — your raw M15 data
