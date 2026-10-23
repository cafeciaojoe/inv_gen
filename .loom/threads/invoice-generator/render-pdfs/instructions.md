# Render invoices with jinja2 + WeasyPrint

- [ ] Template context matches `template/invoice.html` (business, tax, invoice,
      client, charges, totals, pay, payment, terms_days, work, draft)
- [ ] `money` filter: Decimal → `1,234.56`
- [ ] Add the missing CSS: `.watermark` (fixed, repeats every page, readable
      in greyscale), red `h2.draft`, `.draftnote`
- [ ] Print the client's `Remarks/Reference` (the brief requires it; the
      template currently omits it)
- [ ] Remove the stale "packing" comment in the template
- [ ] Work log: week and hourly rows only, never fixed-price rows
- [ ] Refuse to overwrite an existing PDF path
- [ ] Look at the rendered fixtures (draft and final) by eye
