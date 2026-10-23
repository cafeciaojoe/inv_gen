# One markdown pipe-table parser

Used for `clients.txt`, `rates.txt` and `timesheet.txt`.

- [ ] Split on `|`, drop the leading and trailing empty fields, drop the `| --- |` row
- [ ] Strip every cell
- [ ] Keep each row's original text verbatim so errors can echo it
- [ ] Look up columns by header prefix (`Billing type`, `Week rate tag`), not exact header text
- [ ] A row whose cell count doesn't match the header is a hard error
- [ ] Unit tests, including trailing spaces and the em dash in tags
