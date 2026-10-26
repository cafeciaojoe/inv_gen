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
- `template/` (it holds the invoice and rate card templates)

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

`ledger.csv` is created by the first commit, in the invoices folder (see below).
If you have invoices from before the script, enter them as opening rows first
(see [Opening rows](#opening-rows)) so the numbering carries on from them.

## Every month

1. **Paste the timesheet.** In Notion, select the rows you haven't billed yet, copy,
   and paste over everything in `timesheet.txt`. If clients or rates changed,
   paste those tables too.
   Invoice any day after the month ends. Rows from the current month are held back
   (they're listed as "Not invoiced yet"), and Notion's recent dates like
   "Last Thursday" are read as of the day you pasted, so there's no need to wait
   for Notion to turn them into full dates.
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
   `r` to run again, or Enter to exit the script. After Enter, the window closes with
   one click, without Terminal asking to terminate anything.
6. **Send the invoices** from `invoices/YYYY-MM/`, or the folder you set in
   `config.txt` (see [What's in the folder](#whats-in-the-folder)).
7. **Mark the rows as billed in Notion**, so they aren't pasted again next month.
   If the Terminal said some rows were **not sent**, paste `timesheet_not_sent.txt`
   back into Notion so they go out with a later invoice.
   If they are, the script refuses them as duplicates anyway.

### The timesheet

Your Notion timesheet needs these columns. Extra words after a column's name are
fine, like the reminder in `Billing type (Week rate / Fixed Price)`:

| Date | Hours | Task | Project | Billing type | Week rate tag / Fixed price tag | Amount |
| --- | --- | --- | --- | --- | --- | --- |

| Billing type | Tag | Amount |
| --- | --- | --- |
| *(empty)*: hourly | empty | empty |
| `week rate` | names the booked week, the same on every row of it, e.g. `Lantern build week — agreed 14 Oct` | empty for the rate card's week price, or a custom price for that week |
| `fixed price` | names the agreement, e.g. `Tool wall build` | on the row that charges, e.g. `1500`; empty on rows that only log hours |

Booked weeks: give each week its own tag, even within a longer block
(`Pole build — week 1 of 3 (agreed 20 Oct)`), date the rows when the work happens,
and paste a week once it's finished, since a week is billed once. A week that runs
across a month end is charged on the invoice for the month it ends in.

The tags print on page 1 of the invoice, so a fixed-price tag can name the payment:
`Lantern design (50% payment)`, then `Lantern design (100% payment)` for the next
one. A fixed-price payment with no hours of its own takes `0` in Hours.

Fixed-price rows without an amount, logged between payments, go on page 2 of the
client's invoice in the same run, even if they're from earlier months. If a client
has no invoice at all this run, those rows aren't sent: they're written to
`timesheet_not_sent.txt` to paste back into Notion, ready for next time.

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
| no column starts with "Amount" | Add an Amount column to your Notion timesheet (see [The timesheet](#the-timesheet)). |
| … row has no tag | Every week rate and fixed price row needs a tag; it prints on the invoice. |
| Date "Tomorrow" is a future date | Work can't be dated in the future. Fix the date in Notion. |
| Hours "-" is not a number | Hours must be a number. For a fixed-price payment with no hours, put `0`. |
| unknown Project value | The project isn't in Active Projects in your Clients table. Add it, or fix the spelling. |
| this line may already be billed | You pasted a row that's already in the ledger. Leave it out. If it really is new work, make its Task text different. |
| week rate tag … was already billed | That week was invoiced before. If these are new days of an unfinished week, a week can only be billed once: paste a booked week once it's finished. |
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
| `timesheet_not_sent.txt` | the script, when rows weren't sent | No. Paste it back into Notion. |
| `rate cards/` | the script, on every commit | No. Send the one for the client's tier. |
| `invoices/` | the script | No. Holds a folder per month, `summary.csv` and `ledger.csv`. |
| `invoices/ledger.csv` | the script | Only to add opening rows. Never change or delete a row. |

`ledger.csv` is the only file that matters for your records: everything else can
be rebuilt from it. Keep it backed up. The ATO wants five years.

The invoices go in `invoices/` beside the script, one folder per month, with
`summary.csv` and `ledger.csv` beside them. To keep them somewhere else, such as
a folder for the financial year, add this to `config.txt`, as its own section:

```toml
[paths]
invoices = "~/Documents/Invoices"
```

Uncomment both lines: a setting belongs to the `[section]` line above it. The
preview ends by saying where commit will save. A `ledger.csv` left beside the
script is refused, so move it into the invoices folder. A folder with no
`ledger.csv` starts the numbering again from 001, and the preview says so.

`summary.csv`, at the top of that folder, is your overview. Each invoice is a row,
grouped by month, with its hours and its amount split into hourly, daily, week
rate and fixed price, all in AUD. Each month ends with a total, in separate
columns so you can add up the invoice rows without counting it twice. At the
bottom: the financial year to date, and the rolling 12 months that counts toward
GST. It opens in Numbers.

## What the client sees

Page 1 is the cost breakdown: one line per project and kind of charge, such as
`Week rate: <tag>`, `Daily`, `Hourly` or `Fixed price: <tag>`. Page 2,
"Work completed", lists every row with its date, project and task.

By default it shows the hours of hourly and week-rate rows, and hides them on
fixed-price rows, which say "fixed price" instead. To change that, add these two
lines to `config.txt` **under the existing `[invoicing]` heading**, next to
`payment_terms_days`. Not at the end of the file: a setting belongs to the
`[section]` above it, so at the end it would land in the last payment block. The
script refuses it there and says where it belongs.

```toml
[invoicing]
show_fixed_price_hours = false   # true, e.g. for a block of prepaid hours
show_week_rate_hours = true      # false, e.g. for a week sold as a deliverable
```

The Terminal summary reminds you how they're set whenever an invoice has those
kinds of row. The total hours on page 2 only ever counts the hours it shows.

## Rate cards

Every run also draws three rate cards from `rates.txt`, in the same style as the
invoices and dated that day. They're in the Finder preview with the drafts, and
committing saves them to `rate cards/`, replacing the last ones. Send the one for the
client's tier:

| File | Shows |
| --- | --- |
| `Rate card_I.pdf` | Base |
| `Rate card_II.pdf` | Base and Discounted |
| `Rate card_III.pdf` | Base, Discounted and Subsidised |

They're numbered rather than named for the tier, so the file a client gets doesn't say
which tier they're on.

To get a fresh card without invoicing, empty `timesheet.txt` down to its header row
and run: the preview opens with just the rate cards.

## Turning on GST

Once you're registered, set `gst_registered = true` in `config.txt` and check that
your ABN is filled in. Invoices then say "Tax Invoice" and add GST: 10% for
Australian clients, and "GST-free export" for clients abroad. Drafts always say
"Draft Invoice", whatever the setting.

## Opening rows

Invoices made before the script go into `ledger.csv`, in the invoices folder, as one `charge` row per
invoice line, added under the header row. Use your usual numbering
(`INV-0003`) so new invoices carry on after the highest. For example:

```
charge,INV-0003,2026-08-31,Bluegum Theatre Company,,,,,,PO BT-0001,Concept work August,hour,6,120.00,720.00,AUD,1,2026-08-31,,720.00,base,unregistered,,2026-08
```

The columns, in order, are in the header row. Leave the ones that don't apply
empty, but keep the commas. If a row is malformed, the script refuses and names
the line.

To change the numbering, say to one per financial year, set `number_prefix` and
`number_padding` in `config.txt`. New numbers carry on from the highest with the
new prefix, starting at 1. If the new numbering has already begun, put that
invoice in as an opening row with its new-style number, so the script carries
on after it.

Numbers already in the ledger have to match `number_prefix`, so that a typo
can't slip past the numbering. If invoices with the old numbering went out
earlier in the same ledger, name the old prefix as well:

```toml
earlier_prefixes = ["INV-"]
```

Those numbers stay as they were sent. A new financial year's folder starts with
an empty ledger, so it doesn't need the line.

## Troubleshooting

- **The launcher won't open**, or says it can't be run: in Terminal, run
  `chmod +x "Make invoices.command"` in your invoicing folder. Sync services can
  remove that permission. If macOS says it's from an unidentified developer,
  right-click it and choose Open once.
- **"WeasyPrint could not load pango"**: run `brew install pango`.
- **"uv is not installed"**: run `brew install uv pango`.
- **"… is under [payment.SEK], but it belongs under [invoicing]"**: a setting was
  added at the end of `config.txt`. Move it up under the section named.

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
