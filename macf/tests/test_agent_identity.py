"""
Pragmatic tests for agent identity infrastructure.

Tests focus on core functionality: AgentSpec display_name field validation,
get_agent_identity() format correctness, and graceful fallback behavior.
"""

import os
import pytest
from pathlib import Path
from unittest.mock import patch, MagicMock
from pydantic import ValidationError

from macf.models.agent_spec import AgentSpec
from macf.utils.identity import (
    get_agent_identity,
    _get_gecos_name,
    _get_uuid_prefix,
    _resolve_uuid_prefix,
)


# ============================================================================
# AgentSpec.display_name Tests
# ============================================================================

def test_agent_spec_display_name_optional():
    """AgentSpec accepts optional display_name field."""
    agent = AgentSpec(
        username="pa_manny",
        personality="../agents/manny.md",
        display_name="Manny MacEff"
    )

    assert agent.display_name == "Manny MacEff"


def test_agent_spec_display_name_defaults_to_none():
    """AgentSpec display_name defaults to None when not provided."""
    agent = AgentSpec(
        username="pa_manny",
        personality="../agents/manny.md"
    )

    assert agent.display_name is None


# ============================================================================
# get_agent_identity() Tests
# ============================================================================

@patch('macf.utils.identity._get_config_identity_name', return_value=None)
@patch('macf.utils.identity._get_gecos_name')
@patch('macf.utils.identity._resolve_uuid_prefix')
def test_get_agent_identity_format(mock_uuid, mock_gecos, _mock_config):
    """get_agent_identity() returns correct format: DisplayName@uuid.

    `_get_config_identity_name` patched to None so the chain skips the
    config layer (added per cversek/MacEff#96 Phase 1) and exercises the
    GECOS path the test originally covered.
    """
    mock_gecos.return_value = "MannyMacEff"
    mock_uuid.return_value = ("a3f7c2", "global")

    with patch.dict(os.environ, {}, clear=False) as env:
        env.pop("MACEFF_AGENT_NAME", None)
        identity = get_agent_identity()

    assert identity == "MannyMacEff@a3f7c2"


@patch('macf.utils.identity._get_config_identity_name', return_value=None)
@patch('macf.utils.identity._get_gecos_name')
@patch('macf.utils.identity._resolve_uuid_prefix')
@patch.dict(os.environ, {'USER': 'pa_manny'})
def test_get_agent_identity_fallback_missing_gecos(mock_uuid, mock_gecos, _mock_config):
    """get_agent_identity() uses username when GECOS unavailable.

    Config layer patched to None so the original GECOS→username fallback
    is exercised exactly as before.
    """
    mock_gecos.return_value = None
    mock_uuid.return_value = ("a3f7c2", "global")

    with patch.dict(os.environ, {}, clear=False) as env:
        env.pop("MACEFF_AGENT_NAME", None)
        identity = get_agent_identity()

    assert identity == "pa_manny@a3f7c2"


@patch('macf.utils.identity._get_config_identity_name', return_value=None)
@patch('macf.utils.identity._get_gecos_name')
@patch('macf.utils.identity._resolve_uuid_prefix')
@patch.dict(os.environ, {'USER': 'pa_manny'})
def test_get_agent_identity_fallback_missing_uuid(mock_uuid, mock_gecos, _mock_config):
    """get_agent_identity() uses 'unknown' when UUID file missing.

    Config layer patched to None so the GECOS path is exercised as
    originally written.
    """
    mock_gecos.return_value = "MannyMacEff"
    mock_uuid.return_value = ("unknown", "global")

    with patch.dict(os.environ, {}, clear=False) as env:
        env.pop("MACEFF_AGENT_NAME", None)
        identity = get_agent_identity()

    assert identity == "MannyMacEff@unknown"


# ============================================================================
# _get_uuid_prefix() Tests
# ============================================================================

def test_get_uuid_prefix_returns_first_six_chars(tmp_path):
    """_get_uuid_prefix() returns first 6 characters from UUID file.

    find_agent_home is patched alongside Path.home: it is lru_cached and
    would otherwise return the real agent home, whose actual identity file
    leaks into the test (the pre-existing failure mode on developer hosts).
    """
    uuid_file = tmp_path / ".maceff_primary_agent.id"
    uuid_file.write_text("a3f7c2b8d1e4")

    with patch('macf.utils.paths.find_agent_home', return_value=tmp_path), \
         patch('macf.utils.identity.Path.home', return_value=tmp_path):
        uuid_prefix = _get_uuid_prefix()

    assert uuid_prefix == "a3f7c2"


def test_get_uuid_prefix_fallback_file_missing():
    """_get_uuid_prefix() returns 'unknown' when file doesn't exist."""
    with patch('macf.utils.paths.find_agent_home', return_value=Path("/nonexistent")), \
         patch('macf.utils.identity.Path.home', return_value=Path("/nonexistent")):
        uuid_prefix = _get_uuid_prefix()

    assert uuid_prefix == "unknown"


def test_get_uuid_prefix_fallback_empty_file(tmp_path):
    """_get_uuid_prefix() returns 'unknown' when file is empty."""
    uuid_file = tmp_path / ".maceff_primary_agent.id"
    uuid_file.write_text("")

    with patch('macf.utils.paths.find_agent_home', return_value=tmp_path), \
         patch('macf.utils.identity.Path.home', return_value=tmp_path):
        uuid_prefix = _get_uuid_prefix()

    assert uuid_prefix == "unknown"


def test_resolve_uuid_prefix_per_project_scope(tmp_path):
    """_resolve_uuid_prefix() reports 'project' scope for a non-~ agent home."""
    project = tmp_path / "agent_home"
    project.mkdir()
    (project / ".maceff_primary_agent.id").write_text("abc123deadbeef")
    home = tmp_path / "home"
    home.mkdir()

    with patch('macf.utils.paths.find_agent_home', return_value=project), \
         patch('macf.utils.identity.Path.home', return_value=home):
        assert _resolve_uuid_prefix() == ("abc123", "project")


# ============================================================================
# Scope Coherence Tests (global name must not rename a per-project agent)
# ============================================================================

def _project_scope_patches(tmp_path):
    """Build a per-project agent home + distinct user home for scope tests."""
    project = tmp_path / "agent_home"
    project.mkdir()
    (project / ".maceff_primary_agent.id").write_text("abc123deadbeef")
    home = tmp_path / "home"
    home.mkdir()
    return project, home


@patch.dict(os.environ, {'MACEFF_AGENT_NAME': 'GlobalName', 'USER': 'someuser'})
def test_project_scope_config_outranks_global_env(tmp_path):
    """Per-project config calling_card wins over host-global MACEFF_AGENT_NAME."""
    project, home = _project_scope_patches(tmp_path)

    with patch('macf.utils.paths.find_agent_home', return_value=project), \
         patch('macf.utils.identity.Path.home', return_value=home), \
         patch('macf.utils.identity._get_config_identity_name', return_value="ProjectAgent"), \
         patch('macf.utils.identity._get_gecos_name', return_value="HostOwner"):
        assert get_agent_identity() == "ProjectAgent@abc123"


@patch.dict(os.environ, {'MACEFF_AGENT_NAME': 'GlobalName', 'USER': 'someuser'})
def test_project_scope_gecos_outranks_global_env(tmp_path):
    """Without per-project config, GECOS still outranks the global env var."""
    project, home = _project_scope_patches(tmp_path)

    with patch('macf.utils.paths.find_agent_home', return_value=project), \
         patch('macf.utils.identity.Path.home', return_value=home), \
         patch('macf.utils.identity._get_config_identity_name', return_value=None), \
         patch('macf.utils.identity._get_gecos_name', return_value="HostOwner"):
        assert get_agent_identity() == "HostOwner@abc123"


@patch.dict(os.environ, {'MACEFF_AGENT_NAME': 'GlobalName', 'USER': 'someuser'})
def test_project_scope_env_last_resort_warns(tmp_path, capsys):
    """Env var as the only name source in project scope is used but warned about."""
    project, home = _project_scope_patches(tmp_path)

    with patch('macf.utils.paths.find_agent_home', return_value=project), \
         patch('macf.utils.identity.Path.home', return_value=home), \
         patch('macf.utils.identity._get_config_identity_name', return_value=None), \
         patch('macf.utils.identity._get_gecos_name', return_value=None):
        identity = get_agent_identity()

    assert identity == "GlobalName@abc123"
    assert "identity scope mismatch" in capsys.readouterr().err


@patch.dict(os.environ, {'MACEFF_AGENT_NAME': 'GlobalName', 'USER': 'someuser'})
def test_global_scope_env_still_wins(tmp_path, capsys):
    """In global scope the env var keeps its documented top priority, no warning."""
    (tmp_path / ".maceff_primary_agent.id").write_text("fedcba9876")

    with patch('macf.utils.paths.find_agent_home', return_value=tmp_path), \
         patch('macf.utils.identity.Path.home', return_value=tmp_path), \
         patch('macf.utils.identity._get_config_identity_name', return_value="ProjectAgent"), \
         patch('macf.utils.identity._get_gecos_name', return_value="HostOwner"):
        identity = get_agent_identity()

    assert identity == "GlobalName@fedcba"
    assert "identity scope mismatch" not in capsys.readouterr().err
