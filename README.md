# Invoice generator

Once a month, this turns a timesheet pasted from Notion into one PDF invoice per
client, and records what was billed in a permanent ledger. It runs offline, on
your Mac, from the same folder as your data.

Nothing is kept until you've read the drafts and typed `commit`. If anything in
your data looks wrong, it refuses and says exactly which row to fix in Notion.

## Setting up a Mac (once)

1. Install [Homebrew](https://brew.sh) if it isn't there yet.
2. In Terminal:

   ```
   brew install uv pango
   ```

   `uv` runs the script and fetches what it needs the first time. `pango` is what
   draws the text in the PDFs.

That's all. There's no Python to install and no setup to activate.

## Installing the script

Clone this repository anywhere, then drag these three into your invoicing folder,
next to your data:

- `make_invoices.py`
- `Make invoices.command`
- `template/`

To update later, drag them in again and replace the old ones. Your data files
aren't touched. Copy them; don't make aliases or symlinks, or the script will go
looking for your data in the wrong place.

### The first time

Your invoicing folder also needs:

| File | What to put in it |
| --- | --- |
| `config.txt` | Your details, bank accounts and settings. Start from `tests/fixtures/config.txt` in this repo and replace every value; the comments explain each one. |
| `clients.txt` | Your Clients table, pasted from Notion |
| `rates.txt` | Your rate card, pasted from Notion |
| `timesheet.txt` | The month's unbilled rows, pasted from Notion |

`ledger.csv` is created by the first commit. If you have invoices from before the
script, enter them as opening rows first (see [Opening rows](#opening-rows)) so
the numbering carries on from them.

## Every month

1. **Paste the timesheet.** In Notion, select the rows you haven't billed yet, copy,
   and paste over everything in `timesheet.txt`. If clients or rates changed,
   paste those tables too.
2. **If you're billing in SEK**, set `rate` and `as_at` under `[currency.SEK]` in
   `config.txt` to today's rate. The run refuses if `as_at` isn't the invoice date.
3. **Double-click `Make invoices.command`.** A Terminal window opens and checks
   everything.
4. **Read what it shows you.** Finder opens a folder with the draft invoices and
   the new `summary.csv`. Terminal shows each invoice's total, any booked weeks
   that ran long or short, fixed-price hours that charged nothing (check no
   balance was forgotten), and your turnover against the GST threshold.
5. **Type `commit`** to keep them, or anything else to throw them away. Closing the
   window also throws them away. Either way, the draft folder is deleted. Then press
   `r` to run again, or close the window.
6. **Send the invoices** from `invoices/YYYY-MM/`.
7. **Mark the rows as billed in Notion**, so they aren't pasted again next month.
   If they are, the script refuses them as duplicates anyway.

### When it refuses

It prints every problem at once and writes nothing. Each problem names the file,
shows the row exactly as pasted, and says what would have been accepted:

```
clients.txt — unknown Tier value "gold"
  | Fjordlight AB | Kim Exempel | … | gold | SEK | Aurora Lamp |
  allowed: base, discounted, subsidised

Fix it in Notion and paste the table again. Nothing was written.
```

Fix it in Notion, paste the table again, and press `r` in the same window to run
it again. Don't edit the
pasted `.txt` files by hand: Notion is the source, and the next paste would undo
the fix.

The usual ones:

| Message | What to do |
| --- | --- |
| Hours "-" is not a number | Hours must be a number. For a fixed-price payment with no hours, put `0`. |
| unknown Project value | The project isn't in Active Projects in your Clients table. Add it, or fix the spelling. |
| this line may already be billed | You pasted a row that's already in the ledger. Leave it out. If it really is new work, make its Task text different. |
| week rate tag … spans two months | Split the booked week into two tags, one per month. |
| as_at under [currency.SEK] is … | Update the SEK rate and its date for today. |
| dated after the invoice date | A date typo, or an `invoice_date` in `config.txt` left over from last time. |
| … already exists, but ledger.csv has no record of it | An earlier commit stopped partway, or the file was put there by hand. If it was never sent, delete it and run again. |

### Dating invoices on another day

Invoices are dated the day you run the script. To use another date, for example
because the exchange-rate source has no rate for today, uncomment this line in
`config.txt`:

```toml
# invoice_date = 2026-11-30
```

Comment it out again afterwards. If you forget, next month's run refuses, because
its work is dated after that date.

## What's in the folder

| File | Written by | Edit by hand? |
| --- | --- | --- |
| `make_invoices.py`, `Make invoices.command`, `template/` | this repo | No. Drag in new copies to update. |
| `config.txt` | you | Yes, in TextEdit. It's the one input not kept in Notion. |
| `clients.txt`, `rates.txt`, `timesheet.txt` | pasted from Notion | No. Fix things in Notion and paste again. |
| `ledger.csv` | the script | Only to add opening rows. Never change or delete a row. |
| `summary.csv` | the script, on every commit | No. It's rebuilt from the ledger each time. |
| `invoices/` | the script | No. |

`ledger.csv` is the only file that matters for your records: everything else can
be rebuilt from it. Keep it backed up. The ATO wants five years.

`summary.csv` is your monthly view: one row per invoice, sorted by the month the
work was done, with the month it was invoiced, hours, the amount in AUD, a total
per month, and your rolling 12-month turnover. It opens in Numbers.

## Turning on GST

Once you're registered, set `gst_registered = true` in `config.txt` and check that
your ABN is filled in. Invoices then say "Tax Invoice" and add GST: 10% for
Australian clients, and "GST-free export" for clients abroad. Drafts always say
"Draft Invoice", whatever the setting.

## Opening rows

Invoices made before the script go into `ledger.csv` as one `charge` row per
invoice line, added under the header row. Use your usual numbering
(`INV-0003`) so new invoices carry on after the highest. For example:

```
charge,INV-0003,2026-08-31,Bluegum Theatre Company,,,,,,PO BT-0001,Concept work August,hour,6,120.00,720.00,AUD,1,2026-08-31,,720.00,base,unregistered,
```

The columns, in order, are in the header row. Leave the ones that don't apply
empty, but keep the commas. If a row is malformed, the script refuses and names
the line.

## Troubleshooting

- **The launcher won't open**, or says it can't be run: in Terminal, run
  `chmod +x "Make invoices.command"` in your invoicing folder. Sync services can
  remove that permission. If macOS says it's from an unidentified developer,
  right-click it and choose Open once.
- **"WeasyPrint could not load pango"**: run `brew install pango`.
- **"uv is not installed"**: run `brew install uv pango`.

## For developers

The design brief explains every rule and why it exists (it's kept outside the
repository). The tests use invented data in `tests/fixtures/`:

```
uv run --with-requirements make_invoices.py --with pytest pytest -q
```

Library versions are pinned by date with `exclude-newer` at the top of
`make_invoices.py`, so every Mac installs the same ones. To upgrade, move the date
forward, run the tests, and check a draft.

Work is planned in `.loom/` using [loom](https://github.com/zealtv/loom).
