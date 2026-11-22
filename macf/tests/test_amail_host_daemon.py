"""The broker on a host as a declared unit of its own primal daemon (MIS-0002 R53, MIS-0007 R81).

Each test writes the operator's broker config to disk and reads what the plan writes back through
the readers the primal daemon itself uses: ``pd.names.agent_card`` for the identity and
``pd.core.load_declaration`` for the declaration.
"""
import json
import os
import pwd
import sys

import pytest
import yaml

from macf.amail import host_daemon
from macf.pd.core import load_declaration
from macf.pd.names import agent_card


def _broker_config(tmp_path, domain="alpha.test"):
    root = tmp_path / "amail-host"
    root.mkdir()
    addressing = root / "addressing.yaml"
    addressing.write_text(yaml.safe_dump({"domain": domain, "tier": "host", "supervision": "operator-at-terminal",
                                          "agents": {"ira": {"uid": os.getuid(), "home": str(tmp_path / "ira"),
                                                             "shared_uid": True, "card": "Ira_0a1b2c",
                                                             "contacts": []}}}))
    path = root / "broker_config.yaml"
    path.write_text(yaml.safe_dump({"addressing_path": str(addressing)}))
    return path


def _plan(cfg, **kw):
    return host_daemon.plan(cfg, python=sys.executable, account=pwd.getpwuid(os.getuid()).pw_name, path_dirs=["/usr/bin", "/bin"], **kw)


def test_the_broker_daemon_reads_as_its_own_agent_with_one_unit_that_runs_the_broker(tmp_path):
    """Written, the home names the broker daemon's card to the daemon's own identity reader, and its
    declaration loads in the daemon's own loader with one unit, the broker, run on the operator's
    config. No session, no channel: a service daemon, as a container's broker account has."""
    cfg = _broker_config(tmp_path)
    p = _plan(cfg)
    p.write()
    card = agent_card(p.home)
    assert card == host_daemon.card_for("alpha.test") == p.card and card.startswith("AmailBroker_")
    declared = load_declaration(p.home, card)
    (unit,) = declared.units
    assert unit.name == "broker" and unit.command[-1] == "macf.amail.daemons.broker"
    assert unit.environment["AMAIL_BROKER_CONFIG"] == str(cfg.resolve())
    assert not declared.operator_channels and not declared.notice_routes
    assert host_daemon.card_for("beta.test") != card, "each domain on a host has its own broker daemon"


def test_a_second_run_changes_nothing(tmp_path):
    cfg = _broker_config(tmp_path)
    _plan(cfg).write()
    again = _plan(cfg)
    assert not again.files and len(again.unchanged) == 3


def test_a_home_that_belongs_to_another_agent_is_refused(tmp_path):
    """The card is the daemon's identity, and its sockets and launchd label are keyed by it, so a home
    already naming another agent is never taken over."""
    cfg = _broker_config(tmp_path)
    home = tmp_path / "ira"
    (home / ".maceff").mkdir(parents=True)
    (home / ".maceff" / "config.json").write_text(json.dumps({"agent_identity": {"calling_card": "Ira"}}))
    (home / ".maceff_primary_agent.id").write_text("0a1b2c3d-0000-0000-0000-000000000000\n")
    with pytest.raises(host_daemon.HostDaemonError, match="home of Ira_0a1b2c"):
        _plan(cfg, home=home)
    assert json.loads((home / ".maceff" / "config.json").read_text())["agent_identity"]["calling_card"] == "Ira"


def test_the_operators_steps_retire_the_interim_job_before_installing_the_daemon(tmp_path):
    """One broker per system (MIS-0004 R01): the interim job that ran the broker directly is retired
    first, then the daemon is installed. Both are the operator's steps, printed and never run."""
    cfg = _broker_config(tmp_path)
    agents = tmp_path / "LaunchAgents"
    agents.mkdir()
    (agents / "maceff_amail_broker.alpha.plist").write_text("<plist/>")
    p = _plan(cfg, interim_plists=host_daemon.interim_jobs(agents))
    assert len(p.steps) == 2
    assert "launchctl bootout" in p.steps[0] and "maceff_amail_broker.alpha" in p.steps[0]
    assert p.steps[1] == f"MACEFF_AGENT_HOME_DIR={cfg.parent.resolve()} macf_tools pd install"


# ---- the agent init mail step ----------------------------------------------------------------------------

def _mail_home(tmp_path, monkeypatch, *, card_json=None):
    """An agent home with a mail address whose broker config is on disk, and an init context for it."""
    from macf import agent_stack
    from macf.cli import _build_parser
    cfg = _broker_config(tmp_path)
    home = tmp_path / "ira"
    (home / ".maceff").mkdir(parents=True)
    (home / ".maceff" / "amail.json").write_text(json.dumps(
        {"agent": "ira", "domain": "alpha.test", "broker_config": str(cfg)}))
    os.chmod(home / ".maceff" / "amail.json", 0o600)
    monkeypatch.delenv("MACF_AMAIL_SIGNING_KEY", raising=False)
    monkeypatch.setattr(agent_stack, "pd_unit_installed", lambda card, home: False)
    flags = ["agent", "init", "-y"] + (["--peer", card_json] if card_json else [])

    def ctx(plan=False):
        return agent_stack.Context(home=home, login_home=tmp_path / "login", in_container=False,
                                   args=_build_parser().parse_args(flags + (["--plan"] if plan else [])),
                                   dry_run=plan)
    from types import SimpleNamespace
    return SimpleNamespace(home=home, cfg=cfg, ctx=ctx)


def test_the_mail_step_makes_the_key_declares_signing_and_writes_the_brokers_daemon(tmp_path, monkeypatch):
    """One step: the key made, signing every message declared (the file's mode kept), the broker
    daemon's files written, and the operator's install printed, since the daemon isn't installed yet."""
    from macf import agent_stack
    m = _mail_home(tmp_path, monkeypatch)
    home, cfg, ctx = m.home, m.cfg, m.ctx
    r = agent_stack.step_mail(ctx())
    assert r.status == agent_stack.PLANNED, r
    assert agent_stack.signing_key_path(home).exists()
    conf = home / ".maceff" / "amail.json"
    assert json.loads(conf.read_text())["signing_required"] is True and (conf.stat().st_mode & 0o777) == 0o600
    assert agent_card(cfg.parent.resolve()) == host_daemon.card_for("alpha.test")
    assert f"MACEFF_AGENT_HOME_DIR={cfg.parent.resolve()} macf_tools pd install" in r.detail


def test_the_mail_step_under_plan_changes_nothing_and_once_installed_reads_already_done(tmp_path, monkeypatch):
    from macf import agent_stack
    m = _mail_home(tmp_path, monkeypatch)
    home, cfg, ctx = m.home, m.cfg, m.ctx
    conf = home / ".maceff" / "amail.json"
    before = sorted(p.name for p in tmp_path.rglob("*")), conf.read_text()
    assert agent_stack.step_mail(ctx(plan=True)).status == agent_stack.WOULD
    assert (sorted(p.name for p in tmp_path.rglob("*")), conf.read_text()) == before
    agent_stack.step_mail(ctx())
    monkeypatch.setattr(agent_stack, "pd_unit_installed", lambda card, home: True)
    assert agent_stack.step_mail(ctx()).status == agent_stack.ALREADY


def test_the_mail_step_declares_a_peer_from_its_card_and_prints_its_registry_line(tmp_path, monkeypatch):
    from macf import agent_stack
    from macf.amail.crypto import generate_keypair
    key = generate_keypair(tmp_path / "keys" / "sparrow")
    card = json.dumps({"amail_peer_card": 1, "domain": "beta.test", "host": "100.64.0.9", "port": 8030,
                       "agents": {"sparrow": {"card": "Sparrow_6a7b8c", "key": key, "account": "sparrow"}}})
    m = _mail_home(tmp_path, monkeypatch, card_json=card)
    home, cfg, ctx = m.home, m.cfg, m.ctx
    r = agent_stack.step_mail(ctx())
    assert yaml.safe_load(cfg.read_text())["peer_links"]["beta.test"]["agents"] == {"sparrow": "Sparrow_6a7b8c"}
    assert f"registry declare --card Sparrow_6a7b8c --key {key}" in r.detail


def test_an_agent_with_no_address_is_skipped_by_the_mail_step(tmp_path, monkeypatch):
    from macf import agent_stack
    m = _mail_home(tmp_path, monkeypatch)
    home, cfg, ctx = m.home, m.cfg, m.ctx
    (home / ".maceff" / "amail.json").unlink()
    r = agent_stack.step_mail(ctx())
    assert r.status == agent_stack.SKIPPED and not agent_stack.signing_key_path(home).exists()


def test_a_broker_already_a_unit_of_an_agents_own_daemon_gets_no_second_daemon(tmp_path):
    """THM's review of #1102: a host set up by hand may run the broker as a unit of an agent's own primal
    daemon. A second daemon for it would contend for its socket and listener, so the plan refuses,
    naming the daemon that already runs it, and writes nothing."""
    cfg = _broker_config(tmp_path)
    home = tmp_path / "ira"
    (home / ".maceff" / "pd").mkdir(parents=True)
    (home / ".maceff" / "config.json").write_text(json.dumps({"agent_identity": {"calling_card": "Ira"}}))
    (home / ".maceff_primary_agent.id").write_text("0a1b2c3d-0000-0000-0000-000000000000\n")
    (home / ".maceff" / "pd" / "declaration.json").write_text(json.dumps({"version": 1, "agent": "Ira_0a1b2c", "units": [
        {"name": "amail-broker", "command": [sys.executable, "-m", "macf.amail.daemons.broker"],
         "environment": {"AMAIL_BROKER_CONFIG": str(cfg)}}]}))
    with pytest.raises(host_daemon.HostDaemonError, match="already unit 'amail-broker' of Ira_0a1b2c"):
        _plan(cfg)
    assert not (cfg.parent / ".maceff").exists()
    found = host_daemon.declared_broker(cfg, [home])
    assert (found.card, found.unit) == ("Ira_0a1b2c", "amail-broker")


def test_the_mail_step_leaves_a_broker_already_declared_in_an_agents_daemon_alone(tmp_path, monkeypatch):
    from macf import agent_stack
    m = _mail_home(tmp_path, monkeypatch)
    home, cfg, ctx = m.home, m.cfg, m.ctx
    (home / ".maceff" / "pd").mkdir(parents=True)
    (home / ".maceff" / "pd" / "declaration.json").write_text(json.dumps({"version": 1, "agent": "Ira_0a1b2c", "units": [
        {"name": "amail-broker", "command": [sys.executable, "-m", "macf.amail.daemons.broker"],
         "environment": {"AMAIL_BROKER_CONFIG": str(cfg)}}]}))
    r = agent_stack.step_mail(ctx())
    assert r.status == agent_stack.DONE and "already unit 'amail-broker'" in r.detail, r
    assert not (cfg.parent / ".maceff").exists() and "pd install" not in r.detail
