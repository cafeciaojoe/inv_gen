# Open questions (2026-10-21)

Each has a recommended default. "Go with defaults" settles all of them.

## Blocking: these change money or legal output

1. **Rates for SEK clients.** `rates.txt` is in AUD. How does the SEK client's invoice get
   its rates?
   Default: convert the AUD rate card at the invoice-date `[currency.SEK] rate`,
   rounding each converted rate to the cent.
   Alternative: literal SEK figures in `rates.txt`.
    ok
2. **Invoice date.** The brief never says what it is. It also says that when the FX
   source has nothing for today, the invoice "is dated to a day it does", which needs
   some way to set the date.
   Default: today, with an optional `invoice_date` in `[invoicing]` that overrides it.
   Error if any billed work is dated after the invoice date.
   (The fake timesheet has November rows, and today is Oct 21.)
   ? i like the idea of a custom invoice date, but explain where this would be? I do like to keep things simple so it needs to be elegant. 
3. **Week tag crossing a month boundary.** For example, Mon 30 Nov to Fri 4 Dec.
   Invoices are cut by month, so this needs a rule.
   Default: hard error. Split it into two tags in Notion.
   ok 
4. **Week tag already in the ledger.** If half a week was billed last month, nothing
   in the brief stops this month's rows being charged a second week.
   Default: hard error when an incoming tag already appears on a ledger work row.
   ok

## Ledger schema

5. **Charge rows have no description column.** That means invoices can't be
   regenerated from the ledger, despite what the brief says. Default: add `description`.
   ? do be clear you want to add the description to the ledger? yes i like this. 
6. **No `fx_source` column**, though the brief says every row records the source name.
   Default: add it.
   ok
7. **What is `ref`?** Default: the client's Remarks/Reference (PO number) on both row
   types. Week tags go in `description`.
   ? I am not sure what you are asking here
8. **Months in summary.csv.** Charge rows hold only `invoice_date`. Default: add a
   `period` (YYYY-MM of the work) to charge rows and group the summary by it.
   Turnover still uses `invoice_date`.
   ? not sure what this means either. when you say sharge rows do you mean the date rows in the timesheets?  these dates are the dates the work was performed.

## Smaller rules

9. **Day threshold.** Do week-rate and fixed-price hours on a date count toward the
   8 hours? Default: no. Only unbooked hourly rows count.
   ok
10. **Quarter hours.** Should 1.1 hours be a hard error? Default: yes, since the
    brief says hours are logged to the quarter hour.
    ok
11. **`Hour` column** has no number in its header, but the brief says that's an error.
    Default: `Hour` means 1 and is exempt. 
    ? 
12. **Header prefix.** The brief's sample says `Week rate tag / …` but the matching
    rule says the prefix is `Week tag`. Default: accept both prefixes. 
    I changed it to Week rate tag
13. **Known country list.** Default: a built-in list of English country short names
    (ISO 3166), matched strictly. No aliases.
    ok
14. **Preview cleanup.** "Delete the preview folder" is risky if it already holds
    other files. Default: refuse to start if it's non-empty, and on cleanup delete only
    the files this run wrote. 
    Well maybe we change this temp filw to be where the script is frin from /temp. then I am ok with deleting the whole thing. 
15. **lines.csv contents.** Default: the charge lines (description, qty, unit, rate,
    amount, GST), plus the printed work rows as a second block. Or charge lines only?
    ehat is lines.csv
    ?err, idk what lines.csv is doing there. 

    it says in the brief, "INV-xxxx-lines.csv next to each PDF. Redundant against the ledger, but it's what I attach when a client asks for a breakdown." but i think the invoice should just have all the info. So perhaps we get rid of lines, can you see a benefit?
16. **Errors.** Default: report every validation error in one run rather than
    stopping at the first.
    ok
17. **Description text for day and hour lines.** Default: `Day rate — 19 Nov 2026` and
    `Hourly — 19 Nov 2026`.
    ? shouldnt the description be the task?

    ?still not understanding perhaos give me and exmaple more flehshe dout. 

## Setup

18. **Python and deps.** The Mac has Python 3.9.6, and the brief needs 3.11+. OK to
    install via Homebrew (`python@3.12`, `pango`) and use a `.venv` in the repo?
    Alternative: `uv run make_invoices.py`.
    ooh i like the uv option. 
19. **Where the script lives.** The real data sits in the pCloud folder and must
    never reach GitHub (bank details, ledger). Default: keep this repo as the code,
    and have a `deploy` step copy `make_invoices.py` + `template/` into the pCloud
    folder. A symlink would break `Path(__file__).resolve()`.
    Alternative: keep the repo inside pCloud and gitignore the data.
    ? hmmm I was hoping to just clone the repo then just drag a script file into the directory i have my .txt files. 

you’d drag in make_invoices.py plus the template/ folder... so thats it? 
    
20. **Which clients file is current?** Default: `resources/template/clients_fake.txt`
    (country at the end of the address, no Country column, matches the brief).
    yes

---

# Decisions (2026-10-22)

1. Convert the AUD rate card at the invoice-date rate. Round each converted rate to the cent.
2. Invoice date is today. An optional commented-out `invoice_date` in `[invoicing]`
   overrides it. Work dated after the invoice date is an error, which also catches a
   forgotten override.
3. A week tag crossing a month boundary is a hard error.
4. A week tag already on a ledger work row is a hard error.
5. Add `description` to charge rows: the invoice line text.
6. Add `fx_source`.
7. `ref` holds the client's Remarks/Reference (PO). Work rows already carry `task` and
   `invoice_no`.
8. summary.csv groups amounts by **invoice month**. Hours stay grouped by work date.
   No `period` column.
9. Only plain hourly rows count toward the 8-hour day.
10. Hours that aren't quarter hours are a hard error.
11. `Hour` means 1 hour.
12. The header is now `Week rate tag / Fixed price amount`, and the prefix match is
    `Week rate tag`.
13. Built-in ISO 3166 English short names, matched strictly.
14. Drop `preview_folder`. Use a fresh system temp folder each run and delete the whole
    folder afterwards. The script prints the path and opens the folder in Finder.
15. Drop `INV-xxxx-lines.csv`.
16. Report every validation error in one run.
17. Day and hourly lines use the date plus the task text, then the rate:
    `16 Nov — Lantern rework after preview (daily rate)`,
    `16 Nov — Lantern rework after preview (hourly rate)`.
    Several tasks on one date are joined with "; ".
18. Run with `uv run make_invoices.py`, using PEP 723 inline deps. uv and pango are
    installed. The script sets `DYLD_FALLBACK_LIBRARY_PATH=/opt/homebrew/lib` before
    importing weasyprint, because uv's Python can't find pango otherwise.
19. The repo holds code only. To install, drag `make_invoices.py` and `template/` into
    the invoicing folder; to update, drag them in again. A new computer needs only
    Homebrew plus `brew install uv pango`.
4. (amended) A week tag that's already billed is detected from the ledger's week
   charge rows, whose `description` is the tag. No extra column is needed.
20. Use `resources/template/clients_fake.txt`.
