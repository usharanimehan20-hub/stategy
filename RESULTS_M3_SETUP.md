# 3M Candle Theory Test

You asked: **15M bias + 3M candle theory + 1M BOS entry + RR 1:2 fixed**.

## Honest verdict: works at RR 1:2.5+, NOT at RR 1:2

### Walk-forward results (3 folds on M1 data)

| Config | Fold 1 | Fold 2 | Fold 3 | Mean | WR | PF | Robust? |
|---|---|---|---|---|---|---|---|
| 3M+P2+RR 1:1.5 | -23 | +89 | +80 | +49 | 43% | 1.12 | NO (fold 1 negative) |
| **3M+P2+RR 1:2** | **-11** | +100 | +107 | **+66** | 36% | 1.16 | **NO (fold 1 −11)** |
| 3M+P2+RR 1:2.5 | +25 | +9 | +97 | +44 | 32% | 1.11 | **YES** ✓ |
| 3M+P2+RR 1:3 | +38 | +32 | +125 | +65 | 31% | 1.18 | **YES** ✓ |
| 3M+P2+RR 1:4 | +95 | -109 | +109 | +32 | 26% | 1.11 | NO |
| 3M+P2+RR 1:5 | +42 | -48 | +107 | +34 | 24% | 1.10 | NO |

**Why RR 1:2 fails:** at 36% WR, breakeven RR is 1:1.78. RR 1:2 gives only 0.08R/trade expectancy — spread eats it on bad folds.

### Full-window results (entire 3.5 months)

| Config | Trades | WR | Net pts | PF | DD | Trades/day |
|---|---|---|---|---|---|---|
| 3M+P2+RR 1:2 | 651 | 33.6% | +7 | 1.00 | 455 | 6.4 |
| **3M+P2+RR 1:2.5** | **627** | **30.6%** | **+158** | **1.04** | **436** | **6.2** |
| 3M+P2+RR 1:3 | 592 | 27.9% | -40 | 0.99 | 506 | 5.9 |

Full-window winner: **RR 1:2.5 with +158 pts**. RR 1:3 was robust in walk-forward but NEGATIVE on full window — the folds happened to skip the worst chop.

## How it stacks vs the existing winners

| Setup | WR | Net (3.5mo) | PF | Max DD | Trades | trd/day |
|---|---|---|---|---|---|---|
| **PR #3** (15M setup, RR 1:5) | 33% | **+1074** | **1.59** | 238 | 232 | 2.3 |
| PR #5 (15M + BE+trail, RR 1:3) | 53% | +677 | 1.45 | 133 | 274 | 2.7 |
| **NEW: 3M setup + RR 1:2.5** | 31% | +158 | 1.04 | 436 | 627 | 6.2 |
| 3M setup + RR 1:2 (your spec) | 34% | +7 | 1.00 | 455 | 651 | 6.4 |

**The 3M setup is ~7× weaker than the 15M setup** in net P/L, with **2× the drawdown and 3× the trade frequency**.

## Why the 3M setup is weaker

1. **3M candles are noisy.** Smaller bodies, less significance per setup. The 15M candle is a more meaningful "decision point" on the chart.
2. **Fixed RR 1:2 is below break-even** for the WR this strategy generates. Need 50%+ WR to make 1:2 work.
3. **6 trades/day vs 2/day** = more spread cost as % of profit, more drawdown swings, more noise.
4. **The longer history (M5, 17mo) showed RR 1:3 with no BE/trail is the only robust setup** — and that needs 15M setup, not 3M.

## What the data says, plain

- ✅ 15M bias / **15M setup** / 1M BOS / RR 1:5 — best edge (PR #3)
- ✅ 15M bias / **3M setup** / 1M BOS / RR 1:2.5 — also has edge but **7× weaker**
- ❌ 15M bias / 3M setup / 1M BOS / **RR 1:2** — your exact spec — barely break-even
- ❌ 15M bias / **5M setup** / 1M BOS — fails walk-forward
- ❌ Anything single-TF (1M-only, 5M-only) — fails walk-forward

## Recommendation

**Stay with 15M setup (PR #3 or PR #5).** The 3M setup test proves the principle ("setup TF can vary") but in practice 15M is genuinely the sweet spot.

If you want **higher trade frequency** for more action, 3M+RR 1:2.5 works but at 1/7 the P/L of 15M setup. Probably not worth the trade-off.

## Files

- `backtest.py` — engine (already supports arbitrary setup TF via `bias_tf_minutes` param)
- `trades_3m_setup_rr3.csv` — trade log of best walk-forward config (RR 1:3)
- `RESULTS_M3_SETUP.md` — this file
