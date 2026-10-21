"""A type folder can opt out of the knowledge web with a marker file, and the
exclusion is always named, never silent.

The repo owner ruled that a folder of private scratch material stays out of the
web. Before this, every subdirectory of agent/private and agent/public was a
type with no way out. The marker is the way out; the doctor and status name
every folder it removes, so an exclusion cannot hide orphans unseen
(scholarship policy, the section on opting a folder out).
"""
import json
from argparse import Namespace
from pathlib import Path

import pytest

from macf.diagnostics import Severity, format_diagnosis
from macf.knowledge_doctor import OPTED_OUT_CHECK, examine
from macf.knowledge_web import OPT_OUT_MARKER, build_knowledge_web, iter_web_files

EMPTY_KG = {"ca_nodes": {}, "wiki_index": {}, "stats": {}}
LINKED = "# linked\n\n## Wiki-Links\n\n[[hooks]]\n"


def _mk(agent_home: Path, rel: str, text: str = "# linkless\n") -> Path:
    p = agent_home / "agent" / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(text)
    return p


def _opt_out(agent_home: Path, rel: str) -> None:
    folder = agent_home / "agent" / rel
    folder.mkdir(parents=True, exist_ok=True)
    (folder / OPT_OUT_MARKER).write_text("")


@pytest.fixture
def home(tmp_path, monkeypatch):
    monkeypatch.setenv("MACEFF_AGENT_HOME_DIR", str(tmp_path))
    from macf.utils.paths import find_agent_home
    find_agent_home.cache_clear()
    _mk(tmp_path, "private/scratchpad_archive/dump.md", LINKED)
    _mk(tmp_path, "private/scratchpad_archive/linkless.md")
    _opt_out(tmp_path, "private/scratchpad_archive")
    _mk(tmp_path, "private/learnings/2026-01-01_kept.md", LINKED)
    yield tmp_path
    find_agent_home.cache_clear()


def test_a_marked_folder_is_not_walked(home):
    types = {t for t, _r, _p in iter_web_files(home)}
    assert "scratchpad_archive" not in types
    assert "learnings" in types


def test_a_marked_subagent_folder_is_not_walked(tmp_path):
    _mk(tmp_path, "subagents/helper/private/archive/old.md")
    _mk(tmp_path, "subagents/helper/private/notes/kept.md")
    _opt_out(tmp_path, "subagents/helper/private/archive")
    types = {t for t, _r, _p in iter_web_files(tmp_path)}
    assert "archive" not in types and "notes" in types


def test_a_marked_folder_yields_no_nodes(home):
    kg = build_knowledge_web()
    types = {info.get("type") for info in kg["ca_nodes"].values()}
    assert "scratchpad_archive" not in types
    # The unmarked sibling still participates: the marker removes one folder, not the walk.
    assert "learnings" in types


def test_the_doctor_names_each_excluded_folder(home):
    dx = examine(home, kg=EMPTY_KG)
    notes = [f for f in dx.findings if f.check == OPTED_OUT_CHECK]
    assert [f.subject for f in notes] == ["private/scratchpad_archive: out of the web by its marker"]
    assert notes[0].severity == Severity.NOTE
    assert dx.chart.vitals["opted_out"] == 1
    assert "private/scratchpad_archive: out of the web by its marker" in format_diagnosis(dx)
    # Its linkless file is not reported as an orphan: it is out of the web, and said so above.
    assert not [f for f in dx.findings if f.check == "orphans" and "scratchpad_archive" in f.subject]


def test_the_doctor_is_silent_when_nothing_is_excluded(tmp_path):
    _mk(tmp_path, "private/learnings/2026-01-01_kept.md", LINKED)
    dx = examine(tmp_path, kg=EMPTY_KG)
    assert not [f for f in dx.findings if f.check == OPTED_OUT_CHECK]
    assert dx.chart.vitals["opted_out"] == 0


def test_status_json_lists_the_excluded_folders(home, capsys):
    from macf.cli import cmd_knowledge_status
    assert cmd_knowledge_status(Namespace(json_output=True)) == 0
    status = json.loads(capsys.readouterr().out)
    assert status["opted_out"] == ["private/scratchpad_archive"]
