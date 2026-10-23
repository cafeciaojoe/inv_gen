# Commit: final outputs

`commit()` / `ledger_rows()` / `summary_rows()` / `replace_atomically()` in
`make_invoices.py`; tests in `tests/test_commit.py`.

- [x] Pre-checks before anything is written: no target PDF exists, and ledger.csv has
      the same bytes as when the run read it (`Ledger.raw`)
- [x] Re-render without the draft flag, in memory first, then write to
      `invoices/YYYY-MM/INV-xxxx.pdf` with mode "x"
- [x] Append work and charge rows to `ledger.csv`. It is created with its header on the
      first run. The old bytes are kept exactly (a newline is added if missing), then
      replaced atomically via a temp file in the same folder and `os.replace()`.
- [x] Partial failure, including Ctrl-C: if anything fails before the ledger is
      replaced, the PDFs and folders this commit made are removed. The ledger goes last.
- [x] `Batch.logged_only` rows go to the ledger as work rows with an empty `invoice_no`
- [x] `summary.csv` is built in the preview (`summary_after`), staged beside its target
      before the PDFs, and renamed in last. Sorted by work month: one row per
      invoice, a Total row per month, turnover last. Only the final rename failing keeps
      the commit; any earlier problem stops it.
- [x] Preview cleanup: done by run()'s `finally`
- [x] Real commit checked on a fixture copy
