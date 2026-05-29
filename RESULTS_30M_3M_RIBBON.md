# 30M Bias + 3M Ribbon Filter + 3M Candle Theory + 1M BOS

You asked: **30M bias + 3M ribbon-must-align filter + 3M candle theory + 1M BOS entry + 3M-swing SL**.

## Result: ONE robust configuration found

After testing 36 combinations through walk-forward validation, exactly **1 config** was positive in all 3 folds:

```
Bias TF:        30-minute (close above/below all 4 MAs: WMA34/64 + EMA55/100)
Filter:         3-minute close must be above/below 3M Ribbon (WMA 34/64) — no EMA needed
Pattern:        P2 only (opposite candle + break)
Setup TF:       3-minute (candle theory pattern detection)
Entry trigger:  1-minute body close BOS in bias direction
SL:             nearest 3M swing high/low + 3pt buffer
RR:             1:1.5  ← key finding (1:2 fails, 1:1.5 works)
Session:        02, 05, 08, 13, 14, 15, 16, 22 UTC
```

## Walk-forward (3 folds)

| Fold | Window | Net pts | WR | Trades |
|---|---|---|---|---|
| 1 | 2026-03-05 → 03-17 | +1 | 41% | 41 |
| 2 | 2026-03-28 → 04-09 | +89 | 49% | 33 |
| 3 | 2026-04-20 → 05-01 | +2 | 38% | 41 |
| **Mean** | | **+31** | **42%** | 115 total |

PF 1.14, every fold positive. The fold 1 result is razor-thin (+1 pt), so this is a robust edge but a thin one.

## Full-window (3.5 months)

| Metric | Value |
|---|---|
| Trades | 350 |
| Win rate | **43.7%** |
| TP rate | 42.3% |
| Net points | **+612** |
| Profit factor | **1.29** |
| Max drawdown | **142 pts** |
| Trades per day | 3.5 |

## Why RR 1:1.5 — and why 1:2 fails

| RR | Mean / fold | Robust? | Logic |
|---|---|---|---|
| 1:1.5 | +31 | **YES** | 42% WR x 1.5R wins beats 58% x 1R losses |
| 1:2 | +14 | NO | needs 50% WR to break even, only got 35% |
| 1:2.5 | −3 | NO | needs 40% WR, only got 32% |
| 1:3+ | negative | NO | WR drops further as TP target moves further |

The strategy generates ~42% WR with a tight TP. Above 1:1.5, the WR drops faster than the RR rises.

## How it stacks vs the other winners

| Setup | WR | Net (3.5 mo) | PF | Max DD | Trades | Notes |
|---|---|---|---|---|---|---|
| PR #3 (15M setup, RR 1:5) | 33% | **+1074** | **1.59** | 238 | 232 | Highest profit |
| PR #5 (15M + BE+trail, RR 1:3) | 53% | +677 | 1.45 | 133 | 274 | Higher WR but fails on M5 longer data |
| **NEW: 30M bias + 3M ribbon + RR 1:1.5** | **44%** | **+612** | **1.29** | **142** | **350** | **Robust on M1, untested on longer data** |

**vs PR #3:** +44% WR is psychologically nicer; ~57% of total profit; similar drawdown.
**vs PR #5:** −9pp WR but PR #5 was overfit to this short window. THIS one passed walk-forward.

## Summary verdict

You found a **legitimate alternative to PR #3** with materially higher WR (44% vs 33%) at the cost of ~43% lower total profit. Both are robust. Pick by personality:

- Want bigger swings, fewer wins? → **PR #3** (33% WR, RR 1:5, +1074 pts)
- Want more frequent wins, smaller swings? → **NEW** (44% WR, RR 1:1.5, +612 pts)
- Both stack the session filter and 3M-swing SL identically

## Caveats (read these)

1. **Only 1 of 36 configs robust.** Narrow edge — ribbon_only + P2 + RR 1:1.5 specifically. Anything else around it (ribbon+EMA, P1, other RRs) failed walk-forward.
2. **Walk-forward fold 1 was +1 pt** — barely above zero. With one bad week shifted, this could flip.
3. **PF 1.14 in walk-forward** vs 1.29 full window. Folds skip some chop periods, so the "real" edge is closer to 1.14.
4. **Spread modeled at 0.3 pt.** Live broker spread (1.5–5 pt) eats more from RR 1:1.5 trades than from RR 1:5 trades. **This setup is more spread-sensitive than PR #3.**
5. **Untested on longer history** — only 3.5 months of M1 data covers it. PR #5 looked great on 3.5 mo but failed on M5 17-mo data — same risk applies here.

## Recommendation

Paper-trade BOTH:
- **PR #3** (15M setup, RR 1:5) on alternating signals
- **THIS** (30M+3M, RR 1:1.5) on its signals

See which feels more sustainable for your style after 30+ trades. They generate different signals (P2 patterns of different setup TFs) so they may even complement each other.

## Files

- `backtest.py` — engine (already supports parameterized bias TF and ribbon filter via combined-bias series)
- `RESULTS_30M_3M_RIBBON.md` — this file
