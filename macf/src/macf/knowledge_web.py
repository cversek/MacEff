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
import fnmatch
import os
import re
import json
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Iterator, List, Optional, Tuple

from .concepts import extract_not_linked, extract_wiki_concepts

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

# A task record in the home store: N.json, or .N.json when hidden.
_TASK_FILE = re.compile(r"\.?\d+\.json")


# A type folder holding this file is out of the web (scholarship policy, the
# section on opting a folder out): material that is not an artifact, such as an
# archive or a scratch dump. The exclusion is never silent: the doctor names
# every folder it removes, through excluded_type_roots below.
OPT_OUT_MARKER = ".not-in-knowledge-web"


def _opted_out(folder: Path) -> bool:
    """Whether a type folder carries the opt-out marker."""
    return (folder / OPT_OUT_MARKER).exists()


def _subagent_parents(agent_home: Path) -> List[Path]:
    """Each subagent's private and public trees, in role order."""
    subagents = agent_home / "agent" / "subagents"
    if not subagents.exists():
        return []
    return [role / base for role in sorted(p for p in subagents.iterdir() if p.is_dir())
            for base in ("private", "public")]


def _type_folders(parents: List[Path]) -> Iterator[Tuple[str, Path, bool]]:
    """(name, folder, opted_out) for each type folder under the given parents."""
    for parent in parents:
        if not parent.exists():
            continue
        for d in sorted(p for p in parent.iterdir() if p.is_dir()):
            yield d.name, d, _opted_out(d)


def _agent_parents(agent_home: Path) -> List[Path]:
    return [agent_home / "agent" / base for base in ("private", "public")]


def excluded_type_roots(agent_home: Path) -> List[Tuple[str, Path]]:
    """The (name, folder) pairs taken out of the web by the opt-out marker.

    Discovered over the same folders ``_type_roots`` walks. The doctor and
    ``knowledge status`` report these, so an exclusion is always visible to
    whoever reads the web's health.
    """
    parents = _agent_parents(agent_home) + _subagent_parents(agent_home)
    return [(name, d) for name, d, out in _type_folders(parents) if out]


def _type_roots(agent_home: Path) -> List[Tuple[str, Path]]:
    """Discover (ca_type, root) pairs from the filesystem — nothing is declared.

    Every subdirectory of ``agent/private`` and ``agent/public`` is an
    artifact-producing location; its name is its type, unless it carries the
    opt-out marker (``OPT_OUT_MARKER``). Personal policies and subagent trees
    are walked the same way. Framework policies are the one
    location outside the agent tree; the direction is safe (public policy read
    into a private web) and the reverse is forbidden — a policy must never
    link a concept that resolves only in some agent's private tree.
    """
    roots: List[Tuple[str, Path]] = [
        (name, d) for name, d, out in _type_folders(_agent_parents(agent_home)) if not out]
    personal = agent_home / "agent" / "policies" / "personal"
    if personal.exists():
        roots.append(("personal_policies", personal))
    roots.extend((name, d) for name, d, out in _type_folders(_subagent_parents(agent_home)) if not out)
    try:
        from .utils.manifest import get_framework_policies_path
        pol = get_framework_policies_path()
        if pol and pol.exists():
            roots.append(("policies", pol))
            # MIS records sit beside the policies they explain (mis policy §9): an MIS is a
            # whole-document node, and its Wiki-Links must reach the web it promises.
            mis_dir = pol.parent / "mis"
            if mis_dir.is_dir():
                roots.append(("mis", mis_dir))
    except (OSError, ImportError):
        pass
    # The task store participates wherever it is configured to live. It sits
    # under the agent tree by default, but MACF_TASK_STORE_DIR or the
    # task_store config can move it, and a moved store must not silently drop
    # out of the web while task links are still being written into it.
    try:
        from .task.reader import TaskReader
        store = TaskReader._resolve_home_store()
    except (OSError, ImportError, ValueError) as e:
        print(f"⚠️ MACF: task store not resolved for the web: {e}", file=sys.stderr)
        store = None
    if store is not None and store.is_dir() and not _opted_out(store):
        known = {r.resolve() for _, r in roots}
        if store.resolve() not in known:
            roots.append(("tasks", store))
    return roots


def iter_web_files(agent_home: Path) -> Iterator[Tuple[str, Path, Path]]:
    """Yield (ca_type, type_root, path) for every file the web would consider.

    This is the ONE walk — the builder and any doctor examine the same files
    by calling this, so a checker cannot drift from the thing it checks by
    keeping its own copy of the traversal.
    """
    for ca_type, root in _type_roots(agent_home):
        yield from _walk_type(ca_type, root)


# Directories that hold tools' files, never artifacts, defined in the
# scholarship policy (no participation registry: a tool's directory is not an
# artifact-producing location). An experiment that vendors a JavaScript bundle
# brings thousands: on one agent's tree, 7,700 of the 8,300 directories the web
# walked, twice per `knowledge status`, for no participating file.
_TOOL_DIRS = frozenset({"node_modules", "__pycache__", ".git", ".venv",
                        ".pytest_cache", ".mypy_cache", ".ruff_cache"})


def _files_under(root: Path, pattern: str) -> List[Path]:
    """Files under `root` whose name matches `pattern`, sorted, skipping tool
    directories. Like rglob, it does not follow symlinked directories."""
    found: List[Path] = []
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [d for d in dirnames if d not in _TOOL_DIRS]
        found.extend(Path(dirpath) / n for n in filenames if fnmatch.fnmatchcase(n, pattern))
    return sorted(found)


def _walk_type(ca_type: str, root: Path) -> Iterator[Tuple[str, Path, Path]]:
    """The per-type walk: markdown units, plus duty records under a roles root."""
    unit = _UNIT_OF_NODE.get(ca_type)
    for f in _files_under(root, "*.md"):
        if f.name == "INDEX.md":
            continue
        if unit is not None and f.stem not in unit:
            continue
        yield ca_type, root, f
    if ca_type == "roles":
        # Duties are JSON records with a wiki_links field, as ideas are; they
        # participate through the same walk so the doctor sees them too.
        for f in _files_under(root, "DUTY_*.json"):
            yield "duties", root, f
    if ca_type == "tasks":
        # Task records carry wiki_links in their metadata (task_management:
        # knowledge web participation). A hidden task is stored as .N.json.
        for f in sorted(root.glob("*.json")):
            if _TASK_FILE.fullmatch(f.name):
                yield "tasks", root, f


@dataclass(frozen=True, kw_only=True)
class TaskRecord:
    """What the web reads from one task record."""
    id: str
    title: str
    concepts: List[str]
    not_linked: List[str]


def task_record(content: str, path: Optional[Path] = None) -> Optional[TaskRecord]:
    """The id, title and concepts of a task record, or None if it is not one.

    The metadata is only parsed when it mentions wiki_links, so a walk over a
    store of mostly linkless tasks stays cheap.
    """
    try:
        rec = json.loads(content)
    except ValueError as e:
        print(f"⚠️ MACF: task record {path or ''} unreadable for the web: {e}", file=sys.stderr)
        return None
    if not isinstance(rec, dict) or "id" not in rec:
        return None
    concepts: List[str] = []
    not_linked: List[str] = []
    desc = rec.get("description") or ""
    if "wiki_links" in desc or "not_linked" in desc:
        from .task.models import MacfTaskMetaData
        from .concepts import normalize_concepts
        mtmd = MacfTaskMetaData.parse(desc)
        if mtmd:
            concepts = normalize_concepts(mtmd.wiki_links)
            not_linked = normalize_concepts(mtmd.not_linked)
    title = re.sub(r"\x1b\[[0-9;]*m", "", str(rec.get("subject", ""))).strip()[:50]
    return TaskRecord(id=str(rec["id"]), title=title or f"task #{rec['id']}", concepts=concepts,
                      not_linked=not_linked)


def concepts_of(ca_type: str, path: Path, content: str) -> List[str]:
    """The concepts a walked file carries: [[links]] in markdown, the
    wiki_links field in a duty record or in a task's metadata."""
    if ca_type == "tasks" and path.suffix == ".json":
        rec = task_record(content, path)
        return rec.concepts if rec else []
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
            if not scan_dir.exists() or _opted_out(scan_dir):
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
        if ca_type == "tasks" and md_file.suffix == ".json":
            rec = task_record(content, md_file)
            if not rec or not rec.concepts:
                continue
            node_id = f"tasks:#{rec.id}"
            ca_nodes[node_id] = {"type": "tasks", "title": rec.title, "path": str(md_file),
                                 "node_class": node_class_for("tasks"), "not_linked": rec.not_linked}
            for concept in rec.concepts:
                wiki_index[concept].add(node_id)
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
                             "node_class": node_class_for(ca_type),
                             "not_linked": extract_not_linked(content)}
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


# The expansion threshold's default: a neighbour is admitted only through a concept at least this
# specific (inverse document frequency over the web). Chosen with `knowledge eval` on the dev split
# and confirmed once on the held split; see the scholarship policy on how results are ordered.
DEFAULT_MIN_IDF = 2.0


def _stable(node_id: Any) -> str:
    """A tie-break that is deterministic and carries no meaning. Name order is not used, since a
    result list in string order is the defect ranking replaces."""
    import hashlib
    return hashlib.sha256(str(node_id).encode()).hexdigest()


def concept_idf(kg: Dict[str, Any]) -> Dict[str, float]:
    """Each concept's inverse document frequency over the web's nodes: rare concepts weigh more."""
    import math
    n = len(kg["ideas"]) + len(kg.get("ca_nodes", {}))
    return {c: math.log(n / len(m)) for c, m in kg.get("wiki_index", {}).items() if m and n}


@dataclass(frozen=True, kw_only=True)
class _TermMatch:
    """What one query term matched: its nodes, the concepts it named, and how it matched."""
    nodes: frozenset
    named: frozenset
    kind: str


def _resolve_term(term: str, kg: Dict[str, Any]) -> _TermMatch:
    """Resolve a term: an exact concept, then a node id, then a keyword in titles and concept names."""
    ideas, ca_nodes, wiki_index = kg["ideas"], kg.get("ca_nodes", {}), kg.get("wiki_index", {})
    normalized = re.sub(r'^\[\[|\]\]$', '', re.sub(r'\.md$', '', term.lower().strip()))
    if normalized in wiki_index:
        return _TermMatch(nodes=frozenset(wiki_index[normalized]), named=frozenset({normalized}),
                          kind=f"concept: [[{normalized}]]")
    m = re.match(r'#?(\d+)$', term.strip())
    if m and int(m.group(1)) in ideas:
        return _TermMatch(nodes=frozenset({int(m.group(1))}), named=frozenset(), kind=f"idea: #{int(m.group(1)):03d}")
    if ":" in term:
        found = {ca for ca in ca_nodes if term.strip() in ca}
        if found:
            return _TermMatch(nodes=frozenset(found), named=frozenset(), kind=f"ca: {term.strip()}")
    low = term.lower()
    matched = {i for i, idea in ideas.items() if low in idea.get("title", "").lower()}
    matched |= {ca for ca, info in ca_nodes.items() if low in info.get("title", "").lower() or low in ca.lower()}
    named = {c for c in wiki_index if low in c}
    for c in named:
        matched |= wiki_index[c]
    return _TermMatch(nodes=frozenset(matched), named=frozenset(named), kind=f'keyword: "{term}"' if matched else "")


def _node_by_id(node: str, kg: Dict[str, Any]) -> Any:
    """The web node an id names: an idea number, an exact CA id, or the one CA id containing it."""
    ideas, ca_nodes = kg["ideas"], kg.get("ca_nodes", {})
    m = re.match(r'#?(\d+)$', node.strip())
    if m and int(m.group(1)) in ideas:
        return int(m.group(1))
    if node in ca_nodes:
        return node
    found = [ca for ca in ca_nodes if node.strip() in ca]
    if len(found) == 1:
        return found[0]
    if found:
        raise ValueError(f"--like {node!r} names {len(found)} nodes; give more of the id, e.g. {found[0]}")
    raise ValueError(f"--like {node!r} names no node in the knowledge web")


def query_knowledge_web(term: Any = "", kg: Optional[Dict[str, Any]] = None, *, like: Optional[str] = None,
                        any_term: bool = False, min_idf: float = DEFAULT_MIN_IDF) -> Dict[str, Any]:
    """Query the knowledge web, and rank what it returns.

    ``term`` is one term or a list of them: each a concept, a node id (#007, learnings:...), or a
    keyword in titles and concept names. Several terms match nodes that answer every term, or any
    of them with ``any_term``. ``like`` names a node instead: the query is that node's concepts,
    "what bears on this artifact".

    Ranking: a matched node scores the summed inverse document frequency (IDF) of the query
    concepts it carries, plus how strongly it is tied into the rest of the match through specific
    concepts. A neighbour is admitted only through a concept whose IDF is at least ``min_idf``, and
    scores by the same tie. Equal scores go to the node with fewer concepts first, since it is
    more specifically about what it shares with the query; then a stable hash, never the name.

    Returns the subweb: ranked matched nodes and neighbours, each with its score and the concepts
    it matched through, and the shared concepts.
    """
    if kg is None:
        kg = build_knowledge_web()
    ideas, ca_nodes = kg["ideas"], kg.get("ca_nodes", {})
    edges, wiki_index = kg["edges"], kg.get("wiki_index", {})
    idf = concept_idf(kg)
    concepts_of: Dict[Any, set] = {}
    for c, members in wiki_index.items():
        for nid in members:
            concepts_of.setdefault(nid, set()).add(c)
    terms = [term] if isinstance(term, str) else list(term or [])
    label = like if like else " ".join(terms)

    neighbours: Dict[Any, float] = {}
    via: Dict[Any, List[str]] = {}
    if like:
        source = _node_by_id(like, kg)
        query = concepts_of.get(source, set())
        candidates = {x for c in query if idf.get(c, 0.0) >= min_idf for x in wiki_index.get(c, ())} - {source}
        matched = {x: sum(idf.get(c, 0.0) for c in query & concepts_of.get(x, set())) for x in candidates}
        for x in candidates:
            via[x] = sorted(query & concepts_of.get(x, set()), key=lambda c: -idf.get(c, 0.0))
        match_type = f"like: {source}"
    else:
        sets, named, kinds = [], set(), []
        for t in terms:
            match = _resolve_term(t, kg)
            if match.kind:
                sets.append(set(match.nodes))
                named |= match.named
                kinds.append(match.kind)
            elif not any_term:
                sets = []
                break
        hits = (set().union(*sets) if any_term else set.intersection(*sets)) if sets else set()
        if not hits:
            return {"match_type": "none", "term": label, "nodes": [], "neighbors": [],
                    "concepts": [], "edges": 0}
        match_type = "; ".join(kinds) + (" (any)" if any_term and len(kinds) > 1 else "")

        def tie(x: Any, within: set) -> Tuple[float, List[str]]:
            """How strongly x is tied into ``within``: each specific concept it shares, weighted by
            its IDF and by the share of ``within`` that carries it."""
            score, through = 0.0, []
            for c in concepts_of.get(x, set()) - named:
                w = idf.get(c, 0.0)
                share = len(wiki_index.get(c, set()) & within - {x}) / len(within)
                if w >= min_idf and share:
                    score += w * share
                    through.append(c)
            return score, sorted(through, key=lambda c: -idf.get(c, 0.0))

        matched = {}
        for x in hits:
            base = sum(idf.get(c, 0.0) for c in named & concepts_of.get(x, set()))
            extra, through = tie(x, hits)
            matched[x] = base + extra
            via[x] = sorted(named & concepts_of.get(x, set())) + through[:3]
        # A prefilter only: tie() counts no concept under min_idf, so a node reached through none
        # scores 0 and is dropped below either way.
        expansion = {c for x in hits for c in concepts_of.get(x, set()) - named if idf.get(c, 0.0) >= min_idf}
        for x in {y for c in expansion for y in wiki_index.get(c, ())} - hits:
            score, through = tie(x, hits)
            if score:
                neighbours[x], via[x] = score, through[:3]

    def order(x: Any, score: float) -> Tuple[float, int, str]:
        return (-score, len(concepts_of.get(x, ())), _stable(x))  # noqa: MACEFF004 - a sort key, compared positionally by design
    ranked = sorted(matched, key=lambda x: order(x, matched[x]))
    ranked_n = sorted(neighbours, key=lambda x: order(x, neighbours[x]))
    all_subgraph = set(matched) | set(neighbours)
    relevant_concepts = sorted(((c, len(m & all_subgraph)) for c, m in wiki_index.items()
                                if len(m & all_subgraph) >= 2), key=lambda x: (-x[1], x[0]))

    def _node_info(node_id: Any, score: float) -> Optional[Dict[str, Any]]:
        extra = {"score": round(score, 3), "via": via.get(node_id, [])[:4]}
        if isinstance(node_id, int) and node_id in ideas:
            idea = ideas[node_id]
            return {
                "id": str(node_id), "label": f"#{node_id:03d}",
                "title": idea.get("title", ""), "type": "idea",
                "status": idea.get("status", ""), "category": idea.get("category", ""),
                "degree": len(edges.get(node_id, set())),
                # An idea is prospective, but its claim is meant to outlive the
                # moment; status carries the proposal-versus-finding weighting.
                "node_class": "conceptual_authority", **extra,
            }
        if node_id in ca_nodes:
            info = ca_nodes[node_id]
            return {
                "id": str(node_id), "label": str(node_id).split(":")[-1][:25],
                "title": info.get("title", ""), "type": info.get("type", "ca"),
                "status": "", "category": info.get("type", ""),
                "degree": len(edges.get(node_id, set())),
                "node_class": info.get("node_class", "conceptual_authority"), **extra,
            }
        return None

    subgraph_edges = sum(1 for x in all_subgraph for y in edges.get(x, set()) if y in all_subgraph) // 2
    return {
        "match_type": match_type,
        "term": label,
        "min_idf": min_idf,
        "nodes": [n for n in (_node_info(x, matched[x]) for x in ranked) if n],
        "neighbors": [n for n in (_node_info(x, neighbours[x]) for x in ranked_n) if n],
        "concepts": [{"concept": c, "members": n} for c, n in relevant_concepts],
        "edges": subgraph_edges,
    }


def format_query_result(result: Dict[str, Any]) -> str:
    """Format query_knowledge_web result for terminal output."""
    from .ideas import STATUS_ICON

    if result["match_type"] == "none":
        return f"No matches for \"{result['term']}\" in knowledge web."

    def _via(n: Dict[str, Any]) -> str:
        return f"  via {', '.join(n['via'][:3])}" if n.get("via") else ""

    lines = [
        f"🔍 Query: {result['match_type']}",
        f"   {len(result['nodes'])} matched, {len(result['neighbors'])} neighbors, "
        f"{result['edges']} edges in subweb; ranked by IDF score, neighbours through concepts "
        f"with IDF ≥ {result.get('min_idf', DEFAULT_MIN_IDF)}",
        "",
    ]

    if result["nodes"]:
        lines.append("📌 Matched:")
        for n in result["nodes"]:
            icon = STATUS_ICON.get(n.get("status", ""), "📄") if n["type"] == "idea" else (
                "📝" if n["type"] == "learnings" else "🔭" if n["type"] == "observations" else "📄")
            cat = f"  [{n['category']}]" if n.get("category") else ""
            lines.append(f"   {n['score']:6.2f}  {icon} {n['label']} {n['title'][:50]}{cat}{_via(n)}")

    if result["neighbors"]:
        lines.append("")
        lines.append("🔗 Neighbors:")
        for n in result["neighbors"]:
            icon = STATUS_ICON.get(n.get("status", ""), "📄") if n["type"] == "idea" else (
                "📝" if n["type"] == "learnings" else "🔭" if n["type"] == "observations" else "📄")
            lines.append(f"   {n['score']:6.2f}  {icon} {n['label']} {n['title'][:50]}{_via(n)}")

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


def detect_web_gaps(kg: Optional[Dict[str, Any]] = None,
                    include_rejected: bool = False) -> List[Dict[str, Any]]:
    """Detect missing wiki-links by comparing node title keywords with wiki concepts.

    For each node with degree < 3, extract title keywords and check overlap
    with existing wiki concepts. Returns gap suggestions sorted by confidence.
    A concept the artifact has declined (its ``not_linked``) is left out, or
    with ``include_rejected`` kept and marked ``rejected``.
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

    def _check_node(node_id, title: str, node_type: str, node_degree: int, declined=()):
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
            rejected = concept in declined
            if rejected and not include_rejected:
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
                "rejected": rejected,
            })

    # Check ideas. Archived ideas are retired seeds -- suggesting new links
    # for them is pure noise, so they are excluded from gap analysis (they
    # stay in the web itself for historical edges).
    for idea_id, idea in ideas.items():
        if idea.get("status") == "archived":
            continue
        deg = len(edges.get(idea_id, set()))
        from .concepts import normalize_concepts
        declined = set(normalize_concepts(idea.get("links", {}).get("not_linked") or []))
        _check_node(idea_id, idea.get("title", ""), "idea", deg, declined)

    # Check CA nodes
    for ca_id, info in ca_nodes.items():
        deg = len(edges.get(ca_id, set()))
        _check_node(ca_id, info.get("title", ""), info.get("type", "ca"), deg,
                    set(info.get("not_linked") or ()))

    # Sort by confidence descending
    gaps.sort(key=lambda g: (-g["confidence"], g["node_id"]))
    return gaps


_KEYWORDS_LINE = re.compile(r"\*\*Keywords\*\*:\s*(.+)|^keywords:\s*(.+)$", re.MULTILINE)


def declared_keywords(content: str) -> List[str]:
    """The subject terms an author declared: a ``**Keywords**:`` line, or a
    ``keywords:`` front-matter field. Tokens written in ALL CAPS are activation
    markers (the learnings policy's LEARN), not subjects, and are skipped."""
    m = _KEYWORDS_LINE.search(content[:4000])
    if not m:
        return []
    from .concepts import normalize_concepts
    raw = [t.strip() for t in re.split(r"[,;]", m.group(1) or m.group(2))]
    return normalize_concepts(t for t in raw if t and not (t.isupper() and t.replace("_", "").isalpha()))


def suggest_concepts(kg: Optional[Dict[str, Any]] = None, min_members: int = 3) -> List[Dict[str, Any]]:
    """Keywords several artifacts declare that no concept carries yet.

    A concept exists only once something links it, so a subject that many
    artifacts name can have no node at all. An author who wrote a keyword and
    never linked it has already said what the artifact is about; this finds the
    keywords at least ``min_members`` artifacts share. Every walked file is
    read, orphans included, since those are the likeliest members.

    Titles were measured as the source first and rejected: on one corpus they
    produced 868 candidates led by "learn", "complete" and "checkpoint", while
    declared keywords produced 95 led by real subjects. The cost is coverage:
    only artifacts that declare keywords are seen.
    """
    from collections import defaultdict
    from .utils.paths import find_agent_home

    kg = kg or build_knowledge_web()
    covered = set(kg.get("wiki_index", {}))
    members: Dict[str, List[str]] = defaultdict(list)
    agent_home = find_agent_home()
    for _ca_type, _root, path in (iter_web_files(agent_home) if agent_home else []):
        if path.suffix != ".md":
            continue
        try:
            content = path.read_text(errors="replace")
        except OSError:
            continue
        for kw in declared_keywords(content):
            if len(kw) > 3 and kw not in covered:
                members[kw].append(str(path))
    out = [{"concept": k, "count": len(v), "members": v} for k, v in members.items() if len(v) >= min_members]
    out.sort(key=lambda d: (-d["count"], d["concept"]))
    return out


def format_concept_suggestions(suggestions: List[Dict[str, Any]], limit: int = 25) -> str:
    if not suggestions:
        return "No declared keyword is shared by several artifacts without a concept."
    lines = [f"🧩 {len(suggestions)} declared keywords shared by several artifacts with no concept yet", ""]
    for s in suggestions[:limit]:
        shown = ", ".join(Path(m).stem for m in s["members"][:4])
        more = f" +{s['count'] - 4}" if s["count"] > 4 else ""
        lines.append(f"  [[{s['concept']}]]  {s['count']} artifacts: {shown}{more}")
    if len(suggestions) > limit:
        lines.append(f"  ... {len(suggestions) - limit} more (--json for all)")
    lines.append("")
    lines.append("💡 A real subject becomes a concept with one knowledge link per member; "
                 "query it first so it does not duplicate one that exists under another name.")
    return "\n".join(lines)


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
        if g.get("rejected"):
            concept = f"✗ {concept}"
        conf = f"{g['confidence']:.0%}"
        cluster = g["target_cluster"][:25]
        lines.append(f"{node_label:<30} {concept:<22} {conf:>5}  {cluster}")

    lines.append("")
    lines.append("💡 knowledge link <node> <concept> to accept a suggestion; "
                 "knowledge gaps --reject <node> <concept> to stop it being suggested.")
    if any(g.get("rejected") for g in gaps):
        lines.append("   ✗ marks a suggestion the artifact has already declined.")
    return "\n".join(lines)
