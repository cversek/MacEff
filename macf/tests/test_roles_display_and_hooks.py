"""Display, focus and the hook seams, held to the roles policy.

The stanza never truncates open duties; completed duties follow the succinct
rule; the pointers are scoped; focus is derived from events; the nag fires on
the schedule and only on it, and stops after a refocus; the Stop gate blocks
in AUTO_MODE only while due-now duties are unserviced, composes with the scope
gate, fails open with the shared failsafe, and never blocks on undated duties.
"""
import json
import time
from datetime import date, datetime, timedelta
from unittest.mock import patch

import pytest

from macf.agent_events_log import append_event
from macf.roles import RoleStore
from macf.roles import display as disp
from macf.roles import hooks as rh
from macf.roles.focus import current_focus, set_focus

# The nag counts REAL events after a tier-entry time, so the clock the tiers
# read must agree with the event log's clock: pin it to now, and place every
# due date relative to it.
NOW = datetime.now().replace(microsecond=0)
TODAY = datetime(NOW.year, NOW.month, NOW.day)
LATE = TODAY - timedelta(days=2)          # 🔴 OVERDUE 2d
SOON2 = TODAY + timedelta(days=2)         # ⏳2d with a 3d horizon
SOON3 = TODAY + timedelta(days=3)         # ⏳3d with a 3d horizon (entered TODAY 00:00)


@pytest.fixture
def store(tmp_path, monkeypatch):
    monkeypatch.setenv("MACF_ROLES_DIR", str(tmp_path / "roles"))
    monkeypatch.setenv("MACF_ROLES_NOW", NOW.isoformat())
    monkeypatch.setenv("MACF_TOUCH_NAG_BASE", "4")
    return RoleStore()


@pytest.fixture
def lab(store):
    role, folder = store.create_role("Lab Course Assistant", icon="🎓", expires=date(2026, 12, 15),
                                     review_by=date(2026, 12, 15), review_horizon="14d")
    return role, folder


def _tool_calls(n, at=None):
    for _ in range(n):
        append_event("tool_call_started", {"tool": "Bash"})


# ---- display -----------------------------------------------------------------

def test_focused_role_expands_every_open_duty_never_truncated(store, lab):
    role, folder = lab
    for i in range(40):
        store.add_duty(role, folder, f"duty {i:02d}")
    lines = disp.stanza(store, "focused", role.id, at=NOW, ansi=False)
    assert lines[0] == "🎭 ROLES"
    assert "🎯" in lines[1] and lines[1].startswith("◼ 🎓 Lab Course Assistant")
    assert sum(1 for l in lines if "📌" in l) == 40


def test_unfocused_role_collapses_with_last_and_next(store, lab):
    role, folder = lab
    store.add_duty(role, folder, "board plan", due=SOON3, horizon="3d", why="w")
    lines = disp.stanza(store, "focused", None, at=NOW, ansi=False)
    assert len(lines) == 2 and "· last: board plan" in lines[1] and f"next: board plan ({SOON3:%m-%d})" in lines[1]
    assert "⏳3d" in lines[1] and "🎯" not in lines[1] and "👈" in lines[1]
    assert disp.stanza(store, "none", None, at=NOW) == []


def test_status_boxes_marks_and_the_role_line_carries_the_most_urgent(store, lab):
    role, folder = lab
    store.add_duty(role, folder, "late", due=LATE, horizon="1d", why="w")
    store.add_duty(role, folder, "soon", due=SOON2, horizon="3d", why="w")
    store.add_duty(role, folder, "plain")
    lines = disp.stanza(store, "focused", role.id, at=NOW, ansi=False)
    assert "🔴 OVERDUE 2d" in lines[1] and lines[1].endswith("🎯" ) is False   # 👈 age comes last
    assert lines[1].split("🎯")[1].strip().startswith("👈")
    assert lines[2].startswith("    ◻ 📌 late") and "🔴 OVERDUE 2d" in lines[2]
    assert lines[3].startswith("    ◻ 📌 soon") and "⏳2d" in lines[3]
    assert lines[4].startswith("    ◻ 📌 plain")
    assert sum(1 for l in lines[2:] if "👈" in l) == 1               # one pointer per role


def test_succinct_rule_for_completed_duties(store, lab, monkeypatch):
    role, folder = lab
    d, _ = store.add_duty(role, folder, "welcome")
    store.advance_duty(d, folder, "deferred", "not needed")
    d2, _ = store.find_duty(d.id)
    sess = d2.updates[-1].breadcrumb.split("/")[0][2:]          # the session that touched it
    shown = disp.stanza(store, "focused", role.id, session_id=sess, at=NOW, ansi=False)
    assert any("📌 welcome" in l for l in shown)
    hidden = disp.stanza(store, "focused", role.id, session_id="deadbeef", at=NOW, ansi=False)
    assert not any("📌 welcome" in l for l in hidden)
    assert any("1 done/deferred hidden" in l for l in hidden)
    everything = disp.stanza(store, "focused", role.id, session_id="deadbeef", at=NOW, ansi=False, show_all=True)
    assert any("📌 welcome" in l for l in everything)


def test_trace_header_and_next_duty_line(store, lab):
    role, folder = lab
    store.add_duty(role, folder, "board plan", due=SOON3, horizon="3d", why="w")
    assert disp.trace_header(store, None, NOW) == []
    head = disp.trace_header(store, role.id, NOW)[0]
    assert head.startswith("   🎯 focus: 🎓 Lab Course Assistant") and f"next due: board plan ({SOON3:%a %m-%d}" in head
    assert "next duty board plan (DUE_SOON, ⏳3d)" in disp.next_duty_line(store, role.id, NOW)


# ---- focus -----------------------------------------------------------------------

def test_focus_is_derived_from_events_one_at_a_time(store, lab):
    role, folder = lab
    other, _ = store.create_role("Corpus Librarian", icon="📚")
    assert current_focus() is None
    set_focus(role.id, None)
    assert current_focus() == role.id
    set_focus(other.id, role.id)
    assert current_focus() == other.id
    set_focus(None, other.id, unserviced=[{"duty_id": "x"}], note="stepping away")
    assert current_focus() is None
    assert rh.focus_marker(store) == ""
    set_focus(role.id, None)
    assert rh.focus_marker(store) == "🎓"


# ---- the Conscientiousness nag -------------------------------------------------------

def test_nag_fires_on_the_schedule_and_stops_after_refocus(store, lab):
    """DUE_SOON at B, 2B, 4B ...; nothing in between; cleared by focusing the role."""
    role, folder = lab
    store.add_duty(role, folder, "board plan", due=SOON3, horizon="3d", why="w")
    fired = []
    for n in range(1, 18):
        _tool_calls(1)
        msg = rh.conscientiousness_nag(store, NOW)
        if msg:
            fired.append(n)
            assert "🎓 Lab Course Assistant" in msg and f"macf_tools role focus {role.id}" in msg
            assert "DUE_SOON" in msg and "board plan" in msg
    assert fired == [4, 8, 16]
    set_focus(role.id, None)                       # acknowledged
    _tool_calls(4)
    assert rh.conscientiousness_nag(store, NOW) == ""
    set_focus(None, role.id)                       # unfocus does not re-arm the same entry
    _tool_calls(8)
    assert rh.conscientiousness_nag(store, NOW) == ""


def test_nag_overdue_every_base_with_tone_ramp(store, lab):
    role, folder = lab
    store.add_duty(role, folder, "late", due=LATE, horizon="1d", why="w")
    tones = {}
    for n in range(1, 13):
        _tool_calls(1)
        msg = rh.conscientiousness_nag(store, NOW)
        if msg:
            tones[n] = msg[0]
    assert tones == {4: "🌱", 8: "🌿", 12: "🌳"}


def test_nag_silent_when_nothing_is_due_or_role_is_focused(store, lab):
    role, folder = lab
    store.add_duty(role, folder, "plain")
    _tool_calls(8)
    assert rh.conscientiousness_nag(store, NOW) == ""
    store.add_duty(role, folder, "soon", due=SOON2, horizon="3d", why="w")
    set_focus(role.id, None)
    _tool_calls(8)
    assert rh.conscientiousness_nag(store, NOW) == ""


# ---- the focus gate ------------------------------------------------------------------

def test_gate_injects_list_and_blocks_only_in_auto_while_unserviced(store, lab):
    role, folder = lab
    d, _ = store.add_duty(role, folder, "board plan", due=SOON3, horizon="3d", why="w")
    store.add_duty(role, folder, "undated")
    assert rh.focus_gate(True, store, NOW)["text"] == ""            # nothing focused: silent
    set_focus(role.id, None)
    g = rh.focus_gate(True, store, NOW)
    assert g["block"] and g["unserviced"] == [d.id]
    assert "duty priorities" in g["text"] and "DUE_SOON  board plan" in g["text"] and "NORMAL    undated" in g["text"]
    assert "Due-now duties unserviced" in g["text"] and "role unfocus" in g["text"]
    g_manual = rh.focus_gate(False, store, NOW)
    assert g_manual["block"] is False and "Due-now duties unserviced" in g_manual["text"]
    # a service since tier entry clears the bound; the list is still injected
    store.note_duty(d, folder, "drafting")
    g2 = rh.focus_gate(True, store, NOW)
    assert g2["block"] is False and g2["unserviced"] == [] and "duty priorities" in g2["text"]


def test_gate_clears_on_defer_and_never_blocks_on_undated(store, lab):
    role, folder = lab
    d, _ = store.add_duty(role, folder, "late", due=LATE, horizon="1d", why="w")
    store.add_duty(role, folder, "undated", importance="critical")
    set_focus(role.id, None)
    assert rh.focus_gate(True, store, NOW)["block"]
    store.advance_duty(d, folder, "deferred", "the section was cancelled")
    assert rh.focus_gate(True, store, NOW)["block"] is False


def test_unfocus_records_what_was_due_and_clears_the_gate(store, lab, capsys):
    from macf.agent_events_log import get_log_path
    role, folder = lab
    d, _ = store.add_duty(role, folder, "late", due=LATE, horizon="1d", why="w")
    set_focus(role.id, None)
    import argparse
    from macf.roles.cli import add_role_parser
    p = argparse.ArgumentParser(); add_role_parser(p.add_subparsers(dest="cmd"))
    args = p.parse_args(["role", "unfocus"])
    assert args.func(args) == 0
    out = capsys.readouterr().out
    assert "left due-now and unserviced (recorded): late" in out
    events = [json.loads(l) for l in get_log_path().read_text().splitlines()]
    last = [e for e in events if e["event"] == "role_focus_change"][-1]
    assert last["data"]["role_id"] is None and last["data"]["unserviced_due_now"][0]["duty_id"] == d.id
    assert rh.focus_gate(True, store, NOW)["block"] is False


def test_prompt_line_only_when_today_overdue_or_review(store, lab):
    role, folder = lab
    d, _ = store.add_duty(role, folder, "board plan", due=SOON3, horizon="3d", why="w")
    set_focus(role.id, None)
    assert rh.prompt_line(store, NOW) == ""                          # DUE_SOON but not today
    assert "board plan (⏰ today)" in rh.prompt_line(store, SOON3 + timedelta(hours=9))
    assert "board plan (🔴 OVERDUE 1d)" in rh.prompt_line(store, SOON3 + timedelta(days=1, hours=9))
    assert "review ⏳10d" in rh.prompt_line(store, datetime(2026, 12, 5, 9))


# ---- the Stop hook, end to end -------------------------------------------------------------

@pytest.fixture(autouse=True)
def _fresh_failsafe():
    """The idle-stop counter is a global sidecar (/tmp/macf); start each test full
    and leave it full, so a test neither inherits a low count nor leaves one."""
    from macf.task.scope_gate_failsafe import reset
    reset()
    yield
    reset()


def _stop(auto):
    from macf.hooks.handle_stop import run
    with patch("macf.hooks.handle_stop.detect_auto_mode", return_value=(auto, "test")):
        return run(json.dumps({"stop_reason": "end_turn", "session_id": "test-sess"}))


def test_stop_hook_composes_focus_gate(store, lab, tmp_path, monkeypatch):
    monkeypatch.setenv("MACEFF_AGENT_HOME_DIR", str(tmp_path))
    from macf.utils.paths import find_agent_home
    find_agent_home.cache_clear()
    role, folder = lab
    d, _ = store.add_duty(role, folder, "late", due=LATE, horizon="1d", why="w")
    # no focus: the stop hook says nothing about roles
    r = _stop(True)
    assert r["continue"] is True and "duty priorities" not in json.dumps(r)
    set_focus(role.id, None)
    # MANUAL: injected, allowed
    r = _stop(False)
    assert r.get("decision") != "block" and "duty priorities" in r.get("systemMessage", "")
    # AUTO: blocked with the list, no active scope needed
    r = _stop(True)
    assert r.get("decision") == "block" and "late" in r["reason"] and "idle-stop counter" in r["reason"]
    # service clears it
    store.note_duty(d, folder, "handled")
    r = _stop(True)
    assert r.get("decision") != "block" and "duty priorities" in r.get("systemMessage", "")


def test_stop_hook_focus_and_scope_gates_concatenate(store, lab, tmp_path, monkeypatch):
    monkeypatch.setenv("MACEFF_AGENT_HOME_DIR", str(tmp_path))
    from macf.utils.paths import find_agent_home
    find_agent_home.cache_clear()
    from macf.task.scope import set_scope
    role, folder = lab
    store.add_duty(role, folder, "late", due=LATE, horizon="1d", why="w")
    set_focus(role.id, None)
    set_scope(["4242"])
    r = _stop(True)
    assert r.get("decision") == "block"
    assert "4242" in r["reason"] and "duty priorities" in r["reason"] and "late" in r["reason"]


def test_focus_gate_fails_open_with_the_shared_failsafe(store, lab, tmp_path, monkeypatch):
    monkeypatch.setenv("MACEFF_AGENT_HOME_DIR", str(tmp_path))
    from macf.utils.paths import find_agent_home
    find_agent_home.cache_clear()
    from macf.task.scope_gate_failsafe import COUNT_INIT
    role, folder = lab
    store.add_duty(role, folder, "late", due=LATE, horizon="1d", why="w")
    set_focus(role.id, None)
    # Same arithmetic as the sprint gate: the counter starts at COUNT_INIT and
    # each blocked Stop decrements it; the Stop that reaches 0 is let through.
    results = [_stop(True) for _ in range(COUNT_INIT)]
    assert all(r.get("decision") == "block" for r in results[:-1])
    assert all("idle-stop counter" in r["reason"] for r in results[:-1])
    assert results[-1].get("decision") != "block" and "fail-open" in results[-1].get("systemMessage", "")


def test_mode_set_work_is_unaffected_by_focus(store, lab):
    """Focus is a layer beside the work mode, not a mode."""
    from macf.modes.detection import format_mode_indicators
    role, folder = lab
    set_focus(role.id, None)
    marker = rh.focus_marker(store)
    assert format_mode_indicators({"AUTO_MODE", "DISCOVER"}, marker) == " 🤖 🎓🔍"
    assert format_mode_indicators({"AUTO_MODE", "SPRINT"}, marker) == " 🤖 🎓🏃"
    assert format_mode_indicators({"AUTO_MODE"}, "") == " 🤖"


def test_stanza_trims_titles_to_the_trees_title_width(store, lab):
    """The stanza follows the tree's truncation: titles to title_width with '...',
    the collapsed line's last/next to half of it, and no last: label at all in the
    40-column scanning view, where the pointer age already says when."""
    role, folder = lab
    long = "Confirm which of the A/B groups meets on the first Tuesday of the semester, 09-15"
    store.add_duty(role, folder, long, due=SOON2, horizon="3d", why="w")
    wide = disp.stanza(store, "focused", None, at=NOW, ansi=False, title_width=80)[1]
    assert f"next: {disp.fit(long, 40)} (" in wide and "last: " in wide     # half of 80
    narrow = disp.stanza(store, "focused", None, at=NOW, ansi=False, title_width=40)[1]
    assert f"next: {disp.fit(long, 20)} (" in narrow and "last: " not in narrow and "👈" in narrow
    expanded = disp.stanza(store, "focused", role.id, at=NOW, ansi=False, title_width=40)
    assert any(l.startswith(f"    ◻ 📌 {disp.fit(long, 40)}") for l in expanded)
    assert disp.fit(long, 40).endswith("...") and len(disp.fit(long, 40)) <= 40
    untrimmed = disp.stanza(store, "focused", role.id, at=NOW, ansi=False, title_width=0)
    assert any(long in l for l in untrimmed)
