# Backtest Results — Honest Read

Strategy is fully implemented per `STRATEGY.md`. We ran three parallel backtests on the data you uploaded and the findings below tell the real story before automation. All P/L figures are in **gold points** (1 pt = $1 per 1.0 lot on standard XAUUSD), with 0.3 pt round-trip spread modeled.

## Why three runs, not one

You have:

| File | Bars | Coverage |
|---|---|---|
| `XAUUSD_M1_*.csv` | 100,192 | **3.5 months** (Feb 16 → May 29, 2026) |
| `XAUUSD_M15_*.csv` | 100,013 | **4 years** (Mar 2022 → May 2026) |

1-minute history is too short to be statistically robust. 1M data **cannot** be reconstructed from 15M without fabricating intra-bar movement, so we don't synthesize it. Instead:

| Run | Data | Engine mode | Trade window |
|---|---|---|---|
| **A** | Real M1 | Setup on resampled 15M, entry on real 1M | 3.5 months |
| **B-recent** | M15 only | Everything on 15M (next-bar trigger) | Same 3.5 months as A |
| **B-full** | M15 only | Everything on 15M | Full 4 years |

A vs B-recent = how much edge we lose by stepping the entry from 1M to 15M.
B-full = does the strategy hold up over multiple market regimes?

## Top 5 from each run

### Mode A — Real 1M, 3.5 months
```
ma_combo      pattern  rr   sl_buf  trades  win%   net_pts  PF    max_DD  trd/day
ribbon_only   P2       3.0  2.0     697     28.3   226.08   1.06  243.15  6.90
ribbon_ema55  P2       3.0  2.0     707     28.4   225.82   1.06  245.49  7.00
ribbon_ema55  P2       5.0  2.0     643     21.6   197.26   1.06  321.65  6.37
ribbon_ema55  P2       4.0  2.0     677     23.5   174.86   1.05  250.41  6.70
ribbon_only   P2       5.0  2.0     636     21.1   174.49   1.05  394.24  6.30
```

### Mode B-recent — 15M only, same 3.5-month window
```
ma_combo      pattern  rr   sl_buf  trades  win%   net_pts  PF    max_DD  trd/day
ribbon_ema55  P2       5.0  2.0     390     33.9   589.88   1.19  358.45  3.85
ribbon_ema55  P2       2.0  2.0     420     39.5   574.25   1.17  307.36  4.14
ribbon_only   P2       2.0  2.0     417     39.3   569.27   1.17  307.36  4.11
ribbon_only   P2       5.0  2.0     392     33.4   566.54   1.17  375.27  3.87
ribbon_only   P2       5.0  3.0     383     34.5   555.95   1.17  426.46  3.78
```

### Mode B-full — 15M only, 4 years
```
ma_combo      pattern  rr   sl_buf  trades  win%   net_pts  PF    max_DD  trd/day
ribbon_ema55  P1       5.0  3.0     6062    39.1   641.99   1.03  1408.98 3.93
ribbon_only   P1       5.0  3.0     6092    39.7   448.15   1.02  1538.08 3.95
ribbon_only   P2       3.0  3.0     4936    39.9   327.83   1.02  1604.09 3.20
ribbon_only   P2       5.0  3.0     4876    39.4   298.03   1.02  1538.32 3.16
ribbon_ema55  P1       5.0  2.0     6447    36.9   258.44   1.01  1593.55 4.18
```

Full 144-config tables: `results_modeA.csv`, `results_modeB_recent.csv`, `results_modeB_full.csv`.

## Findings

1. **MA combo:** `ribbon_only` and `ribbon + EMA55` consistently beat anything that includes EMA100 across all three runs. **EMA100 in the bias filter hurts performance.**
2. **Pattern:** Pattern 2 dominates in the recent windows (both A and B-recent). Pattern 1 wins only in the long 4-year run, and even there with very thin edge.
3. **RR:** sweet spot is **1:3 to 1:5**. RR 1:1 and 1:1.5 lose money in every run.
4. **SL buffer:** 2 pts mostly beats 3 pts (tighter stops + better avg trade).
5. **Edge is thin:**
   - Mode A best: PF 1.06 (every $1.06 won per $1 lost — barely profitable after real-world slippage).
   - Mode B-recent best: PF 1.19 (better, but on coarser entries).
   - Mode B-full best: PF 1.03 (over 4 years, basically breakeven).
6. **Drawdown is heavy:** Mode B-full's best config has max DD of **1409 pts vs 642 pts net P/L**, i.e. peak-to-trough loss > 2× total profit.
7. **Mode A monthly breakdown** (best config): Feb -135, Mar +311, Apr +192, May -142 → **2 winning months, 2 losing months**. Equity curve is choppy.

## Honest verdict on automation readiness

**Not yet.** The strategy as defined has a real but very thin edge. Things that need to be addressed before live automation:

1. **Slippage / commission realism.** Live spread on gold is typically 2–5 pts during NY session, far above the 0.3 pt I modeled. With 5 pt spread × 700 trades = 3500 pts cost — wipes out the edge entirely.
2. **No regime/session filter.** Most of the bad months are during low-volatility/range-bound periods. Adding a simple ATR or session filter (e.g., only trade London/NY overlap) likely materially improves PF.
3. **Bias persistence policy.** Currently a bias persists indefinitely until invalidated — in 4-year data this leads to many trades during low-volatility chop. A "fresh bias only for N bars after set" rule is worth testing.
4. **Pattern split is window-dependent.** P2 in 2026, P1 in long history. Either we trust the recent window or we'd want to test specific years. This suggests **regime sensitivity**.

## Recommended next steps (your call)

| Priority | What | Why |
|---|---|---|
| 1 | Re-run Mode A with realistic spread (2 / 3 / 5 pts) | Find break-even spread — tells us if strategy is live-tradeable |
| 2 | Add session filter (e.g., 12:00–20:00 UTC only) | Likely cuts trade count and lifts PF |
| 3 | Add ATR filter on entry candle (skip if ATR < threshold) | Skips chop |
| 4 | Test "bias must be fresh" (set within last N 15M bars) | Avoids stale-bias trades |
| 5 | If still thin, lock RR to 1:3 + Ribbon-only + Pattern 2 and **paper-trade** before live | Verify in real conditions |

If you want me to proceed with any of these, say the word. I'd start with #1 because it determines if the strategy is even worth automating with realistic broker costs.

## Files in this PR

- `STRATEGY.md` — strategy specification (unchanged from prior commit)
- `backtest.py` — engine with Mode A + Mode B
- `RESULTS.md` — this file
- `results_modeA.csv` — Mode A leaderboard (144 configs)
- `results_modeB_recent.csv` — Mode B-recent leaderboard
- `results_modeB_full.csv` — Mode B-full leaderboard
- `trades_modeA.csv` — full trade log of Mode A's best config
- `trades_modeB_full.csv` — full trade log of Mode B-full's best config
- `trades_modeB_recent.csv` — full trade log of Mode B-recent's best config

To re-run yourself after dropping new data:
```bash
python3 backtest.py --csv your_m1_file.csv          # Mode A (auto)
python3 backtest.py --csv your_m15_file.csv         # Mode B (auto)
python3 backtest.py --csv your_m15_file.csv --start 2024-01-01    # date slice
python3 backtest.py --csv your_m1_file.csv --quick  # smoke test
```
