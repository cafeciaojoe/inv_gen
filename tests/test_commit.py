"""Typing commit: final PDFs, the ledger append, summary.csv, and every way it can fail."""

import csv

import pytest

import make_invoices
from conftest import TODAY
from make_invoices import EXIT_COMMITTED, EXIT_REFUSED, run

NUMBERS = [f"INV-000{n}" for n in range(1, 8)]
PDFS = {
    "invoices/2026-09": ["INV-0001.pdf", "INV-0002.pdf"],
    "invoices/2026-11": ["INV-0003.pdf", "INV-0004.pdf", "INV-0005.pdf", "INV-0006.pdf"],
    "invoices/2026-12": ["INV-0007.pdf"],
}


def commit_run(folder, answer="commit", today=TODAY, during_prompt=None, preview=None):
    """Run with `answer` typed at the prompt. `preview`, a dict, gets the preview's files."""
    opened = []

    def ask(prompt):
        if preview is not None:
            preview.update({p.name: p.read_bytes() for p in opened[0].iterdir()})
        if during_prompt:
            during_prompt()
        return answer
    return run(folder.path, today, ask=ask, open_folder=opened.append)


def ledger(folder):
    with open(folder.path / "ledger.csv", newline="") as f:
        return list(csv.DictReader(f))


def pdfs_on_disk(folder):
    root = folder.path / "invoices"
    if not root.exists():
        return {}
    return {str(d.relative_to(folder.path)): sorted(p.name for p in d.iterdir())
            for d in sorted(root.iterdir())}


# ---- A clean commit ---------------------------------------------------------


def test_commit_writes_final_pdfs_by_work_month(folder):
    assert commit_run(folder) == EXIT_COMMITTED
    assert pdfs_on_disk(folder) == PDFS
    pdf = (folder.path / "invoices/2026-11/INV-0003.pdf").read_bytes()
    assert pdf.startswith(b"%PDF")


def test_final_pdfs_are_rerendered_without_the_draft_flag(folder, monkeypatch):
    flags = []
    real = make_invoices.render_pdf
    monkeypatch.setattr(make_invoices, "render_pdf",
                        lambda *a, **kw: flags.append(kw.get("draft", a[-1])) or real(*a, **kw))
    commit_run(folder)
    assert flags == [True] * 7 + [False] * 7


def test_ledger_rows(folder):
    commit_run(folder)
    rows = ledger(folder)
    assert len(rows) == 26 + 19  # every timesheet row, plus every invoice line
    assert [r["row_type"] for r in rows[:6]] == ["work", "work", "charge", "charge", "work", "work"]

    work = rows[0]
    assert {k: work[k] for k in ("invoice_no", "invoice_date", "client", "date", "hours", "task",
                                 "project", "billing_type", "ref", "amount")} == {
        "invoice_no": "INV-0001", "invoice_date": "2026-12-11",
        "client": "Bluegum Theatre Company", "date": "2026-09-07", "hours": "2",
        "task": "Lantern concept sketches", "project": "Stage Lantern", "billing_type": "",
        "ref": "PO BT-0001", "amount": ""}

    sek = next(r for r in rows if r["description"] == "20 Nov — Shade test print (hourly rate)")
    assert {k: sek[k] for k in ("unit", "qty", "rate", "amount", "currency", "fx_rate", "fx_date",
                                "fx_source", "amount_aud", "tier", "gst_treatment",
                                "gst_amount")} == {
        "unit": "hour", "qty": "1.5", "rate": "827.59", "amount": "1241.39", "currency": "SEK",
        "fx_rate": "0.1450", "fx_date": "2026-12-11",
        "fx_source": "TEST DATA — not a real rate source", "amount_aud": "180.00",
        "tier": "base", "gst_treatment": "unregistered", "gst_amount": ""}

    week = next(r for r in rows if r["unit"] == "week")
    assert (week["description"], week["rate"], week["fx_rate"], week["fx_source"]) == (
        "Lantern build week — agreed 14 Oct", "3000.00", "1", "")
    fixed = next(r for r in rows if r["unit"] == "fixed")
    assert (fixed["rate"], fixed["amount"]) == ("1500.00", "1500.00")


def test_fixed_price_hours_are_kept_in_the_ledger(folder):
    commit_run(folder)
    tasks = [r["task"] for r in ledger(folder) if r["invoice_no"] == "INV-0005"]
    assert "Tool wall layout and CAD" in tasks  # 6 hours, never on the invoice


def test_gst_columns_once_registered(folder):
    folder.edit("config.txt", "gst_registered = false", "gst_registered = true")
    commit_run(folder)
    rows = [r for r in ledger(folder) if r["row_type"] == "charge"]
    dom = [r for r in rows if r["invoice_no"] == "INV-0003"]
    assert {r["gst_treatment"] for r in dom} == {"domestic"}
    assert [r["gst_amount"] for r in dom] == ["300.00", "48.00", "300.00", "80.00", "18.00", "39.00"]
    exp = [r for r in rows if r["invoice_no"] == "INV-0004"]
    assert {(r["gst_treatment"], r["gst_amount"]) for r in exp} == {("export", "0.00")}


def test_summary_csv(folder):
    commit_run(folder)
    assert (folder.path / "summary.csv").read_text() == (
        "work_month,client,invoice,invoiced,hours,AUD,SEK,total_aud\n"
        "2026-09,Bluegum Theatre Company,INV-0001,2026-12,3.25,390.00,,390.00\n"
        "2026-09,Tidewater Labs,INV-0002,2026-12,9.25,712.50,,712.50\n"
        "2026-09,Total,,,12.5,1102.50,,1102.50\n"
        "2026-11,Bluegum Theatre Company,INV-0003,2026-12,94.75,7850.00,,7850.00\n"
        "2026-11,Fjordlight AB,INV-0004,2026-12,12.75,,9448.30,1370.00\n"
        "2026-11,Northside Makers Trust,INV-0005,2026-12,14.5,1800.00,,1800.00\n"
        "2026-11,Tidewater Labs,INV-0006,2026-12,2,180.00,,180.00\n"
        "2026-11,Total,,,124,9830.00,9448.30,11200.00\n"
        "2026-12,Northside Makers Trust,INV-0007,2026-12,11.25,2000.00,,2000.00\n"
        "2026-12,Total,,,11.25,2000.00,,2000.00\n"
        "\n"
        ',"Turnover, 12 months to 2026-12-11",,,,,,14302.50\n'
    )


def test_summary_has_a_column_only_for_currencies_invoiced(folder):
    text = (folder.path / "timesheet.txt").read_text()
    kept = [line for line in text.splitlines() if "Aurora Lamp" not in line]
    (folder.path / "timesheet.txt").write_text("\n".join(kept) + "\n")
    commit_run(folder)
    summary = (folder.path / "summary.csv").read_text().splitlines()
    assert summary[0] == "work_month,client,invoice,invoiced,hours,AUD,total_aud"
    assert summary[-1] == ',"Turnover, 12 months to 2026-12-11",,,,,12932.50'


def test_commit_prints_what_it_kept(folder, capsys):
    commit_run(folder)
    out = capsys.readouterr().out
    assert "Committed 7 invoices:\n  invoices/2026-09/INV-0001.pdf\n" in out
    assert out.endswith("ledger.csv: 45 rows added.\n"
                        "summary.csv: replaced with the one in the preview.\n")


def test_committed_summary_is_the_one_in_the_preview(folder):
    preview = {}
    commit_run(folder, preview=preview)
    assert preview["summary.csv"] == (folder.path / "summary.csv").read_bytes()


def test_discarding_leaves_the_old_summary(folder):
    commit_run(folder)
    before = (folder.path / "summary.csv").read_bytes()
    header = (folder.path / "timesheet.txt").read_text().splitlines()[:2]
    (folder.path / "timesheet.txt").write_text("\n".join(header + [
        "| December 10, 2026 | 2 | Clock hands | Tide Clock |  |  |"]) + "\n")
    preview = {}
    commit_run(folder, answer="no", preview=preview)
    assert preview["summary.csv"] != before  # the preview showed the would-be summary
    assert (folder.path / "summary.csv").read_bytes() == before


# ---- The ledger is append-only ----------------------------------------------


def test_first_run_creates_the_ledger(folder):
    (folder.path / "ledger.csv").unlink()
    commit_run(folder)
    header = (folder.path / "ledger.csv").read_text().splitlines()[0]
    assert header == ",".join(make_invoices.LEDGER_COLUMNS)


def test_existing_rows_are_kept_byte_for_byte(folder):
    opening = ("work,INV-0003,2026-08-31,Bluegum Theatre Company,2026-08-20,2,Opening sketch,"
               "Stage Lantern,,PO BT-0001" + "," * 13)  # hand-entered, no final newline
    folder.append("ledger.csv", opening)
    before = (folder.path / "ledger.csv").read_bytes()
    commit_run(folder)
    after = (folder.path / "ledger.csv").read_bytes()
    assert after.startswith(before + b"\n")
    assert pdfs_on_disk(folder)["invoices/2026-09"] == ["INV-0004.pdf", "INV-0005.pdf"]


def test_running_the_same_timesheet_again_is_refused(folder, capsys):
    commit_run(folder)
    before = (folder.path / "ledger.csv").read_bytes()
    capsys.readouterr()
    assert commit_run(folder) == EXIT_REFUSED
    err = capsys.readouterr().err
    assert "this line may already be billed, on INV-0001" in err
    assert "was already billed, on INV-0003" in err  # the week tags too
    assert (folder.path / "ledger.csv").read_bytes() == before


def test_next_month_continues_the_numbering(folder):
    commit_run(folder)
    header = (folder.path / "timesheet.txt").read_text().splitlines()[:2]
    (folder.path / "timesheet.txt").write_text("\n".join(header + [
        "| December 10, 2026 | 2 | Clock hands | Tide Clock |  |  |"]) + "\n")
    assert commit_run(folder) == EXIT_COMMITTED
    assert pdfs_on_disk(folder)["invoices/2026-12"] == ["INV-0007.pdf", "INV-0008.pdf"]
    summary = (folder.path / "summary.csv").read_text()
    assert "2026-12,Tidewater Labs,INV-0008,2026-12,2,180.00,,180.00\n" in summary


def test_month_with_nothing_charged_is_logged_without_an_invoice(folder):
    folder.edit("timesheet.txt", "| fixed price | 2000 |", "| fixed price |  |")
    commit_run(folder)
    logged = [r for r in ledger(folder) if r["invoice_no"] == ""]
    assert [(r["date"], r["hours"], r["invoice_date"]) for r in logged] == [
        ("2026-12-02", "7", "2026-12-11"), ("2026-12-09", "4.25", "2026-12-11")]
    summary = (folder.path / "summary.csv").read_text()
    assert "2026-12,Northside Makers Trust,,,11.25,,,0.00\n" in summary


# ---- Refused before anything is written -------------------------------------


def test_existing_pdf_refuses_the_whole_commit(folder, capsys):
    clash = folder.path / "invoices/2026-11/INV-0003.pdf"
    clash.parent.mkdir(parents=True)
    clash.write_bytes(b"sent last week")
    before = (folder.path / "ledger.csv").read_bytes()
    assert commit_run(folder) == EXIT_REFUSED
    assert pdfs_on_disk(folder) == {"invoices/2026-11": ["INV-0003.pdf"]}
    assert clash.read_bytes() == b"sent last week"
    assert (folder.path / "ledger.csv").read_bytes() == before
    assert not (folder.path / "summary.csv").exists()
    assert "invoices/2026-11/INV-0003.pdf — already exists" in capsys.readouterr().err


def test_ledger_edited_while_drafts_were_open(folder, capsys):
    assert commit_run(folder, during_prompt=lambda: folder.append("ledger.csv", "\n")) == EXIT_REFUSED
    assert pdfs_on_disk(folder) == {}
    assert "ledger.csv — changed while the drafts were open" in capsys.readouterr().err


# ---- Failing partway --------------------------------------------------------


@pytest.mark.parametrize("failure", [OSError("disk full"), KeyboardInterrupt()])
def test_failure_before_the_ledger_is_replaced_removes_the_pdfs(folder, monkeypatch, failure):
    def fail(path, data):
        raise failure
    monkeypatch.setattr(make_invoices, "replace_atomically", fail)
    before = (folder.path / "ledger.csv").read_bytes()
    with pytest.raises(type(failure)):
        commit_run(folder)
    assert not (folder.path / "invoices").exists()
    assert (folder.path / "ledger.csv").read_bytes() == before
    assert not (folder.path / "summary.csv").exists()
    assert not [p.name for p in folder.path.iterdir() if p.name.endswith(".tmp")]


def test_a_summary_problem_stops_the_run_before_the_prompt(folder, monkeypatch):
    monkeypatch.setattr(make_invoices, "summary_rows",
                        lambda *a: (_ for _ in ()).throw(ValueError("odd row")))
    before = {p.name: p.read_bytes() for p in folder.path.iterdir() if p.is_file()}
    asked = []
    with pytest.raises(ValueError):
        commit_run(folder, during_prompt=lambda: asked.append(True))
    assert asked == []
    assert {p.name: p.read_bytes() for p in folder.path.iterdir() if p.is_file()} == before


def test_the_last_rename_failing_keeps_the_commit(folder, monkeypatch, capsys):
    real_replace = make_invoices.os.replace

    def replace(src, dst):
        if str(dst).endswith("summary.csv"):
            raise OSError("pCloud hiccup")
        real_replace(src, dst)
    monkeypatch.setattr(make_invoices.os, "replace", replace)
    assert commit_run(folder) == EXIT_COMMITTED
    assert len(ledger(folder)) == 45 and pdfs_on_disk(folder) == PDFS
    assert "summary.csv could not be replaced (pCloud hiccup)" in capsys.readouterr().err
    assert not [p.name for p in folder.path.iterdir() if p.name.endswith(".tmp")]


def test_no_temporary_files_left_behind(folder):
    commit_run(folder)
    assert not [p.name for p in folder.path.iterdir() if p.name.endswith(".tmp")]
