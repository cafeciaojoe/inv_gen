# Goal: invoice generator

`make_invoices.py` does what `resources/Invoicing script — design brief.md` describes:
it turns the Notion-pasted `timesheet.txt` into one PDF invoice per client per month,
previews them as drafts, and keeps them only after a typed `commit`. Keeping them
means re-rendering the final PDFs and appending to `ledger.csv` atomically.

Done when:
- every hard-error check in the brief's Validation section refuses with the
  row-echo message, writes nothing and exits non-zero
- the fake fixtures produce correct, hand-checked invoices end to end
- commit and abort both behave as described in Order of operations
- a README explains setup and the monthly run

When a design decision changes, copy the brief with a date stamp, then edit
the original (the user asked for this).
