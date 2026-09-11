"""The cross-CA knowledge web: concept-mediated edges over consciousness artifacts.

Extracted from ``ideas.py``, where the cross-CA layer had accreted inside the
module for one CA type — every consumer was importing cross-CA machinery from
``ideas``, which is how a second registry gets born one import at a time.

**There is no participation registry.** Participation is emergent: writing
``[[links]]`` into an artifact IS the act of joining the web, and a file
without concepts simply never becomes a node. Scan locations are discovered
from the filesystem, not declared — every artifact-producing directory under
the agent tree is walked, plus the framework policies. The only per-type
knowledge in this module is a pair of derivation rules (unit-of-node and
node class) that *execute* definitions owned by the CA-type policies; the
policy defines the distinction, this code merely applies it (Policy-as-Spec).

Terminology (deliberate, see the operator's WWW/Internet distinction): the
artifact this module builds is the **web** — one link type, concept-mediated,
undirected. The **graph** is the substrate that could also host citations,
task hierarchy, blockedBy, lineage, promoted_to and provenance edges; of the
graph's possible protocols only the web exists so far, and naming the web
"graph" is how the unbuilt remainder disappears into the name.
"""
import re
import json
import sys
from pathlib import Path
from typing import Any, Dict, Iterator, List, Optional, Tuple

from .concepts import extract_wiki_concepts

# Unit-of-node: which files in a type's directory carry the claims. Defined by
# each CA-type policy's "Knowledge Web Participation" section and executed
# here; everything not named is evidence the claiming file cites.
#   experiments: protocol and analysis carry the claims; data/, artifacts/ and
#                quick_tests/ hold the evidence (experiments policy).
#   roadmaps:    the plan is the node; archived todos, designs and subartifacts
#                are execution records (roadmaps policies).
#   roles:       the charter is the node; data.json holds the appointment's
#                facts and changes without the charter being wrong; each
#                DUTY_*.json is its own node of type "duties" (roles policy).
_UNIT_OF_NODE: Dict[str, set] = {
    "experiments": {"protocol", "analysis"},
    "roadmaps": {"roadmap"},
    "roles": {"charter"},
}

# Node class: what kind of claim a type's nodes make. The classes are defined
# once in the scholarship policy on node classes and provenance; which class
# each type belongs to is stated in that type's policy and executed here.
# Types without a stated class default to conceptual_authority until their
# policy says otherwise.
_NODE_CLASS: Dict[str, str] = {
    "policies": "normative",           # framework policies (scholarship)
    "personal_policies": "normative",  # same class, lived provenance
    "checkpoints": "temporal_record",  # checkpoints policy
    "roadmaps": "temporal_record",     # roadmaps policies
    "sprints": "temporal_record",      # execution records
    "amail": "temporal_record",        # correspondence records
    "roles": "conceptual_authority",   # a charter outlives its cycle (roles policy)
    "duties": "conceptual_authority",  # prospective, read with its state (roles policy)
    "tasks": "temporal_record",        # a duty's evidence or tracks pointer into the task store
}
_DEFAULT_CLASS = "conceptual_authority"


def _type_roots(agent_home: Path) -> List[Tuple[str, Path]]:
    """Discover (ca_type, root) pairs from the filesystem — nothing is declared.

    Every subdirectory of ``agent/private`` and ``agent/public`` is an
    artifact-producing location; its name is its type. Personal policies and
    subagent trees are walked the same way. Framework policies are the one
    location outside the agent tree; the direction is safe (public policy read
    into a private web) and the reverse is forbidden — a policy must never
    link a concept that resolves only in some agent's private tree.
    """
    roots: List[Tuple[str, Path]] = []
    for base in ("private", "public"):
        parent = agent_home / "agent" / base
        if not parent.exists():
            continue
        for d in sorted(p for p in parent.iterdir() if p.is_dir()):
            roots.append((d.name, d))
    personal = agent_home / "agent" / "policies" / "personal"
    if personal.exists():
        roots.append(("personal_policies", personal))
    subagents = agent_home / "agent" / "subagents"
    if subagents.exists():
        for role in sorted(p for p in subagents.iterdir() if p.is_dir()):
            for base in ("private", "public"):
                parent = role / base
                if not parent.exists():
                    continue
                for d in sorted(p for p in parent.iterdir() if p.is_dir()):
                    roots.append((d.name, d))
    try:
        from .utils.manifest import get_framework_policies_path
        pol = get_framework_policies_path()
        if pol and pol.exists():
            roots.append(("policies", pol))
    except (OSError, ImportError):
        pass
    return roots


def iter_web_files(agent_home: Path) -> Iterator[Tuple[str, Path, Path]]:
    """Yield (ca_type, type_root, path) for every file the web would consider.

    This is the ONE walk — the builder and any doctor examine the same files
    by calling this, so a checker cannot drift from the thing it checks by
    keeping its own copy of the traversal.
    """
    for ca_type, root in _type_roots(agent_home):
        yield from _walk_type(ca_type, root)


def _walk_type(ca_type: str, root: Path) -> Iterator[Tuple[str, Path, Path]]:
    """The per-type walk: markdown units, plus duty records under a roles root."""
    unit = _UNIT_OF_NODE.get(ca_type)
    for f in sorted(root.rglob("*.md")):
        if f.name == "INDEX.md":
            continue
        if unit is not None and f.stem not in unit:
            continue
        yield ca_type, root, f
    if ca_type == "roles":
        # Duties are JSON records with a wiki_links field, as ideas are; they
        # participate through the same walk so the doctor sees them too.
        for f in sorted(root.rglob("DUTY_*.json")):
            yield "duties", root, f


def concepts_of(ca_type: str, path: Path, content: str) -> List[str]:
    """The concepts a walked file carries: [[links]] in markdown, the
    wiki_links field in a duty record."""
    if ca_type == "duties":
        try:
            import json as _json
            from .concepts import normalize_concepts
            return normalize_concepts(_json.loads(content).get("wiki_links") or [])
        except (ValueError, TypeError, AttributeError) as e:
            print(f"⚠️ MACF: duty record {path} unreadable for the web: {e}", file=sys.stderr)
            return []
    return extract_wiki_concepts(content)


def _pointer_node(pointer: str, path_to_node: Dict[str, str], ca_nodes: Dict[str, Any]) -> Optional[str]:
    """Resolve a duty's tracks/evidence pointer to a node id.

    A task id becomes a `tasks:#N` node (temporal record, titled from the task
    store when it can be read) so the edge from a duty to its implementation
    exists even though tasks are not walked; a CA path resolves to the node
    that file already is, or to nothing if the file is not a node.
    """
    import re as re_mod
    ref = pointer.strip()
    if re_mod.fullmatch(r"#?\d+", ref):
        tid = ref.lstrip("#")
        node_id = f"tasks:#{tid}"
        if node_id not in ca_nodes:
            title = f"task #{tid}"
            try:
                from .task import TaskReader
                t = TaskReader().read_task(tid)
                if t:
                    title = re_mod.sub(r"\x1b\[[0-9;]*m", "", t.subject).strip()[:50]
            except (OSError, ValueError, ImportError, AttributeError):
                pass  # the store may be absent under a scan_dirs build; the id still names the task
            ca_nodes[node_id] = {"type": "tasks", "title": title, "path": f"task:{tid}",
                                 "node_class": node_class_for("tasks")}
        return node_id
    candidates = [Path(ref)]
    try:
        from .utils.paths import find_agent_home
        candidates.append(find_agent_home() / ref)
    except (OSError, ImportError):
        pass
    for c in candidates:
        try:
            hit = path_to_node.get(str(c.resolve()))
        except OSError:
            hit = None
        if hit:
            return hit
    return None


def node_class_for(ca_type: str) -> str:
    """The node class a type's policy assigns it (default: conceptual authority)."""
    return _NODE_CLASS.get(ca_type, _DEFAULT_CLASS)


def build_knowledge_web(scan_dirs: Optional[List[Path]] = None) -> Dict[str, Any]:
    """Build the cross-CA knowledge web: ideas + markdown CAs via wiki-links.

    Scans ideas (JSON, related_ideas + wiki_links fields) and other CAs
    (markdown, ## Wiki-Links sections) for [[concept]] references.
    Nodes are CA identifiers, edges from shared wiki-link concepts.

    ``scan_dirs`` overrides discovery for tests and ad-hoc scans: each entry is
    treated as a type root whose name is its type.
    """
    import re as re_mod
    from collections import defaultdict

    from .ideas import build_idea_graph

    # Start with ideas graph
    graph = build_idea_graph()
    wiki_index = defaultdict(set, {k: set(v) for k, v in graph["wiki_index"].items()})
    ca_nodes = {}  # non-idea CA nodes: {node_id: {type, title, path}}

    if scan_dirs is not None:
        walk = []
        for scan_dir in scan_dirs:
            if not scan_dir.exists():
                continue
            walk.extend(_walk_type(scan_dir.name, scan_dir))
    else:
        walk = []
        try:
            from .utils.paths import find_agent_home
            agent_home = find_agent_home()
            if agent_home:
                walk = list(iter_web_files(agent_home))
        except (OSError, ImportError) as e:
            print(f"⚠️ MACF: knowledge web scan failed: {e}", file=sys.stderr)

    duty_records = []          # (node_id, record) for the structural edges below
    path_to_node: Dict[str, str] = {}
    for ca_type, type_root, md_file in walk:
        try:
            content = md_file.read_text(errors='replace')
        except OSError:
            continue
        if ca_type == "duties":
            try:
                rec = json.loads(content)
            except ValueError:
                continue
            node_id = f"duties:{rec.get('id', md_file.stem)}"
            ca_nodes[node_id] = {"type": "duties", "title": str(rec.get("title", md_file.stem))[:50],
                                 "path": str(md_file), "node_class": node_class_for("duties"),
                                 "state": rec.get("state"), "role_id": rec.get("role_id")}
            for concept in concepts_of(ca_type, md_file, content):
                wiki_index[concept].add(node_id)
            duty_records.append((node_id, rec, md_file))
            continue
        concepts = extract_wiki_concepts(content)
        if not concepts:
            continue
        # Node ID relative to the type root. For nested CAs (experiments),
        # include the immediate parent folder for disambiguation.
        if md_file.parent != type_root:
            stem_part = f"{md_file.parent.name}/{md_file.stem}"
        else:
            stem_part = md_file.stem
        node_id = f"{ca_type}:{stem_part}"
        # Extract title from first heading
        title_match = re_mod.search(r'^#\s+(.+)', content, re_mod.MULTILINE)
        title = title_match.group(1)[:50] if title_match else md_file.stem[:50]
        ca_nodes[node_id] = {"type": ca_type, "title": title,
                             "path": str(md_file),
                             "node_class": node_class_for(ca_type)}
        path_to_node[str(md_file.resolve())] = node_id
        for concept in concepts:
            wiki_index[concept].add(node_id)

    # Rebuild edges including cross-CA connections
    edges = defaultdict(set)
    # Preserve idea-to-idea edges from related_ideas
    for k, v in graph["edges"].items():
        edges[k] = set(v)
    # Duties' structural edges (roles policy, knowledge web participation):
    # the parent role's charter, the tracked tasks, and the evidence that
    # satisfied the duty -- a task id, or a CA path resolved to its node.
    for node_id, rec, duty_path in duty_records:
        charter = duty_path.parent / "charter.md"
        charter_node = path_to_node.get(str(charter.resolve()))
        if charter_node is None and charter.exists():
            # A charter with no links is not a node yet; the duty still points
            # at it, so the edge names the folder the way a node would.
            charter_node = f"roles:{duty_path.parent.name}/charter"
            ca_nodes.setdefault(charter_node, {"type": "roles", "title": duty_path.parent.name[:50],
                                               "path": str(charter), "node_class": node_class_for("roles")})
        if charter_node:
            edges[node_id].add(charter_node)
            edges[charter_node].add(node_id)
        for pointer in list(rec.get("tracks") or []) + list(rec.get("evidence") or []):
            target = _pointer_node(str(pointer), path_to_node, ca_nodes)
            if target:
                edges[node_id].add(target)
                edges[target].add(node_id)
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


def format_web_cluster_cross_ca(kg: Dict[str, Any]) -> str:
    """Format the cross-CA knowledge web as cluster view."""
    from .ideas import STATUS_ICON

    ideas = kg["ideas"]
    ca_nodes = kg["ca_nodes"]
    edges = kg["edges"]
    wiki_index = kg["wiki_index"]
    stats = kg["stats"]

    # Compute degree for all nodes
    degree = {}
    for node_id in set(ideas.keys()) | set(ca_nodes.keys()):
        degree[node_id] = len(edges.get(node_id, set()))

    # BFS connected components across all node types
    all_node_ids = set(ideas.keys()) | set(ca_nodes.keys())
    visited = set()
    components = []
    for node_id in sorted(all_node_ids, key=str):
        if node_id in visited or not edges.get(node_id):
            continue
        component = []
        queue = [node_id]
        while queue:
            node = queue.pop(0)
            if node in visited or node not in all_node_ids:
                continue
            visited.add(node)
            component.append(node)
            for neighbor in sorted(edges.get(node, set()), key=str):
                if neighbor not in visited and neighbor in all_node_ids:
                    queue.append(neighbor)
        components.append(component)

    isolated = sorted([n for n in all_node_ids if n not in visited], key=str)

    lines = [f"📊 Cross-CA Knowledge Web ({stats['total_nodes']} nodes, {stats['total_edges']} edges)", ""]

    for idx, component in enumerate(components):
        idea_ids = [n for n in component if isinstance(n, int)]
        ca_ids = [n for n in component if isinstance(n, str)]
        cluster_concepts = [c for c, ids in wiki_index.items() if len(ids & set(component)) >= 2]
        concept_str = f"  via: {', '.join(f'[[{c}]]' for c in sorted(cluster_concepts))}" if cluster_concepts else ""
        lines.append(f"🌐 Cluster {idx+1} ({len(component)} nodes: {len(idea_ids)} ideas + {len(ca_ids)} CAs){concept_str}")
        for idea_id in sorted(idea_ids):
            idea = ideas.get(idea_id, {})
            icon = STATUS_ICON.get(idea.get("status", ""), "?")
            title = idea.get("title", "")[:50]
            deg = degree.get(idea_id, 0)
            lines.append(f"   {icon} #{idea_id:03d} {title}  (deg {deg})")
        for ca_id in sorted(ca_ids):
            info = ca_nodes.get(ca_id, {})
            ca_type = info.get("type", "")
            icon = "📝" if ca_type == "learnings" else "🔭" if ca_type == "observations" else "📄"
            title = info.get("title", "")[:50]
            deg = degree.get(ca_id, 0)
            lines.append(f"   {icon} {ca_id}  (deg {deg})")
        lines.append("")

    if isolated:
        lines.append(f"💡 Isolated ({len(isolated)} nodes — no connections)")
        for node_id in isolated:
            if isinstance(node_id, int):
                idea = ideas.get(node_id, {})
                icon = STATUS_ICON.get(idea.get("status", ""), "?")
                title = idea.get("title", "")[:50]
                lines.append(f"   {icon} #{node_id:03d} {title}")
            else:
                info = ca_nodes.get(node_id, {})
                ca_type = info.get("type", "")
                icon = "📝" if ca_type == "learnings" else "🔭"
                lines.append(f"   {icon} {node_id}")
        lines.append("")

    if wiki_index:
        lines.append(f"📝 Wiki Concepts ({len(wiki_index)})")
        for concept, ids in sorted(wiki_index.items()):
            int_ids = sorted(i for i in ids if isinstance(i, int))
            str_ids = sorted(i for i in ids if isinstance(i, str))
            idea_parts = [f"#{i:03d}" for i in int_ids]
            ca_parts = list(str_ids)
            lines.append(f"   [[{concept}]] → {', '.join(idea_parts + ca_parts)}")

    return "\n".join(lines)


def format_web_tree(graph: Dict[str, Any]) -> str:
    """Format the ideas view of the web as a tree (most-connected as roots)."""
    from .ideas import format_idea_node

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


def generate_web_html(output_path: str, kg: Optional[Dict[str, Any]] = None) -> Path:
    """Generate interactive HTML knowledge web visualization.

    Delegates to macf.viz.KnowledgeGraphViz for rendering.
    Returns the output file path.
    """
    from .viz import KnowledgeGraphViz

    if kg is None:
        kg = build_knowledge_web()
    viz = KnowledgeGraphViz(kg)
    return viz.render(output_path)


def query_knowledge_web(term: str, kg: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """Query the knowledge web for a concept, node ID, or keyword.

    Resolution order:
    1. Exact wiki concept match (e.g., "compaction")
    2. Node ID match (e.g., "#007" or "learnings:microcompact...")
    3. Keyword search across titles and concept names

    Returns subweb: matched nodes + direct neighbors + shared wiki concepts.
    """
    if kg is None:
        kg = build_knowledge_web()

    ideas = kg["ideas"]
    ca_nodes = kg.get("ca_nodes", {})
    edges = kg["edges"]
    wiki_index = kg.get("wiki_index", {})

    matched_nodes: set = set()
    match_type = ""

    # 1. Exact wiki concept match
    normalized_term = re.sub(r'\.md$', '', term.lower().strip())
    # Strip [[ ]] if user included them
    normalized_term = re.sub(r'^\[\[|\]\]$', '', normalized_term)

    if normalized_term in wiki_index:
        matched_nodes = set(wiki_index[normalized_term])
        match_type = f"concept: [[{normalized_term}]]"
    else:
        # 2. Node ID match
        # Try idea ID: "#007" or "7"
        id_match = re.match(r'#?(\d+)$', term.strip())
        if id_match:
            idea_id = int(id_match.group(1))
            if idea_id in ideas:
                matched_nodes = {idea_id}
                match_type = f"idea: #{idea_id:03d}"
        # Try CA node ID: "learnings:something"
        if not matched_nodes and ":" in term:
            for ca_id in ca_nodes:
                if term.strip() in ca_id:
                    matched_nodes.add(ca_id)
                    match_type = f"ca: {ca_id}"

        # 3. Keyword fallback
        if not matched_nodes:
            term_lower = term.lower()
            # Search in idea titles
            for idea_id, idea in ideas.items():
                if term_lower in idea.get("title", "").lower():
                    matched_nodes.add(idea_id)
            # Search in CA titles
            for ca_id, info in ca_nodes.items():
                if term_lower in info.get("title", "").lower() or term_lower in ca_id.lower():
                    matched_nodes.add(ca_id)
            # Search in wiki concepts
            for concept in wiki_index:
                if term_lower in concept:
                    matched_nodes |= wiki_index[concept]
            if matched_nodes:
                match_type = f"keyword: \"{term}\""

    if not matched_nodes:
        return {"match_type": "none", "term": term, "nodes": [], "neighbors": [],
                "concepts": [], "edges": 0}

    # Expand to neighbors
    neighbor_nodes: set = set()
    for node_id in matched_nodes:
        for neighbor in edges.get(node_id, set()):
            if neighbor not in matched_nodes:
                neighbor_nodes.add(neighbor)

    # Find shared wiki concepts for the subweb
    all_subgraph = matched_nodes | neighbor_nodes
    relevant_concepts = []
    for concept, members in wiki_index.items():
        overlap = members & all_subgraph
        if len(overlap) >= 2:
            relevant_concepts.append((concept, len(overlap)))
    relevant_concepts.sort(key=lambda x: -x[1])

    # Build result nodes
    def _node_info(node_id):
        if isinstance(node_id, int) and node_id in ideas:
            idea = ideas[node_id]
            return {
                "id": str(node_id), "label": f"#{node_id:03d}",
                "title": idea.get("title", ""), "type": "idea",
                "status": idea.get("status", ""), "category": idea.get("category", ""),
                "degree": len(edges.get(node_id, set())),
                # An idea is prospective, but its claim is meant to outlive the
                # moment; status carries the proposal-versus-finding weighting.
                "node_class": "conceptual_authority",
            }
        elif node_id in ca_nodes:
            info = ca_nodes[node_id]
            return {
                "id": str(node_id), "label": str(node_id).split(":")[-1][:25],
                "title": info.get("title", ""), "type": info.get("type", "ca"),
                "status": "", "category": info.get("type", ""),
                "degree": len(edges.get(node_id, set())),
                "node_class": info.get("node_class", "conceptual_authority"),
            }
        return None

    result_nodes = [n for n in (_node_info(nid) for nid in sorted(matched_nodes, key=str)) if n]
    result_neighbors = [n for n in (_node_info(nid) for nid in sorted(neighbor_nodes, key=str)) if n]

    # Count edges within subweb
    subgraph_edges = 0
    for node_id in all_subgraph:
        for neighbor in edges.get(node_id, set()):
            if neighbor in all_subgraph:
                subgraph_edges += 1
    subgraph_edges //= 2

    return {
        "match_type": match_type,
        "term": term,
        "nodes": result_nodes,
        "neighbors": result_neighbors,
        "concepts": [{"concept": c, "members": n} for c, n in relevant_concepts],
        "edges": subgraph_edges,
    }


def format_query_result(result: Dict[str, Any]) -> str:
    """Format query_knowledge_web result for terminal output."""
    from .ideas import STATUS_ICON

    if result["match_type"] == "none":
        return f"No matches for \"{result['term']}\" in knowledge web."

    lines = [
        f"🔍 Query: {result['match_type']}",
        f"   {len(result['nodes'])} matched, {len(result['neighbors'])} neighbors, "
        f"{result['edges']} edges in subweb",
        "",
    ]

    if result["nodes"]:
        lines.append("📌 Matched:")
        for n in result["nodes"]:
            icon = STATUS_ICON.get(n.get("status", ""), "📄") if n["type"] == "idea" else (
                "📝" if n["type"] == "learnings" else "🔭" if n["type"] == "observations" else "📄")
            cat = f"  [{n['category']}]" if n.get("category") else ""
            lines.append(f"   {icon} {n['label']} {n['title'][:50]}{cat} (deg {n['degree']})")

    if result["neighbors"]:
        lines.append("")
        lines.append("🔗 Neighbors:")
        for n in result["neighbors"]:
            icon = STATUS_ICON.get(n.get("status", ""), "📄") if n["type"] == "idea" else (
                "📝" if n["type"] == "learnings" else "🔭" if n["type"] == "observations" else "📄")
            lines.append(f"   {icon} {n['label']} {n['title'][:50]} (deg {n['degree']})")

    if result["concepts"]:
        lines.append("")
        lines.append("📝 Shared concepts:")
        for c in result["concepts"]:
            lines.append(f"   [[{c['concept']}]] ({c['members']} nodes)")

    return "\n".join(lines)


# Stop words excluded from keyword extraction
_STOP_WORDS = frozenset(
    "a an the and or but in on at to for of is it by as with from that this "
    "be are was were has have had do does did not no via use using used "
    "when how what why where which can could should would may might".split()
)


def detect_web_gaps(kg: Optional[Dict[str, Any]] = None) -> List[Dict[str, Any]]:
    """Detect missing wiki-links by comparing node title keywords with wiki concepts.

    For each node with degree < 3, extract title keywords and check overlap
    with existing wiki concepts. Returns gap suggestions sorted by confidence.
    """
    if kg is None:
        kg = build_knowledge_web()

    ideas = kg["ideas"]
    ca_nodes = kg.get("ca_nodes", {})
    edges = kg["edges"]
    wiki_index = kg.get("wiki_index", {})

    # Build set of all wiki concepts
    all_concepts = set(wiki_index.keys())
    if not all_concepts:
        return []

    # Build concept→cluster mapping (which cluster does each concept connect to?)
    # BFS connected components
    all_node_ids = set(ideas.keys()) | set(ca_nodes.keys())
    visited: set = set()
    node_to_cluster: Dict[Any, int] = {}
    cluster_labels: Dict[int, str] = {}
    cluster_idx = 0
    for node_id in sorted(all_node_ids, key=str):
        if node_id in visited or not edges.get(node_id):
            continue
        component: list = []
        queue = [node_id]
        while queue:
            node = queue.pop(0)
            if node in visited or node not in all_node_ids:
                continue
            visited.add(node)
            component.append(node)
            node_to_cluster[node] = cluster_idx
            for neighbor in sorted(edges.get(node, set()), key=str):
                if neighbor not in visited and neighbor in all_node_ids:
                    queue.append(neighbor)
        # Label cluster by its most common concepts
        cluster_concepts = [c for c, ids in wiki_index.items()
                           if len(ids & set(component)) >= 2]
        cluster_labels[cluster_idx] = ", ".join(sorted(cluster_concepts)[:3]) or f"cluster-{cluster_idx}"
        cluster_idx += 1

    gaps = []

    def _extract_keywords(text: str) -> set:
        words = set(re.findall(r'[a-z_]+', text.lower().replace("-", "_")))
        return words - _STOP_WORDS

    def _check_node(node_id, title: str, node_type: str, node_degree: int):
        if node_degree >= 3:
            return  # Well-connected nodes don't need gap analysis
        title_keywords = _extract_keywords(title)
        if not title_keywords:
            return

        # Find wiki concepts whose name overlaps with title keywords
        for concept in all_concepts:
            concept_keywords = set(concept.split("_"))
            overlap = title_keywords & concept_keywords
            if not overlap:
                continue
            # Check node isn't already connected to this concept's members
            concept_members = wiki_index[concept]
            if node_id in concept_members:
                continue  # Already linked
            # Confidence: overlap size / concept keyword count
            confidence = len(overlap) / max(len(concept_keywords), 1)
            if confidence < 0.5:
                continue
            # Find which cluster this concept belongs to
            target_cluster = None
            for member in concept_members:
                if member in node_to_cluster:
                    target_cluster = cluster_labels.get(node_to_cluster[member])
                    break

            gaps.append({
                "node_id": str(node_id),
                "node_type": node_type,
                "title": title[:60],
                "degree": node_degree,
                "suggested_concept": concept,
                "overlap_keywords": sorted(overlap),
                "confidence": round(confidence, 2),
                "target_cluster": target_cluster or "isolated",
            })

    # Check ideas. Archived ideas are retired seeds -- suggesting new links
    # for them is pure noise, so they are excluded from gap analysis (they
    # stay in the web itself for historical edges).
    for idea_id, idea in ideas.items():
        if idea.get("status") == "archived":
            continue
        deg = len(edges.get(idea_id, set()))
        _check_node(idea_id, idea.get("title", ""), "idea", deg)

    # Check CA nodes
    for ca_id, info in ca_nodes.items():
        deg = len(edges.get(ca_id, set()))
        _check_node(ca_id, info.get("title", ""), info.get("type", "ca"), deg)

    # Sort by confidence descending
    gaps.sort(key=lambda g: (-g["confidence"], g["node_id"]))
    return gaps


def format_gap_report(gaps: List[Dict[str, Any]]) -> str:
    """Format gap detection results as terminal table."""
    if not gaps:
        return "No gaps detected — all nodes are well-connected or no keyword overlap found."

    lines = [
        f"🔍 Gap Detection: {len(gaps)} suggestions",
        "",
        f"{'Node':<30} {'Suggested Concept':<22} {'Conf':>5}  {'Cluster'}",
        f"{'─'*30} {'─'*22} {'─'*5}  {'─'*25}",
    ]

    for g in gaps:
        node_label = g["node_id"]
        if g["node_type"] == "idea":
            node_label = f"#{int(g['node_id']):03d} {g['title'][:24]}"
        else:
            node_label = g["node_id"][:30]
        concept = f"[[{g['suggested_concept']}]]"
        conf = f"{g['confidence']:.0%}"
        cluster = g["target_cluster"][:25]
        lines.append(f"{node_label:<30} {concept:<22} {conf:>5}  {cluster}")

    lines.append("")
    lines.append(f"💡 Add suggested [[concepts]] to Wiki-Links sections to strengthen the knowledge web.")
    return "\n".join(lines)
