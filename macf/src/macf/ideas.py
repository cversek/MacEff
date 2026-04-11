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
