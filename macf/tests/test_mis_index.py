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
    assert cli.cmd_mis_index(argparse.Namespace(paths=[str(MIS_DIR)], json=False, open=False)) == 0
    out = capsys.readouterr().out
    assert "MIS-0004" in out and "Accepted" in out
    assert cli.cmd_mis_index(argparse.Namespace(paths=[str(MIS_DIR)], json=True, open=False)) == 0
    rows = json.loads(capsys.readouterr().out)
    assert any(r["number"] == "0004" for r in rows)


def test_a_path_that_does_not_exist_is_refused(capsys):
    import argparse
    assert cli.cmd_mis_index(argparse.Namespace(paths=["/nonexistent/mis"], json=False, open=False)) == 2


# ---- --open: the drafts, from the open pull requests, never mixed into the landed rows -------------

DRAFT = ("# MIS-0009: A browser subsystem\n\n**Number**: 0009\n**Type**: Standards\n**Status**: Draft\n"
         "**Secretary**: the head maintainer\n**Deliberation**: https://github.com/cversek/MacEff/pull/1030\n"
         "**Lands-in**: a new policy\n\n---\n\n## 1 Summary\n")


def _gh(calls):
    """A gh runner answering the three calls open_index makes, from canned replies."""
    import base64

    def run(args):
        calls.append(args)
        if args[:2] == ["pr", "list"]:
            return json.dumps([{"number": 1030, "title": "MIS-0009 (Draft): the operator's browser", "headRefOid": "abc",
                                "url": "https://github.com/cversek/MacEff/pull/1030", "isDraft": True},
                               {"number": 5, "title": "fix: something else", "headRefOid": "d", "url": "u", "isDraft": False}])
        if args[:2] == ["pr", "view"]:
            return json.dumps({"files": [{"path": "changelog.d/x.md"}, {"path": "framework/mis/MIS-0009-browser.md"}]})
        if args[0] == "api":
            return json.dumps({"content": base64.b64encode(DRAFT.encode()).decode()})
        raise AssertionError(args)
    return run


def test_the_open_rows_are_the_mis_pull_requests_read_from_their_heads_headers():
    rows = mis.open_index(_gh([]))
    assert len(rows) == 1
    row = rows[0]
    assert row["number"] == "0009" and row["status"] == "Draft" and row["pr"] == 1030 and row["draft"] is True
    assert row["title"] == "A browser subsystem" and row["secretary"] == "the head maintainer"


def test_a_pull_request_that_is_not_an_mis_is_not_a_row_and_is_not_read():
    calls = []
    mis.open_index(_gh(calls))
    assert not any(a[:3] == ["pr", "view", "5"] for a in calls)


def test_the_default_index_makes_no_network_call_and_open_keeps_the_sections_apart(monkeypatch, capsys):
    import argparse
    monkeypatch.setattr(mis, "gh_runner", lambda: (_ for _ in ()).throw(AssertionError("the default went to the network")))
    assert cli.cmd_mis_index(argparse.Namespace(paths=[str(MIS_DIR)], json=False, open=False)) == 0
    capsys.readouterr()
    monkeypatch.setattr(mis, "gh_runner", lambda: _gh([]))
    assert cli.cmd_mis_index(argparse.Namespace(paths=[str(MIS_DIR)], json=True, open=True)) == 0
    both = json.loads(capsys.readouterr().out)
    assert {r["number"] for r in both["open"]} == {"0009"} and "0009" not in {r["number"] for r in both["landed"]}


# ---- revisions: read from each file's own Deliberation Record, never stored -----------------------

def test_each_row_lists_the_dates_its_mis_was_revised_or_amended():
    by_number = {r["number"]: r for r in mis.index([MIS_DIR])}
    assert {"2026-10-24", "2026-11-09"} <= set(by_number["0002"]["revisions"])
    assert "2026-11-21" in by_number["0004"]["revisions"]
    assert by_number["0001"]["revisions"] == ["2026-10-18"]      # "amended in place by MIS-0005"
    assert all(r["revisions"] == sorted(set(r["revisions"])) for r in by_number.values())


def test_a_line_that_only_mentions_a_revision_is_not_one(tmp_path):
    path = tmp_path / "MIS-0042-example.md"
    path.write_text("# MIS-0042: An example\n\n**Number**: 0042\n**Status**: Accepted\n\n---\n\n"
                    "## 14 Deliberation Record\n\n"
                    "- 2026-11-01: every maintainer commented on the revision.\n"
                    "- 2026-11-02: a revision at the repo owner's request (MIS-0001-R52).\n"
                    "- 2026-11-03: an amendment by MIS-0005.\n"
                    "- 2026-11-04: R7 is passing, conformance, editorial.\n")
    assert mis.index([path])[0]["revisions"] == ["2026-11-02", "2026-11-03"]


def test_the_table_says_how_often_and_when_last_each_mis_was_revised(capsys):
    import argparse
    assert cli.cmd_mis_index(argparse.Namespace(paths=[str(MIS_DIR)], json=False, open=False)) == 0
    out = capsys.readouterr().out
    assert "revised" in out and "last 2026-11-21" in out


import pytest  # noqa: E402


@pytest.mark.parametrize("wording, counted", [
    ("a revision at the repo owner's request", True),
    ("the single revision under MIS-0001-R48", True),
    ("the synthesis revision", True),
    ("revision of section 6", True),
    ("an amendment by MIS-0005", True),
    ("amended in place by MIS-0005", True),
    ("A Revision at the repo owner's request", True),
    ("revisions to the glossary were discussed", False),
    ("every maintainer commented on the revision", False),
    ("R7 is passing, conformance, editorial", False),
])
def test_each_record_wording_is_read_as_the_comment_names_it(wording, counted):
    assert mis.revision_dates([f"- 2026-11-02: {wording}."]) == (["2026-11-02"] if counted else [])


def test_the_table_line_counts_one_revision_and_several(tmp_path):
    def mis_file(n, dates):
        path = tmp_path / f"MIS-00{n}-x.md"
        record = "".join(f"- {d}: a revision at the repo owner's request.\n" for d in dates)
        path.write_text(f"# MIS-00{n}: X\n\n**Number**: 00{n}\n**Status**: Accepted\n\n---\n\n"
                        f"## 14 Deliberation Record\n\n{record}")
        return path
    one, two = mis_file(41, ["2026-11-01"]), mis_file(42, ["2026-11-01", "2026-11-05"])
    out = mis.format_index(mis.index([one, two]))
    assert "revised 1 time, last 2026-11-01" in out and "revised 2 times, last 2026-11-05" in out
