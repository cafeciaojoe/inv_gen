"""Charges for the fixtures, worked out by hand.

Rates (AUD): base 120 / 800 / 3,000, discounted 90 / 600 / 2,250,
subsidised 60 / 400 / 1,500 for hour / day / week. SEK is 0.1450 AUD.
"""

from datetime import date
from decimal import ROUND_HALF_EVEN, Decimal

import pytest

from make_invoices import cents, compute

D = Decimal


def batch_of(folder):
    inputs, errors = folder.check()
    assert errors == []
    return compute(inputs)


def lines_of(invoice):
    return [(l.unit, l.description, l.qty, l.rate, l.amount) for l in invoice.lines]


@pytest.fixture
def invoices(folder):
    return {i.number: i for i in batch_of(folder).invoices}


def test_one_invoice_per_client_per_month_numbered_in_date_order(invoices):
    assert [(n, i.month, i.client.name) for n, i in invoices.items()] == [
        ("INV-0001", date(2026, 9, 1), "Bluegum Theatre Company"),
        ("INV-0002", date(2026, 9, 1), "Tidewater Labs"),
        ("INV-0003", date(2026, 11, 1), "Bluegum Theatre Company"),
        ("INV-0004", date(2026, 11, 1), "Fjordlight AB"),
        ("INV-0005", date(2026, 11, 1), "Northside Makers Trust"),
        ("INV-0006", date(2026, 11, 1), "Tidewater Labs"),
        ("INV-0007", date(2026, 12, 1), "Northside Makers Trust"),
    ]


def test_dates_and_terms(invoices):
    first = invoices["INV-0001"]
    assert first.date == date(2026, 12, 11) and first.due_date == date(2027, 1, 10)


def test_hourly_lines_one_per_date(invoices):
    assert lines_of(invoices["INV-0001"]) == [
        ("hour", "7 Sep — Lantern concept sketches (hourly rate)", D("2"), D("120.00"), D("240.00")),
        ("hour", "8 Sep — Kick-off call (hourly rate)", D("1.25"), D("120.00"), D("150.00")),
    ]


def test_two_projects_on_one_date_reach_a_day_together(invoices):
    assert lines_of(invoices["INV-0002"]) == [
        ("day", "9 Sep — Bench frame CAD; Clock face prototype print (daily rate)",
         D("1"), D("600.00"), D("600.00")),
        ("hour", "9 Sep — Bench frame CAD; Clock face prototype print (hourly rate)",
         D("0.5"), D("90.00"), D("45.00")),
        ("hour", "10 Sep — Supplier quotes (hourly rate)", D("0.75"), D("90.00"), D("67.50")),
    ]
    assert invoices["INV-0002"].total == D("712.50")


def test_weeks_collapse_and_never_tip_a_date_into_a_day(invoices):
    inv = invoices["INV-0003"]
    assert lines_of(inv) == [
        ("week", "Lantern build week — agreed 14 Oct", D("1"), D("3000.00"), D("3000.00")),
        # 6 Nov also has 5 week hours; only the 4 plain hours count, so no day.
        ("hour", "6 Nov — Poster artwork files (hourly rate)", D("4"), D("120.00"), D("480.00")),
        ("week", "Lantern install week — agreed 14 Oct", D("1"), D("3000.00"), D("3000.00")),
        ("day", "16 Nov — Lantern rework after preview (daily rate)", D("1"), D("800.00"), D("800.00")),
        ("hour", "16 Nov — Lantern rework after preview (hourly rate)", D("1.5"), D("120.00"), D("180.00")),
        ("hour", "17 Nov — Lantern rework (hourly rate)", D("3.25"), D("120.00"), D("390.00")),
    ]
    assert inv.total == D("7850.00")
    assert len(inv.work_log) == 12 and inv.hours == D("94.75")


def test_sek_rates_are_converted_then_rounded_per_line(invoices):
    inv = invoices["INV-0004"]
    # 800 / 0.145 = 5517.24..., 120 / 0.145 = 827.586... -> 827.59
    assert lines_of(inv) == [
        ("day", "18 Nov — Lamp shade modelling (daily rate)", D("1"), D("5517.24"), D("5517.24")),
        ("hour", "18 Nov — Lamp shade modelling (hourly rate)", D("0.5"), D("827.59"), D("413.80")),
        ("hour", "19 Nov — Review call (hourly rate)", D("2.75"), D("827.59"), D("2275.87")),
        ("hour", "20 Nov — Shade test print (hourly rate)", D("1.5"), D("827.59"), D("1241.39")),
    ]
    assert inv.total == D("9448.30")
    assert inv.fx_rate == D("0.1450") and inv.client.currency == "SEK"
    assert [l.amount_aud for l in inv.lines] == [D("800.00"), D("60.00"), D("330.00"), D("180.00")]


def test_halves_round_up_not_to_even():
    # 1.5 x 827.59 = 1241.385 exactly: banker's rounding would give .38.
    assert cents(D("1241.385")) == D("1241.39")
    assert D("1241.385").quantize(D("0.01"), ROUND_HALF_EVEN) == D("1241.38")


def test_fixed_price_charges_only_rows_with_an_amount(invoices):
    nov = invoices["INV-0005"]
    assert lines_of(nov) == [
        # 5 hourly hours on 25 Nov; the 3.5 fixed-price hours don't count toward a day.
        ("hour", "25 Nov — Safety signage for the tool wall (hourly rate)", D("5"), D("60.00"), D("300.00")),
        ("fixed", "Tool wall first panels — deposit", D("1"), D("1500"), D("1500.00")),
    ]
    dec = invoices["INV-0007"]
    assert lines_of(dec) == [
        ("fixed", "Tool wall finishing and delivery — balance", D("1"), D("2000"), D("2000.00")),
    ]


def test_fixed_price_hours_never_reach_the_work_log(invoices):
    nov = invoices["INV-0005"]
    assert len(nov.entries) == 3  # both fixed-price rows are still covered
    assert [e.task for e in nov.work_log] == ["Safety signage for the tool wall"]
    assert invoices["INV-0007"].work_log == ()  # the template drops the section


def test_batch_total_in_aud(invoices):
    aud = [l.amount_aud for i in invoices.values() for l in i.lines]
    assert sum(aud) == D("14302.50")


def test_not_registered_means_no_gst(invoices):
    inv = invoices["INV-0003"]
    assert inv.gst_treatment == "unregistered"
    assert all(l.gst is None for l in inv.lines) and inv.gst == 0


def test_registered_domestic_and_export(folder):
    folder.edit("config.txt", "gst_registered = false", "gst_registered = true")
    invoices = {i.number: i for i in batch_of(folder).invoices}
    dom = invoices["INV-0003"]
    assert dom.gst_treatment == "domestic"
    assert dom.gst == D("785.00") and dom.total == D("8635.00")
    exp = invoices["INV-0004"]
    assert exp.gst_treatment == "export"
    assert all(l.gst == D("0.00") for l in exp.lines) and exp.total == D("9448.30")


def test_gst_rounds_per_line(folder):
    folder.edit("config.txt", "gst_registered = false", "gst_registered = true")
    inv = next(i for i in batch_of(folder).invoices if i.number == "INV-0002")
    # 10% of 45.00 and 67.50 is 4.50 and 6.75; of 600 it's 60.
    assert [l.gst for l in inv.lines] == [D("60.00"), D("4.50"), D("6.75")]


def test_numbering_continues_from_the_ledger(folder):
    folder.append("ledger.csv",
                  "charge,INV-0041,2026-08-31,Bluegum Theatre Company,,,,,,,Opening balance,"
                  "fixed,1,500.00,500.00,AUD,1,2026-08-31,opening,500.00,base,unregistered,\n")
    assert batch_of(folder).invoices[0].number == "INV-0042"


def test_ledger_number_with_another_prefix_is_refused(folder):
    folder.append("ledger.csv",
                  "charge,2026-041,2026-08-31,Bluegum Theatre Company,,,,,,,Opening balance,"
                  "fixed,1,500.00,500.00,AUD,1,2026-08-31,opening,500.00,base,unregistered,\n")
    _, errors = folder.check()
    assert errors == ['ledger.csv — invoice number "2026-041" is not number_prefix "INV-" '
                      "followed by digits"]


def test_month_with_nothing_to_charge_makes_no_invoice(folder):
    folder.edit("timesheet.txt", "| fixed price | 2000 |", "| fixed price |  |")
    batch = batch_of(folder)
    assert [i.number for i in batch.invoices][-1] == "INV-0006"
    assert [e.date for e, _ in batch.logged_only] == [date(2026, 12, 2), date(2026, 12, 9)]


def test_week_report(folder):
    assert batch_of(folder).week_report == (
        "  ! Lantern build week — agreed 14 Oct      34.5h  2 Nov to 6 Nov    <- 5.5h under",
        "  ! Lantern install week — agreed 14 Oct    43.5h  9 Nov to 12 Nov   <- 3.5h over, 4 days worked",
    )


def test_nominal_week_is_unmarked(folder):
    folder.edit("timesheet.txt", "| November 6, 2026 | 5 | Diffuser fitting",
                "| November 6, 2026 | 10.5 | Diffuser fitting")
    assert batch_of(folder).week_report[0] == (
        "    Lantern build week — agreed 14 Oct        40h  2 Nov to 6 Nov"
    )
