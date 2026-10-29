"""Mail is watched where the broker delivers it, by the rule `amail list` uses.

The primal daemon once watched <home>/amail/pickup, a path no deployment creates: the host
broker delivers to the handoff directory its amail settings name, and a container's to
/var/lib/amail/handoff/<agent>. It detected no mail anywhere and said nothing (Oct 16).
"""
import json

from macf.amail import pickup as pk


def _settings(home, **cfg):
    (home / ".maceff").mkdir(parents=True, exist_ok=True)
    (home / ".maceff" / "amail.json").write_text(json.dumps(cfg))


def test_the_agents_amail_settings_name_the_box(tmp_path):
    _settings(tmp_path, handoff=str(tmp_path / "handoff"), agent="harbormaster")
    env = {"MACEFF_AGENT_NAME": "other", "MACF_AMAIL_HANDOFF": "/elsewhere"}
    assert pk.resolve_pickup_box(tmp_path, env) == (tmp_path / "handoff" / "harbormaster",
                                                    pk.FROM_SETTINGS)


def test_without_settings_the_environment_names_it(tmp_path):
    env = {"MACEFF_AGENT_NAME": "manny2"}
    assert pk.resolve_pickup_box(tmp_path, env) == (pk.Path("/var/lib/amail/handoff/manny2"),
                                                    pk.FROM_ENVIRONMENT)
    env["MACF_AMAIL_HANDOFF"] = str(tmp_path / "h")
    assert pk.pickup_box(tmp_path, env) == tmp_path / "h" / "manny2"


def test_each_key_is_resolved_on_its_own(tmp_path):
    """A host's settings name only the handoff; the agent comes from the shell. Taken as a
    pair, the box would be the container default, reported as right (CTB on #693)."""
    _settings(tmp_path, handoff="/srv/hostmail/handoff")
    box, how = pk.resolve_pickup_box(tmp_path, {"MACEFF_AGENT_NAME": "seat"})
    assert box == pk.Path("/srv/hostmail/handoff/seat")
    assert how == "handoff from amail.json, agent from environment"


def test_the_daemon_and_amail_list_name_the_same_box(tmp_path, monkeypatch):
    """One rule, two callers: every mix of file keys and environment gives the same box."""
    from macf import cli
    monkeypatch.setattr("macf.utils.paths.find_agent_home", lambda: tmp_path)
    files = [{}, {"handoff": "/f/h"}, {"agent": "fa"}, {"handoff": "/f/h", "agent": "fa"}]
    envs = [{}, {"MACEFF_AGENT_NAME": "ea"}, {"MACF_AMAIL_HANDOFF": "/e/h"},
            {"MACEFF_AGENT_NAME": "ea", "MACF_AMAIL_HANDOFF": "/e/h"}]
    for cfg in files:
        _settings(tmp_path, **cfg)
        for env in envs:
            for k in ("MACEFF_AGENT_NAME", "MACF_AMAIL_HANDOFF"):
                monkeypatch.delenv(k, raising=False)
            for k, v in env.items():
                monkeypatch.setenv(k, v)
            box, how = pk.resolve_pickup_box(tmp_path, env)
            c = cli._amail_config()
            if not c.get("agent"):
                assert how == pk.GUESSED, (cfg, env)
            else:
                assert box == pk.Path(c["handoff"]) / c["agent"], (cfg, env)


def test_nothing_named_is_a_guess_and_says_so(tmp_path):
    (tmp_path / ".maceff").mkdir()
    (tmp_path / ".maceff" / "amail.json").write_text("[]")            # parses, but is no object
    assert pk.resolve_pickup_box(tmp_path, {}) == (tmp_path / "amail" / "pickup", pk.GUESSED)


def test_the_daemons_mail_source_and_unread_check_watch_the_resolved_box(tmp_path, monkeypatch):
    monkeypatch.delenv("MACEFF_AGENT_NAME", raising=False)
    _settings(tmp_path, handoff=str(tmp_path / "handoff"), agent="harbormaster")
    from macf.pd.unread_mail import pickup_box
    from macf.transcript_monitor.sources import agent_store_source
    box = tmp_path / "handoff" / "harbormaster"
    assert pickup_box(tmp_path) == box
    assert agent_store_source(tmp_path).store_dir == box


def test_the_notifier_says_which_box_it_watches(tmp_path, monkeypatch, capsys):
    monkeypatch.delenv("MACEFF_AGENT_NAME", raising=False)
    from macf.pd import notifier as nt
    nt.Notifier(tmp_path, {"amail": "agent"}, events=lambda: [])
    assert "no amail settings or MACEFF_AGENT_NAME" in capsys.readouterr().err
    _settings(tmp_path, handoff=str(tmp_path / "handoff"), agent="me")
    (tmp_path / "handoff" / "me").mkdir(parents=True)
    nt.Notifier(tmp_path, {"amail": "agent"}, events=lambda: [])
    err = capsys.readouterr().err
    assert f"mail is watched in {tmp_path / 'handoff' / 'me'} (from amail.json)" in err
