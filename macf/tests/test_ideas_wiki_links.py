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
    """Non-[a-z0-9_] chars are stripped (not replaced); hyphens fold to underscores first."""
    assert _normalize_wiki_links(["foo!bar@baz"]) == ["foobarbaz"]


def test_normalize_folds_hyphens_into_underscores():
    """Hyphenated spellings are drift to merge, not distinct concepts.

    The scholarship policy spells multi-word concepts with underscores, so
    ``foo-bar`` normalizes to ``foo_bar`` and dedups against it.
    """
    assert _normalize_wiki_links(["foo-bar"]) == ["foo_bar"]
    assert _normalize_wiki_links(["foo_bar", "foo-bar"]) == ["foo_bar"]


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


# ---------- update_idea integration (#124) ----------
#
# `idea update` had no wiki-link surface, so links could only be set at
# creation. Gap-driven curation operates on EXISTING ideas, so closing a
# suggested gap meant hand-editing JSON.

def _make_idea(tmp_path, monkeypatch, **kw):
    monkeypatch.setenv("MACEFF_AGENT_HOME_DIR", str(tmp_path))
    from macf.ideas import create_idea
    return create_idea(title="Idea under test", category="infrastructure",
                       description="testing", **kw)


def test_update_idea_adds_and_normalizes_wiki_links(tmp_path, monkeypatch):
    from macf.ideas import update_idea
    created = _make_idea(tmp_path, monkeypatch, wiki_links=["initial_concept"])

    update_idea(created["idea"]["id"], wiki_links=["Foo Bar", "[[qux]]"])

    written = json.loads(Path(created["path"]).read_text())
    assert written["links"]["wiki_links"] == ["initial_concept", "foo_bar", "qux"]


def test_update_idea_dedups_against_existing_links(tmp_path, monkeypatch):
    """Re-adding an existing link is a no-op, not a duplicate."""
    from macf.ideas import update_idea
    created = _make_idea(tmp_path, monkeypatch, wiki_links=["audit_trail"])

    update_idea(created["idea"]["id"], wiki_links=["Audit Trail"])

    written = json.loads(Path(created["path"]).read_text())
    assert written["links"]["wiki_links"] == ["audit_trail"]


def test_update_idea_removes_wiki_links(tmp_path, monkeypatch):
    """--remove-wiki-link prunes a link found spurious during curation."""
    from macf.ideas import update_idea
    created = _make_idea(tmp_path, monkeypatch, wiki_links=["keep_me", "drop_me"])

    update_idea(created["idea"]["id"], remove_wiki_links=["Drop Me"])

    written = json.loads(Path(created["path"]).read_text())
    assert written["links"]["wiki_links"] == ["keep_me"]


def test_update_idea_records_history_for_link_changes(tmp_path, monkeypatch):
    """Link edits are auditable, like status changes."""
    from macf.ideas import update_idea
    created = _make_idea(tmp_path, monkeypatch)

    update_idea(created["idea"]["id"], wiki_links=["added_one"])
    update_idea(created["idea"]["id"], remove_wiki_links=["added_one"])

    actions = [h["action"] for h in json.loads(Path(created["path"]).read_text())["history"]]
    assert any(a.startswith("wiki_links_added:") for a in actions)
    assert any(a.startswith("wiki_links_removed:") for a in actions)


def test_update_idea_status_only_leaves_links_untouched(tmp_path, monkeypatch):
    """Backward-compat: a status-only update must not disturb existing links."""
    from macf.ideas import update_idea
    created = _make_idea(tmp_path, monkeypatch, wiki_links=["untouched"])

    update_idea(created["idea"]["id"], status="exploring")

    written = json.loads(Path(created["path"]).read_text())
    assert written["links"]["wiki_links"] == ["untouched"]
    assert written["status"] == "exploring"
