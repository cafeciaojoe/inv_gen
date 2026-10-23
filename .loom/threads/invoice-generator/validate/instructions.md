# Cross-file validation (all hard errors, nothing written)

- [ ] Unknown project: not listed in clients.txt
- [ ] Duplicate lines: `date + project + hours + task` matches the ledger, or another
      line in the same paste
- [ ] Unknown country at the end of an address
- [ ] Week tag on rows resolving to more than one client
- [ ] Client currency has no `[payment.<CUR>]` block
- [ ] Foreign currency: `[currency.<CUR>]` exists and `as_at` equals the invoice date
- [ ] Client tier is missing from rates.txt
- [ ] Work dated after the invoice date
- [ ] Week tag whose rows fall in two calendar months
- [ ] Week tag already billed: it matches the `description` of a ledger charge row with
      `unit=week`
- [ ] Collect all errors and print them together (decided)
- [ ] A test per check, each asserting nothing was written
