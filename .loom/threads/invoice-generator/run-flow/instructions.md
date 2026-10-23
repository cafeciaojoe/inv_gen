# Preview, report, and the commit gate

- [ ] Render draft PDFs into a fresh `tempfile.mkdtemp()` folder
- [ ] Print the invoice date (noting when it came from config.txt), per-client totals, the booked-week report, rolling 12-month turnover (AUD,
      ex-GST, with a warning at `turnover_warn_at` and above the threshold) and the
      preview path
- [ ] `open` the preview folder (macOS)
- [ ] Read input: exactly `commit` proceeds, anything else (including EOF or Ctrl-C) aborts
- [ ] Abort: delete the whole temp folder. Nothing in the invoicing folder is touched.
- [ ] Exit codes: 0 when committed, non-zero for validation failures, a distinct code
      when aborted
