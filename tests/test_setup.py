"""Checks that the environment and fixtures match the brief before any logic exists."""

import csv
import tomllib

import make_invoices


def test_weasyprint_finds_pango_and_writes_a_pdf():
    pdf = make_invoices.weasyprint.HTML(string="<p>ok</p>").write_pdf()
    assert pdf.startswith(b"%PDF")


def test_fixture_ledger_header_matches_the_brief(fixtures_dir):
    with open(fixtures_dir / "ledger.csv", newline="") as f:
        assert next(csv.reader(f)) == make_invoices.LEDGER_COLUMNS


def test_fixture_config_is_toml_without_preview_folder(fixtures_dir):
    config = tomllib.loads((fixtures_dir / "config.txt").read_text())
    assert "paths" not in config
    assert config["invoicing"]["number_prefix"] == "INV-"


def test_fixture_timesheet_uses_week_rate_tag_header(fixtures_dir):
    header = (fixtures_dir / "timesheet.txt").read_text().splitlines()[0]
    assert "| Week rate tag" in header


def test_fixture_clients_end_addresses_with_country(fixtures_dir):
    header = (fixtures_dir / "clients.txt").read_text().splitlines()[0]
    assert "Country" not in header
