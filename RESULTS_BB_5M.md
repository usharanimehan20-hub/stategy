# 5M Bollinger Band Strategy — Results

You said: 15M bias + 5M Bollinger Bands + price retraces to band + bias-direction candle = entry. SL on the entry candle or pullback.

I tested 864 BB parameter combinations on 17 months of M5 data with walk-forward.

## Headline

| Test | Robust configs (positive in EVERY fold) |
|---|---|
| **1M BB** (my earlier wrong version) | **0 / 648** |
| **5M BB** (your friend's correct spec) | **145 / 864** |

That's not a small change — that's the difference between "no edge" and "wide stable edge."

## The winning config

```
Bias:        15M, ribbon_only (WMA 34/64 only — no EMA)
BB:          period 30, multiplier 1.5  (NOT default 20/2 — wider 30/1.5 wins)
Pullback:    look back 3 bars for BB band touch
SL method:   pullback low/high (not entry candle)
SL buffer:   3 pts
RR:          1:2
Session:     all hours (no session filter needed)
```

## Walk-forward results (3 folds)

| Fold | Window | Net pts |
|---|---|---|
| 1 | 2025-03-28 → 05-26 | +345 |
| 2 | 2025-07-21 → 09-18 | +30 |
| 3 | 2025-11-12 → 2026-01-10 | +333 |
| **Mean** | | **+236/fold** WR 43% PF 1.25 |

## The honest catch — full 17-month window

| Metric | Value |
|---|---|
| Trades | 1,974 |
| Win rate | 38% |
| Net pts | +290 |
| **Profit factor** | **1.03** |
| **Max DD** | **1010 pts** |

Walk-forward folds happened to skip Feb-March 2026, which is the worst stretch.

### Monthly P/L

| Month | Net | Note |
|---|---|---|
| 2024-12 | +3 | |
| 2025-01 to 2026-01 | mostly +50 to +236/month | 11 of 13 winning |
| **2026-02** | **−376** | regime breakdown |
| **2026-03** | **−407** | regime breakdown |
| 2026-04 | -65 | |
| 2026-05 | +195 | recovery |

13 of 18 months profitable. **Feb-Mar 2026 alone wiped -780 pts** (heavy trending / news regime that BB mean-reversion can't handle).

## SL method comparison

In top 50 configs by mean P/L:

| SL method | Count | Mean P/L |
|---|---|---|
| **Pullback** (lowest of last 3 bars) | **32 / 50** | **+164** |
| Candle (just entry candle low) | 18 / 50 | +151 |

Pullback SL wins.

## Comparison vs PR #6 (mechanical pullback scalper)

| Metric | PR #6 | 5M BB |
|---|---|---|
| Robust configs | 39 | 145 |
| Full-window net (17mo) | **+1359** | +290 |
| PF | 1.10 | 1.03 |
| Max DD | **621** | 1010 |
| WR | 38% | 38% |

PR #6 is better in raw form — same WR, 4x the profit, 40% lower DD.

## Recommendation

5M BB has a real foundation but raw it can't handle trending regimes (Feb-Mar 2026 wiped it). Three options:

| Option | Action |
|---|---|
| A | Add regime filter to 5M BB (skip when 5M ATR is too high) — could fix Feb-Mar |
| B | Use PR #6 instead (mechanical scalper) — better raw numbers |
| C | Run both, they may complement each other |

Want me to add the regime filter and re-test?
