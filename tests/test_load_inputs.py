from datetime import date
from decimal import Decimal

import pytest

from conftest import TODAY
from make_invoices import COUNTRIES


def only_error(folder):
    inputs, errors = folder.load()
    assert inputs is None
    assert len(errors) == 1, errors
    return errors[0]


# ---- The fixtures load cleanly ---------------------------------------------


def test_fixtures_load_with_no_errors(folder):
    inputs, errors = folder.load()
    assert errors == []
    assert len(inputs.clients) == 4
    assert len(inputs.entries) == 26
    assert inputs.ledger.work == () and inputs.ledger.charges == ()


def test_config_values(folder):
    config = folder.load()[0].config
    assert config.invoice_date == TODAY and not config.invoice_date_set
    assert config.gst_registered is False
    assert config.home_currency == "AUD"
    assert config.fx["SEK"].rate == Decimal("0.1450")  # exact, not a float
    assert config.fx["SEK"].as_at == date(2026, 12, 11)
    assert set(config.payment) == {"AUD", "SEK"}
    assert config.number_prefix == "INV-" and config.number_padding == 4


def test_clients_are_stripped_and_typed(folder):
    clients = {c.name: c for c in folder.load()[0].clients}
    tide = clients["Tidewater Labs"]
    assert tide.projects == ("Wave Bench", "Tide Clock")
    assert tide.tier == "discounted" and tide.gst_treatment == "domestic"
    fjord = clients["Fjordlight AB"]
    assert fjord.country == "Sweden" and fjord.gst_treatment == "export"
    assert fjord.currency == "SEK" and fjord.reference == "PO FL-0001"


def test_rate_card_reads_block_sizes_from_headers(folder):
    rates = folder.load()[0].rates
    assert rates.block_hours == {"hour": 1, "day": 8, "week": 40}
    assert rates.rates["base"] == {"hour": Decimal("120.00"), "day": Decimal("800.00"),
                                   "week": Decimal("3000.00")}
    assert set(rates.rates) == {"base", "discounted", "subsidised"}  # prose row skipped


def test_timesheet_entries_are_typed(folder):
    entries = folder.load()[0].entries
    first = entries[0]
    assert first.date == date(2026, 9, 7) and first.hours == Decimal("2")
    assert first.project == "Stage Lantern" and first.billing == ""
    week = next(e for e in entries if e.date == date(2026, 11, 4))
    assert week.billing == "week rate"  # typed "Week rate" in the fixture
    assert week.tag == "Lantern build week — agreed 14 Oct"
    deposit = next(e for e in entries if e.amount is not None)
    assert deposit.billing == "fixed price" and deposit.amount == Decimal("1500")


def test_country_names_have_no_commas():
    assert not [c for c in COUNTRIES if "," in c]
    assert {"Australia", "Sweden", "United Kingdom", "United States"} <= COUNTRIES


# ---- config.txt -------------------------------------------------------------


def test_invoice_date_override(folder):
    folder.edit("config.txt", "# invoice_date = 2026-11-30", "invoice_date = 2026-12-10")
    config = folder.load()[0].config
    assert config.invoice_date == date(2026, 12, 10) and config.invoice_date_set


def test_quoted_invoice_date_is_refused(folder):
    folder.edit("config.txt", "# invoice_date = 2026-11-30", 'invoice_date = "2026-12-10"')
    assert only_error(folder) == (
        "config.txt — invoice_date under [invoicing] must be a date like 2026-11-30, without quotes"
    )


def test_missing_setting(folder):
    folder.edit("config.txt", "payment_terms_days = 30", "")
    assert only_error(folder) == "config.txt — missing payment_terms_days under [invoicing]"


def test_abn_required_once_registered(folder):
    folder.edit("config.txt", "gst_registered = false", "gst_registered = true")
    folder.edit("config.txt", 'abn = "00 000 000 000"', "")
    assert only_error(folder) == "config.txt — missing abn under [tax]"


def test_invalid_toml(folder):
    folder.edit("config.txt", "number_padding = 4", "number_padding = ")
    assert only_error(folder).startswith("config.txt — not valid TOML:")


def test_missing_file(folder):
    (folder.path / "rates.txt").unlink()
    assert only_error(folder) == f"rates.txt — not found in {folder.path}"


# ---- clients.txt ------------------------------------------------------------


def test_unknown_tier_matches_the_brief_format(folder):
    folder.edit("clients.txt", "| subsidised | AUD | Tool Wall  |", "| premium | AUD | Tool Wall  |")
    assert only_error(folder) == (
        'clients.txt — unknown Tier value "premium"\n'
        "  | Northside Makers Trust | Casey Example | 30 Placeholder Lane, Coburg VIC 3999, "
        "Australia | casey@northside.example |  | premium | AUD | Tool Wall  |\n"
        "  allowed: base, discounted, subsidised"
    )


def test_tier_and_country_casefold(folder):
    folder.edit("clients.txt", "| subsidised | AUD |", "| Subsidised | AUD |")
    folder.edit("clients.txt", "Coburg VIC 3999, Australia", "Coburg VIC 3999, australia")
    inputs, errors = folder.load()
    assert errors == []
    northside = next(c for c in inputs.clients if c.name == "Northside Makers Trust")
    assert northside.tier == "subsidised" and northside.country == "Australia"


def test_currency_not_in_config(folder):
    folder.edit("clients.txt", "| base | SEK |", "| base | EUR |")
    error = only_error(folder)
    assert error.startswith('clients.txt — unknown Currency value "EUR"')
    assert error.endswith("allowed: AUD, SEK (the currencies in config.txt)")


@pytest.mark.parametrize("address, typed", [
    ("Exempelgatan 1, 111 11 Stockholm, Sverige", "Sverige"),
    ("Exempelgatan 1, 111 11 Stockholm", "111 11 Stockholm"),
    ("Exempelgatan 1, 111 11 Stockholm, Sweden,", ""),
])
def test_address_must_end_with_a_known_country(folder, address, typed):
    folder.edit("clients.txt", "Exempelgatan 1, 111 11 Stockholm, Sweden", address)
    assert only_error(folder).startswith(
        f'clients.txt — unknown country "{typed}" at the end of Address'
    )


def test_address_typed_over_several_lines_in_notion(folder):
    folder.edit("clients.txt", "Exempelgatan 1, 111 11 Stockholm, Sweden",
                "Exempelgatan 1,\n111 11 Stockholm,\nSweden")
    inputs, errors = folder.load()
    assert errors == []
    fjord = next(c for c in inputs.clients if c.name == "Fjordlight AB")
    assert fjord.address == "Exempelgatan 1, 111 11 Stockholm, Sweden"
    assert fjord.country == "Sweden" and fjord.gst_treatment == "export"


def test_duplicate_client(folder):
    folder.edit("clients.txt", "| Fjordlight AB |", "| Bluegum Theatre Company |")
    error = only_error(folder)
    assert error.startswith('clients.txt — client "Bluegum Theatre Company" is listed twice')
    assert error.count("\n  |") == 2


def test_project_under_two_clients(folder):
    folder.edit("clients.txt", "| Aurora Lamp |", "| Aurora Lamp, Stage Lantern |")
    assert only_error(folder).startswith(
        'clients.txt — project "Stage Lantern" is listed under more than one client'
    )


# ---- rates.txt --------------------------------------------------------------


def test_day_header_needs_a_number(folder):
    folder.edit("rates.txt", "Day (8 hr)", "Day")
    assert only_error(folder).startswith('rates.txt — the "Day" header has no number of hours')


def test_half_numeric_rate_row_is_an_error_not_skipped(folder):
    folder.edit("rates.txt", "$90.00", "$9O.00")
    assert only_error(folder).startswith("rates.txt — a rate in this row is not a dollar figure")


def test_unknown_tier_in_rates(folder):
    folder.edit("rates.txt", "| Base |", "| Standard |")
    assert only_error(folder).startswith('rates.txt — unknown Tier value "Standard"')


# ---- timesheet.txt ----------------------------------------------------------


@pytest.mark.parametrize("old, new, problem", [
    ("| September 7, 2026 | 2 |", "| 7/9/2026 | 2 |", 'Date "7/9/2026" is not a date'),
    ("| September 7, 2026 | 2 |", "| September 7, 2026 | 1.1 |",
     'Hours "1.1" is not on the quarter hour'),
    ("| September 7, 2026 | 2 |", "| September 7, 2026 | two |", 'Hours "two" is not a number'),
    ("| September 7, 2026 | 2 |", "| September 7, 2026 | -2 |", 'Hours "-2" is not a number'),
    ("| Lantern concept sketches |", "|  |", "empty Task"),
    ("| Supplier quotes | Wave Bench |  |", "| Supplier quotes | Wave Bench | weekly |",
     'unknown Billing type value "weekly"'),
    ("| Supplier quotes | Wave Bench |  |  |  |", "| Supplier quotes | Wave Bench |  | quotes |  |",
     'tag "quotes" is filled in but Billing type is empty'),
    ("| Supplier quotes | Wave Bench |  |  |  |", "| Supplier quotes | Wave Bench |  |  | 200 |",
     'Amount "200" is filled in but Billing type is empty'),
    ("| Diffuser fitting | Stage Lantern | week rate | Lantern build week — agreed 14 Oct |",
     "| Diffuser fitting | Stage Lantern | week rate | 3000 |", 'tag "3000" is a number'),
    ("| Diffuser fitting | Stage Lantern | week rate | Lantern build week — agreed 14 Oct |",
     "| Diffuser fitting | Stage Lantern | week rate |  |", "week rate row has no tag"),
    ("| Tool wall revisions | Tool Wall | fixed price | Tool wall build (50% payment) |",
     "| Tool wall revisions | Tool Wall | fixed price |  |", "fixed price row has no tag"),
    ("(100% payment) | 2000 |", "(100% payment) | two thousand |",
     'Amount "two thousand" is not an amount'),
])
def test_bad_timesheet_rows(folder, old, new, problem):
    folder.edit("timesheet.txt", old, new)
    assert only_error(folder).startswith(f"timesheet.txt — {problem}\n  |")


def test_zero_hours_and_comma_amounts_are_fine(folder):
    folder.edit("timesheet.txt", "| November 6, 2026 | 5 |", "| November 6, 2026 | 0 |")
    folder.edit("timesheet.txt", "(100% payment) | 2000 |", "(100% payment) | $2,000.00 |")
    entries = folder.load()[0].entries
    assert any(e.hours == 0 for e in entries)
    assert any(e.amount == Decimal("2000.00") for e in entries)


def test_old_layout_without_an_amount_column_is_refused(folder):
    lines = (folder.path / "timesheet.txt").read_text().splitlines()
    old = ["|".join(line.split("|")[:-2]) + "|" for line in lines]  # drop the last column
    (folder.path / "timesheet.txt").write_text("\n".join(old) + "\n")
    assert only_error(folder).startswith('timesheet.txt — no column starts with "Amount"')


def test_hours_settings_default_to_fixed_hidden_week_shown(folder):
    folder.edit("config.txt", "show_fixed_price_hours = false\n", "")
    folder.edit("config.txt", "show_week_rate_hours = true\n", "")
    assert folder.load()[0].config.show_hours == {
        "": True, "week rate": True, "fixed price": False}


def test_setting_added_at_the_end_of_the_file_is_refused(folder):
    # The last section is [payment.SEK], so this line lands there, not under [invoicing].
    folder.edit("config.txt", "show_fixed_price_hours = false\n", "")
    folder.append("config.txt", "\nshow_fixed_price_hours = true\n")
    assert only_error(folder) == (
        "config.txt — show_fixed_price_hours is under [payment.SEK], but it belongs under "
        "[invoicing]. A setting belongs to the [section] above it, so one added at the end "
        "of the file lands in the last section."
    )


def test_unknown_setting_is_refused(folder):
    folder.edit("config.txt", "payment_terms_days = 30", "payment_terms_days = 30\npayment_term = 14")
    assert only_error(folder) == (
        "config.txt — payment_term under [invoicing] is not a setting the script knows")


def test_old_paths_section_is_refused_with_a_reason(folder):
    folder.append("config.txt", '\n[paths]\npreview_folder = "~/invoice-preview"\n')
    assert only_error(folder).startswith("config.txt — [paths] is no longer used")


def test_hours_settings_can_flip(folder):
    folder.edit("config.txt", "show_fixed_price_hours = false", "show_fixed_price_hours = true")
    folder.edit("config.txt", "show_week_rate_hours = true", "show_week_rate_hours = false")
    assert folder.load()[0].config.show_hours == {
        "": True, "week rate": False, "fixed price": True}


def test_every_bad_row_is_reported_in_one_run(folder):
    folder.edit("timesheet.txt", "| September 7, 2026 | 2 |", "| September 7, 2026 | 2.1 |")
    folder.edit("timesheet.txt", "| September 8, 2026 | 1.25 |", "| Sept 8 | 1.25 |")
    folder.edit("clients.txt", "| base | SEK |", "| gold | SEK |")
    _, errors = folder.load()
    assert len(errors) == 3


# ---- ledger.csv -------------------------------------------------------------

WORK_ROW = ("work,INV-0003,2026-08-31,Bluegum Theatre Company,2026-08-20,2,Opening sketch,"
            "Stage Lantern,,PO BT-0001" + "," * 13)
CHARGE_ROW = ("charge,INV-0003,2026-08-31,Bluegum Theatre Company,,,,,,PO BT-0001,"
              "20 Aug — Opening sketch (hourly rate),hour,2,120.00,240.00,AUD,1,2026-08-31,"
              "opening balance,240.00,base,domestic,0.00")


def test_ledger_rows_are_read(folder):
    folder.append("ledger.csv", WORK_ROW + "\n" + CHARGE_ROW + "\n")
    ledger = folder.load()[0].ledger
    assert ledger.work[0].date == date(2026, 8, 20) and ledger.work[0].hours == 2
    assert ledger.charges[0].amount_aud == Decimal("240.00")
    assert ledger.charges[0].description == "20 Aug — Opening sketch (hourly rate)"


def test_missing_ledger_is_a_first_run(folder):
    (folder.path / "ledger.csv").unlink()
    inputs, errors = folder.load()
    assert errors == [] and inputs.ledger.work == ()


def test_ledger_with_wrong_header(folder):
    (folder.path / "ledger.csv").write_text("row_type,invoice_no\n")
    assert only_error(folder).startswith("ledger.csv — the header row doesn't match")


def test_ledger_bad_row_names_its_line(folder):
    folder.append("ledger.csv", WORK_ROW.replace("2026-08-20", "20/08/2026") + "\n")
    assert only_error(folder).startswith("ledger.csv — line 2:")
