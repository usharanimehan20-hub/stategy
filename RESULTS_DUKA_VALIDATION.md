# Config 1 Validation on 18 Months of Real Dukascopy 1-Minute Data

Downloaded 18 months (Dec 2024 - May 2026) of real XAUUSD 1-minute data directly
from Dukascopy (525,570 bars, verified bit-exact against the user's own export).

## Verdict: Config 1 (strong-reject-ribbon) does NOT survive long data

| RR | WR | Net | PF | Losing months | Walk-forward robust? |
|---|---|---|---|---|---|
| 1:1.5 | 41.9% | -168 | 0.95 | 9/18 | NO |
| 1:2   | 36.2% | -83  | 0.98 | 11/18 | NO |
| 1:3   | 32.0% | +40  | 1.01 | 10/18 | NO |

On the original 3.5-month window Config 1 showed 51% WR / 0 losing months, but that
was OVERFIT to Feb-May 2026. On the full 18 months it loses or breaks even.

## What this means
- The longer data did its job: it exposed a false positive before any real money.
- PR #8 (5M BB scale-out, 17 months M5) remains the only long-validated edge:
  47% WR, +903 pts, PF 1.22, 3/18 losing months.

## Tooling
- `dukascopy_dl.py` downloads any date range of 1-min XAUUSD from Dukascopy,
  bit-exact vs official export. Usage:
    python3.12 dukascopy_dl.py --symbol XAUUSD --start 2024-01-01 --end 2026-05-29 --out out.csv --workers 10
