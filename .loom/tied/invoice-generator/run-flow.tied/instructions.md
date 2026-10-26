# Preview, report, and the commit gate

`run()` / `preview_summary()` / `rolling_turnover()` in `make_invoices.py`; tests in
`tests/test_run.py`.

- [x] Render draft PDFs into a fresh `tempfile.mkdtemp(prefix="invoice-preview-")`
      folder, outside the invoicing folder
- [x] Print the invoice date (noting when it came from config.txt), one line per
      invoice, booked weeks, fixed-price rows that charged nothing, the rolling
      12-month turnover and the preview path. Empty sections are left out.
- [x] Turnover: amount_aud ex GST, ledger plus this run, window (end − 1 year, end]. Warns
      from `turnover_warn_at`, and over the threshold gives the 21-day deadline. No
      warnings once registered.
- [x] `open` the preview folder in Finder (injectable for tests)
- [x] Exactly `commit` (spaces trimmed) proceeds; anything else, EOF or Ctrl-C at the
      prompt discards
- [x] The preview is deleted in a `finally`, so commit, discard and crash all clean up.
      Nothing in the invoicing folder is touched before commit.
- [x] Exit codes: 0 committed or nothing to do, 1 refused, 2 discarded, 130 Ctrl-C
- [x] Real run checked on a fixture copy. `commit()` is a stub until commit-outputs.
