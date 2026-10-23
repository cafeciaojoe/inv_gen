"""The script run as Joe runs it: its own process, its own folder, real stdin.

The other tests call the code in-process. These copy the dragged-in files
and the fixtures into a fresh folder (with a space in its name, as pCloud
paths often have), start make_invoices.py from somewhere else, and type at
it. A stand-in `open` on PATH records what Finder would have been asked to
open, without opening anything.
"""

import os
import pty
import select
import shutil
import signal
import subprocess
import sys
import time

import pytest

from conftest import FIXTURES, REPO


@pytest.fixture
def setup(tmp_path):
    folder = tmp_path / "invoicing folder"
    folder.mkdir()
    for name in ("make_invoices.py", "Make invoices.command"):
        shutil.copy2(REPO / name, folder / name)  # copy2 keeps the launcher runnable
    shutil.copytree(REPO / "template", folder / "template")
    for f in FIXTURES.iterdir():
        shutil.copy(f, folder / f.name)
    config = folder / "config.txt"
    config.write_text(config.read_text().replace("# invoice_date = 2026-11-30",
                                                 "invoice_date = 2026-12-11"))
    fake_bin = tmp_path / "bin"
    fake_bin.mkdir()
    opened = tmp_path / "opened"
    (fake_bin / "open").write_text(f'#!/bin/sh\necho "$@" >> "{opened}"\n')
    (fake_bin / "open").chmod(0o755)
    elsewhere = tmp_path / "elsewhere"
    elsewhere.mkdir()

    class Setup:
        path = folder

        def env(self):
            return {**os.environ, "PATH": f"{fake_bin}:{os.environ['PATH']}"}

        def run(self, answer):
            return subprocess.run([sys.executable, str(folder / "make_invoices.py")],
                                  input=answer, text=True, capture_output=True,
                                  cwd=elsewhere, env=self.env(), timeout=300)

        def opened(self):
            return opened.read_text().splitlines() if opened.exists() else []

        def snapshot(self):
            return {p.relative_to(folder): p.read_bytes()
                    for p in folder.rglob("*") if p.is_file()}

    return Setup()


def test_discard(setup):
    before = setup.snapshot()
    result = setup.run("no\n")
    assert result.returncode == 2, result.stderr
    assert "Discarded. Nothing was written." in result.stdout
    [preview] = setup.opened()
    assert "invoice-preview-" in preview and not os.path.exists(preview)
    assert setup.snapshot() == before


def test_commit_then_the_same_timesheet_again(setup):
    result = setup.run("commit\n")
    assert result.returncode == 0, result.stderr
    assert "Committed 7 invoices:" in result.stdout
    assert sorted(p.name for p in (setup.path / "invoices").rglob("*.pdf")) == [
        f"INV-000{n}.pdf" for n in range(1, 8)]
    assert len((setup.path / "ledger.csv").read_text().splitlines()) == 1 + 45
    assert (setup.path / "summary.csv").read_text().startswith("work_month,client,")
    assert not os.path.exists(setup.opened()[0])

    again = setup.run("commit\n")
    assert again.returncode == 1
    assert "this line may already be billed, on INV-0001" in again.stderr
    assert len(setup.opened()) == 1  # refused before any preview was made


def test_refused_run_opens_nothing(setup):
    (setup.path / "clients.txt").write_text(
        (setup.path / "clients.txt").read_text().replace("| base | AUD |", "| gold | AUD |"))
    result = setup.run("commit\n")
    assert result.returncode == 1
    assert 'clients.txt — unknown Tier value "gold"' in result.stderr
    assert result.stderr.rstrip().endswith("Fix it in Notion and paste the table again. "
                                           "Nothing was written.")
    assert setup.opened() == [] and not (setup.path / "invoices").exists()


@pytest.mark.skipif(shutil.which("uv") is None and not os.path.exists("/opt/homebrew/bin/uv"),
                    reason="the launcher needs uv")
def test_double_click_launcher(setup):
    # Started the way Finder starts it: the file itself, from another folder.
    result = subprocess.run([str(setup.path / "Make invoices.command")], input="commit\n",
                            text=True, capture_output=True, cwd="/", env=setup.env(),
                            timeout=300)
    assert "Committed 7 invoices:" in result.stdout, result.stdout + result.stderr
    assert (setup.path / "invoices" / "2026-11" / "INV-0003.pdf").exists()


@pytest.mark.skipif(shutil.which("uv") is None and not os.path.exists("/opt/homebrew/bin/uv"),
                    reason="the launcher needs uv")
# forkpty() warns when earlier tests have left WeasyPrint threads running. The
# deadlock it warns about needs the child to run Python code; this child execs
# the launcher straight away.
@pytest.mark.filterwarnings("ignore:This process .* is multi-threaded:DeprecationWarning")
def test_launcher_runs_again_on_r(setup):
    # A real terminal, so the launcher's one-key read works as it does in Terminal.
    pid, fd = pty.fork()
    if pid == 0:
        os.chdir("/")
        launcher = str(setup.path / "Make invoices.command")
        os.execve(launcher, [launcher], setup.env())
    seen = b""

    def wait_for(text, times=1, timeout=180):
        nonlocal seen
        deadline = time.time() + timeout
        while seen.count(text.encode()) < times:
            assert time.time() < deadline, seen.decode(errors="replace")
            if select.select([fd], [], [], 1)[0]:
                seen += os.read(fd, 4096)

    try:
        wait_for("Type commit")
        os.write(fd, b"no\n")
        wait_for("Press r to run again, or close this window.")
        os.write(fd, b"x")  # anything but r is ignored
        time.sleep(1)
        assert seen.count(b"Type commit") == 1
        os.write(fd, b"r")
        wait_for("Type commit", times=2)
        os.write(fd, b"no\n")
        wait_for("Discarded. Nothing was written.", times=2)
        wait_for("Press r to run again", times=2)
    finally:
        os.kill(pid, signal.SIGHUP)  # what closing the window sends
        os.waitpid(pid, 0)
        os.close(fd)
    assert not (setup.path / "invoices").exists()
