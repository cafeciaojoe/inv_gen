# Cross-file validation (all hard errors, nothing written)

`validate()` / `check_inputs()` in `make_invoices.py`; tests in
`tests/test_validate.py`.

- [x] Unknown project: not listed in clients.txt. Matched exactly; the error lists the
      known projects.
- [x] Duplicate lines: `date + project + hours + task` matches the ledger (naming the
      invoice) or another line in the same paste. Hours are compared as numbers, so
      2 matches 2.0.
- [x] Unknown country at the end of an address (done in load-inputs)
- [x] Week tag on rows resolving to more than one client
- [x] Week tag whose rows fall in two calendar months
- [x] Week tag already billed: it matches the `description` of a ledger charge row with
      `unit=week`, ignoring case and spacing
- [x] Week tags that differ only in capitals or spacing (they would bill two weeks)
- [x] Work dated after the invoice date, which also catches a forgotten override
- [x] Billed client's tier missing from rates.txt
- [x] Billed client's currency has no `[payment.<CUR>]` block
- [x] Foreign currency: `as_at` equals the invoice date
- [x] All errors are collected and printed together
- [x] A test per check. Clients with nothing in the timesheet can't stop the run.
