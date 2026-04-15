"""
Ideas CA — Prospective knowledge capture with provenance and graph connectivity.

Structured artifacts dedicated to novelty: speculative seeds with lifecycle
tracking, wiki-links, and pull-model promotion to experiments/roadmaps.
"""
import json
import os
import re
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional, Any


def _get_ideas_dir() -> Path:
    """Get the ideas directory, creating if needed."""
    from .utils.paths import find_agent_home
    agent_home = find_agent_home()
    if agent_home:
        ideas_dir = agent_home / "agent" / "public" / "ideas"
    else:
        ideas_dir = Path.cwd() / "agent" / "public" / "ideas"
    ideas_dir.mkdir(parents=True, exist_ok=True)
    return ideas_dir


def _get_next_id(ideas_dir: Path) -> int:
    """Get the next sequential idea ID by scanning existing files."""
    max_id = 0
    for f in ideas_dir.glob("*_idea.json"):
        m = re.match(r"(\d+)_", f.name)
        if m:
            max_id = max(max_id, int(m.group(1)))
    return max_id + 1


def _make_slug(title: str) -> str:
    """Convert title to snake_case slug."""
    slug = title.lower()
    slug = re.sub(r'[^a-z0-9\s]', '', slug)
    slug = re.sub(r'\s+', '_', slug.strip())
    return slug[:60]  # cap length


def create_idea(
    title: str,
    category: str,
    description: str,
    sparked_by: str = "",
    feasibility: str = "",
    reasoning: str = "",
    hypothesis: str = "",
    context: str = "",
) -> Dict[str, Any]:
    """Create a new idea file and return its data."""
    ideas_dir = _get_ideas_dir()
    idea_id = _get_next_id(ideas_dir)
    slug = _make_slug(title)
    now = datetime.now(timezone.utc).astimezone()
    ts_str = now.strftime("%Y-%m-%dT%H:%M:%S%z")
    # Insert colon in timezone offset for ISO 8601
    ts_str = ts_str[:-2] + ":" + ts_str[-2:]
    file_ts = now.strftime("%Y-%m-%d_%H%M%S")

    # Get breadcrumb
    try:
        from .utils.breadcrumbs import get_breadcrumb
        breadcrumb = get_breadcrumb()
    except (ImportError, OSError) as e:
        print(f"⚠️ MACF: breadcrumb generation failed: {e}", file=sys.stderr)
        breadcrumb = "unknown"

    # Get agent identity
    try:
        from .utils.identity import get_agent_identity
        agent_name = get_agent_identity()
    except (ImportError, OSError) as e:
        print(f"⚠️ MACF: agent identity failed: {e}", file=sys.stderr)
        agent_name = "unknown"

    idea = {
        "schema_version": "1.0",
        "id": idea_id,
        "title": title,
        "slug": slug,
        "status": "captured",
        "category": category,
        "description": description,
        "provenance": {
            "created": ts_str,
            "breadcrumb": breadcrumb,
            "sparked_by": sparked_by,
            "present": [agent_name],
            "context": context,
        },
        "links": {
            "related_ideas": [],
            "related_learnings": [],
            "wiki_links": [],
            "promoted_to": None,
            "archived_reason": None,
        },
        "history": [
            {"timestamp": ts_str, "action": "created", "breadcrumb": breadcrumb}
        ],
    }

    if feasibility:
        idea["feasibility"] = feasibility
    if reasoning:
        idea["reasoning"] = reasoning
    if hypothesis:
        idea["hypothesis"] = hypothesis

    filename = f"{idea_id:03d}_{file_ts}_{slug}_idea.json"
    filepath = ideas_dir / filename
    with open(filepath, "w") as f:
        json.dump(idea, f, indent=2)

    return {"idea": idea, "path": str(filepath)}


def list_ideas(
    status: Optional[str] = None,
    category: Optional[str] = None,
) -> List[Dict[str, Any]]:
    """List ideas, optionally filtered by status or category."""
    ideas_dir = _get_ideas_dir()
    results = []

    for f in sorted(ideas_dir.glob("*_idea.json")):
        try:
            with open(f) as fh:
                idea = json.load(fh)
            if status and idea.get("status") != status:
                continue
            if category and idea.get("category") != category:
                continue
            results.append({"idea": idea, "path": str(f)})
        except (json.JSONDecodeError, OSError) as e:
            print(f"⚠️ MACF: could not read {f.name}: {e}", file=sys.stderr)

    return results


def get_idea(idea_id: int) -> Optional[Dict[str, Any]]:
    """Get a specific idea by ID."""
    ideas_dir = _get_ideas_dir()
    for f in ideas_dir.glob(f"{idea_id:03d}_*_idea.json"):
        try:
            with open(f) as fh:
                return {"idea": json.load(fh), "path": str(f)}
        except (json.JSONDecodeError, OSError) as e:
            print(f"⚠️ MACF: could not read {f.name}: {e}", file=sys.stderr)
    return None


def update_idea(
    idea_id: int,
    status: Optional[str] = None,
    promoted_to: Optional[str] = None,
) -> Optional[Dict[str, Any]]:
    """Update an idea's status or promotion target."""
    result = get_idea(idea_id)
    if not result:
        return None

    idea = result["idea"]
    path = Path(result["path"])

    try:
        from .utils.breadcrumbs import get_breadcrumb
        breadcrumb = get_breadcrumb()
    except (ImportError, OSError):
        breadcrumb = "unknown"

    now = datetime.now(timezone.utc).astimezone()
    ts_str = now.strftime("%Y-%m-%dT%H:%M:%S%z")
    ts_str = ts_str[:-2] + ":" + ts_str[-2:]

    if status:
        idea["status"] = status
        idea.setdefault("history", []).append({
            "timestamp": ts_str,
            "action": f"status_changed_to_{status}",
            "breadcrumb": breadcrumb,
        })

    if promoted_to:
        idea.setdefault("links", {})["promoted_to"] = promoted_to

    with open(path, "w") as f:
        json.dump(idea, f, indent=2)

    return {"idea": idea, "path": str(path)}


def archive_idea(idea_id: int, reason: str) -> Optional[Dict[str, Any]]:
    """Archive an idea with a reason."""
    result = get_idea(idea_id)
    if not result:
        return None

    idea = result["idea"]
    path = Path(result["path"])

    try:
        from .utils.breadcrumbs import get_breadcrumb
        breadcrumb = get_breadcrumb()
    except (ImportError, OSError):
        breadcrumb = "unknown"

    now = datetime.now(timezone.utc).astimezone()
    ts_str = now.strftime("%Y-%m-%dT%H:%M:%S%z")
    ts_str = ts_str[:-2] + ":" + ts_str[-2:]

    idea["status"] = "archived"
    idea.setdefault("links", {})["archived_reason"] = reason
    idea.setdefault("history", []).append({
        "timestamp": ts_str,
        "action": "archived",
        "reason": reason,
        "breadcrumb": breadcrumb,
    })

    with open(path, "w") as f:
        json.dump(idea, f, indent=2)

    return {"idea": idea, "path": str(path)}


def search_ideas(query: str) -> List[Dict[str, Any]]:
    """Search ideas by title, description, or reasoning."""
    query_lower = query.lower()
    results = []
    for item in list_ideas():
        idea = item["idea"]
        searchable = " ".join(filter(None, [
            idea.get("title", ""),
            idea.get("description", ""),
            idea.get("reasoning", ""),
            idea.get("hypothesis", ""),
            " ".join(idea.get("links", {}).get("wiki_links", []) or []),
        ])).lower()
        if query_lower in searchable:
            results.append(item)
    return results


# ============================================================================
# Knowledge Graph
# ============================================================================

STATUS_ICON = {"captured": "💡", "exploring": "🔍", "promoted": "🚀", "archived": "📦"}


def build_idea_graph() -> Dict[str, Any]:
    """Build adjacency graph from ideas' related_ideas + wiki-link co-occurrence.

    Returns dict with: ideas, edges, wiki_index, components, isolated, degree, stats.
    """
    import re as re_mod
    from collections import defaultdict

    items = list_ideas()
    ideas = {item["idea"]["id"]: item["idea"] for item in items}
    edges = defaultdict(set)
    wiki_index = defaultdict(set)

    for idea_id, idea in ideas.items():
        links = idea.get("links", {})
        for rid in (links.get("related_ideas") or []):
            if isinstance(rid, int):
                edges[idea_id].add(rid)
                edges[rid].add(idea_id)
        for wl in (links.get("wiki_links") or []):
            m = re_mod.match(r'\[\[(.+?)\]\]', wl)
            if m:
                # Normalize: strip .md suffix for consistent matching
                concept = re_mod.sub(r'\.md$', '', m.group(1))
                wiki_index[concept].add(idea_id)

    for concept, ids in wiki_index.items():
        ids_list = list(ids)
        for i in range(len(ids_list)):
            for j in range(i + 1, len(ids_list)):
                edges[ids_list[i]].add(ids_list[j])
                edges[ids_list[j]].add(ids_list[i])

    degree = {i: len(edges.get(i, set())) for i in ideas}

    # BFS connected components
    visited = set()
    components = []
    for idea_id in sorted(ideas.keys()):
        if idea_id in visited or not edges.get(idea_id):
            continue
        component = []
        queue = [idea_id]
        while queue:
            node = queue.pop(0)
            if node in visited or node not in ideas:
                continue
            visited.add(node)
            component.append(node)
            for neighbor in sorted(edges.get(node, set())):
                if neighbor not in visited and neighbor in ideas:
                    queue.append(neighbor)
        components.append(sorted(component))

    isolated = sorted(i for i in ideas if i not in visited)
    total_edges = sum(len(v) for v in edges.values()) // 2

    return {
        "ideas": ideas,
        "edges": dict(edges),
        "wiki_index": dict(wiki_index),
        "components": components,
        "isolated": isolated,
        "degree": degree,
        "stats": {
            "total_ideas": len(ideas),
            "total_edges": total_edges,
            "connected": len(ideas) - len(isolated),
            "isolated_count": len(isolated),
            "wiki_concepts": len(wiki_index),
            "clusters": len(components),
        },
    }


def build_knowledge_graph(scan_dirs: Optional[List[Path]] = None) -> Dict[str, Any]:
    """Build cross-CA knowledge graph: ideas + learnings + observations via wiki-links.

    Scans ideas (JSON, related_ideas + wiki_links fields) and other CAs
    (markdown, ## Wiki-Links sections) for [[concept]] references.
    Nodes are CA identifiers, edges from shared wiki-link concepts.
    """
    import re as re_mod
    from collections import defaultdict

    # Start with ideas graph
    graph = build_idea_graph()
    wiki_index = defaultdict(set, {k: set(v) for k, v in graph["wiki_index"].items()})
    ca_nodes = {}  # non-idea CA nodes: {node_id: {type, title, path}}

    # Scan additional directories for markdown files with ## Wiki-Links
    if scan_dirs is None:
        try:
            from .utils.paths import find_agent_home
            agent_home = find_agent_home()
            if agent_home:
                scan_dirs = [
                    agent_home / "agent" / "private" / "learnings",
                    agent_home / "agent" / "public" / "observations",
                ]
        except (OSError, ImportError) as e:
            print(f"⚠️ MACF: knowledge graph scan dirs failed: {e}", file=sys.stderr)
            scan_dirs = []

    for scan_dir in (scan_dirs or []):
        if not scan_dir.exists():
            continue
        ca_type = scan_dir.name  # "learnings" or "observations"
        for md_file in sorted(scan_dir.glob("*.md")):
            if md_file.name == "INDEX.md":
                continue
            try:
                content = md_file.read_text(errors='replace')
            except OSError:
                continue
            # Find ## Wiki-Links section
            wl_match = re_mod.search(r'## Wiki-Links\s*\n(.+?)(?:\n##|\Z)', content, re_mod.DOTALL)
            if not wl_match:
                continue
            wl_section = wl_match.group(1)
            concepts = re_mod.findall(r'\[\[(.+?)\]\]', wl_section)
            if not concepts:
                continue
            # Create a node ID for this CA
            node_id = f"{ca_type}:{md_file.stem}"
            # Extract title from first heading
            title_match = re_mod.search(r'^#\s+(.+)', content, re_mod.MULTILINE)
            title = title_match.group(1)[:50] if title_match else md_file.stem[:50]
            ca_nodes[node_id] = {"type": ca_type, "title": title, "path": str(md_file)}
            for concept in concepts:
                wiki_index[concept].add(node_id)

    # Rebuild edges including cross-CA connections
    edges = defaultdict(set)
    # Preserve idea-to-idea edges from related_ideas
    for k, v in graph["edges"].items():
        edges[k] = set(v)
    # Add wiki-link co-occurrence edges (including cross-CA)
    for concept, node_ids in wiki_index.items():
        ids_list = list(node_ids)
        for i in range(len(ids_list)):
            for j in range(i + 1, len(ids_list)):
                edges[ids_list[i]].add(ids_list[j])
                edges[ids_list[j]].add(ids_list[i])

    # Stats
    all_nodes = set(graph["ideas"].keys()) | set(ca_nodes.keys())
    cross_ca_edges = 0
    for node_id, neighbors in edges.items():
        for neighbor in neighbors:
            if (isinstance(node_id, str) and ":" in node_id) != (isinstance(neighbor, str) and ":" in str(neighbor)):
                cross_ca_edges += 1
    cross_ca_edges //= 2

    return {
        "ideas": graph["ideas"],
        "ca_nodes": ca_nodes,
        "edges": dict(edges),
        "wiki_index": dict(wiki_index),
        "stats": {
            "total_ideas": len(graph["ideas"]),
            "total_cas": len(ca_nodes),
            "total_nodes": len(all_nodes),
            "total_edges": sum(len(v) for v in edges.values()) // 2,
            "cross_ca_edges": cross_ca_edges,
            "wiki_concepts": len(wiki_index),
        },
    }


def format_idea_node(idea_id: int, ideas: dict, degree: dict) -> str:
    """Format one idea as a display string."""
    idea = ideas.get(idea_id, {})
    icon = STATUS_ICON.get(idea.get("status", ""), "?")
    title = idea.get("title", "")[:50]
    cat = idea.get("category", "")
    deg = degree.get(idea_id, 0)
    return f"{icon} #{idea_id:03d} {title}  [{cat}] (deg {deg})"


def format_graph_cluster(graph: Dict[str, Any]) -> str:
    """Format graph as cluster view (connected components as groups)."""
    ideas = graph["ideas"]
    degree = graph["degree"]
    wiki_index = graph["wiki_index"]
    lines = [f"📊 Ideas Knowledge Graph ({graph['stats']['total_ideas']} ideas, {graph['stats']['total_edges']} edges)", ""]

    for idx, component in enumerate(graph["components"]):
        cluster_concepts = [c for c, ids in wiki_index.items() if len(ids & set(component)) >= 2]
        concept_str = f"  via: {', '.join(f'[[{c}]]' for c in sorted(cluster_concepts))}" if cluster_concepts else ""
        lines.append(f"🌐 Cluster {idx+1} ({len(component)} ideas){concept_str}")
        for idea_id in component:
            lines.append(f"   {format_idea_node(idea_id, ideas, degree)}")
        lines.append("")

    if graph["isolated"]:
        lines.append(f"💡 Isolated ({len(graph['isolated'])} ideas — no connections)")
        for idea_id in graph["isolated"]:
            lines.append(f"   {format_idea_node(idea_id, ideas, degree)}")
        lines.append("")

    if wiki_index:
        lines.append(f"📝 Wiki Concepts ({len(wiki_index)})")
        for concept, ids in sorted(wiki_index.items()):
            lines.append(f"   [[{concept}]] → {', '.join(f'#{i:03d}' for i in sorted(ids))}")

    return "\n".join(lines)


def format_graph_tree(graph: Dict[str, Any]) -> str:
    """Format graph as tree view (most-connected as roots, neighbors as children)."""
    ideas = graph["ideas"]
    degree = graph["degree"]
    wiki_index = graph["wiki_index"]
    lines = [f"📊 Ideas Knowledge Graph ({graph['stats']['total_ideas']} ideas, {graph['stats']['total_edges']} edges)", ""]

    for component in graph["components"]:
        root = max(component, key=lambda i: degree.get(i, 0))
        lines.append(f"🔗 {format_idea_node(root, ideas, degree)}")
        children = [c for c in component if c != root]
        for idx, child in enumerate(children):
            is_last = (idx == len(children) - 1)
            prefix = "└── " if is_last else "├── "
            lines.append(f"   {prefix}{format_idea_node(child, ideas, degree)}")
            shared = [c for c, ids in wiki_index.items() if root in ids and child in ids]
            if shared:
                sub_prefix = "       " if is_last else "   │   "
                for concept in shared:
                    lines.append(f"{sub_prefix}via [[{concept}]]")
        lines.append("")

    if graph["isolated"]:
        lines.append(f"💡 Isolated ({len(graph['isolated'])} ideas — no connections)")
        for idea_id in graph["isolated"]:
            lines.append(f"   {format_idea_node(idea_id, ideas, degree)}")
        lines.append("")

    if wiki_index:
        lines.append(f"📝 Wiki Concepts ({len(wiki_index)})")
        for concept, ids in sorted(wiki_index.items()):
            lines.append(f"   [[{concept}]] → {', '.join(f'#{i:03d}' for i in sorted(ids))}")

    return "\n".join(lines)
