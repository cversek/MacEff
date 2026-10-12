"""Editing a declared duty or role on the record (#390).

Before these verbs a due date, horizon or cadence could be changed only by editing the
JSON by hand, which leaves no update and no reasoning: the opposite of what the roles
policy asks of a time property.
"""
import time
from datetime import date, datetime

import pytest

from macf.roles import RoleStore
from macf.roles import hooks as rh
from macf.roles.cli import add_role_parser
from macf.roles.display import role_pointer
from macf.roles.store import RoleError


@pytest.fixture
def store(tmp_path, monkeypatch):
    monkeypatch.setenv("MACF_ROLES_DIR", str(tmp_path / "roles"))
    monkeypatch.delenv("MACF_ROLES_NOW", raising=False)
    return RoleStore()


@pytest.fixture
def lab(store):
    return store.create_role("Lab Course Assistant", icon="🎓", expires=date(2026, 12, 15),
                             review_by=date(2026, 12, 15), review_horizon="14d")


def _run(argv):
    import argparse
    p = argparse.ArgumentParser()
    add_role_parser(p.add_subparsers(dest="cmd"))
    args = p.parse_args(argv)
    return args.func(args)


def _dated(store, lab, title="board plan"):
    role, folder = lab
    return store.add_duty(role, folder, title, due=datetime(2026, 11, 3), horizon="3d", why="w")


def test_an_edit_records_old_new_and_why_and_show_lists_it(store, lab, capsys):
    d, path = _dated(store, lab)
    assert _run(["role", "duty", "edit", d.id, "--due", "2026-11-04T23:59", "--why", "the lab moved a day"]) == 0
    d = store.find_duty(d.id)[0]
    assert d.due == datetime(2026, 11, 4, 23, 59)
    last = d.updates[-1]
    assert last.kind == "edit" and last.breadcrumb
    assert last.description == "due 2026-11-03T00:00 -> 2026-11-04T23:59: the lab moved a day"
    capsys.readouterr()
    _run(["role", "duty", "show", d.id])
    assert "edit     due 2026-11-03T00:00 -> 2026-11-04T23:59" in capsys.readouterr().out


def test_a_time_change_needs_why(store, lab):
    d, path = _dated(store, lab)
    with pytest.raises(RoleError, match="needs --why"):
        store.edit_duty(d, path.parent, {"horizon": "5d"})
    assert _run(["role", "duty", "edit", d.id, "--horizon", "5d"]) == 1


def test_a_dated_duty_is_never_left_without_a_horizon(store, lab):
    d, path = _dated(store, lab)
    with pytest.raises(ValueError, match="needs a horizon"):
        store.edit_duty(d, path.parent, {"horizon": None}, why="w")
    assert store.find_duty(d.id)[0].horizon == "3d"          # nothing was written


def test_a_settled_duty_keeps_its_time_but_takes_corrections(store, lab):
    d, path = _dated(store, lab)
    d = store.advance_duty(d, path.parent, "deferred", reason="term ended early")
    with pytest.raises(RoleError, match="deferred"):
        store.edit_duty(d, path.parent, {"due": datetime(2026, 11, 5)}, why="w")
    d = store.edit_duty(d, path.parent, {"title": "board plan, group B"})
    assert d.title == "board plan, group B" and d.state == "deferred"


def test_nothing_to_change_and_an_unknown_duty_are_refused(store, lab):
    d, path = _dated(store, lab)
    with pytest.raises(RoleError, match="nothing to change"):
        store.edit_duty(d, path.parent, {"horizon": "3d"}, why="w")
    assert _run(["role", "duty", "edit", "zzzzzz", "--title", "x"]) == 1
    assert _run(["role", "duty", "edit", d.id]) == 1                 # no field named


def test_an_edit_is_a_service_and_takes_the_pointer(store, lab):
    role, folder = lab
    a, apath = _dated(store, lab, "board plan")
    time.sleep(1.1)                                        # updates are stamped to the second
    store.add_duty(role, folder, "welcome post")
    time.sleep(1.1)
    entered = datetime.now()
    a = store.edit_duty(a, apath.parent, {"body": "both sections"})
    assert rh._serviced_since(a, entered.replace(microsecond=0))
    duties = [d for d, _ in store.duties(folder)]
    assert role_pointer(duties)[0] == a.id


def test_role_edit(store, lab, capsys):
    role, folder = lab
    with pytest.raises(RoleError, match="needs --why"):
        store.edit_role(role, folder, {"expires": date(2026, 12, 20)})
    assert _run(["role", "edit", role.id, "--expires", "2026-12-20", "--why", "grades are due the 20th",
                 "--resource", "~/notes/ipl", "--icon", "🧪"]) == 0
    role = store.find_role(role.id)[0]
    assert role.expires == date(2026, 12, 20) and role.icon == "🧪" and role.resources == ["~/notes/ipl"]
    assert role.updates[-1].kind == "edit" and "expires 2026-12-15 -> 2026-12-20" in role.updates[-1].description
    assert _run(["role", "edit", role.id, "--drop-resource", "~/notes/other"]) == 1
    assert _run(["role", "edit", role.id, "--drop-resource", "~/notes/ipl"]) == 0
    assert store.find_role(role.id)[0].resources == []
    assert role.state == "active"                           # state is never an edit
