# 3 Entry Configs Test — Strong-Reject-Ribbon WINS

Your idea: 15M bias, drop to 1M, three entry triggers (bullish; mirror for bearish):
1. **strong candle that rejects the BB band AND closes above Ribbon 1**
2. only BB band rejection
3. price closes above Ribbon 1

Tested all three on 1M data with walk-forward. "Strong" = candle body >= 1.5x the
average body of the last 20 candles. SL = pullback swing low/high - 3pt.

## Verdict

| Config | Best result | Robust? |
|---|---|---|
| **1. strong + reject + ribbon** | **+375, PF 1.45, 0/4 losing months** | **YES** |
| 2. reject only | negative (best -101) | NO |
| 3. ribbon cross only | weak (+185, PF 1.07) | NO |

**Config 1 is the clear winner** — your full combination (strong candle + band
rejection + ribbon confirmation) is what creates the edge. The pieces alone
(Config 2, Config 3) do not work. Confluence is everything.

## Config 1 — three RR flavors (pick your style)

All use: 15M ribbon bias, BB(30,1.5) on 1M, strong+reject+ribbon entry, all hours,
pullback SL, 2-loss/1h cooldown. Every month profitable in all three.

| Flavor | WR | Eff RR | Net | PF | Max DD | Max consec loss | Trades/day |
|---|---|---|---|---|---|---|---|
| **RR 1:1.5 (high WR)** | **51.0%** | 1.47 | +356 | 1.53 | **68** | 6 | 1.5 |
| **RR 1:2 (balanced)** ⭐ | 42.3% | **2.01** | +365 | 1.48 | 84 | 6 | 1.5 |
| **RR 1:3 (high RR)** | 33.8% | **2.84** | +375 | 1.45 | 90 | 8 | 1.5 |

This is exactly what you asked for: **decent WR + good RR**. The RR 1:2 flavor gives
**42% WR with effective RR 2.0** — a genuinely good payoff profile. Even the high-WR
flavor keeps a 1.47 effective RR at 51% WR.

## Monthly P/L (RR 1:2 balanced)

```
2026-02  +3      (WR 37%)
2026-03  +158    (WR 47%)
2026-04  +182    (WR 46%)
2026-05  +23     (WR 36%)
```
0 losing months. Worst month +3 (never red).

## Why Config 1 works

- **BB rejection** = price stretched too far, snapping back (mean reversion)
- **Strong candle** = real momentum behind the snap-back, not a weak drift
- **Above Ribbon 1** = the snap-back has already reclaimed the short-term trend
- **15M bias** = only taken in the higher-TF direction

All four must align. That selectivity (only ~1.5 trades/day) is why every month is green.

## IMPORTANT caveat — short data window

This used the **1-minute file = only 3.5 months** (Feb–May 2026). So "0/4 losing
months" is a 4-month sample, NOT the 17-month proof we have for the 5M BB strategy
(PR #8). Config 1 is **very promising but not yet proven long-term.**

| Strategy | Window | WR | Net | PF | DD | Proof |
|---|---|---|---|---|---|---|
| PR #8 (5M BB scale-out) | 17 months | 47% | +903 | 1.22 | 160 | strong |
| **This Config 1 (RR2)** | **3.5 months** | **42%** | **+365** | **1.48** | **84** | promising, short |

To truly trust Config 1 we need longer 1-minute history (Dukascopy/HistData export
years of 1M XAUUSD free).

## Files
- `sweep_bb_rejection.py` — 3-config sweep with walk-forward
- `confirm_rejection.py` — monthly confirmation of Config 1
- `results_bb_rejection.csv` — all configs
- `trades_rejection_rr2.0.csv`, `trades_rejection_rr3.0.csv`, `trades_rejection_rr1.5.csv`

## Run
```bash
python3 confirm_rejection.py
```
