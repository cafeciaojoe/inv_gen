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
import sys
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
