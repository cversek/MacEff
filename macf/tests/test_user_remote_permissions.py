"""USER_REMOTE Ask->Deny permission flip (#143 v2).

While USER_REMOTE, tools that block on the CLI (AskUserQuestion + the Ask-list
commands) are moved into the deny list so an attempt is refused immediately
rather than hanging the unattended session. On exit they are restored to where
they came from.
"""

import json

from macf.utils.claude_settings import (
    toggle_user_remote_deny_permissions,
    restore_user_remote_deny_if_active,
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


# --- auto-restore on CLI activity (the returning operator) --------------------

def test_restore_if_active_is_noop_when_nothing_denied(tmp_path):
    """No deny stash → returns None and writes nothing (the common per-prompt path)."""
    seed = {"permissions": {"ask": list(_AUTO_MODE_ASK), "allow": [], "deny": []}}
    _seed(tmp_path, seed)
    res = restore_user_remote_deny_if_active(project_root=tmp_path)
    assert res is None
    # Settings unchanged — the Ask-list is still the Ask-list.
    assert _load(tmp_path) == seed


def test_restore_if_active_restores_when_deny_installed(tmp_path):
    """With a deny installed, a CLI prompt restores the tools to their prior lists."""
    _seed(tmp_path, {"permissions": {"ask": list(_AUTO_MODE_ASK), "allow": [], "deny": []}})
    toggle_user_remote_deny_permissions(True, project_root=tmp_path)
    # Sanity: deny is installed and the stash exists.
    assert "AskUserQuestion" in _load(tmp_path)["permissions"]["deny"]
    assert _load(tmp_path).get("_macf_user_remote_denied")

    res = restore_user_remote_deny_if_active(project_root=tmp_path)
    assert res is not None and res["restored"], "should report the restored entries"
    perms = _load(tmp_path)["permissions"]
    for entry in _AUTO_MODE_ASK:
        assert entry in perms["ask"], f"{entry} not restored to ask"
        assert entry not in perms["deny"]
    assert "AskUserQuestion" not in perms["deny"]
    # Stash cleared — a subsequent prompt is a clean no-op.
    assert not _load(tmp_path).get("_macf_user_remote_denied")
    assert restore_user_remote_deny_if_active(project_root=tmp_path) is None
