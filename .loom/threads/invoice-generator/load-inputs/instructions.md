# Load and type-convert every input

- [ ] `config.txt` via `tomllib`. Check the required keys. `[invoicing] invoice_date` is
      optional and defaults to today. There is no `[paths]` section any more.
- [ ] `clients.txt`: tier, currency and country are closed sets (strip, casefold,
      currency uppercased). Address country is the last comma part. Projects are
      comma-split. Duplicate client and project-under-two-clients are errors.
- [ ] `rates.txt`: block size comes from the header number, except `Hour`, which means 1. Skip rows whose rate cells
      aren't all numeric. Parse `$3,000.00` to Decimal. Tiers are matched casefolded.
- [ ] `timesheet.txt`: date `November 2, 2026` becomes a date. Hours are a Decimal, a multiple of 0.25 and ≥ 0.
      Billing type must be empty, `week rate` or `fixed price`. The last column is a tag,
      a number or empty depending on billing type.
- [ ] `ledger.csv`: read existing work and charge rows (may be header-only)
- [ ] Every error uses the brief's format: file, column, value, verbatim row, allowed values
