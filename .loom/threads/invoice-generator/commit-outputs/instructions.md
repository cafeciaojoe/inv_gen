# Commit: final outputs

- [ ] Re-render without the draft flag into `invoices/YYYY-MM/INV-xxxx.pdf`
      (error if the path exists)
- [ ] Append work and charge rows to `ledger.csv` (creating it with its header on the first
      run): write a temp file in the same dir,
      then `os.replace()`. Never rewrite existing rows (check that the old content is a
      byte-for-byte prefix of the new).
- [ ] Regenerate `summary.csv` from the ledger: amounts by invoice month and hours by work
      month, per client and in total, plus rolling turnover
- [ ] Clean up the preview
- [ ] Think through partial failure: what if PDF 3 of 4 fails during commit
- [ ] Also write `Batch.logged_only` rows to the ledger as work rows with an empty
      `invoice_no` and today as `invoice_date`
