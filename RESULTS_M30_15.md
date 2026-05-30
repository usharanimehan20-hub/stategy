# 30M Bias / 15M Entry — Test Results

You asked: bias on 30M, candle theory on 15M, entry on 15M. Implemented and tested.

## Headline

| # | Configuration | Window | Best config | Net pts | PF | Trades | WR | Max DD |
|---|---|---|---|---|---|---|---|---|
| 1 | **m1** (15M bias / 1M entry) + 3M-swing SL + session | 3.5 mo | ribbon_ema55 + P2 + RR 1:5 + 3pt | **+1125** | **1.64** | 233 | 34.8% | 227 |
| 2 | **m30_15** (30M bias / 15M entry) + 3M-swing SL + session | 3.5 mo | ribbon_ema100 + **P1** + RR 1:5 + 3pt | +789 | 1.36 | 232 | 30.6% | 294 |
| 3 | **m30_15** on M15 only (no 1M data) + session | **4 yrs** | ribbon_only + **P1** + RR 1:5 + 3pt | +1401 | 1.10 | 3015 | 34.5% | 349 |

## Verdict

**The original 15M-bias setup is still the winner** when 1-min data is available.

Going from 15M bias to 30M bias on the same data:
- Net P/L: 1125 → 789 pts (**−30%**)
- PF: 1.64 → 1.36 (**−17%**)
- Max DD slightly worse: 227 → 294

So your gut feeling that "higher TF bias = more reliable" is half-true — it does filter out more noise — but you also lose more good entries because the 30M bias is slow to flip during fast moves.

## Where m30_15 IS useful: long-history M15 backtests

| Run | Net pts (4 yr) | PF |
|---|---|---|
| Old m15 (everything on 15M) | **−274** (loses) | 0.99 |
| New m30_15 on same M15 file | **+1401** (winning) | 1.10 |

So if you only have M15 historical data (no 1M), m30_15 is genuinely better than m15-everything. The 30M bias does its job filtering chop.

## Observations from the run

1. **Pattern preference flips:** With 30M bias, **P1 (favored candle continuation) wins**. With 15M bias, **P2 (opposite candle + break) wins**. Why: 30M bias is stable enough that simple continuation works; 15M bias flips fast enough that reversal trades catch more turning points.

2. **Trade frequency:** m30_15 ≈ m1+filters (both ~2.3 trades/day). So slower TF doesn't reduce trade count — it just changes what counts as a setup.

3. **Drawdown is worse:** Because 30M bias is slow to flip, if you're on the wrong side of a regime change you eat 2–3 losing trades in a row. m1+filters had 227 max DD; m30_15 had 294.

4. **Session filter still works:** Adding session filter to m30_15 took +295 → +789 (M1) and adding session to m30_15-M15 took +815 → +1401 (4yr). Same finding as before — chop hours kill returns.

## Recommendation

**Stick with the original m1 setup (15M bias / 1M entry / 3M-swing SL / session filter).** It wins on every metric.

Use m30_15 only as a **research view** for long-history M15 data where 1M isn't available.

## Files

- `results_m30_15_M1.csv` — m30_15 on M1, no filter
- `results_m30_15_M1_session.csv` — m30_15 on M1 + session
- `results_m30_15_M15.csv` — m30_15 on M15 (4yr), no filter
- `results_m30_15_M15_session.csv` — m30_15 on M15 (4yr) + session
- `trades_m30_15_*.csv` — best-config trade logs
- `backtest.py` — engine now supports `--mode m30_15` and `--sl-method swing15m`

## Re-run

```bash
# 30M bias, 15M entry, on M1 data with session filter
python3 backtest.py --csv XAUUSD_M1_*.csv --mode m30_15 --session "2,5,8,13,14,15,16,22"

# 30M bias, 15M entry, on M15 data (4-year run)
python3 backtest.py --csv XAUUSD_M15_*.csv --mode m30_15 --session "2,5,8,13,14,15,16,22"
```
