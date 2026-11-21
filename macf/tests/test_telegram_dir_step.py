"""``agent init`` says where a seat's Telegram plugin keeps its poller files, and the watch looks there (#1069).

Agents on one login are separated for Telegram only by ``TELEGRAM_STATE_DIR`` in each one's own
settings ``env``. The plugin gets it from the settings of the directory the session starts in, and
its default directory is under the session's own ``HOME``; neither is the process running the check.
"""
import datetime
import json
import os
import types
from pathlib import Path

from macf import agent_stack
from macf.agent_stack import ALREADY, DRIFT, SKIPPED, step_telegram_dir
from macf.pd import interface as pdi
from macf.pd import watch

NOW = 1_800_000_000.0
TELEGRAM = ["plugin:telegram:telegram"]


def _declare(home, channels=TELEGRAM, project=None, session_home=None):
    (home / ".maceff" / "pd").mkdir(parents=True, exist_ok=True)
    (home / ".maceff" / "config.json").write_text(json.dumps({"agent_identity": {"calling_card": "Resident"}}))
    (home / ".maceff_primary_agent.id").write_text("1a2b3c4d-0000")
    session = {"name": "session", "kind": "session", "account": "resident", "restart": "always",
               "liveness_interval_s": 600.0, "memory_limit_mb": 64,
               "command": ["python3", "-m", "macf.cli", "harness", "unit", "--home", "{agent_home}",
                           "--project-dir", project if project is not None else "{agent_home}"]}
    if session_home is not None:
        session["environment"] = {"HOME": session_home}
    declaration = {"version": 1, "agent": "Resident", "units": [session]}
    if channels is not None:
        declaration["operator_channels"] = channels
    pdi.declaration_path(home).write_text(json.dumps(declaration))
    return home


def _ctx(home, in_container=False):
    return types.SimpleNamespace(home=home, in_container=in_container, args=types.SimpleNamespace())


def _settings(folder, body, name="settings.local.json"):
    (folder / ".claude").mkdir(parents=True, exist_ok=True)
    (folder / ".claude" / name).write_text(json.dumps(body))


def test_no_declaration_or_an_unreadable_one_or_none_naming_telegram_is_skipped_and_says_why(tmp_path):
    bare = tmp_path / "bare"
    bare.mkdir()
    assert step_telegram_dir(_ctx(bare)).status == SKIPPED
    broken = _declare(tmp_path / "broken")
    pdi.declaration_path(broken).write_text("{not json")
    r = step_telegram_dir(_ctx(broken))
    assert r.status == SKIPPED and "can't be read" in r.detail
    other = _declare(tmp_path / "other", channels=["plugin:other:other"])
    assert step_telegram_dir(_ctx(other)).detail == "the declaration names no Telegram channel"
    assert step_telegram_dir(_ctx(_declare(tmp_path / "none", channels=None))).status == SKIPPED


def test_in_a_container_the_container_owns_it(tmp_path):
    assert step_telegram_dir(_ctx(_declare(tmp_path / "h"), in_container=True)).detail == agent_stack.CONTAINER_OWNS


def test_the_account_wide_default_is_found_with_drift_naming_the_setting_never_refused(tmp_path):
    home = _declare(tmp_path / "seat", session_home=str(tmp_path / "login"))
    r = step_telegram_dir(_ctx(home))
    assert r.status == DRIFT, r
    assert str(tmp_path / "login" / ".claude" / "channels" / "telegram") in r.detail      # the session's HOME, not ours
    assert "TELEGRAM_STATE_DIR" in r.detail and str(home / ".claude" / "settings.local.json") in r.detail
    assert "never fails the run" in r.detail


def test_a_directory_of_the_seats_own_is_said_with_its_source(tmp_path):
    home = _declare(tmp_path / "seat")
    _settings(home, {"env": {watch.TELEGRAM_STATE_ENV: str(tmp_path / "own")}})
    r = step_telegram_dir(_ctx(home))
    assert r.status == ALREADY and str(tmp_path / "own") in r.detail and "settings.local.json of the home" in r.detail


def test_the_settings_of_the_sessions_project_directory_are_read_not_only_the_homes(tmp_path):
    """The client reads its settings from where the session starts, so that is where the plugin's env is."""
    project = tmp_path / "work"
    home = _declare(tmp_path / "seat", project=str(project))
    _settings(home, {"env": {watch.TELEGRAM_STATE_ENV: str(tmp_path / "from_home")}})
    _settings(project, {"env": {watch.TELEGRAM_STATE_ENV: str(tmp_path / "from_project")}})
    r = step_telegram_dir(_ctx(home))
    assert str(tmp_path / "from_project") in r.detail and "project directory" in r.detail
    (project / ".claude" / "settings.local.json").unlink()          # none there: the home's is the fallback
    assert str(tmp_path / "from_home") in step_telegram_dir(_ctx(home)).detail


def test_the_session_places_come_from_the_session_unit(tmp_path):
    home = _declare(tmp_path / "seat", project="/srv/work", session_home="{agent_home}/login")
    declaration = pdi.Declaration.model_validate_json(pdi.declaration_path(home).read_text())
    assert watch.session_places(declaration, home) == watch.SessionPlaces(
        project_dir=Path("/srv/work"), login_home=home / "login", environment={"HOME": "{agent_home}/login"})
    plain = _declare(tmp_path / "plain")
    assert watch.session_places(pdi.Declaration.model_validate_json(pdi.declaration_path(plain).read_text()),
                                plain) == watch.SessionPlaces(project_dir=plain)


def test_the_watch_judges_the_poller_in_the_directory_the_session_would_use(tmp_path):
    project = tmp_path / "work"
    home = _declare(tmp_path / "seat", project=str(project))
    state = tmp_path / "own"
    state.mkdir()
    (state / "bot.pid").write_text(str(os.getpid()))
    stamp = datetime.datetime.fromtimestamp(NOW - 20, tz=datetime.timezone.utc)
    (state / "diag.jsonl").write_text(json.dumps({"ts": stamp.isoformat().replace("+00:00", "Z"), "pid": os.getpid(),
                                                  "event": "heartbeat"}) + "\n")
    _settings(project, {"env": {watch.TELEGRAM_STATE_ENV: str(state)}})
    (f,) = [x for x in watch.check_home(home, NOW, probe=lambda pid, start: True) if x.subject == "telegram"]
    assert f.verdict == "ALIVE" and "session's project directory" in f.detail, f


def test_a_directory_the_session_unit_declares_is_said_and_its_placeholder_filled_in(tmp_path):
    home = _declare(tmp_path / "seat")
    declaration = json.loads(pdi.declaration_path(home).read_text())
    declaration["units"][0]["environment"] = {watch.TELEGRAM_STATE_ENV: "{agent_home}/telegram"}
    pdi.declaration_path(home).write_text(json.dumps(declaration))
    r = step_telegram_dir(_ctx(home))
    assert r.status == ALREADY and str(home / "telegram") in r.detail and "declared environment" in r.detail


def test_the_process_environment_of_agent_init_is_not_the_sessions(tmp_path, monkeypatch):
    """The step once read it, and in a test environment that set it, said the seat had a directory of its own."""
    monkeypatch.setenv(watch.TELEGRAM_STATE_ENV, str(tmp_path / "shell"))
    assert step_telegram_dir(_ctx(_declare(tmp_path / "seat"))).status == DRIFT


def test_a_directory_in_the_logins_own_settings_is_named_as_shared(tmp_path):
    """Claude Code reads the user-level settings.json for every agent on the login, so a directory named
    there reaches them all: it is a directory, and it is the sharing the step exists to flag."""
    login, seat = tmp_path / "login", tmp_path / "seat"
    seat.mkdir()
    _settings(login, {"env": {watch.TELEGRAM_STATE_ENV: str(tmp_path / "everyones")}}, name="settings.json")
    where, source = watch.telegram_state_dir(seat, seat, login_home=login)
    assert (where, source) == (tmp_path / "everyones", watch.LOGIN_SETTINGS_SOURCE)
    # The seat's own settings come first, and the unit's declared environment after the login's.
    _settings(seat, {"env": {watch.TELEGRAM_STATE_ENV: str(tmp_path / "own")}})
    assert watch.telegram_state_dir(seat, seat, login_home=login)[0] == tmp_path / "own"
    (seat / ".claude" / "settings.local.json").unlink()
    unit_env = {watch.TELEGRAM_STATE_ENV: str(tmp_path / "unit")}
    assert watch.telegram_state_dir(seat, seat, login_home=login, unit_env=unit_env)[1] == watch.LOGIN_SETTINGS_SOURCE


def test_where_the_agent_home_is_the_login_its_settings_json_is_the_shared_one(tmp_path):
    """On a host the agent's home is often the login's home: that settings.json is every agent's, while the
    same directory's settings.local.json is this project's own."""
    home = tmp_path / "both"
    _settings(home, {"env": {watch.TELEGRAM_STATE_ENV: str(tmp_path / "a")}}, name="settings.json")
    assert watch.telegram_state_dir(home, home, login_home=home)[1] == watch.LOGIN_SETTINGS_SOURCE
    _settings(home, {"env": {watch.TELEGRAM_STATE_ENV: str(tmp_path / "b")}})
    assert watch.telegram_state_dir(home, home, login_home=home) == (tmp_path / "b", "settings.local.json of the home")


def test_the_step_flags_a_shared_directory_even_though_one_is_named(tmp_path):
    login = tmp_path / "login"
    _settings(login, {"env": {watch.TELEGRAM_STATE_ENV: str(tmp_path / "everyones")}}, name="settings.json")
    r = step_telegram_dir(_ctx(_declare(tmp_path / "seat", session_home=str(login))))
    assert r.status == DRIFT and "every agent on this login" in r.detail and str(tmp_path / "everyones") in r.detail
