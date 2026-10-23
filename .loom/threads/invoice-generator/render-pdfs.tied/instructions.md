# Render invoices with jinja2 + WeasyPrint

`invoice_context()` / `render_html()` / `write_pdf()` in `make_invoices.py`; tests
in `tests/test_render.py`.

- [x] Template context matches `template/invoice.html` (business, tax, invoice,
      client, charges, totals, pay, payment, terms_days, work, draft)
- [x] `money` filter: Decimal → `1,234.56`. The `lines` filter escapes multi-line
      config values before adding `<br>` (replaces `replace(...) | safe`).
- [x] Autoescape is on, so task text like `R&D` is safe
- [x] Added the missing CSS: `.watermark` (fixed, so it repeats on every page; grey, so
      it survives greyscale), red `h2.draft`, `.draftnote`
- [x] The client's `Remarks/Reference` prints as "Your reference" in the meta table
- [x] Replaced the stale "packing" comment in the template
- [x] Work log: week and hourly rows only, by date; the section is dropped when empty.
      The Date and Project columns no longer wrap.
- [x] `write_pdf` opens with mode "x", so an existing path is refused
- [x] A missing template folder is refused before anything runs
- [x] Looked at rendered PDFs: a draft, an unregistered final, registered domestic and
      export, and a fixed-price-only invoice
