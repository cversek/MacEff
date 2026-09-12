"""Roles and duties in the knowledge web, per the roles policy's participation section.

The charter is the role's node; each duty record is its own node with edges to
its role, its tracked tasks and its evidence; the doctor reads a duty's links
through the same walk as the builder, so a linked duty is never an orphan and
an unlinked one is reported as one.
"""
import json
from types import SimpleNamespace

import pytest

from macf import knowledge_web as kw
from macf.roles import RoleStore


@pytest.fixture
def home(tmp_path, monkeypatch):
    """An agent home with one report, one role with a charter, and two duties."""
    monkeypatch.setenv("MACEFF_AGENT_HOME_DIR", str(tmp_path))
    from macf.utils.paths import find_agent_home
    find_agent_home.cache_clear()
    reports = tmp_path / "agent" / "public" / "reports"
    reports.mkdir(parents=True)
    (reports / "board_plan_report.md").write_text("# Board plan\n\n## Wiki-Links\n[[teaching]] [[lab_course]]\n")
    tasks = tmp_path / "home_tasks"; tasks.mkdir()
    (tasks / "7.json").write_text(json.dumps({"id": "7", "subject": "#7 write the board plan", "status": "completed", "description": "x"}))
    (tasks / "8.json").write_text(json.dumps({"id": "8", "subject": "#8 grading rubric", "status": "in_progress", "description": "x"}))
    monkeypatch.setenv("MACF_TASK_STORE_DIR", str(tasks))
    monkeypatch.setenv("MACF_ROLES_DIR", str(tmp_path / "agent" / "public" / "roles"))
    store = RoleStore()
    role, folder = store.create_role("Lab Course Assistant", icon="🎓", wiki_links=["teaching"])
    (folder / "charter.md").write_text("# Lab Course Assistant\n\n## Purpose\nAssist the sections.\n\n## Wiki-Links\n[[teaching]] [[lab_course]]\n")
    d1, _ = store.add_duty(role, folder, "board plan", wiki_links=["teaching"])
    store.advance_duty(d1, folder, "done", evidence=["7", "agent/public/reports/board_plan_report.md"])
    d2, _ = store.add_duty(role, folder, "rubric", tracks=["8"])
    return SimpleNamespace(home=tmp_path, role=role, folder=folder, done=d1, open=d2)


def test_charter_and_duties_are_nodes_with_structural_edges(home):
    tmp_path, folder, d1, d2 = home.home, home.folder, home.done, home.open
    web = kw.build_knowledge_web()
    nodes = web["ca_nodes"]
    charter = f"roles:{folder.name}/charter"
    assert charter in nodes and nodes[charter]["node_class"] == "conceptual_authority"
    assert f"duties:{d1.id}" in nodes and nodes[f"duties:{d1.id}"]["state"] == "done"
    assert nodes[f"duties:{d1.id}"]["node_class"] == "conceptual_authority"
    edges = web["edges"]
    # parent role
    assert charter in edges[f"duties:{d1.id}"] and f"duties:{d1.id}" in edges[charter]
    # evidence: the completed task and the report it produced
    assert "tasks:#7" in edges[f"duties:{d1.id}"]
    assert "reports:board_plan_report" in edges[f"duties:{d1.id}"]
    assert nodes["tasks:#7"]["title"] == "#7 write the board plan" and nodes["tasks:#7"]["node_class"] == "temporal_record"
    # tracks: the open task
    assert "tasks:#8" in edges[f"duties:{d2.id}"]
    # concept edges still work for duties (wiki_links field), as for ideas
    assert f"duties:{d1.id}" in web["wiki_index"]["teaching"]


def test_query_reaches_the_charter_and_its_duties(home):
    tmp_path, folder, d1, d2 = home.home, home.folder, home.done, home.open
    result = kw.query_knowledge_web("teaching")
    text = json.dumps(result)
    assert f"roles:{folder.name}/charter" in text and f"duties:{d1.id}" in text


def test_doctor_reads_duty_links_through_the_same_walk(home):
    tmp_path, folder, d1, d2 = home.home, home.folder, home.done, home.open
    from macf.knowledge_doctor import examine
    report = examine(tmp_path)
    orphans = " ".join(f.subject for f in report.findings if f.check == "orphans")
    assert f"DUTY_{d1.id}_" not in orphans                 # linked duty: not an orphan
    assert f"DUTY_{d2.id}_" in orphans                     # unlinked duty: reported, not hidden
    assert "data.json" not in orphans                      # the role's facts are not a node


def test_scan_dirs_override_walks_a_roles_root_too(home):
    tmp_path, folder, d1, d2 = home.home, home.folder, home.done, home.open
    web = kw.build_knowledge_web(scan_dirs=[tmp_path / "agent" / "public" / "roles"])
    assert any(n.startswith("duties:") for n in web["ca_nodes"])
    assert any(n.startswith("roles:") for n in web["ca_nodes"])
