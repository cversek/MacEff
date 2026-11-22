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
