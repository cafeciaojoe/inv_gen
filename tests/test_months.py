"""The current month waits, and Notion's relative dates ("Last Thursday")."""

import os
from datetime import date, datetime

import pytest

from conftest import TODAY
from make_invoices import compute, notion_relative_date, preview_summary, run

JAN_ROW = "| January 6, 2027 | 3 | Clock hands | Tide Clock |  |  |  |\n"


def saved_on(folder, day):
    """Set when timesheet.txt was saved, which is what relative dates count from."""
    stamp = datetime(day.year, day.month, day.day, 12).timestamp()
    os.utime(folder.path / "timesheet.txt", (stamp, stamp))


def batch_of(folder, today=TODAY):
    inputs, errors = folder.check(today)
    assert errors == []
    return inputs, compute(inputs)


# ---- The invoice date's month is held back ----------------------------------


def test_this_months_rows_wait(folder):
    folder.append("timesheet.txt", JAN_ROW)
    inputs, batch = batch_of(folder)
    assert [(e.task, c.name) for e, c in batch.held_back] == [("Clock hands", "Tidewater Labs")]
    assert not any(i.month == date(2027, 1, 1) for i in batch.invoices)
    assert len(batch.invoices) == 7  # September to December as before
    out = "\n".join(preview_summary(inputs, batch, folder.path))
    assert ("Not invoiced yet: January 2027\n"
            "  Date             Hours  Project\n"
            "  January 6, 2027      3  Tide Clock\n") in out
    assert "On commit these go to timesheet_not_sent.txt" in out


def test_invoicing_the_day_after_a_month_ends(folder):
    text = (folder.path / "timesheet.txt").read_text()
    (folder.path / "timesheet.txt").write_text(
        "\n".join(l for l in text.splitlines() if "December" not in l) + "\n")
    folder.edit("config.txt", "as_at = 2027-01-11", "as_at = 2026-12-01")
    inputs, batch = batch_of(folder, today=date(2026, 12, 1))
    # 1 December: November is over and billed; nothing from December yet.
    assert batch.invoices[-1].month == date(2026, 11, 1)


def test_december_waits_when_invoicing_in_december(folder):
    folder.edit("config.txt", "as_at = 2027-01-11", "as_at = 2026-12-11")
    inputs, batch = batch_of(folder, today=date(2026, 12, 11))
    assert [e.task for e, _ in batch.held_back] == [
        "Tool wall revisions", "Tool wall finishing and delivery"]
    assert all(i.month < date(2026, 12, 1) for i in batch.invoices)


def test_a_week_ending_this_month_waits_whole(folder):
    folder.append("timesheet.txt",
                  "| December 31, 2026 | 8 | New year build | Stage Lantern | week rate | "
                  "Lantern new year week — agreed 1 Dec |  |\n"
                  "| January 4, 2027 | 8 | New year build | Stage Lantern | week rate | "
                  "Lantern new year week — agreed 1 Dec |  |\n")
    _, batch = batch_of(folder)
    assert [e.date for e, _ in batch.held_back] == [date(2026, 12, 31), date(2027, 1, 4)]
    assert not any("new year" in l.charge for i in batch.invoices for l in i.lines)


def test_held_back_rows_go_into_the_not_sent_file(folder):
    folder.append("timesheet.txt", JAN_ROW)
    assert run(folder.path, TODAY, ask=lambda _: "commit", open_folder=lambda _: None) == 0
    text = (folder.path / "timesheet_not_sent.txt").read_text()
    assert text.splitlines()[2] == JAN_ROW.strip()
    assert "Clock hands" not in (folder.path / "ledger.csv").read_text()


# ---- Notion's relative dates -------------------------------------------------

FRIDAY = date(2026, 12, 4)


@pytest.mark.parametrize("text, expected", [
    ("Today", date(2026, 12, 4)),
    ("@Yesterday", date(2026, 12, 3)),
    ("Last Thursday", date(2026, 12, 3)),
    ("last monday", date(2026, 11, 30)),
    ("@Last Friday", date(2026, 11, 27)),  # a week back, not today
    ("Last Saturday", date(2026, 11, 28)),
])
def test_past_relative_dates(text, expected):
    assert notion_relative_date(text, FRIDAY) == expected


@pytest.mark.parametrize("text", ["Tomorrow", "Next Friday", "Friday", "This Monday"])
def test_future_relative_dates_are_refused(text):
    assert "future" in notion_relative_date(text, FRIDAY)


def test_anything_else_is_not_a_date():
    assert notion_relative_date("Last week", FRIDAY) == "is not a date"


def test_relative_dates_count_from_the_day_the_timesheet_was_saved(folder):
    folder.edit("timesheet.txt", "| November 25, 2026 | 5 |", "| @Last Wednesday | 5 |")
    saved_on(folder, date(2026, 12, 2))  # a Wednesday: Last Wednesday is 25 November
    inputs, batch = batch_of(folder)
    row = next(e for e in inputs.entries if e.task == "Safety signage for the tool wall")
    assert row.date == date(2026, 11, 25)
    assert inputs.relative_as_of == date(2026, 12, 2)
    out = "\n".join(preview_summary(inputs, batch, folder.path))
    assert ("Recent Notion dates (Yesterday, Last Thursday) read as of 2 December 2026, "
            "the day timesheet.txt was saved.") in out


def test_no_note_when_every_date_is_full(folder):
    inputs, batch = batch_of(folder)
    assert inputs.relative_as_of is None
    assert "Recent Notion dates" not in "\n".join(preview_summary(inputs, batch, folder.path))


def test_a_future_relative_date_is_refused_by_name(folder):
    folder.edit("timesheet.txt", "| November 24, 2026 | 2 |", "| Tomorrow | 2 |")
    _, errors = folder.check()
    assert errors[0].startswith('timesheet.txt — Date "Tomorrow" is a future date in '
                                "Notion's words")


def test_a_held_back_relative_date_is_written_back_in_full(folder):
    folder.append("timesheet.txt", "| Yesterday | 3 | Clock hands | Tide Clock |  |  |  |\n")
    saved_on(folder, date(2027, 1, 8))
    run(folder.path, TODAY, ask=lambda _: "commit", open_folder=lambda _: None)
    lines = (folder.path / "timesheet_not_sent.txt").read_text().splitlines()
    assert lines[2] == "| January 7, 2027 | 3 | Clock hands | Tide Clock |  |  |  |"
