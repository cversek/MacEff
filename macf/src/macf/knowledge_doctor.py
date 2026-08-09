"""The knowledge-web specialist: reports what the graph cannot see about itself.

`knowledge gaps` compares keyword overlap between *connected* nodes, so an
artifact with no wiki-links is skipped before comparison begins. That is why a
curation run once reported "no gaps detected" while thirty consciousness
artifacts had zero edges: **a detector defined over relationships cannot see
absent relationships.** The condition the instrument most needed to report was
the one condition it was structurally unable to observe.

This doctor exists to observe it, plus the other ways the graph and the corpus
disagree. Shared vocabulary lives in ``macf.diagnostics``; the checks here are
specific to this corpus.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any, Dict, List, Optional

from .concepts import extract_wiki_concepts, normalize_concept
from .diagnostics import Chart, Diagnosis, Finding, Severity

__all__ = ["examine"]

# Spellings that normalize to the same concept but are written differently in
# source. Harmless to the graph now that extraction normalizes, but they are
# what a reader copies when adding links to a new artifact — so drift spreads
# from the source text, not from the index.
_RAW_LINK = re.compile(r"\[\[([^\]]+)\]\]")


def examine(agent_home: Optional[Path] = None,
            kg: Optional[Dict[str, Any]] = None) -> Diagnosis:
    """Examine the knowledge web and report what it cannot report about itself."""
    from .knowledge_web import build_knowledge_web, iter_web_files
    from .utils.paths import find_agent_home

    agent_home = agent_home or find_agent_home()
    kg = kg or build_knowledge_web()
    findings: List[Finding] = []

    ca_nodes = kg.get("ca_nodes", {})
    wiki_index = kg.get("wiki_index", {}) or {}
    stats = kg.get("stats", {})

    # ---- orphans -----------------------------------------------------------
    # The check `knowledge gaps` structurally cannot perform.
    examined = 0
    orphans_by_type: Dict[str, List[Path]] = {}
    mention_only: List[Path] = []
    scope_types = set()
    for ca_type, _root, path in iter_web_files(agent_home):
        scope_types.add(ca_type)
        examined += 1
        try:
            content = path.read_text(errors="replace")
        except OSError:
            continue
        if extract_wiki_concepts(content):
            continue
        orphans_by_type.setdefault(ca_type, []).append(path)
        # Distinguish "never linked" from "wrote links that do not count".
        # The second is a different mistake and deserves a different remedy.
        if _RAW_LINK.search(content):
            mention_only.append(path)

    for ca_type, paths in sorted(orphans_by_type.items()):
        for p in paths:
            is_mention_only = p in mention_only
            # Nested CA types (experiments, roadmaps) put the identifying name
            # on the DIRECTORY — three findings reading "analysis.md" name the
            # same file three times as far as a reader can tell, and a finding
            # you cannot locate is not actionable.
            label = f"{p.parent.name}/{p.name}" if p.parent.name != ca_type else p.name
            findings.append(Finding(
                check="orphans",
                severity=Severity.CHRONIC,
                subject=f"{ca_type}: {label}",
                detail=("carries [[links]] but ALL of them are inside code spans or fenced "
                        "blocks, so they are mentions rather than uses"
                        if is_mention_only else
                        "no wiki-link concepts; unreachable by concept query"),
                remedy=("rewrite the intended links outside code formatting, or add a "
                        "## Wiki-Links section if the mentions were deliberate"
                        if is_mention_only else
                        f"add a ## Wiki-Links section; see the {ca_type} policy on "
                        "knowledge web participation for what this type should link"),
            ))

    # ---- normalization drift in source text --------------------------------
    drift: Dict[str, set] = {}
    for _ca_type, _root, path in iter_web_files(agent_home):
        try:
            content = path.read_text(errors="replace")
        except OSError:
            continue
        # Strip mentions before looking for drift, exactly as extraction does.
        # Scanning raw content made this check internally inconsistent with the
        # extractor: a concept quoted inside backticks while DOCUMENTING the
        # notation was reported as a misspelling to correct. An artifact that
        # explains the convention would be told to stop explaining it.
        prose = re.sub(r"```.*?```", " ", content, flags=re.DOTALL)
        prose = re.sub(r"~~~.*?~~~", " ", prose, flags=re.DOTALL)
        prose = re.sub(r"`[^`\n]*`", " ", prose)
        for raw in _RAW_LINK.findall(prose):
            canon = normalize_concept(raw)
            if canon and raw.strip() != canon:
                drift.setdefault(canon, set()).add(raw.strip())
    for canon, raws in sorted(drift.items()):
        findings.append(Finding(
            check="normalization drift",
            severity=Severity.NOTE,
            subject=canon,
            detail=f"written in source as {', '.join(sorted(raws))}",
            remedy=("extraction normalizes these to one node, so the graph is correct; "
                    "fix the source text so the next author copies the canonical spelling"),
        ))

    # ---- singleton concepts ------------------------------------------------
    for concept, members in sorted(wiki_index.items()):
        if len(members) == 1:
            findings.append(Finding(
                check="singleton concepts",
                severity=Severity.CHRONIC,
                subject=concept,
                detail=f"connects exactly one node ({next(iter(members))})",
                remedy=("usually a typo or a coinage nobody reused — check against "
                        "`macf_tools knowledge query` for a near-duplicate that already "
                        "exists, or accept it as a genuinely new concept"),
            ))

    # ---- class coverage ----------------------------------------------------
    unclassed = [nid for nid, info in ca_nodes.items() if not info.get("node_class")]
    for nid in sorted(unclassed):
        findings.append(Finding(
            check="node class",
            severity=Severity.ACUTE,
            subject=str(nid),
            detail="node carries no class, so a query cannot tell durable insight "
                   "from expired state",
            remedy="state the type's class in its CA-type policy; the web derives it from there",
        ))

    chart = Chart(
        corpus="knowledge web",
        scope=sorted(scope_types),
        vitals={
            "files_examined": examined,
            "nodes": stats.get("total_nodes", 0),
            "cas": stats.get("total_cas", 0),
            "ideas": stats.get("total_ideas", 0),
            "edges": stats.get("total_edges", 0),
            "concepts": stats.get("wiki_concepts", 0),
            "orphans": sum(len(v) for v in orphans_by_type.values()),
        },
    )
    return Diagnosis(chart=chart, findings=findings)
