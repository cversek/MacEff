"""Knowledge graph HTML visualization renderer.

Transforms knowledge graph data from macf.ideas into interactive d3.js
force-directed HTML files. Separates data transformation (Python) from
presentation (HTML template).
"""
import json
import sys
from pathlib import Path
from string import Template
from typing import Any, Dict, List, Optional, Set, Tuple


# Node type → display color (must match template COLOR map)
NODE_COLORS = {
    "idea_captured":  "#f0c040",
    "idea_promoted":  "#4caf50",
    "idea_exploring": "#29b6f6",
    "idea_archived":  "#616161",
    "learnings":      "#5c6bc0",
    "observations":   "#66bb6a",
    "wiki":           "#78909c",
}

# Legend entries: (label, color, css_extra)
LEGEND_ENTRIES = [
    ("Idea (captured)",  NODE_COLORS["idea_captured"],  ""),
    ("Idea (promoted)",  NODE_COLORS["idea_promoted"],  ""),
    ("Idea (exploring)", NODE_COLORS["idea_exploring"], ""),
    ("Learning",         NODE_COLORS["learnings"],      ""),
    ("Observation",      NODE_COLORS["observations"],   ""),
    ("Wiki Concept",     NODE_COLORS["wiki"],           "border-radius:2px"),
]

TEMPLATE_DIR = Path(__file__).parent / "templates"


class KnowledgeGraphViz:
    """Renders a MACF knowledge graph as an interactive HTML file.

    Usage::

        from macf.ideas import build_knowledge_graph
        from macf.viz import KnowledgeGraphViz

        kg = build_knowledge_graph()
        viz = KnowledgeGraphViz(kg)
        viz.render("/tmp/knowledge_graph.html")
        # or: html_str = viz.to_html()
    """

    def __init__(self, knowledge_graph: Dict[str, Any]):
        self._kg = knowledge_graph
        self._nodes: List[Dict[str, Any]] = []
        self._links: List[Dict[str, Any]] = []
        self._node_index: Dict[Any, int] = {}
        self._build()

    @property
    def stats(self) -> Dict[str, Any]:
        return self._kg["stats"]

    @property
    def node_count(self) -> int:
        return len(self._nodes)

    @property
    def link_count(self) -> int:
        return len(self._links)

    # --- Data transformation ---

    def _build(self) -> None:
        """Transform knowledge graph dict into d3-ready nodes and links."""
        self._build_nodes()
        self._build_links()

    def _build_nodes(self) -> None:
        """Create typed node entries for ideas, CAs, and wiki concepts."""
        ideas = self._kg["ideas"]
        ca_nodes = self._kg.get("ca_nodes", {})
        wiki_index = self._kg.get("wiki_index", {})
        edges = self._kg["edges"]
        idx = 0

        # Idea nodes
        for idea_id in sorted(ideas.keys()):
            idea = ideas[idea_id]
            self._nodes.append({
                "id": str(idea_id),
                "label": f"#{idea_id:03d}",
                "title": idea.get("title", ""),
                "type": "idea",
                "status": idea.get("status", "captured"),
                "category": idea.get("category", ""),
                "degree": len(edges.get(idea_id, set())),
            })
            self._node_index[idea_id] = idx
            idx += 1

        # CA nodes (learnings, observations)
        for ca_id in sorted(ca_nodes.keys()):
            info = ca_nodes[ca_id]
            self._nodes.append({
                "id": ca_id,
                "label": ca_id.split(":")[-1][:25],
                "title": info.get("title", ""),
                "type": info.get("type", "ca"),
                "status": "",
                "category": info.get("type", ""),
                "degree": len(edges.get(ca_id, set())),
            })
            self._node_index[ca_id] = idx
            idx += 1

        # Wiki concept nodes
        for concept in sorted(wiki_index.keys()):
            self._nodes.append({
                "id": f"wiki:{concept}",
                "label": f"[[{concept}]]",
                "title": f"Wiki concept: {concept}",
                "type": "wiki",
                "status": "",
                "category": "concept",
                "degree": len(wiki_index[concept]),
            })
            self._node_index[f"wiki:{concept}"] = idx
            idx += 1

    def _build_links(self) -> None:
        """Create deduplicated link entries from wiki co-occurrence and direct edges."""
        wiki_index = self._kg.get("wiki_index", {})
        edges = self._kg["edges"]
        seen: Set[Tuple[str, str]] = set()

        # Wiki concept ↔ member edges
        for concept, member_ids in wiki_index.items():
            concept_key = f"wiki:{concept}"
            if concept_key not in self._node_index:
                continue
            for member_id in member_ids:
                if member_id not in self._node_index:
                    continue
                pair = tuple(sorted([str(concept_key), str(member_id)]))
                if pair not in seen:
                    seen.add(pair)
                    self._links.append({
                        "source": self._node_index[concept_key],
                        "target": self._node_index[member_id],
                        "type": "wiki",
                    })

        # Direct edges (related_ideas, co-occurrence)
        for node_id, neighbors in edges.items():
            if node_id not in self._node_index:
                continue
            for neighbor in neighbors:
                if neighbor not in self._node_index:
                    continue
                pair = tuple(sorted([str(node_id), str(neighbor)]))
                if pair not in seen:
                    seen.add(pair)
                    self._links.append({
                        "source": self._node_index[node_id],
                        "target": self._node_index[neighbor],
                        "type": "direct",
                    })

    # --- Rendering ---

    def _legend_html(self) -> str:
        """Generate legend item divs from LEGEND_ENTRIES."""
        items = []
        for label, color, css_extra in LEGEND_ENTRIES:
            style = f"background:{color}"
            if css_extra:
                style += f";{css_extra}"
            items.append(
                f'  <div class="legend-item">'
                f'<div class="legend-dot" style="{style}"></div> {label}'
                f'</div>'
            )
        return "\n".join(items)

    def _stats_html(self) -> str:
        """Generate stats bar content."""
        s = self.stats
        parts = [
            f'<span>{s["total_nodes"]}</span> nodes',
            f'<span>{s["total_edges"]}</span> edges',
            f'<span>{s.get("cross_ca_edges", 0)}</span> cross-CA',
            f'<span>{s["wiki_concepts"]}</span> concepts',
        ]
        return " &middot; ".join(parts)

    def _graph_json(self) -> str:
        """Serialize nodes and links for d3."""
        return json.dumps({"nodes": self._nodes, "links": self._links})

    def to_html(self) -> str:
        """Render the complete HTML string."""
        template_path = TEMPLATE_DIR / "knowledge_graph.html"
        try:
            template_text = template_path.read_text()
        except FileNotFoundError:
            print(f"⚠️ MACF: Template not found: {template_path}", file=sys.stderr)
            raise

        tmpl = Template(template_text)
        s = self.stats
        return tmpl.safe_substitute(
            title=f"MACF Knowledge Graph - {s['total_nodes']} nodes, {s['total_edges']} edges",
            graph_json=self._graph_json(),
            legend_items=self._legend_html(),
            stats_html=self._stats_html(),
        )

    def render(self, output_path: str) -> Path:
        """Write HTML to file and return the path."""
        path = Path(output_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(self.to_html())
        return path
