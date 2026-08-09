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
from typing import Any, Dict, List, Optional, Tuple


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


from .concepts import extract_wiki_concepts, normalize_concept, normalize_concepts  # noqa: F401


def _normalize_wiki_links(raw: List[str]) -> List[str]:
    """Backwards-compatible alias for the canonical concept normalizer.

    Retained so existing call sites keep working; the implementation lives in
    ``macf.concepts`` because concepts belong to no single CA type. Note the
    behaviour change this alias inherits: hyphens now normalize to underscores
    rather than surviving, per the scholarship policy's spelling rule.
    """
    return normalize_concepts(raw)


def create_idea(
    title: str,
    category: str,
    description: str,
    sparked_by: str = "",
    feasibility: str = "",
    reasoning: str = "",
    hypothesis: str = "",
    context: str = "",
    wiki_links: Optional[List[str]] = None,
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
            "wiki_links": _normalize_wiki_links(wiki_links or []),
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
    wiki_links: Optional[List[str]] = None,
    remove_wiki_links: Optional[List[str]] = None,
) -> Optional[Dict[str, Any]]:
    """Update an idea's status, promotion target, or wiki-links.

    `wiki_links` are normalized and merged into the existing set (order
    preserved, duplicates dropped); `remove_wiki_links` prunes links found to be
    spurious during curation. Both accept the same loose forms as `create_idea`
    ("Foo Bar", "[[foo_bar]]", "foo_bar").
    """
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

    if wiki_links or remove_wiki_links:
        links = idea.setdefault("links", {})
        current = list(links.get("wiki_links") or [])
        if wiki_links:
            added = [w for w in _normalize_wiki_links(wiki_links) if w not in current]
            current.extend(added)
            if added:
                idea.setdefault("history", []).append({
                    "timestamp": ts_str,
                    "action": f"wiki_links_added:{','.join(added)}",
                    "breadcrumb": breadcrumb,
                })
        if remove_wiki_links:
            drop = set(_normalize_wiki_links(remove_wiki_links))
            removed = [w for w in current if w in drop]
            current = [w for w in current if w not in drop]
            if removed:
                idea.setdefault("history", []).append({
                    "timestamp": ts_str,
                    "action": f"wiki_links_removed:{','.join(removed)}",
                    "breadcrumb": breadcrumb,
                })
        links["wiki_links"] = current

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
            # Accept both bracketed (`[[concept]]`) and bare (`concept`) forms
            # in the JSON array. Bracketed form lets ideas use the same syntax
            # as markdown CAs ([[concept]] in body); bare form is the more
            # natural JSON-array shape and the one the cross-CA index expects
            # (concept keys in wiki_index are stored sans brackets). Without
            # this, ideas with bare-concept arrays never enter wiki_index and
            # the idea↔learning bridge breaks at the seam — closes GH #87.
            if not isinstance(wl, str) or not wl.strip():
                continue
            raw = wl.strip()
            m = re_mod.match(r'^\[\[(.+?)\]\]$', raw)
            concept = m.group(1) if m else raw
            # Normalize: strip .md suffix for consistent matching
            concept = re_mod.sub(r'\.md$', '', concept)
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

