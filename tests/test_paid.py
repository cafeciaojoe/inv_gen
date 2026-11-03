"""Paid on dates typed into summary.csv: carried over, checked, and used."""

import csv
from datetime import date

import pytest

from make_invoices import EXIT_COMMITTED, EXIT_DISCARDED, EXIT_REFUSED
from test_commit import commit_run, summary_table

NEXT_MONTH = date(2027, 2, 2)  # the fixtures' invoices were issued on 11 January 2027


def committed_then_cleared(folder):
    """Commit the fixtures, then leave a timesheet with nothing new, as next month would."""
    assert commit_run(folder) == EXIT_COMMITTED
    header = (folder.path / "timesheet.txt").read_text().splitlines()[:2]
    (folder.path / "timesheet.txt").write_text("\n".join(header) + "\n")


def mark_paid(folder, marks, *, extra_rows=(), encoding="utf-8"):
    """Type paid on dates into summary.csv, keyed by invoice number or by row label."""
    path = folder.path / "invoices" / "summary.csv"
    with open(path, newline="", encoding="utf-8-sig") as f:
        rows = list(csv.reader(f))
    col = rows[0].index("paid on")
    for row in rows[1:]:
        key = row[2] or row[1] if len(row) > 2 else None
        if key in marks:
            row[col] = marks[key]
    rows += [list(r) + [""] * (len(rows[0]) - len(r)) for r in extra_rows]
    with open(path, "w", newline="", encoding=encoding) as f:
        csv.writer(f).writerows(rows)  # \r\n line ends, as some editors save


def by_invoice(folder):
    return {r["invoice"]: r for r in summary_table(folder) if r["invoice"]}


def test_paid_dates_carry_into_the_next_summary(folder):
    committed_then_cleared(folder)
    mark_paid(folder, {"INV-0001": "2027-01-20", "INV-0004": "2027-01-25"},
              encoding="utf-8-sig")  # with the byte-order mark some editors add
    assert commit_run(folder, today=NEXT_MONTH) == EXIT_COMMITTED
    rows = by_invoice(folder)
    assert rows["INV-0001"]["paid on"] == "2027-01-20"
    assert rows["INV-0004"]["paid on"] == "2027-01-25"
    assert rows["INV-0002"]["paid on"] == ""


def test_overdue_invoices_are_listed_until_marked_paid(folder, capsys):
    committed_then_cleared(folder)
    mark_paid(folder, {"INV-0001": "2027-01-20"})
    capsys.readouterr()
    assert commit_run(folder, answer="", today=date(2027, 3, 1)) == EXIT_DISCARDED
    out = capsys.readouterr().out
    overdue = out.split("Overdue, with no paid on date in summary.csv\n")[1].split("\n\n")[0]
    assert [line.split()[0] for line in overdue.splitlines()] == [
        f"INV-000{n}" for n in range(2, 8)]
    # Owed in the client's own currency, GST included (none here: it's abroad).
    assert ("  INV-0004  Fjordlight AB            due 10 February 2027   SEK     9,448.29"
            in overdue.splitlines())


def test_nothing_is_overdue_within_its_terms(folder, capsys):
    committed_then_cleared(folder)
    capsys.readouterr()
    commit_run(folder, answer="", today=date(2027, 2, 10))
    assert "Overdue" not in capsys.readouterr().out


@pytest.mark.parametrize("typed, error", [
    ("20/01/2027", 'summary.csv — line 2: paid on "20/01/2027" for INV-0001 isn\'t a date '
                   "like 2026-11-12"),
    ("2027-01-05", "summary.csv — INV-0001 is paid on 2027-01-05, before it was issued on "
                   "2027-01-11"),
    ("2027-03-01", "summary.csv — INV-0001 is paid on 2027-03-01, after this run's invoice "
                   "date (2027-02-02)"),
])
def test_a_paid_on_date_that_cant_be_right_is_refused(folder, typed, error):
    committed_then_cleared(folder)
    mark_paid(folder, {"INV-0001": typed})
    _, errors = folder.check(NEXT_MONTH)
    assert errors == [error]


def test_a_paid_on_date_on_a_total_row_is_refused(folder):
    committed_then_cleared(folder)
    mark_paid(folder, {"Total": "2027-01-20"})
    _, errors = folder.check(NEXT_MONTH)
    assert errors[0] == ('summary.csv — line 4: paid on "2027-01-20" is in a row with no '
                         "invoice number. Put it on the invoice's own row.")


def test_a_paid_on_date_for_an_unknown_invoice_is_refused(folder):
    committed_then_cleared(folder)
    mark_paid(folder, {}, extra_rows=[["2026-09", "Someone", "INV-0099", "2027-01",
                                       "2027-01-20"]])
    _, errors = folder.check(NEXT_MONTH)
    assert errors == ["summary.csv — paid on 2027-01-20 for INV-0099, which isn't in "
                      "ledger.csv. Check the invoice number."]


def test_an_invoice_paid_twice_is_refused(folder):
    committed_then_cleared(folder)
    mark_paid(folder, {"INV-0001": "2027-01-20"},
              extra_rows=[["2026-09", "Bluegum Theatre Company", "INV-0001", "2027-01",
                           "2027-01-21"]])
    _, errors = folder.check(NEXT_MONTH)
    assert len(errors) == 1 and "INV-0001 has a paid on date twice" in errors[0]


def test_a_summary_from_before_the_paid_on_column_reads_as_nothing_paid(folder):
    (folder.path / "invoices" / "summary.csv").write_text("month,client,invoice\n")
    inputs, errors = folder.check()
    assert errors == [] and inputs.paid == {}


def test_a_summary_edited_while_the_drafts_are_open_is_kept(folder, capsys):
    committed_then_cleared(folder)
    mark = lambda: mark_paid(folder, {"INV-0001": "2027-01-20"})  # noqa: E731
    assert commit_run(folder, today=NEXT_MONTH, during_prompt=mark) == EXIT_REFUSED
    assert "summary.csv — changed while the drafts were open" in capsys.readouterr().err
    assert by_invoice(folder)["INV-0001"]["paid on"] == "2027-01-20"


def test_gst_is_shown_and_owed_includes_it(folder):
    folder.edit("config.txt", "gst_registered = false", "gst_registered = true")
    commit_run(folder)
    rows = by_invoice(folder)
    assert rows["INV-0001"]["GST"] == "39.00"
    assert rows["INV-0004"]["GST"] == ""  # Fjordlight is abroad: GST-free
    # Tax and super come from the amount before GST.
    assert (rows["INV-0001"]["tax set aside"], rows["INV-0001"]["super"]) == ("117.00", "39.00")
    # The month's Total row adds up the same columns.
    september = next(r for r in summary_table(folder)
                     if r["month"] == "2026-09" and r["client"] == "Total")
    assert (september["invoice total"], september["GST"], september["tax set aside"],
            september["super"]) == ("1102.50", "110.25", "330.75", "110.25")


@pytest.mark.parametrize("line", ["tax_set_aside = 1.2", "tax_set_aside = -0.1"])
def test_a_set_aside_share_outside_0_to_1_is_refused(folder, line):
    folder.edit("config.txt", "tax_set_aside = 0.30", line)
    _, errors = folder.load()
    assert errors == ["config.txt — tax_set_aside under [tax] must be a share like 0.3, "
                      "from 0 up to 1"]
