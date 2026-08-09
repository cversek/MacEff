"""USER_REMOTE Ask->Deny permission flip (#143 v2).

While USER_REMOTE, tools that block on the CLI (AskUserQuestion + the Ask-list
commands) are moved into the deny list so an attempt is refused immediately
rather than hanging the unattended session. On exit they are restored to where
they came from.
"""

import json

from macf.utils.claude_settings import (
    toggle_user_remote_deny_permissions,
    _AUTO_MODE_ASK,
    _USER_REMOTE_EXTRA_DENY,
)


def _seed(tmp_path, settings):
    d = tmp_path / ".claude"
    d.mkdir(parents=True, exist_ok=True)
    (d / "settings.local.json").write_text(json.dumps(settings))


def _load(tmp_path):
    return json.loads((tmp_path / ".claude" / "settings.local.json").read_text())


def test_enable_moves_cli_blocking_tools_into_deny(tmp_path):
    _seed(tmp_path, {"permissions": {"ask": list(_AUTO_MODE_ASK), "allow": [], "deny": []}})
    res = toggle_user_remote_deny_permissions(True, project_root=tmp_path)
    assert res is not None
    perms = _load(tmp_path)["permissions"]
    for entry in list(_AUTO_MODE_ASK) + _USER_REMOTE_EXTRA_DENY:
        assert entry in perms["deny"], f"{entry} not denied"
    # Ask-list entries were moved OUT of ask (so they don't ask-and-hang).
    for entry in _AUTO_MODE_ASK:
        assert entry not in perms["ask"]


def test_disable_restores_prior_state(tmp_path):
    _seed(tmp_path, {"permissions": {"ask": list(_AUTO_MODE_ASK), "allow": [], "deny": []}})
    toggle_user_remote_deny_permissions(True, project_root=tmp_path)
    toggle_user_remote_deny_permissions(False, project_root=tmp_path)
    perms = _load(tmp_path)["permissions"]
    for entry in _AUTO_MODE_ASK:
        assert entry in perms["ask"], f"{entry} not restored to ask"
        assert entry not in perms["deny"]
    assert "AskUserQuestion" not in perms["deny"]


def test_enable_is_idempotent_no_duplicate_deny(tmp_path):
    _seed(tmp_path, {"permissions": {"ask": [], "allow": [], "deny": []}})
    toggle_user_remote_deny_permissions(True, project_root=tmp_path)
    toggle_user_remote_deny_permissions(True, project_root=tmp_path)
    deny = _load(tmp_path)["permissions"]["deny"]
    assert len(deny) == len(set(deny)), "deny list has duplicates"


def test_ask_user_question_is_always_denied_under_remote(tmp_path):
    _seed(tmp_path, {"permissions": {"ask": [], "allow": [], "deny": []}})
    toggle_user_remote_deny_permissions(True, project_root=tmp_path)
    assert "AskUserQuestion" in _load(tmp_path)["permissions"]["deny"]
