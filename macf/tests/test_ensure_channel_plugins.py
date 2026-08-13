"""Tests for ensure_channel_plugins in the container provisioner.

agents.yaml declares channel plugins (``claude_config.channels``) and the
harness passes them to ``--channels`` — but until this step, nothing installed
the plugin the declaration names. A fresh deployment shipped with the channel
flag pointing at software that was never on the box (observed 2026-08-13:
one container's agents had no telegram plugin, no marketplace, and no bun).
These tests pin the contract: install when absent, update when present, skip
unknown marketplaces rather than guessing a source, and never run anything
for vanilla-style empty declarations.

``docker/scripts/start.py`` is a container entrypoint, not a package module,
so it is loaded by path here.
"""

import importlib.util
import json
from pathlib import Path
from unittest.mock import patch

import pytest

START_PY = (
    Path(__file__).resolve().parents[2] / "docker" / "scripts" / "start.py"
)

USER = "pa_test"
CHANNEL = "plugin:telegram@claude-plugins-official"
PLUGIN_ID = "telegram@claude-plugins-official"


@pytest.fixture(scope="module")
def start_module():
    spec = importlib.util.spec_from_file_location("maceff_start", START_PY)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture
def home_root(start_module, tmp_path):
    """Point the provisioner at a throwaway home tree."""
    (tmp_path / USER).mkdir()
    with patch.object(start_module, "HOME_ROOT", tmp_path):
        yield tmp_path


@pytest.fixture
def calls(start_module):
    recorded = []
    with patch.object(start_module, "run_command",
                      side_effect=lambda cmd, **kw: recorded.append(cmd)):
        yield recorded


def _su_payloads(calls):
    """Extract the shell string from each su invocation."""
    return [c[-1] for c in calls if c[:2] == ["su", "-"]]


def _seed_state(home_root, marketplaces=None, installed=None):
    plugins = home_root / USER / ".claude" / "plugins"
    plugins.mkdir(parents=True)
    if marketplaces is not None:
        (plugins / "known_marketplaces.json").write_text(
            json.dumps({m: {} for m in marketplaces}))
    if installed is not None:
        (plugins / "installed_plugins.json").write_text(
            json.dumps({"version": 2, "plugins": {p: [] for p in installed}}))


def test_fresh_home_adds_marketplace_and_installs(start_module, home_root, calls):
    start_module.ensure_channel_plugins(USER, [CHANNEL])
    payloads = _su_payloads(calls)
    assert any("marketplace add anthropics/claude-plugins-official" in p
               for p in payloads)
    assert any(f"plugin install {PLUGIN_ID}" in p for p in payloads)
    # And never the update forms on a fresh home.
    assert not any("plugin update" in p or "marketplace update" in p
                   for p in payloads)


def test_present_state_updates_rather_than_reinstalls(start_module, home_root, calls):
    _seed_state(home_root, marketplaces=["claude-plugins-official"],
                installed=[PLUGIN_ID])
    start_module.ensure_channel_plugins(USER, [CHANNEL])
    payloads = _su_payloads(calls)
    assert any("marketplace update claude-plugins-official" in p
               for p in payloads)
    assert any(f"plugin update {PLUGIN_ID}" in p for p in payloads)
    assert not any("marketplace add" in p or "plugin install" in p
                   for p in payloads)


def test_unknown_marketplace_is_skipped_not_guessed(start_module, home_root, calls):
    start_module.ensure_channel_plugins(USER, ["plugin:foo@somebody-random"])
    assert _su_payloads(calls) == []


def test_empty_and_non_plugin_channels_are_noops(start_module, home_root, calls):
    start_module.ensure_channel_plugins(USER, None)
    start_module.ensure_channel_plugins(USER, [])
    start_module.ensure_channel_plugins(USER, ["not-a-plugin-string"])
    assert _su_payloads(calls) == []


def test_commands_run_as_the_user_with_a_timeout(start_module, home_root, calls):
    """Offline containers must still boot: every network-touching call is
    su'd to the agent and wrapped in timeout, and run_command is told not to
    raise."""
    with patch.object(start_module, "run_command") as rc:
        start_module.ensure_channel_plugins(USER, [CHANNEL])
    for call in rc.call_args_list:
        cmd = call.args[0]
        assert cmd[:3] == ["su", "-", USER]
        assert cmd[-1].startswith("timeout ")
        assert call.kwargs.get("check") is False
