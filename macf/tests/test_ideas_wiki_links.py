"""Tests for `macf_tools idea create --wiki-link / --wiki-links`.

Coverage for cversek/MacEff#109 — the `idea create` CLI previously always
wrote `links.wiki_links: []`, forcing a post-hoc edit or knowledge-web
curate pass to connect captured ideas into the graph. The fix adds an
inline normalizer and two CLI surfaces (repeatable single-link and
comma-separated bulk).
"""
import json
from pathlib import Path

import pytest

from macf.ideas import _normalize_wiki_links, create_idea


# ---------- _normalize_wiki_links ----------

def test_normalize_lowercases_and_underscores_spaces():
    assert _normalize_wiki_links(["Audit Trail"]) == ["audit_trail"]
    assert _normalize_wiki_links(["  Foo  Bar  "]) == ["foo_bar"]


def test_normalize_strips_bracket_wrappers():
    """Defensive: caller pasted markdown wiki-link syntax."""
    assert _normalize_wiki_links(["[[soft_delete]]"]) == ["soft_delete"]
    assert _normalize_wiki_links(["[[Cohort Analysis]]"]) == ["cohort_analysis"]


def test_normalize_dedups_preserving_first_seen_order():
    assert _normalize_wiki_links(["audit_trail", "soft_delete", "audit_trail"]) == [
        "audit_trail",
        "soft_delete",
    ]


def test_normalize_drops_empties():
    assert _normalize_wiki_links(["", "  ", None, "valid_token", ""]) == ["valid_token"]


def test_normalize_drops_disallowed_chars():
    """Non-[a-z0-9_-] chars are stripped (not replaced)."""
    assert _normalize_wiki_links(["foo!bar@baz"]) == ["foobarbaz"]


def test_normalize_preserves_underscores_and_hyphens():
    assert _normalize_wiki_links(["foo_bar", "foo-bar"]) == ["foo_bar", "foo-bar"]


def test_normalize_empty_and_none_input():
    assert _normalize_wiki_links([]) == []
    assert _normalize_wiki_links(None) == []


# ---------- create_idea integration ----------

def test_create_idea_writes_wiki_links_to_json(tmp_path, monkeypatch):
    """End-to-end: create_idea persists wiki_links into the JSON file."""
    # Redirect ideas dir into a tmp path so the test doesn't pollute the repo
    monkeypatch.setenv("MACEFF_AGENT_HOME_DIR", str(tmp_path))
    # Force re-import of paths cache if any
    from macf.ideas import _get_ideas_dir
    ideas_dir = _get_ideas_dir()
    assert ideas_dir.exists()

    result = create_idea(
        title="Test idea with wiki links",
        category="infrastructure",
        description="testing",
        wiki_links=["Audit Trail", "[[soft_delete]]", "audit_trail"],  # dup + bracketed + canonical
    )
    written = json.loads(Path(result["path"]).read_text())
    assert written["links"]["wiki_links"] == ["audit_trail", "soft_delete"]


def test_create_idea_no_wiki_links_yields_empty_list(tmp_path, monkeypatch):
    """Backward-compat: omitting wiki_links keeps the empty list shape."""
    monkeypatch.setenv("MACEFF_AGENT_HOME_DIR", str(tmp_path))
    result = create_idea(
        title="Test idea no links",
        category="infrastructure",
        description="testing",
    )
    written = json.loads(Path(result["path"]).read_text())
    assert written["links"]["wiki_links"] == []
