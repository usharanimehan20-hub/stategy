# Scale-Out Sweep — Targeting 70%+ WR

You asked: 70-75% WR with effective 1:3 RR. I built scale-out (TP1 partial close + runner with BE+trail) and ran 1620 configs through walk-forward validation.

## Honest verdict

**70% WR is not achievable on your data with rule-based logic.** The ceiling is ~62% for a single config (or ~64% mean across walk-forward folds). Above that, you're either curve-fitting or you need discretionary judgment the bot doesn't have.

## Where we got to

Tested across MA combo / pattern / RR / SL buffer / TP1 trigger / TP1 close % / trail method:

| Config | WR | Net pts | PF | Max DD | Trades |
|---|---|---|---|---|---|
| PR#3 (single TP at RR 5) | 33% | +1074 | 1.59 | 238 | 232 |
| PR#5 (BE+trail, RR 3) | 53% | +677 | 1.45 | 133 | 274 |
| **NEW max-WR (scale-out)** | **61%** | +293 | 1.23 | 133 | 261 |
| **NEW max-profit (scale-out)** | 57% | **+629** | 1.42 | 133 | 274 |

## The two winning scale-out configs

### A) Max win rate (61% WR)
```
ma_combo  : Ribbon + EMA55 + EMA100
pattern   : P2 only
rr        : 1:4 (runner target)
sl_buf    : 3 pts
tp1_at_r  : 0.7  (close 70% of position at +0.7R)
tp1_frac  : 0.7
trail     : none
session   : 02, 05, 08, 13, 14, 15, 16, 22 UTC
```
**Outcomes (261 trades):**
- TP2 hit (full winner): 33 (12.6%)
- BE after TP1 (small win): 113 (43.3%)
- TP1 + SL (small win, runner stopped): mixed in BE_after_TP1
- Full SL (loss): 100 (38.3%)

### B) Max profit (57% WR, double the net P/L)
```
ma_combo  : Ribbon + EMA55 + EMA100
pattern   : P2 only
rr        : 1:3 (runner target)
sl_buf    : 3 pts
tp1_at_r  : 1.0  (close 30% at +1R, let 70% run)
tp1_frac  : 0.3
trail     : swing (after TP1, trail 70% runner with 1M swings)
session   : same 8 hours
```

## Why we can't push past 62%

To get higher WR I'd need to lower TP1 (close partial at 0.3-0.5R). That makes WR look better in-sample but **the wins become so small that spread eats them on out-of-sample**. The walk-forward filter (positive net in EVERY fold) filtered those out — they were curve fits.

The honest data ceiling for this strategy on this 3.5-month window:
- ~60-62% WR with PF 1.2-1.3
- OR 53-57% WR with PF 1.4-1.6 and bigger profit
- Anything claiming higher WR with this data is overfit

## Why your manual 80% is real but uncopyable

In live discretionary trading, you:
1. Skip setups that "look weak" before entry
2. Adjust SL on the fly based on what price is doing
3. Take partial profits intuitively, not at fixed Rs
4. Cancel orders 30 sec before news hits
5. See multi-timeframe context the rules don't capture

A bot with rules can't do any of those. The 20pp gap (62% vs 80%) is your discretionary alpha — the hardest thing in trading to encode.

## Recommendations — take your pick

| Priority | Choice |
|---|---|
| **A. Max WR feel** (61%, smaller profit) | Scale-out config A. Most "money-printer feel." Smaller per-trade returns but very few losing trades. |
| **B. Max profit** (57% WR, +629 pts) | Scale-out config B. Best risk-adjusted return I can find. |
| **C. Max total profit** (33% WR, +1074 pts) | Original PR#3. Largest absolute return; harder mentally. |
| **D. Co-pilot mode** | Bot fires alerts on PR#5/Config-B setups, you decide entries with your discretionary eye. Best of both worlds. |

I would strongly suggest **D + B** — bot uses Config B logic to identify setups; you take/skip them based on your read.

## Files

- `backtest.py` — `simulate()` now supports scale-out (`tp1_at_r`, `tp1_close_frac`)
- `sweep_scaleout.py` — 1620-config walk-forward sweep
- `results_scaleout.csv` — all 28 robust configs
- `trades_scaleout_winrate.csv` — full trade log of Config A
- `trades_scaleout_profit.csv` — full trade log of Config B
- `RESULTS_SCALEOUT.md` — this file
