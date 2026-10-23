# Documentation

`README.md` in the repo, written for Joe rather than for a developer.

- [x] Setup on a new Mac: Homebrew, then `brew install uv pango`
- [x] Install: clone, then drag `make_invoices.py`, `Make invoices.command` and
      `template/` into the invoicing folder. Update by dragging them in again.
      First-time files.
- [x] The monthly routine: paste from Notion, double-click, read the drafts and
      summary, type `commit`, send, mark billed in Notion. What to do when it refuses,
      with the usual messages.
- [x] What each file in the folder is, and which ones never to edit by hand
- [x] Turning on GST, opening rows (example checked: it loads and numbering continues),
      troubleshooting
- [x] Changing the library date (`exclude-newer`), and running the tests
- [x] Brief read in full against the build. Fixed: GST stored per line, PDFs one per
      client per work month, the preview prints per-invoice totals, turnover includes
      the previewed run, and allowed currencies come from config.txt.
