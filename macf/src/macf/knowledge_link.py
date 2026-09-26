"""One verb to link any artifact into the knowledge web.

Wiki-links live in three shapes: a ``## Wiki-Links`` section in a markdown
artifact, ``links.wiki_links`` in an idea record, and the ``wiki_links`` field
of a task's metadata. Curating them used to take a different tool for each
(and a hand edit for the markdown), so this module takes a target in any of the
forms the graph prints and applies the change in that target's own shape.

Concepts are normalized the one way the web normalizes them, and adding a
concept that is already there changes nothing. Role duties are records the
roles subsystem owns and are declared with their links; they are refused here
with a pointer to that CLI rather than edited behind its back.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Optional, Tuple

from .concepts import extract_not_linked, extract_wiki_concepts, normalize_concepts

__all__ = ["LinkResult", "LinkError", "resolve_target", "apply_links", "decline"]

_SECTION = re.compile(r"(^##\s*Wiki-Links\s*\n)(.*?)(?=^##\s|\Z)", re.MULTILINE | re.DOTALL | re.IGNORECASE)
_TASK_REF = re.compile(r"^(?:tasks?:)?#?(\d+)$")
_IDEA_REF = re.compile(r"^ideas?:#?(\d+)$")


class LinkError(ValueError):
    """A target that cannot be linked, with the reason a caller can print."""


@dataclass
class LinkResult:
    kind: str                      # markdown | idea | task
    target: str                    # what was edited, as a reader would name it
    changed: List[str] = field(default_factory=list)
    concepts: List[str] = field(default_factory=list)
    still_inline: List[str] = field(default_factory=list)


def resolve_target(ref: str) -> Tuple[str, str]:
    """Classify a target as ('markdown', path), ('idea', id) or ('task', id).

    Accepted forms: a path to a markdown artifact; ``task:N``, ``tasks:#N`` or
    ``#N`` for a task; ``idea:N`` for an idea; or a node id as ``knowledge
    graph`` and ``gaps`` print it. A bare number is refused, because an idea and
    a task can share it.
    """
    ref = ref.strip()
    m = _IDEA_REF.match(ref)
    if m:
        return "idea", m.group(1)
    if ref.startswith(("task:", "tasks:", "#")):
        m = _TASK_REF.match(ref)
        if m:
            return "task", m.group(1)
    if re.fullmatch(r"\d+", ref):
        raise LinkError(f"'{ref}' could be an idea or a task; say idea:{ref} or task:{ref}")
    if ref.startswith("duties:"):
        raise LinkError("a duty's links are declared with the duty (macf_tools role duty add "
                        "--wiki-links); the roles subsystem owns duty records")
    path = Path(ref).expanduser()
    if path.is_file():
        if path.suffix != ".md":
            raise LinkError(f"{path} is not a markdown artifact; use idea:N or task:N for records")
        return "markdown", str(path)
    node_path = _node_path(ref)
    if node_path:
        return "markdown", node_path
    raise LinkError(f"no artifact found for '{ref}'")


def _node_path(node_id: str) -> Optional[str]:
    """The file behind a markdown node id such as ``learnings:2026-...``."""
    if ":" not in node_id:
        return None
    from .knowledge_web import build_knowledge_web
    info = build_knowledge_web().get("ca_nodes", {}).get(node_id)
    path = (info or {}).get("path", "")
    return path if path.endswith(".md") and Path(path).is_file() else None


def _edit_markdown(text: str, concepts: List[str], remove: bool) -> Tuple[str, List[str]]:
    """Add or remove concepts in the ``## Wiki-Links`` section only.

    Inline ``[[concept]]`` uses in the prose are the author's and are never
    edited here; ``apply_links`` reports any that keep a removed concept alive.
    """
    m = _SECTION.search(text)
    present = normalize_concepts(re.findall(r"\[\[(.+?)\]\]", m.group(2))) if m else []
    if remove:
        gone = [c for c in concepts if c in present]
        if not gone:
            return text, []
        body = m.group(2)
        for raw in re.findall(r"\[\[(.+?)\]\]", body):
            if normalize_concepts([raw]) and normalize_concepts([raw])[0] in gone:
                body = body.replace(f"[[{raw}]]", "")
        body = re.sub(r"[ \t]+\n", "\n", re.sub(r"[ \t]{2,}", " ", body))
        return text[:m.start(2)] + body + text[m.end(2):], gone
    new = [c for c in concepts if c not in present]
    if not new:
        return text, []
    tokens = " ".join(f"[[{c}]]" for c in new)
    if not m:
        sep = "" if text.endswith("\n\n") else ("\n" if text.endswith("\n") else "\n\n")
        return f"{text}{sep}## Wiki-Links\n\n{tokens}\n", new
    body = m.group(2).rstrip("\n")
    lines = body.split("\n")
    if lines and re.fullmatch(r"\s*(\[\[[^\]]+\]\]\s*)+", lines[-1]):
        lines[-1] = f"{lines[-1].rstrip()} {tokens}"
    else:
        lines.append(tokens)
    rebuilt = "\n".join(lines) + "\n" + ("\n" if m.end(2) < len(text) else "")
    return text[:m.start(2)] + rebuilt + text[m.end(2):], new


def _require_home_store() -> None:
    """Task links are read from the home task store; refuse to write them
    anywhere else. A legacy per-session store is not walked, and its completed
    tasks can be deleted by the client, so a link written there is lost."""
    from .task.reader import TaskReader
    if TaskReader._resolve_home_store() is None:
        raise LinkError("task links live in the home task store, and this deployment has none; "
                        "macf_tools task store-init provisions it (task_management: task storage)")


def _edit_task(task_id: str, concepts: List[str], remove: bool) -> LinkResult:
    _require_home_store()
    from .task import TaskReader, update_task_file, MacfTaskMetaData
    from .task.models import MacfTaskUpdate
    from .utils.breadcrumbs import get_breadcrumb
    import copy

    task = TaskReader().read_task(task_id)
    if not task:
        raise LinkError(f"task #{task_id} not found")
    mtmd = copy.deepcopy(task.mtmd) if task.mtmd else MacfTaskMetaData()
    current = list(mtmd.wiki_links or [])
    if remove:
        changed = [c for c in concepts if c in current]
        mtmd.wiki_links = [c for c in current if c not in changed]
    else:
        changed = [c for c in concepts if c not in current]
        mtmd.wiki_links = current + changed
    if changed:
        verb = "Unlinked" if remove else "Linked"
        mtmd.updates.append(MacfTaskUpdate(breadcrumb=get_breadcrumb(), agent="PA",
                                           description=f"{verb} {', '.join(changed)} (knowledge web)"))
        if not update_task_file(task_id, {"description": task.description_with_updated_mtmd(mtmd)}):
            raise LinkError(f"task #{task_id} could not be written")
    title = re.sub(r"\x1b\[[0-9;]*m", "", task.subject or "").strip()
    return LinkResult("task", f"task #{task_id} {title}".strip(), changed, list(mtmd.wiki_links))


def apply_links(ref: str, raw_concepts: List[str], remove: bool = False) -> LinkResult:
    """Link (or with ``remove``, unlink) concepts on one artifact."""
    concepts = normalize_concepts(raw_concepts)
    if not concepts:
        raise LinkError("no concepts left after normalization")
    kind, handle = resolve_target(ref)

    if kind == "idea":
        from .ideas import update_idea
        before = (get_idea_links(handle) or [])
        result = update_idea(int(handle), wiki_links=None if remove else concepts,
                             remove_wiki_links=concepts if remove else None)
        if result is None:
            raise LinkError(f"idea #{handle} not found")
        after = list(result["idea"].get("links", {}).get("wiki_links") or [])
        changed = [c for c in concepts if (c in before) != (c in after)]
        return LinkResult("idea", f"idea #{handle}", changed, after)

    if kind == "task":
        return _edit_task(handle, concepts, remove)

    path = Path(handle)
    text = path.read_text()
    new_text, changed = _edit_markdown(text, concepts, remove)
    if new_text != text:
        path.write_text(new_text)
    after = extract_wiki_concepts(new_text)
    inline = [c for c in concepts if c in after] if remove else []
    return LinkResult("markdown", str(path), changed, after, inline)


def get_idea_links(idea_id: str) -> Optional[List[str]]:
    from .ideas import get_idea
    result = get_idea(int(idea_id))
    return None if result is None else list(result["idea"].get("links", {}).get("wiki_links") or [])


_NOT_LINKED_LINE = re.compile(r"<!--\s*not linked:.*?-->\n?", re.IGNORECASE | re.DOTALL)


def _decline_markdown(text: str, concepts: List[str]) -> Tuple[str, List[str]]:
    """Merge concepts into the one ``<!-- not linked: ... -->`` line, placing it
    at the end of the Wiki-Links section when there is one, else at the end."""
    declined = extract_not_linked(text)
    new = [c for c in concepts if c not in declined]
    if not new:
        return text, []
    line = f"<!-- not linked: {', '.join(declined + new)} -->\n"
    text = _NOT_LINKED_LINE.sub("", text)
    m = _SECTION.search(text)
    if m:
        body = m.group(2).rstrip("\n") + "\n" + line
        tail = "\n" if m.end(2) < len(text) else ""
        return text[:m.start(2)] + body + tail + text[m.end(2):], new
    sep = "" if text.endswith("\n") else "\n"
    return f"{text}{sep}{line}", new


def decline(ref: str, raw_concepts: List[str]) -> LinkResult:
    """Record that suggested concepts are wrong for one artifact.

    The judgement is kept with the artifact, beside its links (scholarship:
    declining a suggested concept), so gap detection stops proposing it and no
    later curation re-judges it. ``LinkResult.concepts`` is the declined set.
    """
    concepts = normalize_concepts(raw_concepts)
    if not concepts:
        raise LinkError("no concepts left after normalization")
    kind, handle = resolve_target(ref)

    if kind == "idea":
        from .ideas import update_idea
        before = set((_idea_record(handle) or {}).get("links", {}).get("not_linked") or [])
        result = update_idea(int(handle), not_linked=concepts)
        if result is None:
            raise LinkError(f"idea #{handle} not found")
        after = list(result["idea"].get("links", {}).get("not_linked") or [])
        return LinkResult("idea", f"idea #{handle}", [c for c in after if c not in before], after)

    if kind == "task":
        from .task import TaskReader, update_task_file, MacfTaskMetaData
        from .task.models import MacfTaskUpdate
        from .utils.breadcrumbs import get_breadcrumb
        import copy
        _require_home_store()
        task = TaskReader().read_task(handle)
        if not task:
            raise LinkError(f"task #{handle} not found")
        mtmd = copy.deepcopy(task.mtmd) if task.mtmd else MacfTaskMetaData()
        new = [c for c in concepts if c not in (mtmd.not_linked or [])]
        if new:
            mtmd.not_linked = list(mtmd.not_linked or []) + new
            mtmd.updates.append(MacfTaskUpdate(breadcrumb=get_breadcrumb(), agent="PA",
                                               description=f"Declined {', '.join(new)} (knowledge web)"))
            if not update_task_file(handle, {"description": task.description_with_updated_mtmd(mtmd)}):
                raise LinkError(f"task #{handle} could not be written")
        return LinkResult("task", f"task #{handle}", new, list(mtmd.not_linked))

    path = Path(handle)
    text = path.read_text()
    new_text, new = _decline_markdown(text, concepts)
    if new_text != text:
        path.write_text(new_text)
    return LinkResult("markdown", str(path), new, extract_not_linked(new_text))


def _idea_record(idea_id: str) -> Optional[dict]:
    from .ideas import get_idea
    result = get_idea(int(idea_id))
    return None if result is None else result["idea"]
