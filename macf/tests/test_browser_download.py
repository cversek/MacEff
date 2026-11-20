"""MIS-0009 R15, R16: downloads are saved to a named destination with a checksum, never inside the agent's home."""
import hashlib

import pytest

from macf.browser import guard


def test_download_saved_by_event_with_checksum(tmp_path):
    class FakeDownload:
        suggested_filename = "workbook.xlsx"

        def save_as(self, path):
            open(path, "wb").write(b"PK\x03\x04 fake xlsx")

    home = tmp_path / "agent_home"
    home.mkdir()
    out = tmp_path / "inbox"
    receipt = guard.save_download(FakeDownload(), out, agent_home=home)
    assert receipt["path"] == str(out / "workbook.xlsx")
    assert receipt["sha256"] == hashlib.sha256(b"PK\x03\x04 fake xlsx").hexdigest()
    assert receipt["bytes"] == len(b"PK\x03\x04 fake xlsx")


def test_destination_in_agent_home_refused(tmp_path):
    home = tmp_path / "agent_home"
    (home / "agent").mkdir(parents=True)
    for bad in (home, home / "agent", home / "agent" / ".." / "agent" / "x", home / ".maceff" / "x",
                home / ".claude"):
        with pytest.raises(guard.Refused):
            guard.check_destination(bad, agent_home=home)
    assert guard.check_destination(tmp_path / "elsewhere", agent_home=home) == (tmp_path / "elsewhere").resolve()
    # a project directory in the home is where the operator's files belong
    spoke = home / "projects" / "course" / "workbooks"
    assert guard.check_destination(spoke, agent_home=home) == spoke.resolve()


def test_download_name_cannot_escape_destination(tmp_path):
    class Sneaky:
        suggested_filename = "../../etc/x"

        def save_as(self, path):
            open(path, "wb").write(b"x")

    home = tmp_path / "home"
    home.mkdir()
    receipt = guard.save_download(Sneaky(), tmp_path / "out", agent_home=home)
    assert receipt["path"] == str(tmp_path / "out" / "x")
