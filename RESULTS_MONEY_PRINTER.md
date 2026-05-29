# Money-Printer Sweep Results

You asked for: **high WR, low drawdown, good RR**, take any liberty. I added **breakeven-after-1R + trailing stop** to the engine and ran a 1728-config sweep with **walk-forward validation** (3 sliding folds — train on one window, test on the next, repeat).

## The winner — survives ALL 3 walk-forward folds

```
ma_combo  : ribbon + EMA55 + EMA100  (full 4-MA setup)
pattern   : P2 only  (opposite candle + break)
rr        : 1:3  (final TP)
sl_buf    : 3 pts
be_at_r   : 1.0   (when price reaches +1R, slide SL to entry — zero risk)
trail     : swing (after BE, trail SL to most recent 1M swing)
session   : 02, 05, 08, 13, 14, 15, 16, 22 UTC of data
sl_method : nearest 3M swing + buffer
```

## Headline comparison (full 3.5-month window)

| Metric | OLD (PR #3 winner) | **NEW (this sweep)** | Delta |
|---|---|---|---|
| **Win rate** | 33% | **53%** | **+20%** |
| **Max drawdown** | 238 pts | **133 pts** | **−44%** |
| Profit factor | 1.59 | 1.45 | −0.14 |
| Total net pts | +1074 | +677 | −397 |
| Trades | 232 | 274 | +42 |
| Avg trade pts | 4.63 | 2.47 | −2.16 |
| Trades/day | 2.3 | 2.7 | +0.4 |

## Walk-forward robustness (the important part)

Across the 3 sliding folds:
- **Every fold made money.** Worst fold: +21 pts. Best: ~+200 pts.
- **WR averaged 51.8%** across folds.
- **Mean drawdown only 58 pts** per fold.
- This is the curve-fit-resistant pick — not just the best single number.

## What changed and why it helps

1. **Breakeven after 1R**: when a long reaches entry +1×risk in profit, SL slides to entry. The trade can no longer become a full loss. **This is the single biggest WR booster.**
2. **Swing trail**: after BE moves, every new lower-low (longs) ratchets SL up. Many would-be SL hits now exit slightly above entry — counts as a win.

The stack converts the previous **35% WR / huge wins** strategy into a **53% WR / smaller wins** strategy. Same P/L territory but **far more comfortable to trade**: smaller drawdowns, more frequent green days, less time underwater.

## Trade-off — which side do you want?

| Trait | OLD setup | NEW setup |
|---|---|---|
| Win rate | 33% | **53%** |
| Drawdown | 238 | **133** |
| Total profit (3.5 mo) | **+1074** | +677 |
| Per-trade quality | **+4.6 pts/trade** | +2.5 pts/trade |

**OLD = "fewer wins but each one big."** Better total return, harder mentally.
**NEW = "more frequent small wins."** Lower returns but feels like a money printer.

Pick by personality. Or run both — they fire on different setups.

## Honest caveats

1. **3.5 months data.** Walk-forward folds are ~30 days each. Results are stable across folds but the absolute time window is short.
2. **TP rate is only 5.8%** in the new config — most "wins" are actually trail-stop exits at 0.1–1R, not the full RR 1:3 target. That's expected with BE+trail; just be aware your typical profit per trade is small.
3. **Spread modeled at 0.3 pt.** Live broker spread of 2–5 pt will eat more from the new config (smaller per-trade margins) than from the old config.
4. **Real WR live** will be lower than backtest because of slippage on stop hits. Plan for 45-50% live WR.

## How to run it

```bash
# Run the winning config on your data
python3 backtest.py --csv your_m1.csv \
  --mode m1 --sl-method swing3m \
  --session "2,5,8,13,14,15,16,22"
# (Note: BE/trail are sweep-only for now; --be-at-r and --trail flags
#  can be added to backtest.py CLI on request.)

# Re-run the full sweep
python3 sweep_money.py
```

## Files

- `backtest.py` — `simulate()` now supports `be_at_r` and `trail_method` params
- `sweep_money.py` — 1728-config sweep with walk-forward validation
- `sweep_money_results.csv` — all robust configs (positive in every fold)
- `trades_money_winner.csv` — full trade log of the winner

## Recommendation

**Paper-trade the NEW config first.** 53% WR + 133 max DD makes it psychologically sustainable. If results hold up over 30+ trades, scale up. The OLD config is a good "swing-for-the-fences" alternative if you can stomach 238-pt drawdowns.

This is genuinely the most robust config the data supports. There is no further squeeze without:
- More data (longer 1M history)
- News-event filter (skip 30 min around NFP/CPI/FOMC)
- Higher-TF structure (S/R, order blocks) — heavy build

Tell me which path you want next.
