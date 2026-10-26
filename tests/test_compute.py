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
    return [(l.unit, l.project, l.charge, l.qty, l.rate, l.amount) for l in invoice.lines]


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
    assert first.date == date(2027, 1, 11) and first.due_date == date(2027, 2, 10)


def test_hours_add_up_into_one_line_per_project(invoices):
    # 2 h on 7 Sep and 1.25 h on 8 Sep.
    assert lines_of(invoices["INV-0001"]) == [
        ("hour", "Stage Lantern", "Hourly", D("3.25"), D("120.00"), D("390.00")),
    ]


def test_a_day_across_two_projects_names_both(invoices):
    # 9 Sep: 5 h Wave Bench + 3.5 h Tide Clock = one day plus 0.5 h, per client.
    assert lines_of(invoices["INV-0002"]) == [
        ("day", "Wave Bench, Tide Clock", "Daily", D("1"), D("600.00"), D("600.00")),
        ("hour", "Wave Bench, Tide Clock", "Hourly", D("0.5"), D("90.00"), D("45.00")),
        ("hour", "Wave Bench", "Hourly", D("0.75"), D("90.00"), D("67.50")),
    ]
    assert invoices["INV-0002"].total == D("712.50")


def test_each_week_keeps_its_tag_and_never_tips_a_date_into_a_day(invoices):
    inv = invoices["INV-0003"]
    assert lines_of(inv) == [
        ("week", "Stage Lantern", "Week rate: Lantern build week — agreed 14 Oct",
         D("1"), D("3000.00"), D("3000.00")),
        ("week", "Stage Lantern", "Week rate: Lantern install week — agreed 14 Oct",
         D("1"), D("3000.00"), D("3000.00")),
        ("day", "Stage Lantern", "Daily", D("1"), D("800.00"), D("800.00")),
        # 4 h on 6 Nov (which also has 5 week hours, so no day), 1.5 h past the
        # day on 16 Nov, 3.25 h on 17 Nov.
        ("hour", "Stage Lantern", "Hourly", D("8.75"), D("120.00"), D("1050.00")),
    ]
    assert inv.total == D("7850.00")
    assert len(inv.work_log) == 12 and inv.hours == D("94.75")


def test_a_week_can_have_a_custom_price(folder):
    folder.edit("timesheet.txt", "| Diffuser fitting | Stage Lantern | week rate | "
                "Lantern build week — agreed 14 Oct |  |",
                "| Diffuser fitting | Stage Lantern | week rate | "
                "Lantern build week — agreed 14 Oct | 2,500 |")
    inv = next(i for i in batch_of(folder).invoices if i.number == "INV-0003")
    assert lines_of(inv)[0] == ("week", "Stage Lantern",
                                "Week rate: Lantern build week — agreed 14 Oct",
                                D("1"), D("2500"), D("2500.00"))
    assert lines_of(inv)[1][-1] == D("3000.00")  # the other week keeps the rate card


def test_sek_rates_are_converted_then_rounded_per_line(invoices):
    inv = invoices["INV-0004"]
    # 800 / 0.145 = 5517.24..., 120 / 0.145 = 827.586... -> 827.59.
    # Hours: 0.5 past the day on 18 Nov, 2.75 and 1.5 -> 4.75 x 827.59 = 3931.0525.
    assert lines_of(inv) == [
        ("day", "Aurora Lamp", "Daily", D("1"), D("5517.24"), D("5517.24")),
        ("hour", "Aurora Lamp", "Hourly", D("4.75"), D("827.59"), D("3931.05")),
    ]
    assert inv.total == D("9448.29")
    assert inv.fx_rate == D("0.1450") and inv.client.currency == "SEK"
    assert [l.amount_aud for l in inv.lines] == [D("800.00"), D("570.00")]


def test_halves_round_up_not_to_even():
    # 1.5 x 827.59 = 1241.385 exactly: banker's rounding would give .38.
    assert cents(D("1241.385")) == D("1241.39")
    assert D("1241.385").quantize(D("0.01"), ROUND_HALF_EVEN) == D("1241.38")


def test_fixed_price_charges_only_rows_with_an_amount(invoices):
    nov = invoices["INV-0005"]
    assert lines_of(nov) == [
        # 5 hourly hours on 25 Nov; the 3.5 fixed-price hours don't count toward a day.
        ("hour", "Tool Wall", "Hourly", D("5"), D("60.00"), D("300.00")),
        ("fixed", "Tool Wall", "Fixed price: Tool wall build (50% payment)",
         D("1"), D("1500"), D("1500.00")),
    ]
    dec = invoices["INV-0007"]
    assert lines_of(dec) == [
        ("fixed", "Tool Wall", "Fixed price: Tool wall build (100% payment)",
         D("1"), D("2000"), D("2000.00")),
    ]


def test_fixed_price_rows_are_in_the_work_log_with_hours_hidden(invoices):
    nov = invoices["INV-0005"]
    assert [e.task for e in nov.work_log] == [
        "Tool wall layout and CAD", "Tool wall first panels", "Safety signage for the tool wall"]
    assert nov.hours == D("5")  # the 6 + 3.5 fixed-price hours stay hidden
    dec = invoices["INV-0007"]
    assert len(dec.work_log) == 2 and dec.hours == 0


def test_hours_settings_change_what_the_work_log_counts(folder):
    folder.edit("config.txt", "show_fixed_price_hours = false", "show_fixed_price_hours = true")
    folder.edit("config.txt", "show_week_rate_hours = true", "show_week_rate_hours = false")
    invoices = {i.number: i for i in batch_of(folder).invoices}
    assert invoices["INV-0005"].hours == D("14.5")  # 6 + 3.5 fixed + 5 hourly
    assert invoices["INV-0003"].hours == D("16.75")  # only 4 + 9.5 + 3.25 hourly


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
    assert all(l.gst == D("0.00") for l in exp.lines) and exp.total == D("9448.29")


def test_gst_rounds_per_line(folder):
    folder.edit("config.txt", "gst_registered = false", "gst_registered = true")
    inv = next(i for i in batch_of(folder).invoices if i.number == "INV-0002")
    # 10% of 45.00 and 67.50 is 4.50 and 6.75; of 600 it's 60.
    assert [l.gst for l in inv.lines] == [D("60.00"), D("4.50"), D("6.75")]


def test_numbering_continues_from_the_ledger(folder):
    folder.append("ledger.csv",
                  "charge,INV-0041,2026-08-31,Bluegum Theatre Company,,,,,,,Opening balance,"
                  "fixed,1,500.00,500.00,AUD,1,2026-08-31,opening,500.00,base,unregistered,,\n")
    assert batch_of(folder).invoices[0].number == "INV-0042"


def test_ledger_number_with_another_prefix_is_refused(folder):
    folder.append("ledger.csv",
                  "charge,2026-041,2026-08-31,Bluegum Theatre Company,,,,,,,Opening balance,"
                  "fixed,1,500.00,500.00,AUD,1,2026-08-31,opening,500.00,base,unregistered,,\n")
    _, errors = folder.check()
    assert errors == ['ledger.csv — invoice number "2026-041" is not number_prefix "INV-" '
                      "followed by digits"]


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


# ---- Months with nothing to charge -----------------------------------------

def invoice_for(batch, client, month):
    return next(i for i in batch.invoices if i.client.name == client and i.month == month)


def test_rows_between_payments_go_on_the_next_payment_invoice(folder):
    # The way tags name payments: the waiting rows keep the 50% payment's tag.
    folder.append("timesheet.txt",
                  "| September 15, 2026 | 0 | Bench design sign-off | Wave Bench | fixed price | "
                  "Bench build (50% payment) | 900 |\n"
                  "| October 12, 2026 | 6 | Bench frame welding | Wave Bench | fixed price | "
                  "Bench build (50% payment) |  |\n"
                  "| October 14, 2026 | 4 | Bench seat fitting | Wave Bench | fixed price | "
                  "Bench build (50% payment) |  |\n"
                  "| November 26, 2026 | 0 | Bench handover | Wave Bench | fixed price | "
                  "Bench build (100% payment) | 900 |\n")
    batch = batch_of(folder)
    nov = invoice_for(batch, "Tidewater Labs", date(2026, 11, 1))
    assert [e.task for e in nov.work_log] == [
        "Bench frame welding", "Bench seat fitting", "Clock mechanism testing", "Bench handover"]
    assert ("fixed", "Wave Bench", "Fixed price: Bench build (100% payment)",
            D("1"), D("900"), D("900.00")) in lines_of(nov)
    assert not any(i.month == date(2026, 10, 1) for i in batch.invoices)
    sep = invoice_for(batch, "Tidewater Labs", date(2026, 9, 1))
    assert "Bench frame welding" not in [e.task for e in sep.work_log]


def test_a_month_with_a_charge_on_the_project_keeps_its_own_rows(folder):
    # A materials charge is a fixed-price charge on the project too, so rows
    # waiting in that month go on its invoice.
    folder.append("timesheet.txt",
                  "| October 20, 2026 | 5 | Tool wall sketches | Tool Wall | fixed price | "
                  "Tool wall build (50% payment) |  |\n"
                  "| October 21, 2026 | 0 | 3D printing filament | Tool Wall | fixed price | "
                  "Material costs | 180 |\n")
    october = invoice_for(batch_of(folder), "Northside Makers Trust", date(2026, 10, 1))
    assert lines_of(october) == [
        ("fixed", "Tool Wall", "Fixed price: Material costs", D("1"), D("180"), D("180.00"))]
    assert [e.task for e in october.work_log] == ["Tool wall sketches", "3D printing filament"]


def test_a_month_with_nothing_to_charge_goes_on_the_clients_latest_invoice(folder):
    folder.edit("timesheet.txt", "(100% payment) | 2000 |", "(100% payment) |  |")
    batch = batch_of(folder)
    assert [i.number for i in batch.invoices][-1] == "INV-0006"  # no December invoice
    nov = invoice_for(batch, "Northside Makers Trust", date(2026, 11, 1))
    assert [e.task for e in nov.work_log][-2:] == [
        "Tool wall revisions", "Tool wall finishing and delivery"]
    assert batch.not_sent == ()


def test_attached_rows_follow_the_hours_setting(folder):
    folder.edit("timesheet.txt", "(100% payment) | 2000 |", "(100% payment) |  |")
    folder.edit("config.txt", "show_fixed_price_hours = false", "show_fixed_price_hours = true")
    nov = invoice_for(batch_of(folder), "Northside Makers Trust", date(2026, 11, 1))
    assert nov.hours == D("25.75")  # 6 + 3.5 + 7 + 4.25 fixed + 5 hourly


def test_a_client_with_no_invoice_this_run_is_not_sent(folder):
    header = (folder.path / "timesheet.txt").read_text().splitlines()[:2]
    rows = ["| October 12, 2026 | 6 | Bench frame welding | Wave Bench | fixed price | "
            "Bench build (50% payment) |  |",
            "| November 3, 2026 | 2 | Shade test print | Aurora Lamp |  |  |  |"]
    (folder.path / "timesheet.txt").write_text("\n".join(header + rows) + "\n")
    batch = batch_of(folder)
    assert [i.client.name for i in batch.invoices] == ["Fjordlight AB"]
    assert [(e.task, c.name) for e, c in batch.not_sent] == [
        ("Bench frame welding", "Tidewater Labs")]


def test_a_week_crossing_a_month_end_is_charged_once_in_the_month_it_ends(folder):
    folder.edit("timesheet.txt", "| November 2, 2026 | 8 |", "| October 30, 2026 | 8 |")
    batch = batch_of(folder)
    bluegum = [i for i in batch.invoices if i.client.name == "Bluegum Theatre Company"]
    assert [i.month for i in bluegum] == [date(2026, 9, 1), date(2026, 11, 1)]  # no October
    nov = bluegum[-1]
    weeks = [l for l in nov.lines if l.charge == "Week rate: Lantern build week — agreed 14 Oct"]
    assert len(weeks) == 1 and weeks[0].amount == D("3000.00")
    assert nov.work_log[0].date == date(2026, 10, 30)
    assert batch.week_report[0].startswith("  ! Lantern build week — agreed 14 Oct      34.5h  "
                                           "30 Oct to 6 Nov")

