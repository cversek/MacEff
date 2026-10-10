"""The learnings index and its consultation trigger, kept true by a tool.

The learnings policy makes the master index (``agent/private/learnings/
INDEX.md``) the target of a Mandatory Consult Step, and the cluster names in
the auto-loaded memory file the trigger that makes an agent look. Every
curation is supposed to add each new learning under its cluster, keep the
counts and the date current, and check that the trigger still names every
cluster. Done by hand that is the step that gets skipped, and a skipped update
does not look like anything: the index simply stops describing the learnings,
and the consult step finds nothing where something exists.

Two operations. ``add`` inserts one entry under its cluster and updates the
counts; ``verify`` is a doctor for this corpus (corpus_integrity): every entry
resolves, every learning is indexed, the counts are true, and the trigger names
every cluster and points at the index.

The index format is the deployment's. Clusters are ``##`` or ``###`` headings,
optionally ending in a count ``(N)``. An entry is a line under a heading that
names its learning file in backticks, or else by its first link to the bare file
name; any other link on the line is a cross-reference. ``add`` writes a new entry
in the shape of the cluster's existing ones (of the index's, for a new cluster),
and refuses a cluster name that matches no heading unless asked to create it.
"""

from __future__ import annotations

import datetime as _dt
import difflib
import os
import re
import sys
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from .diagnostics import Chart, Diagnosis, Finding, Severity

__all__ = ["learnings_dir", "memory_file_candidates", "parse_index", "add_entry", "verify"]

_HEADING = re.compile(r"^(#{2,3})\s+(.+?)(?:\s+\((\d+)\))?\s*$")
# An entry names its file either as `name.md` (what `add` writes) or as a markdown
# link [title](name.md), the form hand-curated indexes use. The policy prescribes
# neither, and reading only the first reported every linked entry as unindexed.
# Only the line's OWN entry counts: hooks link other files ("see also" a learning,
# a checkpoint), and counting those miscounts the index in the other direction.
# So: the backticked name, or else the first link to a bare file name (an anchor
# allowed). A path part excludes checkpoints and web links alike.
_TICK = re.compile(r"`([^`]+\.md)`")
_LINK = re.compile(r"\]\((?:\./)?([^)/\s#]+\.md)(?:#[^)]*)?\)")


def _entry_files(line: str) -> List[str]:
    ticks = _TICK.findall(line)
    if ticks:
        return ticks
    first = _LINK.search(line)
    return [first.group(1)] if first else []


_TOTAL = re.compile(r"(\*\*Total Learnings\*\*:\s*)(\d+)")
_UPDATED = re.compile(r"(\*\*Last Updated\*\*:\s*)(.+)")
# A file the auto-loaded memory file links to: it loads on recall, not at session start.
_MEMORY_LINK = re.compile(r"\]\(([^)\s]+\.md)\)")
_NOT_LEARNINGS = {"INDEX.md", "CLAUDE.md", "README.md"}
# Headings that organize the index rather than name a cluster.
_STRUCTURAL = {"cep navigation guide", "by topic", "by date", "by application context",
               "topic clusters", "cross-references", "wiki-links"}


def learnings_dir(agent_home: Optional[Path] = None) -> Path:
    from .utils.paths import find_agent_home
    return (agent_home or find_agent_home()) / "agent" / "private" / "learnings"


def memory_file_candidates(project_dir: Optional[Path] = None) -> List[Path]:
    """Where the platform's auto-loaded memory file may be.

    The client keys a project's memory by its path with separators replaced.
    Both spellings seen in the wild are tried, so a miss names what was looked
    for rather than asserting there is no trigger.
    """
    from .utils.paths import find_agent_home
    root = str(project_dir or os.environ.get("CLAUDE_PROJECT_DIR") or find_agent_home())
    base = Path.home() / ".claude" / "projects"
    slugs = dict.fromkeys([root.replace("/", "-"), re.sub(r"[^A-Za-z0-9]", "-", root)])
    return [base / s / "memory" / "MEMORY.md" for s in slugs]


def parse_index(text: str) -> Dict[str, Dict]:
    """Clusters in order: {name: {"count": N or None, "files": [...], "line": i}}."""
    clusters: Dict[str, Dict] = {}
    current = None
    for i, line in enumerate(text.splitlines()):
        m = _HEADING.match(line)
        if m:
            name = m.group(2).strip()
            if name.lower() in _STRUCTURAL:
                current = None
                continue
            current = name
            clusters[current] = {"count": int(m.group(3)) if m.group(3) else None, "files": [], "line": i}
            continue
        if current:
            clusters[current]["files"].extend(_entry_files(line))
    return {k: v for k, v in clusters.items() if v["files"] or v["count"] is not None}


def _learning_title(path: Path) -> str:
    try:
        head = path.read_text(errors="replace")[:2000]
    except OSError:
        return path.stem
    m = re.search(r"^title:\s*(.+)$", head, re.MULTILINE) or \
        re.search(r"^#\s+(?:Learning|LEARN):\s*(.+)$", head, re.MULTILINE) or \
        re.search(r"^#\s+(.+)$", head, re.MULTILINE)
    return m.group(1).strip() if m else path.stem


def _near_names(cluster: str, names: List[str]) -> List[str]:
    """Existing cluster names a mistyped or shortened one most likely meant."""
    low = cluster.lower()
    contains = [n for n in names if low in n.lower()]
    close = difflib.get_close_matches(cluster, names, n=3, cutoff=0.5)
    return list(dict.fromkeys(contains + close))[:3]


def _section_end(lines: List[str], heading_line: int) -> int:
    end = heading_line + 1
    while end < len(lines) and not _HEADING.match(lines[end]):
        end += 1
    return end


def _last_entry_line(lines: List[str], heading_line: int) -> int:
    end = _section_end(lines, heading_line)
    return max((i for i in range(heading_line + 1, end) if _entry_files(lines[i])), default=heading_line)


def _entry_shape(lines: List[str], clusters: Dict[str, Dict], cluster: str) -> str:
    """'link' when the cluster's first entry (the index's, for a new cluster) is a link."""
    pool = [clusters[cluster]] if cluster in clusters else list(clusters.values())
    for info in pool:
        for i in range(info["line"] + 1, _section_end(lines, info["line"])):
            if _entry_files(lines[i]):
                return "backtick" if _TICK.search(lines[i]) else "link"
    return "backtick"


def add_entry(file_name: str, cluster: str, hook: str = "",
              agent_home: Optional[Path] = None, new_cluster: bool = False) -> Tuple[bool, str]:
    """Add one learning to its cluster; returns (added, message).

    A cluster name that matches no heading is refused unless ``new_cluster`` is
    set, with the nearest existing names, so a near-miss cannot quietly become a
    one-entry cluster. A new cluster goes after the last one, and the message
    says to name it in the consultation trigger.
    """
    ldir = learnings_dir(agent_home)
    target = ldir / Path(file_name).name
    if not target.is_file():
        return False, f"no learning named {target.name} in {ldir}"
    index = ldir / "INDEX.md"
    text = index.read_text() if index.exists() else "# Agent Learnings Index\n\n**Total Learnings**: 0\n"
    clusters = parse_index(text)
    if any(target.name in c["files"] for c in clusters.values()):
        return False, f"{target.name} is already indexed"

    lines = text.splitlines()
    creating = cluster not in clusters
    if creating and not new_cluster:
        near = _near_names(cluster, list(clusters))
        return False, (f"no cluster named '{cluster}'"
                       + (f"; did you mean: {'; '.join(near)}" if near else "")
                       + "; pass --new-cluster to create it")
    title = _learning_title(target)
    entry = (f"- [{title}]({target.name})" if _entry_shape(lines, clusters, cluster) == "link"
             else f"- **{title}** -- `{target.name}`") + (f" -- {hook}" if hook else "")
    if creating:
        if not clusters:
            lines += ["", f"## {cluster} (1)", "", entry]
        else:
            first, last = next(iter(clusters.values())), max(clusters.values(), key=lambda c: c["line"])
            level = re.match(r"#+", lines[first["line"]]).group(0)
            at = _last_entry_line(lines, last["line"]) + 1
            lines[at:at] = ["", f"{level} {cluster} (1)", "", entry]
    else:
        info = clusters[cluster]
        lines.insert(_last_entry_line(lines, info["line"]) + 1, entry)
        if info["count"] is not None:
            m = _HEADING.match(lines[info["line"]])
            lines[info["line"]] = f"{m.group(1)} {m.group(2).strip()} ({info['count'] + 1})"
    out = "\n".join(lines) + "\n"
    total = sum(len(c["files"]) for c in parse_index(out).values())
    out = _TOTAL.sub(lambda m: f"{m.group(1)}{total}", out, count=1)
    out = _UPDATED.sub(lambda m: f"{m.group(1)}{_dt.date.today().isoformat()}", out, count=1)
    index.write_text(out)
    note = (f"; {cluster} is a new cluster, so add its name to the consultation trigger"
            if creating else "")
    return True, f"indexed {target.name} under {cluster}{note}"


def verify(agent_home: Optional[Path] = None, memory_file: Optional[Path] = None) -> Diagnosis:
    """The learnings-index doctor: entries resolve, learnings are indexed,
    counts are true, and the trigger names every cluster."""
    ldir = learnings_dir(agent_home)
    index = ldir / "INDEX.md"
    findings: List[Finding] = []
    files = sorted(p.name for p in ldir.glob("*.md") if p.name not in _NOT_LEARNINGS) if ldir.exists() else []
    text = index.read_text() if index.exists() else ""
    clusters = parse_index(text)
    indexed = [f for c in clusters.values() for f in c["files"]]

    if not index.exists():
        findings.append(Finding("index", Severity.ACUTE, str(index), "no index file",
                                "create it; the Mandatory Consult Step has nothing to consult"))
    for name in sorted(set(indexed) - set(files)):
        findings.append(Finding("dangling entries", Severity.ACUTE, name,
                                "the index lists a learning that does not exist",
                                "remove the entry, or restore the file it names"))
    for name in sorted(set(files) - set(indexed)):
        findings.append(Finding("unindexed learnings", Severity.CHRONIC, name,
                                "a learning the consult step cannot find",
                                "macf_tools learnings index add <file> --cluster <name> --hook \"<WHEN ...>\""))
    for name, c in clusters.items():
        if c["count"] is not None and c["count"] != len(c["files"]):
            findings.append(Finding("cluster counts", Severity.NOTE, name,
                                    f"heading says {c['count']}, lists {len(c['files'])}",
                                    "correct the heading's count"))
    m = _TOTAL.search(text)
    if m and int(m.group(2)) != len(indexed):
        findings.append(Finding("total", Severity.ACUTE, "**Total Learnings**",
                                f"says {m.group(2)}, the index lists {len(indexed)}",
                                "correct the total; a reader trusts it as the corpus size"))

    candidates = [memory_file] if memory_file else memory_file_candidates()
    trigger = next((p for p in candidates if p and p.exists()), None)
    if trigger is None:
        findings.append(Finding("consultation trigger", Severity.NOTE, "memory file",
                                "not found at " + ", ".join(str(p) for p in candidates),
                                "pass --memory PATH if this deployment keeps it elsewhere"))
    else:
        mem = trigger.read_text()
        if "INDEX.md" not in mem:
            findings.append(Finding("consultation trigger", Severity.ACUTE, str(trigger),
                                    "does not point at INDEX.md", "add the path to the trigger"))
        linked = {}
        for target in _MEMORY_LINK.findall(mem):
            path = trigger.parent / target
            try:
                linked[target] = path.read_text() if path.is_file() else ""
            except OSError as e:
                print(f"Warning: could not read linked memory file {path}: {e}", file=sys.stderr)
        for name in clusters:
            if name in mem:
                continue
            where = next((t for t, body in linked.items() if name in body), None)
            if where:
                # The taxonomy is the reflex layer, so it must be in the file loaded at
                # session start; a file the index links loads only when recalled.
                findings.append(Finding("consultation trigger", Severity.CHRONIC, name,
                                        f"named only in {where}, which loads when recalled, not at session start",
                                        f"move the cluster names into {trigger.name} itself"))
            else:
                findings.append(Finding("consultation trigger", Severity.CHRONIC, name,
                                        "a cluster the trigger does not name, so it cannot fire a consult",
                                        "add the cluster name to the trigger in the memory file"))
        claimed = re.search(r"(\d+)\s+learnings", mem)
        if claimed and int(claimed.group(1)) != len(files):
            findings.append(Finding("consultation trigger", Severity.NOTE, str(trigger),
                                    f"says {claimed.group(1)} learnings, there are {len(files)}",
                                    "update the count in the trigger"))

    chart = Chart(corpus="learnings index", scope=[str(ldir)] + ([str(trigger)] if trigger else []),
                  vitals={"learnings": len(files), "indexed": len(indexed), "clusters": len(clusters)})
    return Diagnosis(chart=chart, findings=findings)
