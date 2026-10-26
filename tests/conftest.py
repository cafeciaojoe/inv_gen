import shutil
import sys
from datetime import date
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))

import make_invoices  # noqa: E402  (needs the path above)

FIXTURES = Path(__file__).resolve().parent / "fixtures"
TODAY = date(2027, 1, 11)  # after the fixtures' last row, and the SEK as_at date


@pytest.fixture
def fixtures_dir() -> Path:
    return FIXTURES


@pytest.fixture
def folder(tmp_path):
    """A copy of the fixtures that a test can break, with ways to load it."""
    for f in FIXTURES.iterdir():
        shutil.copy(f, tmp_path / f.name)
    shutil.copytree(REPO / "template", tmp_path / "template")

    class Folder:
        path = tmp_path

        def edit(self, name, old, new):
            text = (tmp_path / name).read_text()
            assert old in text, f"{old!r} not in {name}"
            (tmp_path / name).write_text(text.replace(old, new))

        def append(self, name, text):
            with open(tmp_path / name, "a") as f:
                f.write(text)

        def load(self, today=TODAY):
            errors = []
            return make_invoices.load_inputs(tmp_path, today, errors), errors

        def check(self, today=TODAY):
            errors = []
            return make_invoices.check_inputs(tmp_path, today, errors), errors

    return Folder()
