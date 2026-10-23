# End-to-end test and docs

- [ ] Fixture run in a temp copy: preview, then commit, then inspect ledger, summary.csv
      and PDFs
- [ ] Fixture run, then abort: the folder is byte-identical afterwards
- [ ] Second run on the same timesheet: refused as duplicates
- [ ] SEK `as_at` mismatch refuses; `gst_registered = true` exercises domestic and export
- [ ] README: setup (`brew install uv pango`), install by dragging `make_invoices.py`, `Make invoices.command` +
      `template/`, monthly routine, where the files live
