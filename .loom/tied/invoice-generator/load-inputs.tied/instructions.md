# Load and type-convert every input

`load_inputs()` in `make_invoices.py`; tests in `tests/test_load_inputs.py`.

- [x] `config.txt` via `tomllib` with `parse_float=Decimal`, so 0.1450 stays exact.
      Required keys are checked by type. `abn` is required only when registered.
      `[invoicing] invoice_date` is optional and defaults to today. There is no
      `[paths]` section.
- [x] `clients.txt`: tier, currency and country are closed sets (strip, casefold,
      currency uppercased). The allowed currencies are home plus every
      `[currency.X]` in the config. The country is the last comma part, matched
      against `COUNTRIES` (everyday names, none with commas). Duplicate clients and
      projects under two clients are errors, compared ignoring case.
- [x] `rates.txt`: block size comes from the header number, except `Hour`, which
      means 1. Rows with no figures are skipped; rows with some figures are errors.
      `$3,000.00` is parsed to a Decimal.
- [x] `timesheet.txt`: dates like `November 2, 2026`. Hours are a Decimal, a multiple
      of 0.25 and ≥ 0. Billing type must be empty, `week rate` or `fixed price`. The
      last column is a tag, an amount or empty to match. Empty Task or Project is an
      error.
- [x] `ledger.csv`: missing means a first run. The header must equal
      `LEDGER_COLUMNS`. Rows become `LedgerWork` / `LedgerCharge`, and errors name
      the line number.
- [x] Errors follow the brief's format. Every file is checked; cross-file checks wait
      until all files load cleanly.
