#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.11"
# dependencies = [
#     "jinja2>=3.1",
#     "weasyprint>=66",
# ]
#
# [tool.uv]
# # Resolve packages as they were on this date, so every machine gets the
# # same versions. Move it forward deliberately when upgrading.
# exclude-newer = "2026-10-23T00:00:00Z"
# ///
"""Turn a timesheet pasted from Notion into one PDF invoice per client per month.

Run from a terminal with `uv run make_invoices.py`. Every path is resolved from
the folder this file sits in, so it can be run from anywhere. The rules it
follows are in the design brief.
"""

import csv
import io
import os
import re
import shutil
import subprocess
import sys
import tempfile
import tomllib
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from decimal import ROUND_HALF_UP, Decimal, InvalidOperation
from pathlib import Path

# WeasyPrint draws text with pango from Homebrew, but a Python installed by uv
# doesn't search Homebrew's library folder. ctypes reads this variable at the
# moment WeasyPrint looks for pango, so setting it before the import is enough.
# Setting it replaces the system default fallback, so /usr/lib is kept on the end.
_HOMEBREW_LIBS = ["/opt/homebrew/lib", "/usr/local/lib"]  # Apple Silicon, Intel
_existing = os.environ.get("DYLD_FALLBACK_LIBRARY_PATH", "")
os.environ["DYLD_FALLBACK_LIBRARY_PATH"] = os.pathsep.join(
    [p for p in _HOMEBREW_LIBS if os.path.isdir(p)]
    + [p for p in _existing.split(os.pathsep) if p]
    + ["/usr/lib"]
)

try:
    import jinja2
    import markupsafe  # comes with jinja2
    import weasyprint
except OSError as exc:
    sys.exit(
        f"WeasyPrint could not load pango ({exc}).\n"
        "Install it once with:  brew install pango"
    )

SCRIPT_DIR = Path(__file__).resolve().parent

# One header shared by both row types; cells that don't apply stay empty.
# Order is fixed by the brief. Never reorder: the ledger is append-only.
LEDGER_COLUMNS = [
    "row_type", "invoice_no", "invoice_date", "client",
    "date", "hours", "task", "project", "billing_type",
    "ref", "description",
    "unit", "qty", "rate", "amount", "currency",
    "fx_rate", "fx_date", "fx_source", "amount_aud",
    "tier", "gst_treatment", "gst_amount",
]


# ---- Errors -----------------------------------------------------------------
# Every check appends to one list instead of raising, so a single run reports
# everything that needs fixing in Notion.

FIX_IN_NOTION = "Fix it in Notion and paste the table again. Nothing was written."


def row_error(file: str, problem: str, line: str, allowed: str | None = None) -> str:
    """An error in the brief's shape: the file, the problem, the row verbatim.

    The row is echoed as pasted rather than by number, because a line number
    in a throwaway paste means nothing in Notion; the text is what finds it.
    """
    message = f"{file} — {problem}\n  {line}"
    if allowed is not None:
        message += f"\n  allowed: {allowed}"
    return message


# ---- Pipe tables ------------------------------------------------------------
# clients.txt, rates.txt and timesheet.txt are all markdown tables pasted from
# Notion, so one parser reads them. It only splits and strips; what a cell
# means is decided by whoever reads the table.

_UNESCAPED_PIPE = re.compile(r"(?<!\\)\|")
_SEPARATOR_CELL = re.compile(r":?-+:?")


@dataclass(frozen=True)
class Row:
    cells: tuple[str, ...]
    line: str  # as pasted, for error messages


@dataclass(frozen=True)
class Table:
    file: str
    header: tuple[str, ...]
    line: str  # the header row as pasted
    rows: tuple[Row, ...]

    def column(self, prefix: str, errors: list[str]) -> int | None:
        """Index of the one column whose header starts with `prefix`, ignoring case.

        Matching by prefix lets Notion headers carry reminders such as
        "Billing type (Week rate / Fixed Price)" and be reworded freely.
        """
        wanted = prefix.casefold()
        found = [i for i, h in enumerate(self.header) if h.casefold().startswith(wanted)]
        if len(found) == 1:
            return found[0]
        if found:
            problem = f'more than one column starts with "{prefix}"'
        else:
            problem = f'no column starts with "{prefix}"'
        errors.append(row_error(self.file, problem, self.line))
        return None


def split_row(line: str) -> list[str] | None:
    """The stripped cells of a `| a | b |` line, or None if it isn't one.

    A pipe written inside a cell arrives escaped as `\\|` and stays part of
    that cell. Stripping is mandatory: Notion pastes trailing spaces on
    nearly every cell.
    """
    parts = _UNESCAPED_PIPE.split(line.strip())
    if len(parts) < 3 or parts[0] or parts[-1]:
        return None
    return [cell.strip().replace("\\|", "|") for cell in parts[1:-1]]


def parse_table(file: str, text: str, errors: list[str]) -> Table | None:
    """Parse one pasted table. Bad rows become errors and are left out.

    A line break typed inside a Notion cell (Shift-Return in an address, say)
    pastes as a real line break, splitting the row across lines. A row that
    starts with | but doesn't end with one is still open, so the lines after
    it are joined on, each break becoming a space, until it closes. A stray
    line after a row that did close is still refused.
    """
    parsed = []
    open_row = ""
    for raw in text.splitlines():
        line = raw.strip()
        if not line:
            continue  # between rows, or a blank line inside an open cell
        if open_row:
            line, open_row = f"{open_row} {line}", ""
        cells = split_row(line)
        if cells is None:
            if line.startswith("|"):
                open_row = line
            else:
                errors.append(row_error(file, "this line is not a table row", line))
            continue
        if all(_SEPARATOR_CELL.fullmatch(cell) for cell in cells):
            continue  # the | --- | row under the header
        parsed.append((tuple(cells), line))
    if open_row:
        errors.append(row_error(file, "this row never closes with a |", open_row))

    if not parsed:
        errors.append(f"{file} — no table found. Paste the table from Notion.")
        return None

    (header, header_line), *body = parsed
    repeated = sorted({h for h in header if header.count(h) > 1})
    if repeated:
        errors.append(row_error(
            file, "repeated column name " + ", ".join(f'"{h}"' for h in repeated),
            header_line,
        ))

    rows = []
    for cells, line in body:
        if len(cells) != len(header):
            errors.append(row_error(
                file, f"row has {len(cells)} cells but the header has {len(header)}", line,
            ))
            continue
        rows.append(Row(cells, line))
    return Table(file, header, header_line, tuple(rows))


# ---- Closed sets ------------------------------------------------------------

TIERS = ("base", "discounted", "subsidised")
BILLING_TYPES = ("", "week rate", "fixed price")
HOME_COUNTRY = "Australia"  # anything else at the end of an address is export

# Everyday English names, one per ISO 3166 country or territory. The official
# ISO forms are not used because several contain commas ("Korea, Republic of")
# and the country is read from after the address's last comma. No aliases:
# "Aus" or "Sverige" is an error, so Notion is fixed rather than tolerated.
COUNTRIES = frozenset("""
Afghanistan|Åland Islands|Albania|Algeria|American Samoa|Andorra|Angola|Anguilla|
Antarctica|Antigua and Barbuda|Argentina|Armenia|Aruba|Australia|Austria|
Azerbaijan|Bahamas|Bahrain|Bangladesh|Barbados|Belarus|Belgium|Belize|Benin|
Bermuda|Bhutan|Bolivia|Bosnia and Herzegovina|Botswana|Bouvet Island|Brazil|
British Indian Ocean Territory|British Virgin Islands|Brunei|Bulgaria|
Burkina Faso|Burundi|Cambodia|Cameroon|Canada|Cape Verde|Caribbean Netherlands|
Cayman Islands|Central African Republic|Chad|Chile|China|Christmas Island|
Cocos (Keeling) Islands|Colombia|Comoros|Cook Islands|Costa Rica|Côte d'Ivoire|
Croatia|Cuba|Curaçao|Cyprus|Czechia|Democratic Republic of the Congo|Denmark|
Djibouti|Dominica|Dominican Republic|Ecuador|Egypt|El Salvador|
Equatorial Guinea|Eritrea|Estonia|Eswatini|Ethiopia|Falkland Islands|
Faroe Islands|Fiji|Finland|France|French Guiana|French Polynesia|
French Southern Territories|Gabon|Gambia|Georgia|Germany|Ghana|Gibraltar|
Greece|Greenland|Grenada|Guadeloupe|Guam|Guatemala|Guernsey|Guinea|
Guinea-Bissau|Guyana|Haiti|Heard Island and McDonald Islands|Honduras|
Hong Kong|Hungary|Iceland|India|Indonesia|Iran|Iraq|Ireland|Isle of Man|Israel|
Italy|Jamaica|Japan|Jersey|Jordan|Kazakhstan|Kenya|Kiribati|Kuwait|Kyrgyzstan|
Laos|Latvia|Lebanon|Lesotho|Liberia|Libya|Liechtenstein|Lithuania|Luxembourg|
Macao|Madagascar|Malawi|Malaysia|Maldives|Mali|Malta|Marshall Islands|
Martinique|Mauritania|Mauritius|Mayotte|Mexico|Micronesia|Moldova|Monaco|
Mongolia|Montenegro|Montserrat|Morocco|Mozambique|Myanmar|Namibia|Nauru|Nepal|
Netherlands|New Caledonia|New Zealand|Nicaragua|Niger|Nigeria|Niue|
Norfolk Island|North Korea|North Macedonia|Northern Mariana Islands|Norway|
Oman|Pakistan|Palau|Palestine|Panama|Papua New Guinea|Paraguay|Peru|
Philippines|Pitcairn Islands|Poland|Portugal|Puerto Rico|Qatar|
Republic of the Congo|Réunion|Romania|Russia|Rwanda|Saint Barthélemy|
Saint Helena|Saint Kitts and Nevis|Saint Lucia|Saint Martin|
Saint Pierre and Miquelon|Saint Vincent and the Grenadines|Samoa|San Marino|
São Tomé and Príncipe|Saudi Arabia|Senegal|Serbia|Seychelles|Sierra Leone|
Singapore|Sint Maarten|Slovakia|Slovenia|Solomon Islands|Somalia|South Africa|
South Georgia and the South Sandwich Islands|South Korea|South Sudan|Spain|
Sri Lanka|Sudan|Suriname|Svalbard and Jan Mayen|Sweden|Switzerland|Syria|
Taiwan|Tajikistan|Tanzania|Thailand|Timor-Leste|Togo|Tokelau|Tonga|
Trinidad and Tobago|Tunisia|Türkiye|Turkmenistan|Turks and Caicos Islands|
Tuvalu|Uganda|Ukraine|United Arab Emirates|United Kingdom|United States|
United States Minor Outlying Islands|Uruguay|U.S. Virgin Islands|Uzbekistan|
Vanuatu|Vatican City|Venezuela|Vietnam|Wallis and Futuna|Western Sahara|Yemen|
Zambia|Zimbabwe
""".replace("\n", "").split("|"))
_COUNTRY_BY_FOLDED = {c.casefold(): c for c in COUNTRIES}

_PLAIN_NUMBER = re.compile(r"\d+(\.\d+)?")
_MONEY = re.compile(r"\$?(\d{1,3}(,\d{3})+|\d+)(\.\d{1,2})?")


def parse_money(text: str) -> Decimal | None:
    """`$3,000.00`, `1500` or `1,500.50` as a Decimal; None if it isn't money."""
    if not _MONEY.fullmatch(text):
        return None
    return Decimal(text.replace("$", "").replace(",", ""))


def read_table(base: Path, name: str, errors: list[str]) -> Table | None:
    try:
        text = (base / name).read_text(encoding="utf-8-sig")
    except FileNotFoundError:
        errors.append(f"{name} — not found in {base}")
        return None
    return parse_table(name, text, errors)


def columns(table: Table, prefixes: list[str], errors: list[str]) -> dict[str, int] | None:
    """Look up several columns at once; None if any is missing."""
    found = {p: table.column(p, errors) for p in prefixes}
    return None if None in found.values() else found


# ---- config.txt -------------------------------------------------------------


@dataclass(frozen=True)
class FxRate:
    rate: Decimal  # AUD per one unit of the foreign currency
    as_at: date


@dataclass(frozen=True)
class Config:
    raw: dict  # the whole file, for the template's business/tax/payment blocks
    invoice_date: date
    invoice_date_set: bool  # True when [invoicing] invoice_date overrode today
    gst_registered: bool
    turnover_threshold: Decimal
    turnover_warn_at: Decimal
    home_currency: str
    fx_source: str
    fx: dict[str, FxRate]
    number_prefix: str
    number_padding: int
    terms_days: int
    payment: dict[str, dict]  # currency -> its [payment.<CURRENCY>] block
    payment_note: str


_KINDS = {
    "text": lambda v: isinstance(v, str),
    "true or false": lambda v: isinstance(v, bool),
    "a whole number": lambda v: isinstance(v, int) and not isinstance(v, bool),
    "a number": lambda v: isinstance(v, (int, Decimal)) and not isinstance(v, bool),
    "a date like 2026-11-30, without quotes":
        lambda v: isinstance(v, date) and not isinstance(v, datetime),
}


def load_config(base: Path, today: date, errors: list[str]) -> Config | None:
    try:
        text = (base / "config.txt").read_text(encoding="utf-8-sig")
    except FileNotFoundError:
        errors.append(f"config.txt — not found in {base}")
        return None
    try:
        # parse_float=Decimal keeps 0.1450 exact instead of a binary float.
        raw = tomllib.loads(text, parse_float=Decimal)
    except tomllib.TOMLDecodeError as exc:
        errors.append(f"config.txt — not valid TOML: {exc}")
        return None

    count_before = len(errors)

    def setting(section: str, key: str, kind: str, required: bool = True):
        block = raw.get(section, {})
        if not isinstance(block, dict) or key not in block:
            if required:
                errors.append(f"config.txt — missing {key} under [{section}]")
            return None
        value = block[key]
        if not _KINDS[kind](value):
            errors.append(f"config.txt — {key} under [{section}] must be {kind}")
            return None
        return value

    for key in ("trading_name", "address", "email"):
        setting("business", key, "text")

    gst_registered = setting("tax", "gst_registered", "true or false")
    if gst_registered:
        setting("tax", "abn", "text")
    threshold = setting("tax", "turnover_threshold", "a number")
    warn_at = setting("tax", "turnover_warn_at", "a number")

    home = setting("currency", "home", "text")
    source = setting("currency", "source", "text")
    fx = {}
    for code, block in raw.get("currency", {}).items():
        if not isinstance(block, dict):
            continue  # home and source, checked above
        rate, as_at = block.get("rate"), block.get("as_at")
        if not _KINDS["a number"](rate) or rate <= 0:
            errors.append(f"config.txt — rate under [currency.{code}] must be a number above 0")
        elif not _KINDS["a date like 2026-11-30, without quotes"](as_at):
            errors.append(
                f"config.txt — as_at under [currency.{code}] must be a date like 2026-11-30, without quotes"
            )
        else:
            fx[code.upper()] = FxRate(Decimal(rate), as_at)

    prefix = setting("invoicing", "number_prefix", "text")
    padding = setting("invoicing", "number_padding", "a whole number")
    if padding is not None and padding < 1:
        errors.append("config.txt — number_padding under [invoicing] must be 1 or more")
    terms = setting("invoicing", "payment_terms_days", "a whole number")
    if terms is not None and terms < 0:
        errors.append("config.txt — payment_terms_days under [invoicing] can't be negative")
    override = setting(
        "invoicing", "invoice_date", "a date like 2026-11-30, without quotes", required=False
    )

    payment = raw.get("payment", {})
    if not isinstance(payment, dict):
        payment = {}
    note = setting("payment", "note", "text", required=False) or ""
    blocks = {code.upper(): block for code, block in payment.items() if isinstance(block, dict)}

    if len(errors) > count_before:
        return None
    return Config(
        raw=raw,
        invoice_date=override or today,
        invoice_date_set=override is not None,
        gst_registered=gst_registered,
        turnover_threshold=Decimal(threshold),
        turnover_warn_at=Decimal(warn_at),
        home_currency=home.upper(),
        fx_source=source,
        fx=fx,
        number_prefix=prefix,
        number_padding=padding,
        terms_days=terms,
        payment=blocks,
        payment_note=note,
    )


# ---- clients.txt ------------------------------------------------------------


@dataclass(frozen=True)
class Client:
    name: str
    care_of: str
    address: str
    country: str  # spelled as in COUNTRIES
    email: str
    reference: str
    tier: str  # one of TIERS
    currency: str  # uppercased ISO 4217 code
    projects: tuple[str, ...]
    line: str

    @property
    def gst_treatment(self) -> str:
        return "domestic" if self.country == HOME_COUNTRY else "export"


def load_clients(base: Path, currencies: set[str] | None, errors: list[str]) -> list[Client]:
    """`currencies` is every currency config.txt knows; None skips that check."""
    table = read_table(base, "clients.txt", errors)
    if table is None:
        return []
    col = columns(table, ["Client", "Care of", "Address", "Email", "Remarks",
                          "Tier", "Currency", "Active Projects"], errors)
    if col is None:
        return []

    clients = []
    for row in table.rows:
        cell = lambda name: row.cells[col[name]]
        problems_before = len(errors)

        name = cell("Client")
        if not name:
            errors.append(row_error("clients.txt", "empty Client", row.line))

        tier = cell("Tier").casefold()
        if tier not in TIERS:
            errors.append(row_error("clients.txt", f'unknown Tier value "{cell("Tier")}"',
                                    row.line, ", ".join(TIERS)))

        currency = cell("Currency").upper()
        if currencies is not None and currency not in currencies:
            errors.append(row_error(
                "clients.txt", f'unknown Currency value "{cell("Currency")}"', row.line,
                ", ".join(sorted(currencies)) + " (the currencies in config.txt)",
            ))

        address = cell("Address")
        typed_country = address.rsplit(",", 1)[-1].strip()
        country = _COUNTRY_BY_FOLDED.get(typed_country.casefold())
        if country is None:
            errors.append(row_error(
                "clients.txt", f'unknown country "{typed_country}" at the end of Address',
                row.line, "an address ending with a country name after its last comma, "
                "e.g. Australia, Sweden, United Kingdom, United States",
            ))

        if len(errors) == problems_before:
            projects = tuple(p.strip() for p in cell("Active Projects").split(",") if p.strip())
            clients.append(Client(name, cell("Care of"), address, country, cell("Email"),
                                  cell("Remarks"), tier, currency, projects, row.line))

    # Neither duplicate can be resolved by guessing which row is meant.
    by_name: dict[str, list[Client]] = {}
    for c in clients:
        by_name.setdefault(c.name.casefold(), []).append(c)
    for same in by_name.values():
        if len(same) > 1:
            errors.append(row_error("clients.txt", f'client "{same[0].name}" is listed twice',
                                    "\n  ".join(c.line for c in same)))

    by_project: dict[str, list[Client]] = {}
    for c in clients:
        for p in c.projects:
            by_project.setdefault(p.casefold(), []).append(c)
    for project, owners in by_project.items():
        if len({c.name.casefold() for c in owners}) > 1:
            shown = next(p for p in owners[0].projects if p.casefold() == project)
            errors.append(row_error(
                "clients.txt", f'project "{shown}" is listed under more than one client',
                "\n  ".join(c.line for c in owners),
            ))
    return clients


# ---- rates.txt --------------------------------------------------------------

UNITS = ("hour", "day", "week")


@dataclass(frozen=True)
class RateCard:
    block_hours: dict[str, Decimal]  # unit -> hours in one block: 1, 8, 40
    rates: dict[str, dict[str, Decimal]]  # tier -> unit -> AUD


def load_rates(base: Path, errors: list[str]) -> RateCard | None:
    table = read_table(base, "rates.txt", errors)
    if table is None:
        return None
    col = columns(table, ["Tier", "Hour", "Day", "Week"], errors)
    if col is None:
        return None

    # The block size is read from the header — the 8 in "Day (8 hr)" — so the
    # rate card clients read and the rule the script applies can't drift apart.
    block_hours = {"hour": Decimal(1)}
    for unit in ("day", "week"):
        header = table.header[col[unit.title()]]
        number = re.search(r"\d+(\.\d+)?", header)
        if number is None:
            errors.append(row_error("rates.txt", f'the "{header}" header has no number of hours, '
                                    f'e.g. "{unit.title()} (8 hr)"', table.line))
        else:
            block_hours[unit] = Decimal(number.group())

    rates: dict[str, dict[str, Decimal]] = {}
    for row in table.rows:
        figures = {u: parse_money(row.cells[col[u.title()]]) for u in UNITS}
        if all(f is None for f in figures.values()):
            continue  # an explanatory row, like "How it's charged"
        if any(f is None for f in figures.values()):
            errors.append(row_error("rates.txt", "a rate in this row is not a dollar figure",
                                    row.line, "figures like $120.00 or $3,000.00 in every rate column"))
            continue
        typed = row.cells[col["Tier"]]
        tier = typed.casefold()
        if tier not in TIERS:
            errors.append(row_error("rates.txt", f'unknown Tier value "{typed}"', row.line,
                                    ", ".join(TIERS)))
        elif tier in rates:
            errors.append(row_error("rates.txt", f'tier "{typed}" is listed twice', row.line))
        elif any(f <= 0 for f in figures.values()):
            errors.append(row_error("rates.txt", "a rate must be more than zero", row.line))
        else:
            rates[tier] = figures

    if len(block_hours) < len(UNITS):
        return None
    return RateCard(block_hours, rates)


# ---- timesheet.txt ----------------------------------------------------------


@dataclass(frozen=True)
class Entry:
    date: date
    hours: Decimal
    task: str
    project: str
    billing: str  # one of BILLING_TYPES
    tag: str  # week rate rows only
    amount: Decimal | None  # fixed price rows that carry an amount
    line: str


def load_timesheet(base: Path, errors: list[str]) -> list[Entry]:
    table = read_table(base, "timesheet.txt", errors)
    if table is None:
        return []
    col = columns(table, ["Date", "Hours", "Task", "Project", "Billing type", "Week rate tag"],
                  errors)
    if col is None:
        return []

    def bad(problem: str, row: Row, allowed: str | None = None):
        errors.append(row_error("timesheet.txt", problem, row.line, allowed))

    entries = []
    for row in table.rows:
        cell = lambda name: row.cells[col[name]]
        problems_before = len(errors)

        try:
            day = datetime.strptime(cell("Date"), "%B %d, %Y").date()
        except ValueError:
            day = None
            bad(f'Date "{cell("Date")}" is not a date', row, "dates like November 2, 2026")

        hours = None
        if not _PLAIN_NUMBER.fullmatch(cell("Hours")):
            bad(f'Hours "{cell("Hours")}" is not a number', row, "hours like 3, 1.25 or 0")
        elif (Decimal(cell("Hours")) * 4) % 1:
            bad(f'Hours "{cell("Hours")}" is not on the quarter hour', row,
                "whole multiples of 0.25, like 1, 1.25, 1.5 or 1.75")
        else:
            hours = Decimal(cell("Hours"))

        if not cell("Task"):
            bad("empty Task", row)
        if not cell("Project"):
            bad("empty Project", row)

        billing = cell("Billing type").casefold()
        last = cell("Week rate tag")
        tag, amount = "", None
        if billing not in BILLING_TYPES:
            bad(f'unknown Billing type value "{cell("Billing type")}"', row,
                "empty, week rate, fixed price")
        elif billing == "week rate":
            # A number where a tag belongs is refused, not reinterpreted.
            if not last:
                bad("week rate row has no tag", row, "a tag naming the booked week")
            elif parse_money(last) is not None:
                bad(f'week rate tag "{last}" is a number', row,
                    "a tag naming the booked week, e.g. Lantern build week — agreed 14 Oct")
            else:
                tag = last
        elif billing == "fixed price":
            if last:
                amount = parse_money(last)
                if amount is None or amount <= 0:
                    bad(f'fixed price amount "{last}" is not an amount', row,
                        "empty, or an amount like 1500 or 1,500.00")
        elif last:
            bad(f'"{last}" is filled in but Billing type is empty', row,
                "empty, unless Billing type is week rate or fixed price")

        if len(errors) == problems_before:
            entries.append(Entry(day, hours, cell("Task"), cell("Project"), billing, tag,
                                 amount, row.line))
    return entries


# ---- ledger.csv -------------------------------------------------------------
# Written by the script, apart from the opening rows entered by hand, so its
# errors name a line number: unlike a Notion paste, the line is the thing to fix.


@dataclass(frozen=True)
class LedgerWork:
    invoice_no: str
    client: str
    date: date
    hours: Decimal
    task: str
    project: str


@dataclass(frozen=True)
class LedgerCharge:
    invoice_no: str
    invoice_date: date
    client: str
    unit: str
    description: str
    amount_aud: Decimal


@dataclass(frozen=True)
class Ledger:
    work: tuple[LedgerWork, ...]
    charges: tuple[LedgerCharge, ...]
    raw: bytes | None  # the file exactly as read; None before the first commit


def parse_ledger(raw: bytes, errors: list[str]) -> Ledger:
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError:
        errors.append("ledger.csv — not UTF-8 text. Save it from Numbers as CSV (UTF-8).")
        return Ledger((), (), raw)
    reader = csv.reader(io.StringIO(text, newline=""))
    header = next(reader, None)
    if header != LEDGER_COLUMNS:
        errors.append("ledger.csv — the header row doesn't match the columns the script "
                      "writes:\n  " + ",".join(LEDGER_COLUMNS))
        return Ledger((), (), raw)
    work, charges = [], []
    for cells in reader:
        line = reader.line_num
        if not any(cells):
            continue
        if len(cells) != len(LEDGER_COLUMNS):
            errors.append(f"ledger.csv — line {line}: has {len(cells)} fields, "
                          f"expected {len(LEDGER_COLUMNS)}")
            continue
        row = dict(zip(LEDGER_COLUMNS, cells))
        try:
            if row["row_type"] == "work":
                work.append(LedgerWork(row["invoice_no"], row["client"],
                                       date.fromisoformat(row["date"]),
                                       Decimal(row["hours"]), row["task"], row["project"]))
            elif row["row_type"] == "charge":
                charges.append(LedgerCharge(row["invoice_no"],
                                            date.fromisoformat(row["invoice_date"]),
                                            row["client"], row["unit"], row["description"],
                                            Decimal(row["amount_aud"])))
            else:
                errors.append(f'ledger.csv — line {line}: row_type "{row["row_type"]}" '
                              f"is not work or charge")
        except (ValueError, InvalidOperation):
            errors.append(f"ledger.csv — line {line}: a date isn't YYYY-MM-DD or a number "
                          f"isn't a number\n  {','.join(cells)}")
    return Ledger(tuple(work), tuple(charges), raw)


def load_ledger(base: Path, errors: list[str]) -> Ledger:
    try:
        raw = (base / "ledger.csv").read_bytes()
    except FileNotFoundError:
        return Ledger((), (), None)  # first run: created on the first commit
    return parse_ledger(raw, errors)


# ---- All inputs -------------------------------------------------------------


@dataclass(frozen=True)
class Inputs:
    config: Config
    clients: tuple[Client, ...]
    rates: RateCard
    entries: tuple[Entry, ...]
    ledger: Ledger


def load_inputs(base: Path, today: date, errors: list[str]) -> Inputs | None:
    """Read and type-check every input file, collecting every problem.

    Returns None if anything failed. Checks that compare one file with another
    run only on inputs that loaded cleanly, so a bad row can't set off a
    chain of misleading follow-on errors.
    """
    config = load_config(base, today, errors)
    currencies = {config.home_currency, *config.fx} if config else None
    clients = load_clients(base, currencies, errors)
    rates = load_rates(base, errors)
    entries = load_timesheet(base, errors)
    ledger = load_ledger(base, errors)
    if errors:
        return None
    return Inputs(config, tuple(clients), rates, tuple(entries), ledger)


# ---- Cross-file checks ------------------------------------------------------


def _same_tag(tag: str) -> str:
    return " ".join(tag.split()).casefold()


def validate(inputs: Inputs, errors: list[str]) -> None:
    """The checks that compare one file with another. Every failure is an error.

    Settings that only matter for an invoice (rates, payment details, the
    exchange rate) are checked for the clients being billed, so a client with
    nothing in this timesheet can't stop the run.
    """
    config, ledger = inputs.config, inputs.ledger
    owner = {p: c for c in inputs.clients for p in c.projects}

    # Unknown project. A dropped row means undercharging, which nobody sees.
    billed: list[tuple[Entry, Client]] = []
    for e in inputs.entries:
        client = owner.get(e.project)
        if client is None:
            errors.append(row_error(
                "timesheet.txt", f'unknown Project value "{e.project}"', e.line,
                ", ".join(sorted(owner)) + " (the Active Projects in clients.txt)",
            ))
        else:
            billed.append((e, client))

    # Work after the invoice date: usually a mistyped date, or an invoice_date
    # override left in config.txt from last month.
    source = " (set by invoice_date in config.txt)" if config.invoice_date_set else ""
    for e in inputs.entries:
        if e.date > config.invoice_date:
            errors.append(row_error(
                "timesheet.txt",
                f"dated after the invoice date, {config.invoice_date.isoformat()}{source}",
                e.line,
            ))

    # Duplicate lines. Pasting loses Notion's page IDs, so this compares content;
    # two genuinely separate entries trip it only if their Task text is identical.
    retell = "If these really are separate pieces of work, make their Task text differ in Notion."
    already = {}
    for w in ledger.work:
        already.setdefault((w.date, w.project, w.hours, w.task), w.invoice_no)
    batch: dict[tuple, list[Entry]] = {}
    for e in inputs.entries:
        key = (e.date, e.project, e.hours, e.task)
        batch.setdefault(key, []).append(e)
        if key in already:
            where = (f"billed, on {already[key]}" if already[key]
                     else "logged, as fixed-price work with nothing charged that month")
            errors.append(row_error(
                "timesheet.txt", f"this line may already be {where}", e.line,
            ) + f"\n  {retell}")
    for same in batch.values():
        if len(same) > 1:
            errors.append(row_error(
                "timesheet.txt", "the same line appears more than once",
                "\n  ".join(e.line for e in same),
            ) + f"\n  {retell}")

    # Week tags. Every row with one tag becomes one week charge, so the tag has
    # to belong to one client and one month, and must not have been billed.
    weeks: dict[str, list[tuple[Entry, Client]]] = {}
    for e, client in billed:
        if e.billing == "week rate":
            weeks.setdefault(e.tag, []).append((e, client))
    billed_tags = {_same_tag(ch.description): ch.invoice_no
                   for ch in ledger.charges if ch.unit == "week"}
    spellings: dict[str, list[str]] = {}
    for tag, rows in weeks.items():
        lines = "\n  ".join(e.line for e, _ in rows)
        if len({c.name for _, c in rows}) > 1:
            errors.append(row_error(
                "timesheet.txt", f'week rate tag "{tag}" is on projects of more than one client',
                lines,
            ))
        if len({(e.date.year, e.date.month) for e, _ in rows}) > 1:
            errors.append(row_error(
                "timesheet.txt", f'week rate tag "{tag}" spans two months', lines,
                "one month per tag, since invoices are cut by month. "
                "Split it into two tags in Notion.",
            ))
        if _same_tag(tag) in billed_tags:
            errors.append(row_error(
                "timesheet.txt",
                f'week rate tag "{tag}" was already billed, on {billed_tags[_same_tag(tag)]}',
                lines, "a new tag for each booked week",
            ))
        spellings.setdefault(_same_tag(tag), []).append(tag)
    for variants in spellings.values():
        if len(variants) > 1:
            # Two spellings would bill two weeks for what is surely one.
            errors.append(
                "timesheet.txt — week rate tags differ only in capitals or spacing: "
                + ", ".join(f'"{v}"' for v in variants)
                + "\n  Make every row of one booked week carry exactly the same tag."
            )

    # New numbers continue from the ledger's highest, so every number in it
    # has to be readable as prefix + digits.
    pattern = re.compile(re.escape(config.number_prefix) + r"\d+")
    odd = sorted({r.invoice_no for r in (*ledger.work, *ledger.charges)
                  if r.invoice_no and not pattern.fullmatch(r.invoice_no)})
    for number in odd:
        errors.append(f'ledger.csv — invoice number "{number}" is not number_prefix '
                      f'"{config.number_prefix}" followed by digits')

    # Per billed client: a rate for its tier, a way to pay, and today's rate.
    clients = sorted({c.name: c for _, c in billed}.values(), key=lambda c: c.name)
    for c in clients:
        if c.tier not in inputs.rates.rates:
            errors.append(f'rates.txt — no rates for tier "{c.tier}", used by {c.name}')
    by_currency: dict[str, list[str]] = {}
    for c in clients:
        by_currency.setdefault(c.currency, []).append(c.name)
    for currency, names in sorted(by_currency.items()):
        who = ", ".join(names)
        if currency not in config.payment:
            errors.append(f"config.txt — no [payment.{currency}] block, so there is no way "
                          f"to pay the invoice for {who}")
        if currency != config.home_currency:
            fx = config.fx[currency]
            if fx.as_at != config.invoice_date:
                errors.append(
                    f"config.txt — as_at under [currency.{currency}] is {fx.as_at.isoformat()} "
                    f"but the invoice date is {config.invoice_date.isoformat()}{source}. "
                    f"Update rate and as_at to that day's rate (needed for {who})."
                )


def check_inputs(base: Path, today: date, errors: list[str]) -> Inputs | None:
    """Load everything, then compare the files with each other. None on any error."""
    for name in TEMPLATE_FILES:
        if not (base / name).is_file():
            errors.append(f"{name} — not found in {base}. Copy the template/ folder in "
                          "beside make_invoices.py.")
    inputs = load_inputs(base, today, errors)
    if inputs is None or errors:
        return None
    validate(inputs, errors)
    return None if errors else inputs


# ---- Charges ----------------------------------------------------------------

GST_RATE = Decimal("0.10")  # unchanged since GST began in 2000
CENT = Decimal("0.01")
_LINE_ORDER = {"week": 0, "day": 1, "hour": 2, "fixed": 3}  # within one date


def cents(amount: Decimal) -> Decimal:
    """Round to the cent, halves up, as the ATO wants.

    Python's default is banker's rounding, which sends an exact half to the
    even cent instead. Getting this wrong is silent, so every rounding in the
    script goes through here.
    """
    return amount.quantize(CENT, rounding=ROUND_HALF_UP)


def fmt_hours(hours: Decimal) -> str:
    return format(hours.normalize(), "f")  # 40, 34.5, 1.25


def short_date(d: date) -> str:
    return f"{d.day} {d:%b}"  # 16 Nov


@dataclass(frozen=True)
class Line:
    date: date  # for ordering; a week's first day
    unit: str  # week, day, hour or fixed
    description: str
    qty: Decimal
    rate: Decimal  # in the invoice's currency
    amount: Decimal
    amount_aud: Decimal
    gst: Decimal | None  # None when not registered for GST


@dataclass(frozen=True)
class Invoice:
    number: str
    client: Client
    month: date  # first day of the month the work was done
    date: date
    due_date: date
    fx_rate: Decimal  # AUD per unit of the client's currency; 1 at home
    gst_treatment: str  # domestic, export, or unregistered
    lines: tuple[Line, ...]
    entries: tuple[Entry, ...]  # every row it covers, fixed-price ones included

    @property
    def work_log(self) -> tuple[Entry, ...]:
        """The rows the client sees. Fixed-price hours are internal only."""
        return tuple(e for e in self.entries if e.billing != "fixed price")

    @property
    def hours(self) -> Decimal:
        return sum((e.hours for e in self.work_log), Decimal(0))

    @property
    def subtotal(self) -> Decimal:
        return sum((line.amount for line in self.lines), Decimal(0))

    @property
    def gst(self) -> Decimal:
        return sum((line.gst or Decimal(0) for line in self.lines), Decimal(0))

    @property
    def total(self) -> Decimal:
        return self.subtotal + self.gst


@dataclass(frozen=True)
class Batch:
    invoices: tuple[Invoice, ...]
    # Fixed-price rows in a month where their client has nothing to charge.
    # They are kept in the ledger as work with no invoice number.
    logged_only: tuple[tuple[Entry, Client], ...]
    week_report: tuple[str, ...]


def highest_invoice_number(ledger: Ledger, prefix: str) -> int:
    numbers = [int(r.invoice_no[len(prefix):]) for r in (*ledger.work, *ledger.charges)
               if r.invoice_no]
    return max(numbers, default=0)


def charge_lines(entries: list[Entry], client: Client, card: RateCard,
                 fx: Decimal | None, gst_registered: bool) -> list[Line]:
    """Price one client's month. `fx` is AUD per unit of a foreign currency.

    Nothing aggregates across the month: a week is one tagged block, a day
    is one date, and a fixed price is one row carrying an amount.
    """
    tier = card.rates[client.tier]

    def priced(day: date, unit: str, description: str, qty: Decimal, rate: Decimal) -> Line:
        amount = cents(qty * rate)  # rounded per line, the taxable-supply rule
        amount_aud = amount if fx is None else cents(amount * fx)
        if not gst_registered:
            gst = None
        elif client.gst_treatment == "domestic":
            gst = cents(amount * GST_RATE)
        else:
            gst = Decimal("0.00")
        return Line(day, unit, description, qty, rate, amount, amount_aud, gst)

    def from_card(day: date, unit: str, description: str, qty: Decimal) -> Line:
        # The rate card is in AUD; a foreign client's rate is converted at
        # the invoice date and rounded to the cent before multiplying.
        rate = tier[unit] if fx is None else cents(tier[unit] / fx)
        return priced(day, unit, description, qty, rate)

    lines = []
    weeks: dict[str, list[Entry]] = {}
    hourly: dict[date, list[Entry]] = {}
    for e in entries:
        if e.billing == "week rate":
            weeks.setdefault(e.tag, []).append(e)
        elif e.billing == "fixed price":
            if e.amount is not None:  # already in the client's own currency
                lines.append(priced(e.date, "fixed", e.task, Decimal(1), e.amount))
        else:
            hourly.setdefault(e.date, []).append(e)

    # Every row carrying one tag collapses into one week charge, however many
    # hours or days it covers, and those rows bill nothing else.
    for tag, rows in weeks.items():
        lines.append(from_card(min(r.date for r in rows), "week", tag, Decimal(1)))

    # Only plain hourly rows count toward a day: week and fixed-price hours
    # are already paid for.
    day_hours = card.block_hours["day"]
    for day, rows in hourly.items():
        hours = sum((r.hours for r in rows), Decimal(0))
        label = f"{short_date(day)} — " + "; ".join(dict.fromkeys(r.task for r in rows))
        if hours >= day_hours:
            lines.append(from_card(day, "day", f"{label} (daily rate)", Decimal(1)))
            hours -= day_hours
        if hours > 0:
            lines.append(from_card(day, "hour", f"{label} (hourly rate)", hours))

    lines.sort(key=lambda line: (line.date, _LINE_ORDER[line.unit]))
    return lines


def week_report(entries: tuple[Entry, ...], card: RateCard) -> list[str]:
    """One line per booked week, marked when it differs from 40 hours over 5 days.

    A week's span is reported, not refused: weeks run long or short by
    agreement. Two weeks sharing a tag show up here as double the hours.
    """
    nominal_hours = card.block_hours["week"]
    nominal_days = int(nominal_hours / card.block_hours["day"])
    weeks: dict[str, list[Entry]] = {}
    for e in entries:
        if e.billing == "week rate":
            weeks.setdefault(e.tag, []).append(e)
    def span(rows: list[Entry]) -> str:
        return f"{short_date(min(r.date for r in rows))} to {short_date(max(r.date for r in rows))}"

    width = max((len(tag) for tag in weeks), default=0)
    span_width = max((len(span(rows)) for rows in weeks.values()), default=0)

    report = []
    for tag, rows in sorted(weeks.items(), key=lambda kv: min(r.date for r in kv[1])):
        hours = sum((r.hours for r in rows), Decimal(0))
        days = len({r.date for r in rows})
        notes = []
        if hours < nominal_hours:
            notes.append(f"{fmt_hours(nominal_hours - hours)}h under")
        elif hours > nominal_hours:
            notes.append(f"{fmt_hours(hours - nominal_hours)}h over")
        if days != nominal_days:
            notes.append(f"{days} days worked")
        text = f"  {'!' if notes else ' '} {tag:<{width}}  {fmt_hours(hours):>6}h  "
        if notes:
            text += f"{span(rows):<{span_width}}   <- " + ", ".join(notes)
        else:
            text += span(rows)
        report.append(text)
    return report


def compute(inputs: Inputs) -> Batch:
    """Cut the checked inputs into invoices: one per client per work month."""
    config, card = inputs.config, inputs.rates
    clients = {c.name: c for c in inputs.clients}
    owner = {p: c for c in inputs.clients for p in c.projects}

    groups: dict[tuple[date, str], list[Entry]] = {}
    for e in inputs.entries:
        groups.setdefault((e.date.replace(day=1), owner[e.project].name), []).append(e)

    # Numbered in date order: by month, then client name within a month.
    number = highest_invoice_number(inputs.ledger, config.number_prefix)
    invoices, logged_only = [], []
    for month, name in sorted(groups):
        client, entries = clients[name], groups[(month, name)]
        home = client.currency == config.home_currency
        fx = None if home else config.fx[client.currency].rate
        lines = charge_lines(entries, client, card, fx, config.gst_registered)
        if not lines:
            logged_only.extend((e, client) for e in entries)
            continue
        number += 1
        invoices.append(Invoice(
            number=f"{config.number_prefix}{number:0{config.number_padding}d}",
            client=client,
            month=month,
            date=config.invoice_date,
            due_date=config.invoice_date + timedelta(days=config.terms_days),
            fx_rate=Decimal(1) if home else fx,
            gst_treatment=client.gst_treatment if config.gst_registered else "unregistered",
            lines=tuple(lines),
            entries=tuple(entries),
        ))
    return Batch(tuple(invoices), tuple(logged_only), tuple(week_report(inputs.entries, card)))


# ---- PDFs -------------------------------------------------------------------

TEMPLATE_FILES = ("template/invoice.html", "template/invoice.css")


def long_date(d: date) -> str:
    return f"{d.day} {d:%B %Y}"  # 11 December 2026


def _money(value) -> str:
    return f"{Decimal(value):,.2f}"


def _lines(text: str):
    """A multi-line config value as HTML lines, escaped before the <br>s go in."""
    return markupsafe.Markup("<br>").join(text.strip().splitlines())


def template_env(base: Path) -> jinja2.Environment:
    env = jinja2.Environment(
        loader=jinja2.FileSystemLoader(base / "template"),
        autoescape=True,  # task text like "R&D" must reach the PDF intact
    )
    env.filters["money"] = _money
    env.filters["lines"] = _lines
    return env


def invoice_context(inv: Invoice, config: Config, draft: bool) -> dict:
    """Everything template/invoice.html reads, by the names it uses."""
    client = inv.client
    return {
        "draft": draft,
        "business": config.raw["business"],
        "tax": {"gst_registered": config.gst_registered,
                "abn": config.raw["tax"].get("abn"), "gst_rate": GST_RATE},
        "invoice": {"number": inv.number, "date": long_date(inv.date),
                    "due_date": long_date(inv.due_date), "period": f"{inv.month:%B %Y}"},
        "client": {"name": client.name, "care_of": client.care_of, "address": client.address,
                   "email": client.email, "reference": client.reference,
                   "currency": client.currency, "gst_treatment": client.gst_treatment},
        "charges": [{"description": l.description, "qty": fmt_hours(l.qty),
                     "rate": l.rate, "amount": l.amount} for l in inv.lines],
        "totals": {"subtotal": inv.subtotal, "gst": inv.gst, "total": inv.total,
                   "hours": fmt_hours(inv.hours)},
        "pay": config.payment[client.currency],
        "payment": {"note": config.payment_note},
        "terms_days": config.terms_days,
        # Week and hourly rows only: fixed-price hours never reach the client.
        "work": [{"date": f"{e.date.day} {e.date:%b %Y}", "project": e.project,
                  "task": e.task, "hours": fmt_hours(e.hours)}
                 for e in sorted(inv.work_log, key=lambda e: e.date)],
    }


def render_html(env: jinja2.Environment, inv: Invoice, config: Config, draft: bool) -> str:
    return env.get_template("invoice.html").render(invoice_context(inv, config, draft))


def write_pdf(base: Path, env: jinja2.Environment, inv: Invoice, config: Config,
              draft: bool, path: Path) -> None:
    """Render one invoice to `path`, refusing to replace a file already there.

    Invoice numbers come from the ledger's high-water mark, so an existing
    file means something is wrong upstream, and overwriting it would hide that.
    """
    pdf = render_pdf(base, env, inv, config, draft)
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "xb") as f:  # x: fail if it exists, atomically
        f.write(pdf)


def render_pdf(base: Path, env: jinja2.Environment, inv: Invoice, config: Config,
               draft: bool) -> bytes:
    html = render_html(env, inv, config, draft)
    return weasyprint.HTML(string=html, base_url=str(base / "template")).write_pdf()


# ---- Turnover and the preview summary ---------------------------------------


def year_before(d: date) -> date:
    try:
        return d.replace(year=d.year - 1)
    except ValueError:  # 29 February
        return d.replace(year=d.year - 1, day=28)


def rolling_turnover(ledger: Ledger, batch: Batch | None, end: date) -> Decimal:
    """GST turnover for the 12 months ending `end`, in AUD, excluding GST.

    Export sales count in full: GST-free is not the same as outside the
    threshold. Summing amount_aud rather than amount keeps SEK invoices from
    being added to AUD ones.
    """
    start = year_before(end)
    charges = [c.amount_aud for c in ledger.charges if start < c.invoice_date <= end]
    if batch is not None:
        charges += [l.amount_aud for inv in batch.invoices if start < inv.date <= end
                    for l in inv.lines]
    return sum(charges, Decimal(0))


def preview_summary(inputs: Inputs, batch: Batch, preview: Path) -> list[str]:
    """What the run prints before asking for `commit`. Empty sections are left out."""
    config = inputs.config
    owner = {p: c for c in inputs.clients for p in c.projects}
    note = " (set in config.txt)" if config.invoice_date_set else ""
    out = [f"Invoice date  {long_date(config.invoice_date)}{note}", ""]

    if batch.invoices:
        width = max(len(i.client.name) for i in batch.invoices)
        for inv in batch.invoices:
            out.append(f"  {inv.number}  {inv.month:%b %Y}  {inv.client.name:<{width}}  "
                       f"{inv.client.currency}  {inv.total:>12,.2f}")
    else:
        out.append("  No invoices: nothing in timesheet.txt charges anything this run.")

    if batch.week_report:
        out += ["", "Booked weeks", *batch.week_report]

    # A forgotten fixed-price amount would never be billed and never complain,
    # so every fixed-price row that charged nothing is shown here.
    uncharged = sorted((e for e in inputs.entries
                        if e.billing == "fixed price" and e.amount is None),
                       key=lambda e: e.date)
    if uncharged:
        width = max(len(owner[e.project].name) for e in uncharged)
        out += ["", "Fixed-price hours with no charge"]
        out += [f"  {owner[e.project].name:<{width}}  {short_date(e.date):>6}  "
                f"{fmt_hours(e.hours):>5}h  {e.task}" for e in uncharged]

    turnover = rolling_turnover(inputs.ledger, batch, config.invoice_date)
    threshold = config.turnover_threshold
    out += ["", f"Turnover, last 12 months: A${turnover:,.2f} of A${threshold:,.0f}, "
                "including this run"]
    if not config.gst_registered:
        if turnover >= threshold:
            out.append("  ! Over the GST threshold. Registration is due within 21 days of "
                       "crossing it, backdated to the day it was crossed.")
        elif turnover >= threshold * config.turnover_warn_at:
            out.append(f"  ! Past {config.turnover_warn_at:.0%} of the GST registration "
                       "threshold.")

    drafts = {0: "summary.csv is", 1: "The draft invoice and summary.csv are"}.get(
        len(batch.invoices), "The draft invoices and summary.csv are")
    out += ["", f"{drafts} open in Finder: {preview}"]
    return out


def open_in_finder(path: Path) -> None:
    subprocess.run(["open", str(path)], check=False)


# ---- Commit -----------------------------------------------------------------

SUMMARY_COLUMNS = ["work_month", "client", "invoice", "invoiced", "hours", "amount_aud"]


def csv_text(rows: list[list[str]]) -> str:
    buffer = io.StringIO()
    csv.writer(buffer, lineterminator="\n").writerows(rows)
    return buffer.getvalue()


def stage(path: Path, data: bytes) -> Path:
    """Write `data` to a temporary file beside `path`, ready to os.replace() over it.

    Beside, not in the system temp folder: the invoicing folder may be on
    another drive (pCloud), and a rename only replaces a file in one step
    within a single filesystem.
    """
    fd, tmp = tempfile.mkstemp(dir=path.parent, prefix=f".{path.name}.", suffix=".tmp")
    try:
        with os.fdopen(fd, "wb") as f:
            f.write(data)
            f.flush()
            os.fsync(f.fileno())
    except BaseException:
        Path(tmp).unlink(missing_ok=True)
        raise
    return Path(tmp)


def replace_atomically(path: Path, data: bytes) -> None:
    """Write `data` to `path` so the file on disk is always the old or the new one."""
    tmp = stage(path, data)
    try:
        os.replace(tmp, path)
    except BaseException:
        tmp.unlink(missing_ok=True)
        raise


def ledger_rows(batch: Batch, config: Config) -> list[list[str]]:
    """The rows one commit appends: each invoice's work rows, then its charges."""
    issued = config.invoice_date.isoformat()

    def row(**cells: str) -> list[str]:
        return [cells.get(column, "") for column in LEDGER_COLUMNS]

    def work(e: Entry, client: Client, number: str) -> list[str]:
        return row(row_type="work", invoice_no=number, invoice_date=issued, client=client.name,
                   date=e.date.isoformat(), hours=fmt_hours(e.hours), task=e.task,
                   project=e.project, billing_type=e.billing, ref=client.reference)

    rows = []
    for inv in batch.invoices:
        home = inv.client.currency == config.home_currency
        rows += [work(e, inv.client, inv.number) for e in inv.entries]
        rows += [row(row_type="charge", invoice_no=inv.number, invoice_date=issued,
                     client=inv.client.name, ref=inv.client.reference,
                     description=l.description, unit=l.unit, qty=fmt_hours(l.qty),
                     rate=f"{l.rate:.2f}", amount=f"{l.amount:.2f}",
                     currency=inv.client.currency, fx_rate=str(inv.fx_rate), fx_date=issued,
                     fx_source="" if home else config.fx_source,
                     amount_aud=f"{l.amount_aud:.2f}", tier=inv.client.tier,
                     gst_treatment=inv.gst_treatment,
                     gst_amount="" if l.gst is None else f"{l.gst:.2f}")
                 for l in inv.lines]
    # Fixed-price work in a month with nothing to charge: kept, but not invoiced.
    rows += [work(e, client, "") for e, client in batch.logged_only]
    return rows


def summary_rows(ledger: Ledger, end: date) -> list[list[str]]:
    """summary.csv: one row per invoice, by the month the work was done.

    Each invoice covers one month of work, so its work rows give the month.
    An opening row entered by hand without work rows goes under the month it
    was invoiced.
    """
    work: dict[str, list[LedgerWork]] = {}
    for w in ledger.work:
        work.setdefault(w.invoice_no, []).append(w)
    charges: dict[str, list[LedgerCharge]] = {}
    for c in ledger.charges:
        charges.setdefault(c.invoice_no, []).append(c)

    rows = []  # work month, client, invoice, invoiced, hours, amount
    for number in sorted((set(work) | set(charges)) - {""}):
        ws, cs = work.get(number, []), charges.get(number, [])
        month = min(w.date for w in ws) if ws else cs[0].invoice_date
        rows.append((f"{month:%Y-%m}", (cs or ws)[0].client, number,
                     f"{cs[0].invoice_date:%Y-%m}" if cs else "",
                     sum((w.hours for w in ws), Decimal(0)),
                     sum((c.amount_aud for c in cs), Decimal(0))))
    logged: dict[tuple[str, str], Decimal] = {}
    for w in work.get("", []):
        key = (f"{w.date:%Y-%m}", w.client)
        logged[key] = logged.get(key, Decimal(0)) + w.hours
    rows += [(month, client, "", "", hours, Decimal(0)) for (month, client), hours in logged.items()]
    rows.sort(key=lambda r: (r[0], r[2] or "~", r[1]))  # no-invoice rows last in a month

    out = [SUMMARY_COLUMNS]
    for month in sorted({r[0] for r in rows}):
        group = [r for r in rows if r[0] == month]
        out += [[m, client, number, invoiced, fmt_hours(hours), f"{amount:.2f}"]
                for m, client, number, invoiced, hours, amount in group]
        out.append([month, "Total", "", "",
                    fmt_hours(sum((r[4] for r in group), Decimal(0))),
                    f"{sum((r[5] for r in group), Decimal(0)):.2f}"])
    out.append([])
    out.append(["", f"Turnover, 12 months to {end.isoformat()}", "", "", "",
                f"{rolling_turnover(ledger, None, end):.2f}"])
    return out


def appended_ledger(inputs: Inputs, batch: Batch) -> tuple[bytes, list[list[str]]]:
    """ledger.csv as it will be after this commit, and the rows it gains.

    The existing bytes are kept exactly; the new rows only ever follow them.
    """
    old = inputs.ledger.raw
    if old is None:
        old = csv_text([LEDGER_COLUMNS]).encode()
    elif not old.endswith(b"\n"):
        old += b"\n"
    rows = ledger_rows(batch, inputs.config)
    return old + csv_text(rows).encode("utf-8"), rows


def summary_after(inputs: Inputs, batch: Batch) -> bytes:
    """summary.csv as it will be after this commit, built for the preview."""
    new_ledger, _ = appended_ledger(inputs, batch)
    rows = summary_rows(parse_ledger(new_ledger, []), inputs.config.invoice_date)
    return csv_text(rows).encode("utf-8")


def commit(base: Path, inputs: Inputs, batch: Batch, summary: bytes) -> list[str]:
    """Keep the run: final PDFs, then the ledger, then the reviewed summary.csv.

    Returns the problems found before anything is written; an empty list
    means it all went through. The ledger is the record, so if anything fails
    before it is replaced, the files this commit wrote are removed again and
    the folder is as it was. `summary` is the summary.csv shown in the
    preview; the ledger check below is what keeps it correct.
    """
    config = inputs.config
    ledger_path = base / "ledger.csv"
    targets = {inv.number: base / "invoices" / f"{inv.month:%Y-%m}" / f"{inv.number}.pdf"
               for inv in batch.invoices}

    problems = []
    for path in targets.values():
        if path.exists():
            # Numbers continue from the ledger, so a file here means an earlier
            # commit stopped partway or the file was put there by hand.
            problems.append(f"{path.relative_to(base)} — already exists, but ledger.csv has no "
                            "record of it. If it was never sent, delete it and run again.")
    current = ledger_path.read_bytes() if ledger_path.exists() else None
    if current != inputs.ledger.raw:
        problems.append("ledger.csv — changed while the drafts were open. Run again, so this "
                        "run is checked against the new version.")
    if problems:
        return problems

    # Re-render rather than move the drafts: a draft is a different document.
    # Rendering everything first means a template problem stops the commit
    # before a single file exists.
    env = template_env(base)
    pdfs = {inv.number: render_pdf(base, env, inv, config, draft=False)
            for inv in batch.invoices}
    new_ledger, rows = appended_ledger(inputs, batch)

    written: list[Path] = []
    made: list[Path] = []
    staged_summary = None
    try:
        staged_summary = stage(base / "summary.csv", summary)
        for inv in batch.invoices:
            path = targets[inv.number]
            for folder in (base / "invoices", path.parent):
                if not folder.exists():
                    folder.mkdir()
                    made.append(folder)
            with open(path, "xb") as f:
                written.append(path)
                f.write(pdfs[inv.number])
        replace_atomically(ledger_path, new_ledger)
    except BaseException:
        for path in written:
            path.unlink(missing_ok=True)
        for folder in reversed(made):
            folder.rmdir()
        if staged_summary is not None:
            staged_summary.unlink(missing_ok=True)
        print("\nThe commit did not finish. The files it had written were removed and "
              "ledger.csv is unchanged.", file=sys.stderr)
        raise

    print(f"\nCommitted {len(written)} invoice{'s' if len(written) != 1 else ''}:")
    print("\n".join(f"  {path.relative_to(base)}" for path in written))
    print(f"ledger.csv: {len(rows)} rows added.")

    # The summary is already fully written beside its target, so all that is
    # left is one rename. It is derived from the ledger, so even if that fails
    # nothing is lost: the next commit rebuilds it.
    try:
        os.replace(staged_summary, base / "summary.csv")
        print("summary.csv: replaced with the one in the preview.")
    except OSError as exc:
        staged_summary.unlink(missing_ok=True)
        print(f"summary.csv could not be replaced ({exc}). The invoices and ledger.csv are "
              "kept; summary.csv is rebuilt on the next commit.", file=sys.stderr)
    return []


NOTION_FILES = ("clients.txt", "rates.txt", "timesheet.txt")


def report_errors(errors: list[str]) -> None:
    print("\n\n".join(errors), file=sys.stderr)
    pasted = any(e.startswith(NOTION_FILES) for e in errors)
    print("\n" + (FIX_IN_NOTION if pasted else "Nothing was written."), file=sys.stderr)


EXIT_COMMITTED, EXIT_REFUSED, EXIT_DISCARDED = 0, 1, 2


def run(base: Path, today: date, ask=input, open_folder=open_in_finder) -> int:
    """One full run against the invoicing folder at `base`. Returns the exit code.

    Two gates: nothing is rendered until every check passes, and nothing is
    kept until a person has read the drafts and typed `commit`. The drafts
    live in a fresh temporary folder outside `base`, deleted whatever happens.

    `today`, `ask` and `open_folder` are parameters so tests can pin the date,
    answer the prompt and skip Finder; the command line passes the real ones.
    """
    errors: list[str] = []
    inputs = check_inputs(base, today, errors)
    if inputs is None:
        report_errors(errors)
        return EXIT_REFUSED
    batch = compute(inputs)
    if not batch.invoices and not batch.logged_only:
        print("Nothing to do: timesheet.txt has no rows.")
        return EXIT_COMMITTED

    preview = Path(tempfile.mkdtemp(prefix="invoice-preview-"))
    try:
        env = template_env(base)
        for inv in batch.invoices:
            write_pdf(base, env, inv, inputs.config, True, preview / f"{inv.number}.pdf")
        # The summary.csv this commit would leave, so the totals get read too.
        summary = summary_after(inputs, batch)
        (preview / "summary.csv").write_bytes(summary)
        print("\n".join(preview_summary(inputs, batch, preview)))
        open_folder(preview)

        try:
            answer = ask("\nType commit to keep them, anything else to discard: ")
        except (EOFError, KeyboardInterrupt):
            answer = ""
        if answer.strip() != "commit":
            print("\nDiscarded. Nothing was written.")
            return EXIT_DISCARDED
        problems = commit(base, inputs, batch, summary)
        if problems:
            report_errors(problems)
            return EXIT_REFUSED
        return EXIT_COMMITTED
    finally:
        shutil.rmtree(preview, ignore_errors=True)


def main() -> int:
    try:
        return run(SCRIPT_DIR, date.today())
    except KeyboardInterrupt:  # the preview folder is already gone by now
        print("\nStopped.", file=sys.stderr)
        return 130


if __name__ == "__main__":
    sys.exit(main())
