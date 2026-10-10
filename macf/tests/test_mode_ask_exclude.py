"""A deployment can keep the mode switch away from ask rules it manages itself.

Switching to AUTO_MODE added a fixed ask list to settings.local.json, and switching
back removed it, whatever the deployment had done. A deployment that removed three
of those asks on purpose (a hook decides them per repository, and an ask rule always
beats an allow) found them back after a MANUAL detour, and nothing said so.
"""

import json
import os

from macf.utils import claude_settings as cs

GH = ["Bash(gh pr create:*)", "Bash(gh issue create:*)", "Bash(gh issue close:*)"]


def _settings(root, ask=()):
    (root / ".claude").mkdir(parents=True, exist_ok=True)
    (root / ".claude" / "settings.local.json").write_text(
        json.dumps({"permissions": {"ask": list(ask), "allow": [], "deny": []}}))


def _ask(root):
    return json.loads((root / ".claude" / "settings.local.json").read_text())["permissions"]["ask"]


def _events(name):
    path = os.environ["MACF_EVENTS_LOG_PATH"]
    with open(path) as f:
        return [e for e in map(json.loads, f) if e.get("event") == name]


def test_auto_entry_leaves_out_the_excluded_asks(tmp_path):
    _settings(tmp_path)

    result = cs.toggle_auto_mode_ask_permissions(True, project_root=tmp_path, exclude=GH)

    ask = _ask(tmp_path)
    assert not set(GH) & set(ask)
    assert "Bash(git push:*)" in ask
    assert result["excluded"] == GH


def test_manual_return_leaves_the_excluded_asks_alone(tmp_path):
    """An excluded rule the deployment keeps as its own ask survives the return."""
    _settings(tmp_path, ask=["Bash(gh pr create:*)"])

    cs.toggle_auto_mode_ask_permissions(True, project_root=tmp_path, exclude=GH)
    cs.toggle_auto_mode_ask_permissions(False, project_root=tmp_path, exclude=GH)

    assert _ask(tmp_path) == ["Bash(gh pr create:*)"]


def test_the_exclude_list_comes_from_the_agent_config(tmp_path, monkeypatch):
    (tmp_path / ".maceff").mkdir()
    (tmp_path / ".maceff" / "config.json").write_text(
        json.dumps({"modes": {"auto": {"ask_exclude": GH}}}))
    monkeypatch.setattr("macf.utils.paths.find_agent_home", lambda *a, **k: tmp_path)
    _settings(tmp_path)

    cs.toggle_auto_mode_ask_permissions(True, project_root=tmp_path)

    assert not set(GH) & set(_ask(tmp_path))


def test_the_mode_switch_records_what_it_changed(tmp_path):
    _settings(tmp_path, ask=["Bash(git push:*)"])

    result = cs.toggle_auto_mode_ask_permissions(True, project_root=tmp_path, exclude=GH)

    events = _events("mode_permissions_changed")
    assert len(events) == 1
    data = events[0]["data"]
    assert data["mode"] == "AUTO_MODE"
    assert data["ask_added"] == result["changed"] and "Bash(git push:*)" not in data["ask_added"]
    assert data["excluded"] == GH
