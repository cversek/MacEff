"""Unsent feedback drafts are said before they block a restart (cversek/MacEff#903).

A draft makes `inject exit` refuse, and until now nothing mentioned one before that: the
operator first heard of two drafts, 6 and 18 days old, when they stopped a restart. `pd status`
now says they're there, and the refusal gives each draft's title and age. The drafts are only
read, never changed (#812).
"""
import json
from datetime import datetime, timezone
from unittest.mock import patch

from macf import supervisor
from macf.utils.feedback_drafts import age, unsent_drafts

NOW = datetime(2026, 11, 9, 12, 0, tzinfo=timezone.utc)


def _draft(tmp_path, monkeypatch, name, **data):
    monkeypatch.setenv("CLAUDE_CONFIG_DIR", str(tmp_path))
    drafts = tmp_path / "feedback" / "drafts"
    drafts.mkdir(parents=True, exist_ok=True)
    (drafts / name).write_text(json.dumps(data))
    return drafts / name


def test_drafts_are_read_oldest_first_with_title_and_age(tmp_path, monkeypatch):
    _draft(tmp_path, monkeypatch, "b.json", title="A newer note", created_at="2026-11-03T12:00:00.000Z")
    _draft(tmp_path, monkeypatch, "a.json", title="An old note", created_at="2026-10-22T09:00:00.000Z")
    drafts = unsent_drafts()
    assert [d.title for d in drafts] == ["An old note", "A newer note"]
    assert [age(d, NOW) for d in drafts] == ["18 days old", "6 days old"]


def test_an_unreadable_draft_is_still_listed(tmp_path, monkeypatch):
    path = _draft(tmp_path, monkeypatch, "c.json")
    path.write_text("not json")
    [draft] = unsent_drafts()
    assert draft.title == "" and draft.created is not None and draft.path == path


def test_the_refusal_names_each_drafts_title_and_age(tmp_path, monkeypatch, capsys):
    path = _draft(tmp_path, monkeypatch, "e.json", title="A queued note", created_at="2026-10-22T09:00:00Z")
    with patch.object(supervisor, "own_pane_target", return_value="seat"), \
         patch.object(supervisor, "_draft_in_box", return_value=""), \
         patch.object(supervisor, "send_keys", return_value=0) as send:
        assert supervisor.send_slash_to_self("exit") == 1
    send.assert_not_called()
    err = capsys.readouterr().err
    assert '"A queued note"' in err and "days old" in err and str(path) in err
    assert json.loads(path.read_text())["title"] == "A queued note"     # read, never changed


def test_pd_status_says_drafts_are_waiting(tmp_path, monkeypatch, capsys):
    from macf.pd import cli as pd_cli
    _draft(tmp_path, monkeypatch, "e.json", title="A queued note", created_at="2026-10-22T09:00:00Z")
    pd_cli._say_drafts()
    out = capsys.readouterr().out
    assert "1 unsent feedback draft(s)" in out and "days old" in out and "inject exit" in out


def test_pd_status_says_nothing_without_drafts(tmp_path, monkeypatch, capsys):
    from macf.pd import cli as pd_cli
    monkeypatch.setenv("CLAUDE_CONFIG_DIR", str(tmp_path))
    pd_cli._say_drafts()
    assert capsys.readouterr().out == ""
