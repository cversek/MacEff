"""Registry-integrity behaviour of the knowledge doctor.

Covers the declared-but-not-participating registry form (scholarship: "declare
it — participating or explicitly not"). A location can produce real artifacts
without being a graph member; the declaration is what separates a deliberate
exclusion from the undeclared-but-real state the acute finding exists to catch.
"""
from pathlib import Path

from macf.ideas import CA_PARTICIPATION
from macf.knowledge_doctor import _participating_files, examine

EMPTY_KG = {"ca_nodes": {}, "wiki_index": {}, "stats": {}}


def _registry_findings(agent_home: Path):
    diagnosis = examine(agent_home=agent_home, kg=EMPTY_KG)
    return [f for f in diagnosis.findings if f.check == "registry integrity"]


def test_undeclared_artifact_dir_is_acute(tmp_path):
    d = tmp_path / "agent" / "public" / "mystery_output"
    d.mkdir(parents=True)
    (d / "artifact.md").write_text("# something real\n")
    subjects = {f.subject for f in _registry_findings(tmp_path)
                if str(f.severity) == "acute"}
    assert "public/mystery_output" in subjects


def test_declared_not_participating_dir_is_not_flagged(tmp_path):
    d = tmp_path / "agent" / "public" / "amail"
    d.mkdir(parents=True)
    (d / "README.md").write_text("# correspondence\n")
    subjects = {f.subject for f in _registry_findings(tmp_path)
                if str(f.severity) == "acute"}
    assert "public/amail" not in subjects


def test_not_participating_files_are_never_examined(tmp_path):
    d = tmp_path / "agent" / "public" / "amail"
    d.mkdir(parents=True)
    (d / "message.md").write_text("# a message with no links\n")
    examined = [p for _t, _s, p in _participating_files(tmp_path, CA_PARTICIPATION)]
    assert (d / "message.md") not in examined


def test_participating_dirs_still_yield(tmp_path):
    """Positive control: the skip must not swallow participating types."""
    d = tmp_path / "agent" / "private" / "learnings"
    d.mkdir(parents=True)
    (d / "2026-01-01_000000_x_learning.md").write_text("# x\n")
    examined = [p.name for _t, _s, p in
                _participating_files(tmp_path, CA_PARTICIPATION)]
    assert "2026-01-01_000000_x_learning.md" in examined


def test_registry_declares_amail_and_sprints_with_reasons():
    for name in ("amail", "sprints"):
        spec = CA_PARTICIPATION[name]
        assert spec.get("participates") is False
        assert spec.get("reason"), f"{name} must record why it does not participate"
