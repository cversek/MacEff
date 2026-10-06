"""A change to a settings file's permission rules becomes one event naming what changed.

Claude Code tells a ConfigChange hook only which file changed, never what changed in it,
so the hook diffs against the rules it last saw. A widened allowlist used to leave no
record of when, or by which file.
"""
import json

from macf.agent_events_log import read_events
from macf.hooks import handle_config_change as cc


def _settings(path, allow=(), ask=(), deny=(), mode=None, **extra):
    perms = {"allow": list(allow), "ask": list(ask), "deny": list(deny)}
    if mode:
        perms["defaultMode"] = mode
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"permissions": perms, **extra}))


def _fire(path, source="project_settings"):
    return cc.run(json.dumps({"hook_event_name": "ConfigChange", "source": source,
                              "file_path": str(path), "session_id": "s1"}))


def _events(name):
    return [e for e in read_events(reverse=False, scope="all") if e.get("event") == name]


def test_first_sight_is_a_baseline_not_a_change(isolated_events_log, tmp_path):
    f = tmp_path / ".claude" / "settings.json"
    _settings(f, allow=["Bash(ls:*)"])
    assert _fire(f) == {"continue": True}
    assert len(_events(cc.BASELINE_EVENT)) == 1
    assert _events(cc.CHANGED_EVENT) == []


def test_a_widened_allowlist_names_the_rule_added(isolated_events_log, tmp_path):
    f = tmp_path / ".claude" / "settings.json"
    _settings(f, allow=["Bash(ls:*)"])
    _fire(f)
    _settings(f, allow=["Bash(ls:*)", "Bash(rm:*)"], deny=[])
    _fire(f)
    (ev,) = _events(cc.CHANGED_EVENT)
    assert ev["data"]["added"] == {"allow": ["Bash(rm:*)"]}
    assert "removed" not in ev["data"]
    assert ev["data"]["source"] == "project_settings"
    assert ev["data"]["file_path"] == str(f)


def test_removed_rules_and_mode_change_are_named(isolated_events_log, tmp_path):
    f = tmp_path / ".claude" / "settings.json"
    _settings(f, allow=["A"], deny=["D"], mode="default")
    _fire(f)
    _settings(f, allow=[], deny=["D"], mode="acceptEdits")
    _fire(f)
    (ev,) = _events(cc.CHANGED_EVENT)
    assert ev["data"]["removed"] == {"allow": ["A"]}
    assert ev["data"]["default_mode"] == {"from": "default", "to": "acceptEdits"}


def test_a_change_outside_permissions_records_nothing(isolated_events_log, tmp_path):
    f = tmp_path / ".claude" / "settings.json"
    _settings(f, allow=["A"])
    _fire(f)
    _settings(f, allow=["A"], statusLine={"type": "command"})
    _fire(f)
    assert _events(cc.CHANGED_EVENT) == []


def test_an_unreadable_file_is_never_every_rule_removed(isolated_events_log, tmp_path):
    f = tmp_path / ".claude" / "settings.json"
    _settings(f, allow=["A", "B"])
    _fire(f)
    f.write_text("{ not json")
    _fire(f)
    assert _events(cc.CHANGED_EVENT) == []
    _settings(f, allow=["A", "B", "C"])     # the cache still holds the last good rules
    _fire(f)
    (ev,) = _events(cc.CHANGED_EVENT)
    assert ev["data"]["added"] == {"allow": ["C"]}


def test_session_start_seeds_so_the_first_change_is_a_diff(isolated_events_log, tmp_path):
    f = tmp_path / ".claude" / "settings.local.json"
    _settings(f, allow=["A"])
    assert cc.seed_baselines([f, tmp_path / "absent.json"], "s1") == 1
    assert cc.seed_baselines([f], "s1") == 0          # seen already, unchanged: nothing
    _settings(f, allow=["A", "B"])
    _fire(f, source="local_settings")
    (ev,) = _events(cc.CHANGED_EVENT)
    assert ev["data"]["added"] == {"allow": ["B"]}


def test_the_hook_is_installed():
    from macf.cli import _hooks_to_install_list
    assert ("config_change.py", "handle_config_change") in _hooks_to_install_list()


def test_a_change_between_sessions_is_recorded_at_session_start(isolated_events_log, tmp_path):
    f = tmp_path / ".claude" / "settings.json"
    _settings(f, allow=["A"])
    cc.seed_baselines([f], "s1")
    _settings(f, allow=["A", "B"])                    # edited while no session ran
    assert cc.seed_baselines([f], "s2") == 1
    (ev,) = _events(cc.CHANGED_EVENT)
    assert ev["data"]["source"] == "between_sessions"
    assert ev["data"]["added"] == {"allow": ["B"]}
    assert cc.seed_baselines([f], "s3") == 0          # recorded once, not every session
