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


def test_manual_mode_asks_about_real_work_and_lets_the_scratchpad_through(project):
    root, home = project
    (root / ".claude" / "settings.local.json").write_text(json.dumps({"permissions": {"ask": ["Write"]}}))
    assert cs.toggle_write_ask_for_auto_mode(True, root)
    assert cs.toggle_write_ask_for_auto_mode(False, root)
    ask, allow = _rules(root / ".claude" / "settings.local.json")
    assert "Write" not in ask, "a bare Write ask prompted for every scratch write"
    assert set(cs.MANUAL_ASK_RULES) <= set(ask) and set(cs.MANUAL_ALLOW_RULES) <= set(allow)
    assert not set(cs.MANUAL_ALLOW_RULES) & set(ask), "an ask rule would outrank the allow"


def test_a_round_trip_leaves_the_operators_own_rules(project):
    root, home = project
    local, glob = root / ".claude" / "settings.local.json", home / ".claude" / "settings.json"
    mine = {"permissions": {"ask": ["Bash(rm:*)", cs.MANUAL_ASK_RULES[0]], "allow": ["Read", cs.MANUAL_ALLOW_RULES[0]]}}
    local.write_text(json.dumps(mine))
    glob.write_text(json.dumps({"permissions": {"ask": ["Bash(git push:*)"], "allow": ["Bash(ls:*)"]}}))
    cs.toggle_write_ask_for_auto_mode(False, root)       # MANUAL: only the rules not already there are added
    cs.toggle_write_ask_for_auto_mode(True, root)        # AUTO: exactly those come out
    cs.toggle_write_ask_for_auto_mode(False, root)
    cs.toggle_write_ask_for_auto_mode(True, root)
    ask, allow = _rules(local)
    assert ask == ["Bash(rm:*)", cs.MANUAL_ASK_RULES[0]], "the operator's identical rule is theirs and stays"
    assert allow == ["Read", cs.MANUAL_ALLOW_RULES[0]]
    g_ask, g_allow = _rules(glob)
    assert g_ask == ["Bash(git push:*)"] and g_allow == ["Bash(ls:*)"]
    assert not (root / ".claude" / cs._MANUAL_RECORD).exists() and not (home / ".claude" / cs._MANUAL_RECORD).exists()


def test_manual_mode_does_not_add_a_rule_twice_and_the_global_file_is_switched_too(project):
    root, home = project
    glob = home / ".claude" / "settings.json"
    glob.write_text(json.dumps({"permissions": {"ask": ["Write"]}}))
    cs.toggle_write_ask_for_auto_mode(False, root)
    cs.toggle_write_ask_for_auto_mode(False, root)
    ask, allow = _rules(glob)
    assert ask.count(cs.MANUAL_ASK_RULES[0]) == 1 and allow.count(cs.MANUAL_ALLOW_RULES[0]) == 1
    cs.toggle_write_ask_for_auto_mode(True, root)
    ask, allow = _rules(glob)
    assert "Write" not in ask and not set(cs.MANUAL_ASK_RULES) & set(ask) and not set(cs.MANUAL_ALLOW_RULES) & set(allow)


def test_an_unreadable_record_removes_nothing_and_says_so(project, capsys):
    root, home = project
    local = root / ".claude" / "settings.local.json"
    cs.toggle_write_ask_for_auto_mode(False, root)
    (root / ".claude" / cs._MANUAL_RECORD).write_text("{ not json")
    assert cs.toggle_write_ask_for_auto_mode(True, root)
    ask, allow = _rules(local)
    assert set(cs.MANUAL_ASK_RULES) <= set(ask), "what it can't prove it added, it does not remove"
    assert "is unreadable" in capsys.readouterr().err
