"""The orphan census as one line per type, what is new listed on request, and
every curation metric in one call (#392 items 4 and 7).

The doctor used to list every orphan on every run, the same backlog ahead of
anything new, which is the noise the corpus-integrity policy warns trains a
reader to skim the whole report.
"""
import json
import os
import time
from argparse import Namespace

import pytest

from macf.knowledge_doctor import artifact_date, examine


@pytest.fixture
def home(tmp_path, monkeypatch):
    monkeypatch.setenv("MACEFF_AGENT_HOME_DIR", str(tmp_path))
    from macf.utils.paths import find_agent_home
    find_agent_home.cache_clear()
    ref = tmp_path / "agent" / "private" / "reflections"
    ref.mkdir(parents=True)
    for name in ("2025-01-01_a.md", "2025-02-01_b.md", "2026-09-20_c.md"):
        (ref / name).write_text("# linkless\n")
    rep = tmp_path / "agent" / "public" / "reports"
    rep.mkdir(parents=True)
    (rep / "2025-03-01_r.md").write_text("# linkless\n")
    (rep / "2025-03-02_s.md").write_text("# linked\n\n## Wiki-Links\n\n[[hooks]]\n")
    return tmp_path


def _orphans(dx, prefix=""):
    return [f.subject for f in dx.findings if f.check == "orphans" and f.subject.startswith(prefix)]


def test_the_default_census_is_one_line_per_type(home):
    dx = examine(home, orphans="summary")
    assert _orphans(dx, "reflections") == ["reflections: 3 orphans"]
    assert _orphans(dx, "reports") == ["reports: 1 orphan"]
    f = next(f for f in dx.findings if f.subject == "reflections: 3 orphans")
    assert "2025-01-01 to 2026-09-20" in f.detail and "--type reflections" in f.remedy
    assert dx.chart.vitals["orphans"] == examine(home).chart.vitals["orphans"], \
        "the chart counts the whole census whichever view is printed"


def test_since_lists_the_new_and_summarises_the_rest(home):
    cutoff = time.mktime(time.strptime("2026-01-01", "%Y-%m-%d"))
    subjects = _orphans(examine(home, orphans="summary", since=cutoff), "reflections")
    assert subjects == ["reflections: 2 orphans (and 1 listed below)", "reflections: 2026-09-20_c.md"]


def test_type_lists_every_orphan_of_that_type(home):
    subjects = _orphans(examine(home, orphans="summary", orphan_type="reflections"), "reflections")
    assert subjects == ["reflections: 2025-01-01_a.md", "reflections: 2025-02-01_b.md",
                        "reflections: 2026-09-20_c.md"]


def test_type_reports_that_type_alone(home):
    """--type is the bulk pass over one type: its orphans, and no other type's."""
    dx = examine(home, orphans="summary", orphan_type="reflections")
    assert len(_orphans(dx, "reflections")) == 3
    assert _orphans(dx, "reports") == []


def test_a_type_the_doctor_does_not_examine_is_refused(home, capsys):
    """A type that matches nothing would bring the whole report back, as if it had run.
    Ideas live in their own store, so asking for them says where to look instead."""
    from macf.cli import main
    with pytest.raises(SystemExit) as exited:
        main(["knowledge", "doctor", "--type", "idea"])
    assert exited.value.code == 2
    out = capsys.readouterr().out
    assert "does not examine 'idea'" in out and "reflections" in out and "idea graph --json" in out


def test_a_date_in_the_name_beats_the_modified_time(tmp_path):
    dated = tmp_path / "2024-05-06_x" / "analysis.md"
    dated.parent.mkdir()
    dated.write_text("x")
    undated = tmp_path / "notes.md"
    undated.write_text("x")
    os.utime(undated, (1_000_000_000, 1_000_000_000))
    assert time.strftime("%Y-%m-%d", time.localtime(artifact_date(dated))) == "2024-05-06"
    assert artifact_date(undated) == 1_000_000_000


def test_status_is_every_metric_in_one_call(home, capsys):
    from macf.cli import cmd_knowledge_status
    assert cmd_knowledge_status(Namespace(json_output=True)) == 0
    status = json.loads(capsys.readouterr().out)
    assert status["orphans"] == examine(home).chart.vitals["orphans"]
    assert {"nodes", "edges", "cross_ca_edges", "concepts", "acute", "chronic", "gaps"} <= set(status)


@pytest.mark.parametrize("value, age", [("7d", 7 * 86400), ("12h", 12 * 3600), ("last week", None)])
def test_since_takes_a_date_or_an_age(value, age):
    from macf.cli import _parse_since
    if age is None:
        with pytest.raises(ValueError, match="date"):
            _parse_since(value)
    else:
        assert abs((time.time() - _parse_since(value)) - age) < 60
    assert _parse_since("2026-09-01") == time.mktime(time.strptime("2026-09-01", "%Y-%m-%d"))


def test_idea_graph_lists_its_isolated_ideas(home, capsys):
    """The doctor sends ideas to the idea graph, so the graph must name the isolated ones,
    not only count them."""
    import json
    from macf.cli import main
    for title, link in (("Alpha", "shared"), ("Beta", "shared"), ("Gamma", "alone")):
        with pytest.raises(SystemExit):
            main(["idea", "create", "--title", title, "--category", "tooling", "--wiki-links", link])
    capsys.readouterr()
    with pytest.raises(SystemExit):
        main(["idea", "graph", "--json"])
    graph = json.loads(capsys.readouterr().out)
    assert [i["title"] for i in graph["isolated"]] == ["Gamma"]
    assert graph["isolated_count"] == 1
