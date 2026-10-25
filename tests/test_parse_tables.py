from make_invoices import parse_table, split_row


def parse(text):
    errors = []
    table = parse_table("timesheet.txt", text, errors)
    return table, errors


def test_cells_are_stripped_and_separator_row_dropped():
    table, errors = parse(
        "| Date | Project |\n"
        "| --- | --- |\n"
        "| November 2, 2026  | Stage Lantern  |\n"
    )
    assert errors == []
    assert table.header == ("Date", "Project")
    assert [r.cells for r in table.rows] == [("November 2, 2026", "Stage Lantern")]


def test_row_keeps_its_pasted_text_for_error_messages():
    table, _ = parse("| A | B |\n| --- | --- |\n| x  | y |   \n")
    assert table.rows[0].line == "| x  | y |"


def test_empty_cells_and_em_dash_survive():
    table, errors = parse(
        "| Billing type | Week rate tag |\n| --- | --- |\n"
        "| week rate | Lantern build week — agreed 14 Oct |\n"
        "|  |  |\n"
    )
    assert errors == []
    assert table.rows[0].cells[1] == "Lantern build week — agreed 14 Oct"
    assert table.rows[1].cells == ("", "")


def test_escaped_pipe_stays_inside_its_cell():
    assert split_row(r"| a \| b | c |") == ["a | b", "c"]


def test_blank_lines_are_ignored():
    table, errors = parse("\n| A |\n| --- |\n\n| 1 |\n\n")
    assert errors == []
    assert len(table.rows) == 1


def test_column_found_by_prefix_ignoring_case():
    table, _ = parse(
        "| Date | Billing type (Week rate / Fixed Price) | Week rate tag / Fixed price amount |\n"
        "| --- | --- | --- |\n"
    )
    errors = []
    assert table.column("Billing type", errors) == 1
    assert table.column("week rate tag", errors) == 2
    assert errors == []


def test_missing_column_is_an_error_echoing_the_header():
    table, _ = parse("| Date | Hours |\n| --- | --- |\n")
    errors = []
    assert table.column("Billing type", errors) is None
    assert errors == ['timesheet.txt — no column starts with "Billing type"\n  | Date | Hours |']


def test_ambiguous_prefix_is_an_error():
    table, _ = parse("| Week rate tag | Week rate tag notes |\n| --- | --- |\n")
    errors = []
    assert table.column("Week rate tag", errors) is None
    assert "more than one column" in errors[0]


def test_wrong_cell_count_is_an_error_and_row_is_left_out():
    table, errors = parse("| A | B |\n| --- | --- |\n| 1 | 2 |\n| 3 |\n")
    assert len(table.rows) == 1
    assert errors == ["timesheet.txt — row has 1 cells but the header has 2\n  | 3 |"]


def test_stray_text_is_an_error():
    table, errors = parse("| A |\n| --- |\nsome note\n| 1 |\n")
    assert len(table.rows) == 1
    assert errors == ["timesheet.txt — this line is not a table row\n  some note"]


def test_line_breaks_inside_a_cell_are_joined():
    table, errors = parse(
        "| Client | Address | Tier |\n| --- | --- | --- |\n"
        "| Example Co | 16 Example Street, Town,\n"
        "VIC 3999,\n"
        "\n"
        "Australia | base |\n"
        "| Other Co | 1 Road, Australia | base |\n"
    )
    assert errors == []
    assert [r.cells for r in table.rows] == [
        ("Example Co", "16 Example Street, Town, VIC 3999, Australia", "base"),
        ("Other Co", "1 Road, Australia", "base"),
    ]
    assert table.rows[0].line == ("| Example Co | 16 Example Street, Town, VIC 3999, "
                                  "Australia | base |")


def test_row_that_never_closes_is_an_error():
    _, errors = parse("| A | B |\n| --- | --- |\n| 1 | 2 |\n| 3 | 4\n")
    assert errors == ["timesheet.txt — this row never closes with a |\n  | 3 | 4"]


def test_stray_text_after_a_closed_row_is_still_refused():
    table, errors = parse("| A |\n| --- |\n| 1 |\nsome note\n")
    assert len(table.rows) == 1
    assert errors == ["timesheet.txt — this line is not a table row\n  some note"]


def test_empty_file_is_an_error():
    table, errors = parse("\n  \n")
    assert table is None
    assert errors == ["timesheet.txt — no table found. Paste the table from Notion."]


def test_repeated_column_name_is_an_error():
    _, errors = parse("| Date | Date |\n| --- | --- |\n")
    assert errors == ['timesheet.txt — repeated column name "Date"\n  | Date | Date |']


def test_all_three_fixtures_parse_cleanly(fixtures_dir):
    counts = {}
    for name in ("clients.txt", "rates.txt", "timesheet.txt"):
        errors = []
        table = parse_table(name, (fixtures_dir / name).read_text(), errors)
        assert errors == [], name
        counts[name] = len(table.rows)
    assert counts == {"clients.txt": 4, "rates.txt": 4, "timesheet.txt": 26}
