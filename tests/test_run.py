"""The run as a whole: the draft preview, the summary, and the commit prompt."""

from datetime import date

import pytest

import make_invoices
from conftest import TODAY
from make_invoices import EXIT_COMMITTED, EXIT_DISCARDED, EXIT_REFUSED, run

LEDGER_CHARGE = ("charge,INV-0001,{day},Bluegum Theatre Company,,,,,,,Earlier work,fixed,1,"
                 "{aud},{aud},AUD,1,{day},opening,{aud},base,unregistered,\n")


def snapshot(path):
    return {p.relative_to(path): p.read_bytes() for p in path.rglob("*") if p.is_file()}


class Prompt:
    """Stands in for the person at the keyboard and for Finder."""

    def __init__(self, answer="no"):
        self.answer, self.preview, self.drafts, self.asked = answer, None, None, False

    def open_folder(self, path):
        self.preview = path

    def ask(self, prompt):
        self.asked = True
        self.drafts = sorted(p.name for p in self.preview.iterdir())
        if isinstance(self.answer, BaseException):
            raise self.answer
        return self.answer


def run_with(folder, prompt, today=TODAY):
    return run(folder.path, today, ask=prompt.ask, open_folder=prompt.open_folder)


@pytest.fixture
def committed(monkeypatch):
    calls = []
    monkeypatch.setattr(make_invoices, "commit", lambda *args: calls.append(args))
    return calls


# ---- The two gates ----------------------------------------------------------


def test_drafts_are_rendered_outside_the_folder_then_deleted(folder):
    prompt = Prompt()
    run_with(folder, prompt)
    assert prompt.drafts == [f"INV-000{n}.pdf" for n in range(1, 8)] + ["summary.csv"]
    assert folder.path not in prompt.preview.parents
    assert not prompt.preview.exists()


def test_anything_but_commit_discards_and_writes_nothing(folder, committed):
    before = snapshot(folder.path)
    prompt = Prompt("yes")
    assert run_with(folder, prompt) == EXIT_DISCARDED
    assert committed == []
    assert snapshot(folder.path) == before


@pytest.mark.parametrize("answer", [EOFError(), KeyboardInterrupt()])
def test_closing_the_prompt_discards(folder, committed, answer):
    prompt = Prompt(answer)
    assert run_with(folder, prompt) == EXIT_DISCARDED
    assert committed == [] and not prompt.preview.exists()


def test_commit_proceeds_and_preview_is_still_deleted(folder, committed):
    prompt = Prompt("  commit \n")
    assert run_with(folder, prompt) == EXIT_COMMITTED
    assert len(committed) == 1
    assert not prompt.preview.exists()


def test_refused_run_renders_nothing_and_asks_nothing(folder, monkeypatch, capsys):
    folder.edit("timesheet.txt", "| Supplier quotes | Wave Bench |", "| Supplier quotes | Wave bench |")
    monkeypatch.setattr(make_invoices.tempfile, "mkdtemp",
                        lambda **_: pytest.fail("a preview folder was made"))
    prompt = Prompt()
    assert run_with(folder, prompt) == EXIT_REFUSED
    assert not prompt.asked
    assert "Fix it in Notion and paste the table again." in capsys.readouterr().err


def test_a_crash_while_rendering_still_deletes_the_preview(folder, monkeypatch):
    made = []
    real_mkdtemp = make_invoices.tempfile.mkdtemp
    monkeypatch.setattr(make_invoices.tempfile, "mkdtemp",
                        lambda **kw: made.append(real_mkdtemp(**kw)) or made[-1])
    monkeypatch.setattr(make_invoices, "write_pdf",
                        lambda *a: (_ for _ in ()).throw(OSError("disk full")))
    with pytest.raises(OSError):
        run_with(folder, Prompt())
    assert made and not make_invoices.Path(made[0]).exists()


def test_empty_timesheet_has_nothing_to_do(folder, capsys):
    header = (folder.path / "timesheet.txt").read_text().splitlines()[:2]
    (folder.path / "timesheet.txt").write_text("\n".join(header) + "\n")
    prompt = Prompt()
    assert run_with(folder, prompt) == EXIT_COMMITTED
    assert not prompt.asked
    assert "Nothing to do" in capsys.readouterr().out


# ---- The summary ------------------------------------------------------------


def test_summary_for_the_fixtures(folder, capsys):
    prompt = Prompt()
    run_with(folder, prompt)
    out = capsys.readouterr().out
    assert out.startswith("Invoice date  11 December 2026\n\n")
    assert "  INV-0003  Nov 2026  Bluegum Theatre Company  AUD      7,850.00\n" in out
    assert "  INV-0004  Nov 2026  Fjordlight AB            SEK      9,448.30\n" in out
    assert "\nBooked weeks\n  ! Lantern build week" in out
    assert ("\nFixed-price hours with no charge\n"
            "  Northside Makers Trust  23 Nov      6h  Tool wall layout and CAD\n"
            "  Northside Makers Trust   2 Dec      7h  Tool wall revisions\n") in out
    assert "Turnover, last 12 months: A$14,302.50 of A$75,000, including this run\n" in out
    assert "  ! " not in out.split("Turnover")[1]  # no threshold warning
    assert f"The draft invoices and summary.csv are open in Finder: {prompt.preview}\n" in out
    assert out.endswith("Discarded. Nothing was written.\n")


def test_finder_line_matches_what_is_in_the_folder(folder, capsys):
    header = (folder.path / "timesheet.txt").read_text().splitlines()[:2]
    one = "| December 10, 2026 | 2 | Clock hands | Tide Clock |  |  |"
    none = "| December 10, 2026 | 2 | Tool wall touch-up | Tool Wall | fixed price |  |"
    for row, expected in [(one, "The draft invoice and summary.csv are"),
                          (none, "summary.csv is")]:
        (folder.path / "timesheet.txt").write_text("\n".join(header + [row]) + "\n")
        prompt = Prompt()
        run_with(folder, prompt)
        assert f"{expected} open in Finder: {prompt.preview}\n" in capsys.readouterr().out


def test_override_date_is_flagged(folder, capsys):
    folder.edit("config.txt", "# invoice_date = 2026-11-30", "invoice_date = 2026-12-11")
    run_with(folder, Prompt(), today=date(2027, 1, 5))
    assert capsys.readouterr().out.startswith(
        "Invoice date  11 December 2026 (set in config.txt)\n")


def test_sections_with_nothing_in_them_are_left_out(folder, capsys):
    text = (folder.path / "timesheet.txt").read_text()
    kept = [l for l in text.splitlines() if "week rate" not in l.casefold()
            and "fixed price" not in l.casefold()]
    (folder.path / "timesheet.txt").write_text("\n".join(kept) + "\n")
    run_with(folder, Prompt())
    out = capsys.readouterr().out
    assert "Booked weeks" not in out and "Fixed-price hours" not in out


# ---- Turnover ---------------------------------------------------------------


def turnover_line(folder, capsys, aud, day="2026-06-01"):
    folder.append("ledger.csv", LEDGER_CHARGE.format(day=day, aud=aud))
    run_with(folder, Prompt())
    return capsys.readouterr().out.split("Turnover, ")[1].split("\n\nThe draft")[0]


def test_turnover_warns_from_80_percent(folder, capsys):
    line = turnover_line(folder, capsys, "46000.00")
    assert line == ("last 12 months: A$60,302.50 of A$75,000, including this run\n"
                    "  ! Past 80% of the GST registration threshold.")


def test_turnover_over_the_threshold(folder, capsys):
    line = turnover_line(folder, capsys, "61000.00")
    assert "Over the GST threshold. Registration is due within 21 days" in line


def test_turnover_window_is_twelve_months(folder, capsys):
    # Exactly a year before the invoice date falls outside the window.
    line = turnover_line(folder, capsys, "61000.00", day="2025-12-11")
    assert line.startswith("last 12 months: A$14,302.50 ")


def test_no_threshold_warning_once_registered(folder, capsys):
    folder.edit("config.txt", "gst_registered = false", "gst_registered = true")
    line = turnover_line(folder, capsys, "61000.00")
    assert "!" not in line
