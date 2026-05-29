# EMA 8/21 Scalper — Tested. Doesn't work.

## What I built

A standard trend-pullback scalper on gold 1M:
- **Bias (15M):** EMA8 > EMA21 + EMA21 sloping up (mirror for shorts)
- **Setup (1M):** price pulled back to or below EMA21 within last 3-8 bars
- **Entry (1M):** body close back above EMA8 with BOS (close > prev close)
- **SL:** low of last 3 bars − buffer
- **TP:** RR 1:1 to 1:3, with optional BE@0.5R / 1R + EMA21 or swing trail
- **Session:** the 8 hot hours from earlier analysis
- **Walk-forward:** 3 sliding folds, 216 configs

## Result

**Zero configurations were profitable in every walk-forward fold.**

Top by mean P/L (NOT robust — loses in at least one fold):

| pullback | RR | sl_buf | be_at_r | trail | trades | mean WR | mean PF | mean net | min fold net |
|---|---|---|---|---|---|---|---|---|---|
| 5 | 3.0 | 2.0 | 1.0 | none | 378 | 19.5% | 1.14 | +47 | **−62** |
| 8 | 3.0 | 3.0 | 1.0 | none | 338 | 20.1% | 1.16 | +40 | **−108** |
| 5 | 3.0 | 2.0 | — | — | 319 | 26.9% | 1.08 | +36 | **−68** |

Best mean: +47 pts. But the **worst fold loses 62 pts**. That means the strategy is unstable — works in some windows, fails in others. Live, you'd be on the wrong side of a losing fold and quit before the winning fold catches up.

## Why it failed

1. **Too many signals.** Even with session filter, ~10 trades/day. Pullback-to-EMA21 happens constantly on 1M — most are noise.
2. **EMA 8/21 alone is not a strong enough trend filter** for gold's 1M chop. The 4-MA bias (your original WMA 34/64 + EMA 55/100) was filtering out a LOT of bad setups that this scalper now takes.
3. **PF ~1.1, WR ~20%.** Combined with 0.3pt modeled spread (live broker spread is 2-5pt), live PF would be < 1.0 — money loser.

## What this proves

Your original strategy's edge **lives in the 4-MA stack + Pattern 2 setup**, not in any specific entry timeframe or simpler MA combo. When I strip away the WMA ribbon and replace it with EMA 8/21, the edge vanishes.

The hypothesis "EMA 8/21 gives high WR + high RR" is **not supported by data**. Gold's 1M timeframe is too noisy for that simple a setup.

## What is supported by data (re-confirming earlier results)

| Setup | WR | DD | Net (3.5mo) | PF | Status |
|---|---|---|---|---|---|
| PR #3: Ribbon + P2 + RR 1:5 + session + 3M-swing SL | 33% | 238 | +1074 | 1.59 | Edge confirmed |
| **PR #5: same + BE@1R + swing trail (RR 1:3)** | **53%** | **133** | **+677** | **1.45** | **Edge confirmed, more comfortable** |
| EMA 8/21 scalp | 20% | 130+ | +47 (best fold), −108 (worst fold) | 1.1 | **No edge** |

## My recommendation, plain

Your strategy IS your edge. The 4-MA bias + Pattern 2 candle theory is the money-maker. PR #5 (BE+trail variant) is the most comfortable version of it. Anything simpler — including pure EMA 8/21 — doesn't work on this data.

To genuinely push beyond PR #5 needs **new information** not currently in the engine:
- **News calendar feed** (skip 30 min around NFP, FOMC, CPI)
- **Higher-TF S/R levels** (daily/weekly pivots)
- **Volume / order flow** (we don't have volume data in the CSV)
- **Multi-instrument confirmation** (DXY, US10Y for gold context)

These are real builds (days, not hours) and they may or may not move the needle. Pure parameter tuning has reached its limit on this data.

## Files
- `scalp_8_21.py` — the EMA 8/21 scalp implementation
- `results_scalp_8_21_wf.csv` — empty (zero robust configs)
- `RESULTS_SCALP_8_21.md` — this file
