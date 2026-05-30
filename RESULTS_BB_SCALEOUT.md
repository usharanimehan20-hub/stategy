# BB Scale-Out Refinement — Better RR + Lower Drawdown

You asked: keep the decent WR, get a better reward:risk. The fix is **scale-out**
(bank a partial near target, move stop to breakeven, trail a runner). Tested on
the PR#7 foundation, exit-management only.

## Winner vs PR#7

| Metric | PR#7 (fixed RR1.5) | **Scale-out winner** | Change |
|---|---|---|---|
| Win rate | 46.4% | **47.1%** | +0.7pp |
| Net (17mo) | +791 | **+903** | +14% |
| Profit factor | 1.18 | **1.22** | +0.04 |
| **Max drawdown** | 206 | **160** | **−22%** |
| Effective RR (avg win/avg loss) | 1.36 | 1.37 | ~same |
| Losing months | 3/18 | **3/18** | same |
| Worst month | −100 | **−92** | better |
| Max consecutive losses | 16 | 16 | same |

A clean Pareto improvement: more money, higher PF, lower drawdown, same WR.

## The winning config

```
FOUNDATION (unchanged from PR#7):
  Bias:    30M ribbon-only (WMA 34/64)
  BB:      BB(30, 1.5) on 5M
  Entry:   price touches band against bias within 3 bars, then 5M closes back in bias dir
  SL:      pullback swing low/high - 3pt
  Filters: ATR ratio < 1.5, London+NY (08-17 UTC), 2-loss/1h cooldown

NEW EXIT MANAGEMENT (scale-out):
  TP1:     at +1.5R, close 70% of the position
  Runner:  remaining 30% -> stop to breakeven, then trail on 5M swings
  Final:   runner target RR 1:5 (rarely reached; trail usually exits sooner)
```

## Walk-forward (3 folds) — ROBUST

| Fold | Window | Trades | WR | Net | PF |
|---|---|---|---|---|---|
| 1 | 2025-03-28 → 05-26 | 114 | 53.5% | +163 | 1.41 |
| 2 | 2025-07-21 → 09-18 | 91 | 48.4% | +74 | 1.31 |
| 3 | 2025-11-12 → 2026-01-10 | 113 | 49.6% | +205 | 1.48 |

Positive in every fold.

## Monthly P/L (15 of 18 winning)

Feb-Mar 2026 (the regime that destroyed the raw BB) now print **+141 / +110**.
The 3 small losing months: 2025-07 (-3), 2025-09 (-92), 2026-04 (-64).

## The RR honesty note

Effective RR is ~1.37 (avg win +10.8 / avg loss -7.9). If you want a genuinely
*higher* RR number, the only lever is to widen the target and trail harder:

```
be+trail rr=5, BE@1R, swing trail  ->  effRR 1.90  BUT  WR 38%, DD 323
```

That trades win-rate and drawdown for a bigger RR number. It is NOT better overall
(net +682 vs +903). On this data, **47% WR x effRR 1.37 is the efficient point** —
pushing RR higher mechanically drops WR proportionally so the edge is similar but
the ride is rougher.

## Files
- `sweep_bb_rr.py` — exit-management sweep (fixed RR vs scale-out vs be+trail)
- `confirm_bb_rr.py` — monthly + walk-forward confirmation of the winner
- `results_bb_rr.csv` — all exit configs
- `trades_bb_scaleout_winner.csv` — winning config trade log

## Run it
```bash
python3 confirm_bb_rr.py
```
