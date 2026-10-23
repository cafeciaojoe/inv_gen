# One markdown pipe-table parser

Used for `clients.txt`, `rates.txt` and `timesheet.txt`. Implemented as
`parse_table()` / `Table.column()` in `make_invoices.py`, with tests in
`tests/test_parse_tables.py`.

- [x] Split on unescaped `|`, drop the leading and trailing empty fields, drop the
      `| --- |` row. An escaped `\|` stays inside its cell.
- [x] Strip every cell
- [x] Keep each row's original text verbatim (`Row.line`) so errors can echo it
- [x] Look up columns by header prefix, ignoring case (`Billing type`, `Week rate tag`).
      A missing or ambiguous prefix is an error that echoes the header.
- [x] A row whose cell count doesn't match the header is a hard error. So are stray
      non-table lines, an empty file and repeated column names.
- [x] Errors are appended to a shared list in the brief's format (`row_error`), not
      raised
- [x] Unit tests, including trailing spaces and the em dash in tags, and a check that all
      three fixtures parse cleanly
