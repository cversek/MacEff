"""Tests for build_knowledge_graph() — cross-CA wiki-link indexing.

Closes GH issue #73 (macf_tools knowledge cross-CA graph only indexed ideas).
The expanded indexer now picks up learnings, checkpoints, reflections,
observations, experiments (recursive), and reports — and falls back to
whole-document ``[[concept]]`` scanning when no explicit ## Wiki-Links
section is present.
"""

import pytest
from pathlib import Path

from macf.ideas import build_knowledge_graph


def _write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text)


@pytest.fixture
def fake_agent_root(tmp_path):
    """An agent root tree mirroring the layout build_knowledge_graph scans."""
    (tmp_path / "agent" / "private" / "learnings").mkdir(parents=True)
    (tmp_path / "agent" / "private" / "checkpoints").mkdir(parents=True)
    (tmp_path / "agent" / "private" / "reflections").mkdir(parents=True)
    (tmp_path / "agent" / "public" / "observations").mkdir(parents=True)
    (tmp_path / "agent" / "public" / "experiments").mkdir(parents=True)
    (tmp_path / "agent" / "public" / "reports").mkdir(parents=True)
    return tmp_path


class TestBuildKnowledgeGraphCrossCA:
    """Shape tests for the expanded cross-CA indexer."""

    def test_indexes_learnings_with_explicit_wiki_links_section(self, fake_agent_root):
        _write(
            fake_agent_root / "agent" / "private" / "learnings" / "l1.md",
            "# Learning One\n\n## Wiki-Links\n[[concept-A]] [[concept-B]]\n",
        )
        scan_dirs = [fake_agent_root / "agent" / "private" / "learnings"]
        kg = build_knowledge_graph(scan_dirs=scan_dirs)
        assert "learnings:l1" in kg["ca_nodes"]
        assert kg["ca_nodes"]["learnings:l1"]["title"] == "Learning One"

    def test_falls_back_to_whole_document_wiki_link_scan(self, fake_agent_root):
        """CCPs/JOTEWRs without an explicit ## Wiki-Links section still get edges."""
        _write(
            fake_agent_root / "agent" / "private" / "checkpoints" / "cp1.md",
            (
                "# Checkpoint One\n\n"
                "We discussed [[concept-A]] in passing here. Also touched on [[concept-C]].\n\n"
                "## Other Section\nNo wiki-links section header in this document.\n"
            ),
        )
        scan_dirs = [fake_agent_root / "agent" / "private" / "checkpoints"]
        kg = build_knowledge_graph(scan_dirs=scan_dirs)
        assert "checkpoints:cp1" in kg["ca_nodes"]

    def test_indexes_recursive_experiment_subfolders(self, fake_agent_root):
        """Experiments nest under dated subfolders; the indexer must rglob."""
        exp_dir = fake_agent_root / "agent" / "public" / "experiments" / "2026-05-01_my_experiment"
        _write(exp_dir / "protocol.md", "# Protocol\n\n[[concept-A]]\n")
        scan_dirs = [fake_agent_root / "agent" / "public" / "experiments"]
        kg = build_knowledge_graph(scan_dirs=scan_dirs)
        # Node id includes the dated parent folder for disambiguation
        assert "experiments:2026-05-01_my_experiment/protocol" in kg["ca_nodes"]

    def test_skips_index_md(self, fake_agent_root):
        """INDEX.md is the human-readable index, not a CA — skip it."""
        _write(
            fake_agent_root / "agent" / "private" / "learnings" / "INDEX.md",
            "# Learnings INDEX\n\n[[concept-A]]\n",
        )
        scan_dirs = [fake_agent_root / "agent" / "private" / "learnings"]
        kg = build_knowledge_graph(scan_dirs=scan_dirs)
        assert "learnings:INDEX" not in kg["ca_nodes"]

    def test_files_without_wiki_links_are_omitted(self, fake_agent_root):
        """If a CA has no [[concept]] anywhere, no node is added."""
        _write(
            fake_agent_root / "agent" / "private" / "learnings" / "no_links.md",
            "# Plain Learning\n\nNo wiki-link references in this document.\n",
        )
        scan_dirs = [fake_agent_root / "agent" / "private" / "learnings"]
        kg = build_knowledge_graph(scan_dirs=scan_dirs)
        assert "learnings:no_links" not in kg["ca_nodes"]

    def test_cross_ca_edges_via_shared_concept(self, fake_agent_root):
        """Two CAs in different directories sharing a [[concept]] get an edge."""
        _write(
            fake_agent_root / "agent" / "private" / "learnings" / "lA.md",
            "# Learning A\n\n[[shared-concept]]\n",
        )
        _write(
            fake_agent_root / "agent" / "private" / "checkpoints" / "cpA.md",
            "# Checkpoint A\n\n[[shared-concept]]\n",
        )
        scan_dirs = [
            fake_agent_root / "agent" / "private" / "learnings",
            fake_agent_root / "agent" / "private" / "checkpoints",
        ]
        kg = build_knowledge_graph(scan_dirs=scan_dirs)
        assert "learnings:lA" in kg["ca_nodes"]
        assert "checkpoints:cpA" in kg["ca_nodes"]
        # Edges are bidirectional via the wiki-index
        edges = kg["edges"]
        assert "checkpoints:cpA" in edges.get("learnings:lA", set())
        assert "learnings:lA" in edges.get("checkpoints:cpA", set())
