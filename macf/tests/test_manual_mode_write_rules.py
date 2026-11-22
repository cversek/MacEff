"""MANUAL_MODE asks about the agent's real work and not about every write (#876): a round trip
MANUAL -> AUTO -> MANUAL leaves the operator's own rules alone."""
import json

import pytest

from macf.utils import claude_settings as cs


@pytest.fixture
def project(tmp_path, monkeypatch):
    home = tmp_path / "home"
    (home / ".claude").mkdir(parents=True)
    monkeypatch.setattr(cs.Path, "home", classmethod(lambda cls: home))
    root = tmp_path / "project"
    (root / ".claude").mkdir(parents=True)
    return root, home


def _rules(path):
    perms = json.loads(path.read_text())["permissions"]
    return perms.get("ask", []), perms.get("allow", [])


def test_the_rules_are_exactly_these_strings_and_cover_the_macos_scratchpad_path():
    """Claude Code reads each string as written: a changed one is a silent change of what is asked. On macOS /tmp
    is a link to /private/tmp and the scratchpad's real path is the second form."""
    assert cs.MANUAL_ASK_RULES == ("Edit(~/**)", "Edit(//opt/**)")
    assert cs.MANUAL_ALLOW_RULES == ("Edit(//tmp/claude-*/**)", "Edit(//private/tmp/claude-*/**)")
    assert not any(a.startswith("Edit(//tmp") or a.startswith("Edit(//private") for a in cs.MANUAL_ASK_RULES)


def test_manual_mode_asks_about_real_work_and_lets_the_scratchpad_through(project):
    root, home = project
    local = root / ".claude" / "settings.local.json"
    local.write_text(json.dumps({"permissions": {"ask": ["Write"]}}))
    assert cs.toggle_write_ask_for_auto_mode(True, root)
    assert cs.toggle_write_ask_for_auto_mode(False, root)
    ask, allow = _rules(local)
    assert "Write" not in ask, "a bare Write ask prompted for every scratch write"
    assert set(cs.MANUAL_ASK_RULES) <= set(ask) and set(cs.MANUAL_ALLOW_RULES) <= set(allow)


def test_a_round_trip_leaves_the_operators_own_rules(project):
    root, home = project
    local = root / ".claude" / "settings.local.json"
    local.write_text(json.dumps({"permissions": {"ask": ["Bash(rm:*)", cs.MANUAL_ASK_RULES[0]],
                                                 "allow": ["Read", cs.MANUAL_ALLOW_RULES[0]]}}))
    for enable_auto in (False, True, False, True):       # MANUAL adds only what is new; AUTO removes exactly that
        cs.toggle_write_ask_for_auto_mode(enable_auto, root)
    ask, allow = _rules(local)
    assert ask == ["Bash(rm:*)", cs.MANUAL_ASK_RULES[0]], "the operator's identical rule is theirs and stays"
    assert allow == ["Read", cs.MANUAL_ALLOW_RULES[0]]
    # a rule the operator adds after a cycle is theirs: the cleared record must not take it out on the next AUTO
    local.write_text(json.dumps({"permissions": {"ask": ["Bash(rm:*)", cs.MANUAL_ASK_RULES[1]], "allow": []}}))
    cs.toggle_write_ask_for_auto_mode(True, root)
    assert cs.MANUAL_ASK_RULES[1] in _rules(local)[0]


def test_the_user_level_file_is_shared_so_a_manual_switch_adds_nothing_to_it(project):
    """~/.claude/settings.json serves every agent on the login: one agent's MANUAL switch must not ask about
    writes for the others. Only its bare Write comes out, on the way to AUTO_MODE."""
    root, home = project
    glob = home / ".claude" / "settings.json"
    glob.write_text(json.dumps({"permissions": {"ask": ["Write", "Bash(git push:*)"], "allow": ["Bash(ls:*)"]}}))
    cs.toggle_write_ask_for_auto_mode(False, root)
    ask, allow = _rules(glob)
    assert ask == ["Write", "Bash(git push:*)"] and allow == ["Bash(ls:*)"], "MANUAL added nothing to the shared file"
    cs.toggle_write_ask_for_auto_mode(True, root)
    ask, allow = _rules(glob)
    assert ask == ["Bash(git push:*)"] and allow == ["Bash(ls:*)"]


def test_a_repeated_manual_switch_adds_nothing_twice_and_still_comes_out_whole(project):
    root, home = project
    local = root / ".claude" / "settings.local.json"
    cs.toggle_write_ask_for_auto_mode(False, root)
    cs.toggle_write_ask_for_auto_mode(False, root)
    ask, allow = _rules(local)
    assert ask.count(cs.MANUAL_ASK_RULES[0]) == 1 and allow.count(cs.MANUAL_ALLOW_RULES[0]) == 1
    cs.toggle_write_ask_for_auto_mode(True, root)
    ask, allow = _rules(local)
    assert not set(cs.MANUAL_ASK_RULES) & set(ask) and not set(cs.MANUAL_ALLOW_RULES) & set(allow)


def test_what_it_added_is_read_from_the_event_log_and_a_new_project_file_is_its_own_record(project):
    """No file is stored beside the settings: the record is an event, per settings file."""
    from macf.agent_events_log import read_events
    root, home = project
    cs.toggle_write_ask_for_auto_mode(False, root)
    ev = next(read_events(reverse=True, scope="all", only=cs.RULES_EVENT))
    assert ev["data"]["path"].endswith("settings.local.json") and set(ev["data"]["added"]["ask"]) == set(cs.MANUAL_ASK_RULES)
    assert not list((root / ".claude").glob("*manual*")), "no sidecar file"
    other = root.parent / "other"
    (other / ".claude").mkdir(parents=True)
    (other / ".claude" / "settings.local.json").write_text(json.dumps({"permissions": {"ask": list(cs.MANUAL_ASK_RULES)}}))
    cs.toggle_write_ask_for_auto_mode(True, other)       # another project's file: nothing of ours is recorded for it
    assert set(cs.MANUAL_ASK_RULES) <= set(_rules(other / ".claude" / "settings.local.json")[0])
