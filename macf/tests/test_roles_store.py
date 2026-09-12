"""The roles store and its CLI, checked against the roles policy.

Each test names the policy clause it holds the code to. Fixtures are generic:
a role called "Lab Course Assistant" with a few duties, a task store holding
one completed and one open task, and an events log in a temp file.
"""
import json
from datetime import date, datetime

import pytest

from macf.lifecycle import IllegalTransition, check_transition
from macf.roles import Duty, Role, RoleError, RoleStore
from macf.roles.cadence import CadenceError, parse_cadence, parse_horizon_minutes
from macf.roles.cli import add_role_parser


@pytest.fixture
def tasks(tmp_path, monkeypatch):
    """A home task store with #7 completed and #8 in progress."""
    store = tmp_path / "home_tasks"
    store.mkdir()
    for tid, status in (("7", "completed"), ("8", "in_progress")):
        (store / f"{tid}.json").write_text(json.dumps(
            {"id": tid, "subject": f"#{tid} something", "status": status, "description": "x"}))
    monkeypatch.setenv("MACF_TASK_STORE_DIR", str(store))
    return store


@pytest.fixture
def store(tmp_path, monkeypatch, tasks):
    root = tmp_path / "roles"
    monkeypatch.setenv("MACF_ROLES_DIR", str(root))
    return RoleStore()


@pytest.fixture
def lab(store):
    role, folder = store.create_role("Lab Course Assistant", icon="🎓", expires=date(2026, 12, 15),
                                     review_by=date(2026, 12, 15), review_horizon="14d",
                                     charter_seed="Assist the lab sections.")
    return role, folder


def _parse(argv):
    import argparse
    p = argparse.ArgumentParser()
    add_role_parser(p.add_subparsers(dest="cmd"))
    return p.parse_args(argv)


def _run(argv):
    args = _parse(argv)
    return args.func(args)


# ---- identity and layout (policy: identity and the store) ---------------------

def test_role_folder_and_charter_scaffold(lab):
    role, folder = lab
    assert folder.name == f"{date.today().isoformat()}_{role.id}_Lab_Course_Assistant"
    assert (folder / "data.json").exists()
    charter = (folder / "charter.md").read_text()
    assert charter.startswith("# Lab Course Assistant")
    assert "Assist the lab sections." in charter
    assert "## Wiki-Links" in charter


def test_ids_are_six_hex_and_unique(store, lab):
    role, folder = lab
    ids = {role.id}
    for i in range(20):
        d, _ = store.add_duty(role, folder, f"duty {i}")
        assert len(d.id) == 6 and int(d.id, 16) >= 0
        assert d.id not in ids
        ids.add(d.id)
    assert store.all_ids() == ids


def test_round_trip_survives_a_fresh_store_instance(store, lab):
    """Success criterion: created, noted, reviewed, then read back byte-for-byte."""
    role, folder = lab
    d, path = store.add_duty(role, folder, "board plan", due=datetime(2026, 9, 15), horizon="3d",
                             why="draft one afternoon, review the day before", importance="high")
    store.note_duty(d, folder, "drafted")
    store.note_role(role, folder, "first week")
    before = {p.name: p.read_bytes() for p in folder.iterdir()}

    fresh = RoleStore()
    r2, f2 = fresh.find_role(role.id)
    d2, p2 = fresh.find_duty(d.id)
    assert r2 == Role.model_validate(json.loads((folder / "data.json").read_text()))
    assert d2.title == "board plan" and d2.horizon == "3d" and d2.updates[0].kind == "declare"
    assert "review the day before" in d2.updates[0].description
    after = {p.name: p.read_bytes() for p in f2.iterdir()}
    assert before == after


def test_find_by_title_prefix_and_ambiguity(store, lab):
    role, folder = lab
    store.create_role("Lab Safety Officer", icon="⛑️")
    assert store.find_role("lab course")[0].id == role.id
    with pytest.raises(RoleError, match="ambiguous"):
        store.find_role("lab")
    with pytest.raises(RoleError, match="no role matches"):
        store.find_role("zzz")


# ---- time properties (policy: horizon belongs to the duty) --------------------

def test_dated_duty_without_horizon_is_refused_and_names_the_policy(store, lab):
    role, folder = lab
    with pytest.raises(RoleError, match="reasoning a horizon"):
        store.add_duty(role, folder, "board plan", due=datetime(2026, 9, 15))
    with pytest.raises(RoleError, match="reasoning a horizon"):
        store.add_duty(role, folder, "sections", cadence="weekly:tue", horizon=None)
    with pytest.raises(RoleError, match="--why"):
        store.add_duty(role, folder, "board plan", due=datetime(2026, 9, 15), horizon="3d")


def test_horizon_reasoning_is_the_first_note(store, lab):
    role, folder = lab
    d, _ = store.add_duty(role, folder, "welcome post", due=datetime(2026, 9, 12), horizon="1d",
                          why="ten minutes, no dependencies")
    assert d.updates[0].description == "Declared. Horizon 1d: ten minutes, no dependencies"
    assert d.horizon_minutes() == 1440


@pytest.mark.parametrize("text,minutes", [("3d", 4320), ("36h", 2160), ("90m", 90)])
def test_horizon_units(text, minutes):
    assert parse_horizon_minutes(text) == minutes


@pytest.mark.parametrize("bad", ["", "3", "3w", "-1d", "0d"])
def test_horizon_refuses_other_shapes(bad):
    with pytest.raises(CadenceError):
        parse_horizon_minutes(bad)


def test_cadence_grammar():
    c = parse_cadence("weekly:tue,thu at 11:45 dur 6h until 2026-12-15")
    assert c.kind == "weekly" and c.weekdays == [1, 3]
    assert c.at.hour == 11 and c.at.minute == 45
    assert c.duration_minutes == 360 and c.until == date(2026, 12, 15)
    assert parse_cadence("monthly:15").day_of_month == 15
    assert parse_cadence("daily").kind == "daily"
    for bad in ("weekly:tues", "monthly:32", "yearly", "daily at noon", "daily dur 2w", "daily until soon", "weekly:"):
        with pytest.raises(CadenceError):
            parse_cadence(bad)


# ---- lifecycle (policy: lifecycle; shared check_transition) -------------------

def test_shared_transition_check():
    m = {"a": ["b"], "b": []}
    assert check_transition(m, None, "b") == "b"
    with pytest.raises(IllegalTransition):
        check_transition(m, "b", "a")
    with pytest.raises(ValueError, match="not a key"):
        check_transition(m, "zzz", "a")


def test_role_lifecycle_terminal_states_refuse_resume(store, lab):
    role, folder = lab
    store.advance_role(role, folder, "paused", "break")
    store.advance_role(role, folder, "expired")
    with pytest.raises(RoleError, match="Illegal transition"):
        store.advance_role(role, folder, "active")
    with pytest.raises(RoleError, match="expired"):
        store.add_duty(role, folder, "too late")
    kinds = [u.kind for u in store.find_role(role.id)[0].updates]
    assert kinds == ["assign", "paused", "expired"]


def test_done_requires_evidence_that_is_completed(store, lab):
    """Policy: a declaration is satisfied only by an implementation on record."""
    role, folder = lab
    d, _ = store.add_duty(role, folder, "welcome post")
    with pytest.raises(RoleError, match="done requires evidence"):
        store.advance_duty(d, folder, "done")
    with pytest.raises(RoleError, match="in_progress, not completed"):
        store.advance_duty(d, folder, "done", evidence=["8"])
    with pytest.raises(RoleError, match="does not exist"):
        store.advance_duty(d, folder, "done", evidence=["999"])
    with pytest.raises(RoleError, match="does not exist"):
        store.advance_duty(d, folder, "done", evidence=["agent/public/reports/nope.md"])
    store.advance_duty(d, folder, "done", evidence=["#7"])
    d2, _ = store.find_duty(d.id)
    assert d2.state == "done" and d2.evidence == ["#7"]
    with pytest.raises(RoleError, match="Illegal transition"):
        store.advance_duty(d2, folder, "active")


def test_the_record_itself_refuses_done_without_evidence():
    """The schema, not only the verb: a hand-edited file cannot claim done for nothing."""
    with pytest.raises(ValueError, match="evidence"):
        Duty(id="abc123", role_id="abc124", title="x", state="done")
    with pytest.raises(ValueError, match="horizon"):
        Duty(id="abc123", role_id="abc124", title="x", due=datetime(2026, 1, 1))
    with pytest.raises(ValueError, match="extra"):
        Duty(id="abc123", role_id="abc124", title="x", parent_duty="abc125")


def test_defer_needs_a_reason_and_can_be_reactivated(store, lab):
    role, folder = lab
    d, _ = store.add_duty(role, folder, "rubric")
    with pytest.raises(RoleError, match="--reason"):
        store.advance_duty(d, folder, "deferred")
    store.advance_duty(d, folder, "deferred", "the department supplies one")
    store.advance_duty(d, folder, "pending", "they did not")
    assert [u.kind for u in store.find_duty(d.id)[0].updates] == ["declare", "deferred", "pending"]


# ---- tracks and occurrences ---------------------------------------------------

def test_tracks_resolve_live_task_status(store, lab):
    role, folder = lab
    d, _ = store.add_duty(role, folder, "board plan")
    with pytest.raises(RoleError, match="does not exist"):
        store.link(d, folder, ["999"])
    store.link(d, folder, ["8", "#7"])
    d2, _ = store.find_duty(d.id)
    assert d2.state == "active" and d2.tracks == ["7", "8"]
    assert store.live_tracks(d2) == [("7", "completed", "#7 something"), ("8", "in_progress", "#8 something")]
    store.unlink(d2, folder, ["7"])
    with pytest.raises(RoleError, match="does not track"):
        store.unlink(d2, folder, ["7"])


def test_cadence_occurrence_notes_carry_done_on(store, lab):
    role, folder = lab
    d, _ = store.add_duty(role, folder, "sections", cadence="weekly:tue", horizon="2d", why="prep")
    store.note_duty(d, folder, "both ran", kind="occurrence", done_on=date(2026, 9, 15))
    d2, _ = store.find_duty(d.id)
    assert d2.done_on_dates() == [date(2026, 9, 15)]
    assert json.loads((folder / f"DUTY_{d.id}_sections.json").read_text())["updates"][-1]["done_on"] == "2026-09-15"


def test_events_are_emitted_for_every_mutation(store, lab):
    from macf.agent_events_log import get_log_path
    role, folder = lab
    d, _ = store.add_duty(role, folder, "x")
    store.note_duty(d, folder, "n")
    store.advance_duty(d, folder, "done", evidence=["7"])
    store.advance_role(role, folder, "paused")
    events = [json.loads(l)["event"] for l in get_log_path().read_text().splitlines()]
    for e in ("role_created", "duty_added", "duty_serviced", "duty_lifecycle_advanced", "role_lifecycle_advanced"):
        assert e in events, events


# ---- the CLI surface ----------------------------------------------------------

def test_cli_create_add_show_json(store, capsys):
    assert _run(["role", "create", "Corpus Librarian", "--icon", "📚", "--json"]) == 0
    rid = json.loads(capsys.readouterr().out)["id"]
    assert _run(["role", "duty", "add", rid, "intake", "--due", "2026-10-01", "--horizon", "2d",
                 "--why", "a day to read, a day of slack", "--json"]) == 0
    duty = json.loads(capsys.readouterr().out)
    assert duty["role_id"] == rid and duty["horizon"] == "2d"
    assert _run(["role", "show", "corpus", "--json"]) == 0
    rec = json.loads(capsys.readouterr().out)
    assert [d["title"] for d in rec["duties"]] == ["intake"]


def test_cli_refusals_are_one_line_and_exit_1(store, lab, capsys):
    role, folder = lab
    assert _run(["role", "duty", "add", role.id, "x", "--due", "2026-10-01"]) == 1
    out = capsys.readouterr().out
    assert out.startswith("❌") and out.count("\n") == 1 and "reasoning a horizon" in out
    assert _run(["role", "duty", "add", role.id, "x", "--cadence", "weekly:tues", "--horizon", "1d", "--why", "w"]) == 1
    out = capsys.readouterr().out
    assert out.startswith("❌ cadence:") and out.count("\n") == 1
    assert _run(["role", "duty", "add", role.id, "x", "--due", "2026-10-01", "--json"]) == 1
    assert json.loads(capsys.readouterr().out)["ok"] is False


def test_cli_done_defer_review_lifecycle(store, lab, capsys):
    role, folder = lab
    _run(["role", "duty", "add", role.id, "welcome"])
    capsys.readouterr()
    assert _run(["role", "duty", "done", "welcome"]) == 1
    assert "evidence" in capsys.readouterr().out
    assert _run(["role", "duty", "done", "welcome", "--evidence", "7", "--note", "posted"]) == 0
    capsys.readouterr()
    assert _run(["role", "review", role.id, "--outcome", "still teaching", "--next", "2027-01-10"]) == 0
    capsys.readouterr()
    r = store.find_role(role.id)[0]
    assert r.review_by == date(2027, 1, 10) and r.updates[-1].kind == "review"
    assert _run(["role", "review", role.id, "--outcome", "done", "--retire"]) == 0
    assert store.find_role(role.id)[0].state == "retired"
    assert _run(["role", "list"]) == 0
    assert "no roles" in capsys.readouterr().out
    assert _run(["role", "list", "--all"]) == 0
    assert "Lab Course Assistant" in capsys.readouterr().out
