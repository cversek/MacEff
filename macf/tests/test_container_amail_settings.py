"""Container start names each agent's pickup box in its own amail.json.

The outer tier starts a primal daemon with identity variables only, so a seat's daemon
can't learn its mail name from MACEFF_AGENT_NAME the way its session does. Without
`handoff` and `agent` in the agent's amail.json it watches a guessed path and sees no mail.
"""
import importlib.util
import json
import stat
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import pytest

START_PY = Path(__file__).resolve().parents[2] / "docker" / "scripts" / "start.py"


@pytest.fixture(scope="module")
def start_module():
    spec = importlib.util.spec_from_file_location("maceff_start_amail_settings", START_PY)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture
def chowns(start_module):
    """os.chown needs root; record it instead."""
    recorded = []
    with patch.object(start_module.os, "chown", side_effect=lambda p, u, g: recorded.append((Path(p).name, u, g))):
        yield recorded


def _read(home):
    return json.loads((home / ".maceff" / "amail.json").read_text())


def test_a_new_file_names_the_box_and_is_the_agents_own(start_module, chowns, tmp_path):
    start_module.write_amail_settings(tmp_path, Path("/var/lib/amail/handoff"), "manny2", 1002, 1002)
    assert _read(tmp_path) == {"handoff": "/var/lib/amail/handoff", "agent": "manny2"}
    assert chowns == [("amail.json.tmp", 1002, 1002)]
    assert stat.S_IMODE((tmp_path / ".maceff" / "amail.json").stat().st_mode) == 0o600


def test_other_keys_are_kept_and_the_two_names_corrected(start_module, chowns, tmp_path):
    (tmp_path / ".maceff").mkdir()
    (tmp_path / ".maceff" / "amail.json").write_text(json.dumps(
        {"domain": "manny.local", "agent": "old", "socket": "/run/amail/broker.sock"}))
    start_module.write_amail_settings(tmp_path, Path("/h"), "manny2", 1, 1)
    assert _read(tmp_path) == {"domain": "manny.local", "agent": "manny2",
                               "socket": "/run/amail/broker.sock", "handoff": "/h"}


def test_nothing_is_rewritten_when_it_already_says_so(start_module, chowns, tmp_path):
    start_module.write_amail_settings(tmp_path, Path("/h"), "a", 1, 1)
    chowns.clear()
    start_module.write_amail_settings(tmp_path, Path("/h"), "a", 1, 1)
    assert chowns == []


def test_a_file_that_is_not_an_object_is_left_alone(start_module, chowns, tmp_path):
    (tmp_path / ".maceff").mkdir()
    (tmp_path / ".maceff" / "amail.json").write_text("[]")
    start_module.write_amail_settings(tmp_path, Path("/h"), "a", 1, 1)
    assert (tmp_path / ".maceff" / "amail.json").read_text() == "[]"


def test_provisioning_writes_it_for_each_addressed_agent(start_module, chowns, tmp_path):
    homes = {"pa_manny2": tmp_path / "pa_manny2", "pa_manny3": tmp_path / "pa_manny3"}
    for h in homes.values():
        h.mkdir()
    addressing = tmp_path / "addressing.yaml"
    addressing.write_text("agents:\n  manny2: {account: pa_manny2}\n  manny3: {account: pa_manny3}\n")
    broker = tmp_path / "broker.yaml"
    broker.write_text(f"addressing_path: {addressing}\n")
    handoff = tmp_path / "handoff"

    def getpwnam(name):
        if name == "amail_broker":
            return SimpleNamespace(pw_uid=999, pw_gid=999, pw_dir="/nonexistent")
        return SimpleNamespace(pw_uid=1000, pw_gid=1000, pw_dir=str(homes[name]))

    with patch.object(start_module.pwd, "getpwnam", side_effect=getpwnam):
        start_module.provision_pickup_boxes(broker, handoff)
    assert _read(homes["pa_manny2"]) == {"handoff": str(handoff), "agent": "manny2"}
    assert _read(homes["pa_manny3"]) == {"handoff": str(handoff), "agent": "manny3"}
