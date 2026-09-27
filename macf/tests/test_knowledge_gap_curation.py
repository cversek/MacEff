"""A suggestion judged wrong stays declined, and declared keywords without a
concept are proposed as new ones (#392 items 3 and 5).

The same keyword-overlap suggestions came back on every curation and were
re-judged every time. A rejection now lives with the artifact, beside its
links, in the artifact's own shape; nothing else remembers it.
"""
import json
from types import SimpleNamespace

import pytest

from macf import knowledge_web as kw
from macf.knowledge_link import decline


def _suggested(node_id, include_rejected=False):
    return {g["suggested_concept"]: g.get("rejected", False)
            for g in kw.detect_web_gaps(include_rejected=include_rejected) if g["node_id"] == node_id}


@pytest.fixture
def home(tmp_path, monkeypatch):
    """Two artifacts share [[machine_learning]]; a third, titled with the word
    "machine" and linked only to [[photo]], is proposed [[machine_learning]]."""
    monkeypatch.setenv("MACEFF_AGENT_HOME_DIR", str(tmp_path))
    from macf.utils.paths import find_agent_home
    find_agent_home.cache_clear()
    lr = tmp_path / "agent" / "private" / "learnings"
    lr.mkdir(parents=True)
    for n in ("a", "b"):
        (lr / f"2026-01-0{ord(n) - 96}_{n}_learning.md").write_text(
            f"# {n}\n\n## Wiki-Links\n\n[[machine_learning]]\n")
    target = lr / "2026-01-03_photo_learning.md"
    target.write_text("# Machine photo metrology\n\n## Wiki-Links\n\n[[photo]]\n")
    store = tmp_path / "agent" / "public" / "tasks"
    store.mkdir(parents=True)
    monkeypatch.setenv("MACF_TASK_STORE_DIR", str(store))
    desc = '<macf_task_metadata version="1.0">\ntask_type: TASK\nwiki_links:\n- photo\n</macf_task_metadata>'
    (store / "21.json").write_text(json.dumps({"id": "21", "subject": "#21 machine calibration",
                                               "status": "pending", "description": desc,
                                               "blocks": [], "blockedBy": []}))
    return SimpleNamespace(home=tmp_path, target=target, learnings=lr)


def test_a_declined_suggestion_is_not_suggested_again(home):
    node = "learnings:2026-01-03_photo_learning"
    assert "machine_learning" in _suggested(node), "precondition: the wrong suggestion is made"
    decline(str(home.target), ["Machine Learning"])
    assert "machine_learning" not in _suggested(node)
    assert _suggested(node, include_rejected=True)["machine_learning"] is True
    web = kw.build_knowledge_web()
    assert node not in web["wiki_index"]["machine_learning"], "a rejection is never read as a link"


def test_the_rejection_is_one_line_in_the_links_section(home):
    decline(str(home.target), ["machine_learning"])
    decline(str(home.target), ["agent_teleport", "machine_learning"])
    text = home.target.read_text()
    assert text.count("not linked") == 1
    assert text.endswith("[[photo]]\n<!-- not linked: machine_learning, agent_teleport -->\n")


def test_a_task_and_an_idea_decline_in_their_own_shape(home):
    from macf.ideas import create_idea, get_idea
    from macf.task import TaskReader
    iid = create_idea(title="machine vision", category="tooling", description="d",
                      wiki_links=["photo"])["idea"]["id"]
    idea_node = str(iid)   # gap reports carry node ids as strings
    assert "machine_learning" in _suggested("tasks:#21")
    assert "machine_learning" in _suggested(idea_node)
    decline("task:21", ["machine_learning"])
    decline(f"idea:{iid}", ["machine_learning"])
    assert TaskReader().read_task("21").mtmd.not_linked == ["machine_learning"]
    assert get_idea(iid)["idea"]["links"]["not_linked"] == ["machine_learning"]
    assert "machine_learning" not in _suggested("tasks:#21")
    assert "machine_learning" not in _suggested(idea_node)


def test_keywords_several_artifacts_declare_without_a_concept_are_proposed(home):
    for i, extra in enumerate((", pair", ", pair", "")):
        (home.learnings / f"2026-02-0{i + 1}_k{i}_learning.md").write_text(
            f"# k{i}\n\n**Keywords**: LEARN, fillets, Machine Learning{extra}\n")
    found = {s["concept"]: s for s in kw.suggest_concepts()}
    assert found["fillets"]["count"] == 3 and len(found["fillets"]["members"]) == 3
    assert "learn" not in found, "an ALL CAPS activation marker is not a subject"
    assert "machine_learning" not in found, "an existing concept is not proposed again"
    assert "pair" not in found, "a keyword only two artifacts share is not a cluster"
