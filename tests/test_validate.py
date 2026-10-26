from datetime import date

from conftest import TODAY

LEDGER_TAIL = "," * 13  # the empty charge columns on a work row


def errors_of(folder, today=TODAY):
    inputs, errors = folder.check(today)
    assert inputs is None and errors
    return errors


def only_error(folder, today=TODAY):
    errors = errors_of(folder, today)
    assert len(errors) == 1, errors
    return errors[0]


def test_fixtures_pass_every_check(folder):
    inputs, errors = folder.check()
    assert errors == [] and inputs is not None


# ---- Unknown project --------------------------------------------------------


def test_unknown_project_is_matched_exactly(folder):
    folder.edit("timesheet.txt", "| Supplier quotes | Wave Bench |", "| Supplier quotes | Wave bench |")
    error = only_error(folder)
    assert error.startswith('timesheet.txt — unknown Project value "Wave bench"\n'
                            "  | September 10, 2026 | 0.75 | Supplier quotes | Wave bench |")
    assert error.endswith("(the Active Projects in clients.txt)")


def test_truncated_clients_paste_refuses_every_orphaned_row(folder):
    folder.edit("clients.txt", "| Northside Makers Trust |", "| Northside Makers Trust (old) |")
    folder.edit("clients.txt", "| Tool Wall  |", "|  |")
    errors = errors_of(folder)
    assert len(errors) == 5
    assert all(e.startswith('timesheet.txt — unknown Project value "Tool Wall"') for e in errors)


# ---- Duplicate lines --------------------------------------------------------


def test_double_paste_within_one_batch(folder):
    folder.append("timesheet.txt",
                  "| September 7, 2026 | 2.0 | Lantern concept sketches | Stage Lantern |  |  |  |\n")
    error = only_error(folder)
    assert error.startswith("timesheet.txt — the same line appears more than once\n")
    assert error.count("\n  | September 7, 2026") == 2  # both rows, verbatim
    assert error.endswith("make their Task text differ in Notion.")


def test_line_already_in_the_ledger(folder):
    folder.append("ledger.csv",
                  "work,INV-0001,2026-09-30,Bluegum Theatre Company,2026-09-07,2,"
                  "Lantern concept sketches,Stage Lantern,,PO BT-0001" + LEDGER_TAIL + "\n")
    error = only_error(folder)
    assert error.startswith("timesheet.txt — this line may already be billed, on INV-0001\n"
                            "  | September 7, 2026 | 2 | Lantern concept sketches |")


def test_line_logged_without_an_invoice(folder):
    folder.append("ledger.csv",
                  "work,,2027-01-11,Northside Makers Trust,2026-12-02,7,Tool wall revisions,"
                  "Tool Wall,fixed price," + LEDGER_TAIL + "\n")
    assert only_error(folder).startswith(
        "timesheet.txt — this line may already be logged, as fixed-price work with nothing "
        "charged that month\n  | December 2, 2026 |"
    )


# ---- Week tags --------------------------------------------------------------

NOV_6_WEEK = "| November 6, 2026 | 5 | Diffuser fitting | Stage Lantern | week rate |"


def test_week_tag_on_two_clients(folder):
    folder.edit("timesheet.txt", NOV_6_WEEK, NOV_6_WEEK.replace("Stage Lantern", "Aurora Lamp"))
    assert only_error(folder).startswith(
        'timesheet.txt — week rate tag "Lantern build week — agreed 14 Oct" '
        "is on projects of more than one client"
    )


def test_week_rows_disagreeing_on_a_custom_price(folder):
    folder.edit("timesheet.txt", NOV_6_WEEK + " Lantern build week — agreed 14 Oct |  |",
                NOV_6_WEEK + " Lantern build week — agreed 14 Oct | 2500 |")
    folder.edit("timesheet.txt", "| November 5, 2026 | 6 | Wiring and diffuser fitting | "
                "Stage Lantern  | week rate | Lantern build week — agreed 14 Oct |  |",
                "| November 5, 2026 | 6 | Wiring and diffuser fitting | "
                "Stage Lantern  | week rate | Lantern build week — agreed 14 Oct | 2400 |")
    assert only_error(folder).startswith(
        'timesheet.txt — week rate tag "Lantern build week — agreed 14 Oct" has different '
        "Amounts on its rows"
    )


def test_a_week_crossing_a_month_end_is_accepted(folder):
    folder.edit("timesheet.txt", "| November 2, 2026 | 8 |", "| October 30, 2026 | 8 |")
    _, errors = folder.check()
    assert errors == []


def test_week_tag_already_billed_even_with_other_capitals(folder):
    folder.append("ledger.csv",
                  "charge,INV-0002,2026-10-31,Bluegum Theatre Company,,,,,,PO BT-0001,"
                  "lantern build week — agreed 14 oct,week,1,3000.00,3000.00,AUD,1,2026-10-31,"
                  "TEST,3000.00,base,domestic,0.00\n")
    assert only_error(folder).startswith(
        'timesheet.txt — week rate tag "Lantern build week — agreed 14 Oct" '
        "was already billed, on INV-0002"
    )


def test_week_tag_already_billed_found_on_ledger_work_rows(folder):
    folder.append("ledger.csv",
                  "work,INV-0002,2026-10-31,Bluegum Theatre Company,2026-10-20,8,Earlier build,"
                  "Stage Lantern,week rate,PO BT-0001,Lantern install week — agreed 14 Oct"
                  + "," * 12 + "\n")
    assert only_error(folder).startswith(
        'timesheet.txt — week rate tag "Lantern install week — agreed 14 Oct" '
        "was already billed, on INV-0002"
    )


def test_tags_differing_only_in_capitals(folder):
    folder.edit("timesheet.txt",
                "| 7.5 | Lantern frame build | Stage Lantern | week rate | Lantern build week",
                "| 7.5 | Lantern frame build | Stage Lantern | week rate | Lantern Build Week")
    assert only_error(folder).startswith(
        "timesheet.txt — week rate tags differ only in capitals or spacing"
    )


# ---- Per billed client ------------------------------------------------------


def test_tier_missing_from_rates(folder):
    folder.edit("rates.txt", "| Subsidised | 50% | $60.00 | $400.00 | $1,500.00 |\n", "")
    assert only_error(folder) == (
        'rates.txt — no rates for tier "subsidised", used by Northside Makers Trust'
    )


def test_no_payment_details_for_currency(folder):
    folder.edit("config.txt", "[payment.SEK]", "[payment.EUR]")
    assert only_error(folder) == (
        "config.txt — no [payment.SEK] block, so there is no way to pay the invoice "
        "for Fjordlight AB"
    )


def test_unbilled_client_cannot_stop_the_run(folder):
    folder.edit("config.txt", "[payment.SEK]", "[payment.EUR]")
    text = (folder.path / "timesheet.txt").read_text()
    kept = [line for line in text.splitlines() if "Aurora Lamp" not in line]
    (folder.path / "timesheet.txt").write_text("\n".join(kept) + "\n")
    inputs, errors = folder.check()
    assert errors == []


def test_exchange_rate_must_be_dated_to_the_invoice_date(folder):
    assert only_error(folder, today=date(2027, 1, 12)) == (
        "config.txt — as_at under [currency.SEK] is 2027-01-11 but the invoice date is "
        "2027-01-12. Update rate and as_at to that day's rate (needed for Fjordlight AB)."
    )


# ---- Invoice date -----------------------------------------------------------


def test_work_after_the_invoice_date(folder):
    errors = errors_of(folder, today=date(2026, 12, 8))
    assert errors[0].startswith("timesheet.txt — dated after the invoice date, 2026-12-08\n"
                                "  | December 9, 2026 |")
    assert len(errors) == 2  # and the SEK rate is no longer dated to the invoice date


def test_forgotten_override_is_caught(folder):
    folder.edit("config.txt", "# invoice_date = 2026-11-30", "invoice_date = 2026-11-30")
    folder.edit("config.txt", "as_at = 2027-01-11", "as_at = 2026-11-30")
    errors = errors_of(folder)
    assert len(errors) == 2  # the two December rows
    assert all("(set by invoice_date in config.txt)" in e for e in errors)
