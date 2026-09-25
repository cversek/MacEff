"""Tasks carry wiki-links, and one verb links every artifact type (#392 items 1 and 2).

The graph already showed task nodes, and the gap detector proposed concepts for
them, with no way to attach one; linking a learning, an idea and a task took
three different tools. Here a task's links live in its metadata, the web reads
them through the one walk, and `knowledge link` edits each shape in place.
"""
import json
from types import SimpleNamespace

import pytest

from macf import knowledge_web as kw
from macf.knowledge_link import LinkError, apply_links, resolve_target


def _task(store, tid, subject, links=None, hidden=False):
    mtmd = 'task_type: TASK\n'
    if links:
        mtmd += "wiki_links:\n" + "".join(f"- {c}\n" for c in links)
    desc = f'<macf_task_metadata version="1.0">\n{mtmd}</macf_task_metadata>'
    name = f".{tid}.json" if hidden else f"{tid}.json"
    (store / name).write_text(json.dumps({"id": tid, "subject": subject, "status": "pending",
                                          "description": desc, "blocks": [], "blockedBy": []}))


@pytest.fixture
def home(tmp_path, monkeypatch):
    """An agent home whose task store is the home store under agent/public/tasks."""
    monkeypatch.setenv("MACEFF_AGENT_HOME_DIR", str(tmp_path))
    from macf.utils.paths import find_agent_home
    find_agent_home.cache_clear()
    store = tmp_path / "agent" / "public" / "tasks"
    store.mkdir(parents=True)
    monkeypatch.setenv("MACF_TASK_STORE_DIR", str(store))
    learnings = tmp_path / "agent" / "private" / "learnings"
    learnings.mkdir(parents=True)
    _task(store, "11", "#11 carry the scope", links=["compaction", "Sprint Scope"])
    _task(store, "12", "#12 unlinked chore")
    _task(store, "13", "#13 hidden but linked", links=["compaction"], hidden=True)
    return SimpleNamespace(home=tmp_path, store=store, learnings=learnings)


def test_a_linked_task_is_a_node_and_an_unlinked_one_an_orphan(home):
    web = kw.build_knowledge_web()
    node = web["ca_nodes"]["tasks:#11"]
    assert node["node_class"] == "temporal_record" and node["title"] == "#11 carry the scope"
    assert {"tasks:#11", "tasks:#13"} <= web["wiki_index"]["compaction"]
    assert "tasks:#11" in web["wiki_index"]["sprint_scope"], "concepts normalize as everywhere else"
    assert "tasks:#12" not in web["ca_nodes"]
    from macf.knowledge_doctor import examine
    # The walk also reads the framework policies; only the task orphans are this test's.
    orphans = [f for f in examine(home.home).findings
               if f.check == "orphans" and f.subject.startswith("tasks:")]
    assert [f.subject for f in orphans] == ["tasks: 12.json"]
    assert "knowledge link task:" in orphans[0].remedy


def test_linking_a_task_writes_its_metadata_and_needs_no_grant(home):
    first = apply_links("task:12", ["hooks", "[[Triage]]"])
    again = apply_links("#12", ["hooks", "session"])
    assert first.changed == ["hooks", "triage"] and again.changed == ["session"]
    from macf.task import TaskReader
    mtmd = TaskReader().read_task("12").mtmd
    assert mtmd.wiki_links == ["hooks", "triage", "session"]
    assert "Linked session (knowledge web)" in mtmd.updates[-1].description
    assert "tasks:#12" in kw.build_knowledge_web()["wiki_index"]["session"]
    assert apply_links("task:12", ["hooks"], remove=True).changed == ["hooks"]
    assert TaskReader().read_task("12").mtmd.wiki_links == ["triage", "session"]


def test_markdown_gains_a_section_then_extends_it_and_unlink_leaves_prose_alone(home):
    f = home.learnings / "2026-01-01_x_learning.md"
    f.write_text("# X\n\nThe [[compaction]] passage.\n")
    apply_links(str(f), ["hooks"])
    apply_links(str(f), ["triage", "hooks"])
    text = f.read_text()
    assert text.endswith("## Wiki-Links\n\n[[hooks]] [[triage]]\n") and text.count("[[hooks]]") == 1
    r = apply_links(str(f), ["hooks", "compaction"], remove=True)
    assert r.changed == ["hooks"] and r.still_inline == ["compaction"]
    assert "The [[compaction]] passage." in f.read_text() and "[[hooks]]" not in f.read_text()


def test_a_node_id_from_the_graph_resolves_to_its_file(home):
    f = home.learnings / "2026-01-02_y_learning.md"
    f.write_text("# Y\n\n## Wiki-Links\n\n[[hooks]]\n")
    assert resolve_target("learnings:2026-01-02_y_learning") == ("markdown", str(f))
    apply_links("learnings:2026-01-02_y_learning", ["triage"])
    assert "[[hooks]] [[triage]]" in f.read_text()


def test_an_idea_is_linked_through_its_own_update(home):
    from macf.ideas import create_idea, get_idea
    iid = create_idea(title="t", category="tooling", description="d", wiki_links=["hooks"])["idea"]["id"]
    r = apply_links(f"idea:{iid}", ["Knowledge Web", "hooks"])
    assert r.changed == ["knowledge_web"] and r.concepts == ["hooks", "knowledge_web"]
    assert get_idea(iid)["idea"]["links"]["wiki_links"] == ["hooks", "knowledge_web"]


@pytest.mark.parametrize("ref, says", [
    ("12", "idea or a task"),
    ("duties:D123", "role duty add"),
    ("nowhere.md", "no artifact found"),
])
def test_ambiguous_or_foreign_targets_are_refused(home, ref, says):
    with pytest.raises(LinkError, match=says):
        resolve_target(ref)
