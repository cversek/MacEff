"""Doctor + web walk behaviour under emergent participation.

There is no participation registry: scan locations are discovered from the
filesystem, and writing ``[[links]]`` is the act of joining the web. These
tests pin the walk (discovery, unit-of-node, INDEX exclusion) and the doctor's
orphan reporting over it.
"""
from pathlib import Path

from macf.knowledge_doctor import examine
from macf.knowledge_web import iter_web_files, node_class_for

EMPTY_KG = {"ca_nodes": {}, "wiki_index": {}, "stats": {}}


def _mk(agent_home: Path, rel: str, text: str = "# x\n") -> Path:
    p = agent_home / "agent" / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(text)
    return p


def test_any_artifact_dir_is_discovered_without_declaration(tmp_path):
    """A brand-new directory participates the moment it holds markdown."""
    _mk(tmp_path, "public/brand_new_type/artifact.md")
    walked = {(t, p.name) for t, _r, p in iter_web_files(tmp_path)}
    assert ("brand_new_type", "artifact.md") in walked


def test_unit_of_node_experiments(tmp_path):
    """Protocol and analysis carry the claims; per-arm data is evidence."""
    _mk(tmp_path, "public/experiments/2026-01-01_x/protocol.md")
    _mk(tmp_path, "public/experiments/2026-01-01_x/analysis.md")
    _mk(tmp_path, "public/experiments/2026-01-01_x/data/arm1_results.md")
    names = [p.name for t, _r, p in iter_web_files(tmp_path) if t == "experiments"]
    assert sorted(names) == ["analysis.md", "protocol.md"]


def test_unit_of_node_roadmaps(tmp_path):
    """The plan is the node; archived todos and designs are execution records."""
    _mk(tmp_path, "public/roadmaps/2026-01-01_m/roadmap.md")
    _mk(tmp_path, "public/roadmaps/2026-01-01_m/archived_todos/old.md")
    _mk(tmp_path, "public/roadmaps/2026-01-01_m/DESIGN_notes.md")
    names = [p.name for t, _r, p in iter_web_files(tmp_path) if t == "roadmaps"]
    assert names == ["roadmap.md"]


def test_index_files_are_never_nodes(tmp_path):
    _mk(tmp_path, "private/learnings/INDEX.md")
    _mk(tmp_path, "private/learnings/2026-01-01_000000_x_learning.md")
    names = [p.name for _t, _r, p in iter_web_files(tmp_path)]
    assert "INDEX.md" not in names
    assert "2026-01-01_000000_x_learning.md" in names


def test_node_class_derivation_executes_policy_definitions():
    assert node_class_for("policies") == "normative"
    assert node_class_for("checkpoints") == "temporal_record"
    assert node_class_for("roadmaps") == "temporal_record"
    assert node_class_for("learnings") == "conceptual_authority"
    assert node_class_for("never_heard_of_it") == "conceptual_authority"


def test_doctor_reports_linkless_file_as_orphan(tmp_path):
    _mk(tmp_path, "private/learnings/2026-01-01_000000_x_learning.md",
        "# a learning with no links\n")
    diagnosis = examine(agent_home=tmp_path, kg=EMPTY_KG)
    orphans = [f for f in diagnosis.findings if f.check == "orphans"]
    assert any("x_learning" in f.subject for f in orphans)


def test_doctor_has_no_registry_check(tmp_path):
    """Under emergent participation there is no registry to drift from."""
    _mk(tmp_path, "public/whatever/thing.md")
    diagnosis = examine(agent_home=tmp_path, kg=EMPTY_KG)
    assert not [f for f in diagnosis.findings if f.check == "registry integrity"]
