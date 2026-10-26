# Group rows and compute charges

`compute()` / `charge_lines()` / `week_report()` in `make_invoices.py`; tests in
`tests/test_compute.py`, with every fixture invoice worked out by hand.

- [x] One invoice per client per work month, numbered by month then client name,
      from the ledger's high-water mark (prefix + digits; other formats refused in
      validate)
- [x] Week: each tag collapses to one week charge, and its rows bill nothing else
- [x] Day: 8+ hours of plain hourly rows for one client on one date is one day, plus the
      remainder hourly. Several tasks are joined with "; ".
- [x] Hour: every other date, at the exact decimal hours
- [x] Fixed: one line per row carrying an amount (already in the client's currency),
      described by its Task. Hours never reach the work log.
- [x] Line text: `16 Nov — <task> (daily rate)` / `(hourly rate)`. Lines are in date
      order; within a date, week, day, hour, fixed.
- [x] Decimal throughout. `cents()` quantizes per line with ROUND_HALF_UP (tested on a
      case where banker's rounding differs).
- [x] GST: none and `unregistered` while unregistered, 10% domestic or 0.00 export, per
      line
- [x] FX: rate = AUD rate / fx, rounded. amount_aud = amount × fx. Invoice carries
      `fx_rate`.
- [x] A month with nothing to charge makes no invoice. Its rows go to
      `Batch.logged_only`, for the ledger as work rows with an empty invoice_no.
- [x] Booked-week report with `!` marks, aligned
