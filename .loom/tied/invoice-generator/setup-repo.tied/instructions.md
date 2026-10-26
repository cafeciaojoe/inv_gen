# Set up repo and environment

- [x] `git init -b main`. `.gitignore` covers `resources/` (brief and notes), real data
      at the repo root, and local tooling. Staged, not committed.
- [x] Layout: `make_invoices.py` and `template/` at the root. The fakes are in
      `tests/fixtures/` under the names the script expects.
- [x] Clients fixture taken from the old `resources/template/clients_fake.txt`. The
      outdated copy with the Country column stays in `resources/` (ignored).
- [x] `uv` and `pango` installed via Homebrew (2026-10-22)
- [x] PEP 723 header: python >=3.11, jinja2>=3.1, weasyprint>=66, `exclude-newer`
      pinned to 2026-10-23. `DYLD_FALLBACK_LIBRARY_PATH` is set before the import, and a
      friendly message appears if pango is missing.
- [x] Fixtures updated: ledger header with `description` and `fx_source`, `[paths]`
      dropped from the config, and a commented `invoice_date` added. The timesheet
      already used `Week rate tag`.
- [x] `run(base, today)` takes the folder and date. `main()` passes `SCRIPT_DIR` and
      `date.today()`.

## Notes

Run the tests with:

    uv run --with-requirements make_invoices.py --with pytest pytest -q

`./make_invoices.py` also works, thanks to the `uv run --script` shebang.
