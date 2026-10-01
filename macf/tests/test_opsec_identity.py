"""The opsec gate's identity patterns: the display moniker, and the full UUID.

The identity file holds only the agent's UUID, and the display name the agent
signs with is resolved the way the calling card is. These tests build a home
the way a real one looks, rather than writing the name into the identity file,
which is how an earlier test passed while the gate never saw a display name.
"""

import json
import re

import pytest

from macf import opsec
from macf.utils.paths import find_agent_home

UUID = "0f1e2d3c-4b5a-4978-8a9b-0c1d2e3f4a5b"


@pytest.fixture
def agent_home(tmp_path, monkeypatch):
    home = tmp_path / "agent_home"
    (home / ".maceff").mkdir(parents=True)
    (home / ".maceff_primary_agent.id").write_text(UUID + "\n")
    (home / ".maceff" / "config.json").write_text(
        json.dumps({"agent_identity": {"calling_card": "Decoyagent"}}))
    monkeypatch.delenv("MACEFF_AGENT_NAME", raising=False)
    monkeypatch.setenv("MACEFF_AGENT_HOME_DIR", str(home))
    find_agent_home.cache_clear()
    yield home
    find_agent_home.cache_clear()


def _labels_matching(text):
    return {label for pattern, label in opsec.environment_patterns() if re.search(pattern, text)}


def test_the_moniker_is_the_display_name_not_the_uuid(agent_home):
    assert opsec._moniker_from(agent_home) == "Decoyagent"


def test_a_home_without_an_identity_file_has_no_moniker(tmp_path):
    assert opsec._moniker_from(tmp_path) is None


def test_the_display_name_in_prose_is_caught(agent_home):
    assert "agent moniker" in _labels_matching("reviewed and signed by Decoyagent")


def test_the_full_uuid_is_caught_as_a_uuid(agent_home):
    assert "agent uuid" in _labels_matching(f"the session for {UUID} restarted")
