"""`macf_tools mis index`: the registry of MIS files, read from their own headers (#1066).

Nothing in it is typed by hand: each row is a header the file already carries, so the index cannot drift
from the files. The fixtures are the repository's real MIS files.
"""
import json
from pathlib import Path

from macf import cli, mis

REPO = Path(__file__).resolve().parents[2]
MIS_DIR = REPO / "framework" / "mis"


def test_every_landed_mis_has_a_row_with_its_number_title_status_and_deliberation():
    rows = mis.index([MIS_DIR])
    by_number = {r["number"]: r for r in rows}
    assert {"0001", "0002", "0004"} <= set(by_number)
    four = by_number["0004"]
    assert four["title"].startswith("Agent mail as one system")
    assert four["status"] == "Accepted"
    assert four["deliberation"].startswith("https://github.com/")
    assert "amail" in four["lands_in"]
    assert four["file"] == "framework/mis/MIS-0004-amail.md" or four["file"].endswith("MIS-0004-amail.md")


def test_the_template_is_not_a_registry_row():
    assert "0000" not in {r["number"] for r in mis.index([MIS_DIR])}


def test_rows_come_in_number_order():
    numbers = [r["number"] for r in mis.index([MIS_DIR])]
    assert numbers == sorted(numbers)


def test_a_file_missing_header_fields_is_listed_with_them_blank_not_skipped(tmp_path):
    path = tmp_path / "MIS-0042-example.md"
    path.write_text("# MIS-0042: An example\n\n**Number**: 0042\n**Status**: Draft\n\n---\n\n## 1 Summary\n")
    row = mis.index([path])[0]
    assert row["number"] == "0042" and row["title"] == "An example" and row["status"] == "Draft"
    assert row["deliberation"] == "" and row["lands_in"] == ""


def test_the_table_has_one_line_per_mis_and_the_command_prints_it_and_json(capsys):
    import argparse
    assert cli.cmd_mis_index(argparse.Namespace(paths=[str(MIS_DIR)], json=False)) == 0
    out = capsys.readouterr().out
    assert "MIS-0004" in out and "Accepted" in out
    assert cli.cmd_mis_index(argparse.Namespace(paths=[str(MIS_DIR)], json=True)) == 0
    rows = json.loads(capsys.readouterr().out)
    assert any(r["number"] == "0004" for r in rows)


def test_a_path_that_does_not_exist_is_refused(capsys):
    import argparse
    assert cli.cmd_mis_index(argparse.Namespace(paths=["/nonexistent/mis"], json=False)) == 2
