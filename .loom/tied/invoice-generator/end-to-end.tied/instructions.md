# End-to-end tests

Most of the original list was already covered in-process. `tests/test_end_to_end.py`
adds what wasn't: the script as its own process, in a folder with a space in its name,
started from another folder, typed at through real stdin, with a stand-in `open` on
PATH.

- [x] Fixture run: preview, then commit, then check ledger, summary.csv and PDFs
      (test_commit.py, and as a process in test_end_to_end.py)
- [x] Fixture run, then discard: the folder is byte-identical afterwards (both)
- [x] Second run on the same timesheet: refused as duplicates, with no preview made (both)
- [x] SEK `as_at` mismatch refuses (test_validate.py); `gst_registered = true` exercises
      domestic and export (test_compute, test_render, test_commit)
- [x] A refused run opens nothing and ends with the Notion footer
- [x] The double-click launcher, run as a file from `/`, commits the fixtures
