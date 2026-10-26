import re
import shutil
from datetime import date

import pytest

from make_invoices import compute, render_html, template_env, write_pdf


@pytest.fixture
def render(folder):
    """render(number, draft=False) -> the invoice's HTML, from the folder as it is now."""
    def go(number, draft=False):
        inputs, errors = folder.check()
        assert errors == []
        invoice = next(i for i in compute(inputs).invoices if i.number == number)
        return render_html(template_env(folder.path), invoice, inputs.config, draft)
    return go


def register(folder):
    folder.edit("config.txt", "gst_registered = false", "gst_registered = true")


def worklog(html):
    return html.split('class="worklog"', 1)[1] if 'class="worklog"' in html else ""


# ---- Heading and draft marking ----------------------------------------------


def test_unregistered_final_is_a_plain_invoice(render):
    html = render("INV-0003")
    assert ">Invoice</h2>" in html
    assert "Tax Invoice" not in html and "GST" not in html and "ABN" not in html
    assert "DRAFT" not in html and "Preview only" not in html


def test_draft_is_marked_three_ways(render):
    html = render("INV-0003", draft=True)
    assert '<div class="watermark" aria-hidden="true">DRAFT</div>' in html
    assert '<h2 class="draft">Draft Invoice</h2>' in html
    assert "Preview only. Not a valid tax invoice and not issued." in html


def test_draft_never_says_tax_invoice_even_when_registered(folder, render):
    register(folder)
    assert "Tax Invoice" not in render("INV-0003", draft=True)
    assert ">Tax Invoice</h2>" in render("INV-0003")


# ---- GST --------------------------------------------------------------------


def test_registered_domestic_shows_abn_and_gst(folder, render):
    register(folder)
    html = render("INV-0003")
    assert "ABN 00 000 000 000" in html
    assert "GST (10%)" in html and "785.00" in html and "8,635.00" in html


def test_registered_export_is_gst_free(folder, render):
    register(folder)
    html = render("INV-0004")
    assert "GST (GST-free export)" in html
    assert "GST-free as an export of services" in html
    assert "GST (10%)" not in html


# ---- Content ----------------------------------------------------------------


def test_bill_to_and_reference(render):
    html = render("INV-0004")
    assert "Exempelgatan 1<br>111 11 Stockholm<br>Sweden" in html
    assert "c/o Kim Exempel<br>" in html
    assert "<th>Your reference</th><td>PO FL-0001</td>" in html
    assert "Your reference" not in render("INV-0005")  # Northside has none


def test_business_address_keeps_its_lines(render):
    assert "1 Example Street<br>Exampleton VIC 3999<br>Australia" in render("INV-0001")


def test_amounts_and_currency(render):
    html = render("INV-0004")
    assert "5,517.24" in html and "Total SEK" in html and "9,448.29" in html
    assert "<th>Issued</th><td>11 January 2027</td>" in html
    assert "<th>Due</th><td>10 February 2027</td>" in html
    assert "<th>Period</th><td>November 2026</td>" in html


def test_payment_block_matches_currency(render):
    sek, aud = render("INV-0004"), render("INV-0003")
    assert "SE00 0000 0000 0000 0000 0000" in sek and "BSB" not in sek
    assert "1 Example Square<br>000 00 Exampleville<br>Sweden" in sek
    assert "000-000" in aud and "IBAN" not in aud
    assert "Please quote the invoice number as the payment reference." in aud


def test_cost_breakdown_has_project_and_charge_columns(render):
    html = render("INV-0003")
    assert ('<td class="project">Stage Lantern</td>\n'
            '        <td class="desc">Week rate: Lantern build week — agreed 14 Oct</td>\n'
            '        <td class="num">1 week</td>') in html
    assert '<td class="desc">Daily</td>\n        <td class="num">1 day</td>' in html
    assert '<td class="desc">Hourly</td>\n        <td class="num">8.75 h</td>' in html
    assert "(hourly rate)" not in html and "Lantern rework after preview</td>" in worklog(html)


def test_fixed_price_line_has_no_qty_or_rate(render):
    html = render("INV-0007")
    assert ('<td class="desc">Fixed price: Tool wall build (100% payment)</td>\n'
            '        <td class="num"></td>\n'
            '        <td class="num"></td>\n'
            '        <td class="num">2,000.00</td>') in html


def test_work_log_shows_fixed_price_rows_without_their_hours(render):
    log = worklog(render("INV-0005"))
    assert "Tool wall layout and CAD" in log and "Tool wall first panels" in log
    assert log.count('<td class="num">fixed price</td>') == 2
    assert "Total hours" in log and '<td class="num">5</td>' in log


def test_work_log_without_any_hours_shown_has_no_total(render):
    log = worklog(render("INV-0007"))
    assert log.count('<td class="num">fixed price</td>') == 2
    assert "Total hours" not in log


def test_hidden_week_rate_hours(folder, render):
    folder.edit("config.txt", "show_week_rate_hours = true", "show_week_rate_hours = false")
    log = worklog(render("INV-0003"))
    assert log.count('<td class="num">week rate</td>') == 9
    assert '<td class="num">16.75</td>' in log  # hourly hours only


def test_task_text_is_escaped(folder, render):
    folder.edit("timesheet.txt", "| Kick-off call |", "| R&D <sketch> |")
    html = render("INV-0001")
    assert "R&amp;D &lt;sketch&gt;" in html and "<sketch>" not in html


# ---- Files ------------------------------------------------------------------


def test_writes_a_pdf_and_refuses_to_overwrite(folder, tmp_path):
    inputs, _ = folder.check()
    invoice = compute(inputs).invoices[0]
    env = template_env(folder.path)
    path = tmp_path / "out" / "INV-0001.pdf"
    write_pdf(folder.path, env, invoice, inputs.config, True, path)
    first = path.read_bytes()
    assert first.startswith(b"%PDF")
    with pytest.raises(FileExistsError):
        write_pdf(folder.path, env, invoice, inputs.config, False, path)
    assert path.read_bytes() == first


def test_missing_template_is_refused_before_anything_runs(folder):
    shutil.rmtree(folder.path / "template")
    _, errors = folder.check()
    assert errors[0].startswith("template/invoice.html — not found")
    assert len(errors) == 3


# ---- Rate cards -------------------------------------------------------------


@pytest.fixture
def cards(folder):
    from make_invoices import rate_card_pages
    def go():
        inputs, errors = folder.check()
        assert errors == []
        return rate_card_pages(folder.path, inputs, date(2026, 10, 26))
    return go


def tiers_on(html):
    return re.findall(r'<td class="desc">([^<]+)</td>', html)


def test_one_card_per_tier_showing_it_and_every_dearer_one(cards):
    pages = cards()
    assert list(pages) == ["Rate card_I.pdf", "Rate card_II.pdf",
                           "Rate card_III.pdf"]
    assert tiers_on(pages["Rate card_I.pdf"]) == ["Base"]
    assert tiers_on(pages["Rate card_II.pdf"]) == ["Base", "Discounted"]
    assert tiers_on(pages["Rate card_III.pdf"]) == ["Base", "Discounted", "Subsidised"]


def test_card_prints_the_rates_and_headers_as_written(cards):
    html = cards()["Rate card_II.pdf"]
    assert "<th class=\"num\">Day (8 hr)</th>" in html and "Week (40 hr)" in html
    assert "<th class=\"num\">Discount</th>" in html and "<td class=\"num\">25%</td>" in html
    assert "2,250.00" in html and "600.00" in html and "90.00" in html
    assert "<th>Rates as at</th><td>26 October 2026</td>" in html
    assert "<td>AUD</td>" in html and "GST" not in html


def test_base_card_leaves_out_the_discount_column(cards):
    html = cards()["Rate card_I.pdf"]
    assert "Discount" not in html and "3,000.00" in html


def test_card_carries_the_explanatory_row(cards):
    html = cards()["Rate card_III.pdf"]
    assert "<h3>How it&#39;s charged</h3>" in html  # the apostrophe, escaped
    assert "<p>Hours are logged to the quarter hour. Eight or more hours" in html


def test_card_says_excluding_gst_once_registered(folder, cards):
    folder.edit("config.txt", "gst_registered = false", "gst_registered = true")
    html = cards()["Rate card_I.pdf"]
    assert "<td>AUD, excluding GST</td>" in html and "ABN 00 000 000 000" in html

