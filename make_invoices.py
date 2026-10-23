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

import os
import re
import sys
from dataclasses import dataclass
from datetime import date
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
    """Parse one pasted table. Bad rows become errors and are left out."""
    parsed = []
    for line in text.splitlines():
        if not line.strip():
            continue
        cells = split_row(line)
        if cells is None:
            errors.append(row_error(file, "this line is not a table row", line.strip()))
            continue
        if all(_SEPARATOR_CELL.fullmatch(cell) for cell in cells):
            continue  # the | --- | row under the header
        parsed.append((tuple(cells), line.strip()))

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


def run(base: Path, today: date) -> int:
    """One full run against the invoicing folder at `base`. Returns the exit code.

    `base` and `today` are parameters so tests can point a run at the fixtures
    and pin the date; the command line always passes the script's own folder
    and the real date.
    """
    print("make_invoices: not built yet.")
    return 1


def main() -> int:
    return run(SCRIPT_DIR, date.today())


if __name__ == "__main__":
    sys.exit(main())
