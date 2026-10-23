# Group rows and compute charges

- [ ] One invoice per client per work month, numbered in date order from the
      ledger's high-water mark
- [ ] Week: each tag collapses to one week charge, and its rows bill nothing else
- [ ] Day: 8+ hours (block size from the header) of plain hourly rows for one client on
      one date is one day, plus the remainder hourly
- [ ] Line text: `19 Nov — <task; task> (daily rate)` / `(hourly rate)`. Week lines use the
      tag; fixed lines use the row's Task.
- [ ] Foreign currency: rate = AUD rate / fx rate, rounded to the cent. Line = qty × rate.
      amount_aud = amount × fx rate.
- [ ] Hour: every other date, at the exact decimal hours
- [ ] Fixed: one line per row carrying an amount, described by that row's Task. Hours never
      reach the invoice.
- [ ] Decimal throughout. Quantize per line with ROUND_HALF_UP.
- [ ] GST: none (unregistered), 10% domestic or 0% export, per line
- [ ] FX: `amount_aud`, `fx_rate`, `fx_date`, plus the source name
- [ ] Booked-week report lines (`!` marked when hours ≠ 40 or days ≠ 5)
- [ ] Hand-check the fixture results in a test
