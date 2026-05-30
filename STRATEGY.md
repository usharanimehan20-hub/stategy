# Gold (XAUUSD) — Multi-MA Bias + Candle Theory Strategy

## 1. Instrument & Timeframes

| Item | Value |
|---|---|
| Asset | Gold (XAUUSD) |
| **Bias timeframe** | **15-minute** |
| **Entry timeframe** | **1-minute** |
| Session filter | None — 24/5 |
| Trade count limit | None |

---

## 2. Indicators

### Bias indicators (plotted on 15M)
| MA | Type | Length | Source | Role |
|---|---|---|---|---|
| WMA 34 | Weighted | 34 | Close | Ribbon 1 |
| WMA 64 | Weighted | 64 | Close | Ribbon 1 |
| EMA 55 | Exponential | 55 | Close | Trend filter |
| EMA 100 | Exponential | 100 | Close | Trend filter |

### Stop-loss anchors (plotted on 1M)
| MA | Type | Length | Source |
|---|---|---|---|
| EMA 8 | Exponential | 8 | Close |
| EMA 21 | Exponential | 21 | Close |

> Slope direction is **irrelevant**. Only price-vs-MA position matters.

---

## 3. Bias Rules (15M, strict)

A **15-minute candle** sets bias only when its **body close** satisfies all four conditions in the same direction.

### Bullish bias is set when:
- Close > WMA 34 **AND**
- Close > WMA 64 **AND** *(i.e. body fully above Ribbon 1)*
- Close > EMA 55 **AND**
- Close > EMA 100

### Bearish bias is set when:
- Close < WMA 34 **AND**
- Close < WMA 64 **AND**
- Close < EMA 55 **AND**
- Close < EMA 100

### No bias / Avoid:
- Body crosses Ribbon 1 but EMA 55/100 still on the other side → **no trade**.

### Bias persistence
Once set, the bias remains **active until invalidated** by an opposite-direction qualifying 15M close. All 1-min entries during this window use the active bias.

---

## 4. Entry Rules — Candle Theory

The setup pattern lives on the **15-minute** chart. The entry trigger is taken from the **1-minute** chart inside the next 15M window.

### Pattern 1 — Favored 15M candle, then 1M BOS confirmation
Bias = bullish (mirror for bearish):
1. A **15M candle** closes **green** (close > open) — the "favored" setup candle.
2. During the next 15M window (i.e. the next 15 one-minute bars), watch the 1-minute chart.
3. The **first 1-minute bar** that satisfies BOTH:
   - body close in bias direction (close > open), AND
   - close > previous 1-min close (BOS body close)

   → **Entry** at that 1-minute close.

### Pattern 2 — Opposite 15M candle, then high break + 1M BOS
Bias = bullish (mirror for bearish):
1. A **15M candle** closes **red** (close < open) — opposite-direction setup candle.
2. During the next 15M window, on the 1-minute chart:
   - First, a 1-min bar's **high must break the prior 15M candle's high**.
   - Then (or on the same 1-min bar), the first 1-min bar with body close in bias direction AND close > previous 1-min close.

   → **Entry** at that 1-minute close.

### Setup expiry
A setup is armed at the close of the 15M setup candle and expires **15 one-minute bars later** (i.e., at the close of the next 15M). If no entry trigger fires within that window, the setup is dead.

### One-position rule
Only one trade open at a time. New setups armed while a position is live are skipped (no pyramiding).

---

## 5. Stop Loss

- **Long:** SL = **EMA 21 (1M) − buffer**
- **Short:** SL = **EMA 21 (1M) + buffer**
- **Buffer:** 2–3 points (configurable; will sweep both in backtest)

EMA 8 is shown as a reference for tighter trailing reads but the hard SL anchor is EMA 21.

---

## 6. Take Profit

To be determined by backtest. Sweep range: **RR 1:1, 1:1.5, 1:2, 1:3, 1:4, 1:5** of the SL distance.

---

## 7. Backtest Matrix

We will run the full cross of:

| Axis | Values |
|---|---|
| MA combo for bias | (a) WMA 34/64 only<br>(b) WMA 34/64 + EMA 55<br>(c) WMA 34/64 + EMA 100<br>(d) WMA 34/64 + EMA 55 + EMA 100 *(your full setup)* |
| Risk:Reward | 1:1, 1:1.5, 1:2, 1:3, 1:4, 1:5 |
| SL buffer | 2 pts, 3 pts |
| Entry pattern | Pattern 1 only, Pattern 2 only, Both combined |

**Total combinations:** 4 × 6 × 2 × 3 = **144 configurations** — we report top performers by:
- Net P/L
- Win rate
- Profit factor
- Max drawdown
- Trades per day

---

## 8. Open assumptions (please confirm or override)

| # | Assumption | My default |
|---|---|---|
| A | When a 15M bias-setting candle closes mid 1M-trade, do we keep the trade? | Yes — once entered, manage by SL/TP only |
| B | Re-entry on the same bar after stop-out? | No — one position at a time, no pyramiding |
| C | If TP and SL both hit in same 1M bar, which wins? | Conservative: assume SL hit first |
| D | Spread / commission | Modeled as 0.3 points round-trip (gold typical); easy to change |
| E | "Body close in bias direction" for confirmation = candle closes green for bullish, red for bearish? | Yes |

---

## 9. Data requirement

CSV with **1-minute** XAUUSD bars. Required columns:

```
timestamp, open, high, low, close
```

(Volume optional, ignored.) The 15M bias is **resampled internally** from the 1-min data — so a single 1-min CSV is enough.
