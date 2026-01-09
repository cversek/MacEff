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
from macf.utils.identity import get_agent_identity, _get_gecos_name, _get_uuid_prefix


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

@patch('macf.utils.identity._get_gecos_name')
@patch('macf.utils.identity._get_uuid_prefix')
def test_get_agent_identity_format(mock_uuid, mock_gecos):
    """get_agent_identity() returns correct format: DisplayName@uuid."""
    mock_gecos.return_value = "MannyMacEff"
    mock_uuid.return_value = "a3f7c2"

    identity = get_agent_identity()

    assert identity == "MannyMacEff@a3f7c2"


@patch('macf.utils.identity._get_gecos_name')
@patch('macf.utils.identity._get_uuid_prefix')
@patch.dict(os.environ, {'USER': 'pa_manny'})
def test_get_agent_identity_fallback_missing_gecos(mock_uuid, mock_gecos):
    """get_agent_identity() uses username when GECOS unavailable."""
    mock_gecos.return_value = None
    mock_uuid.return_value = "a3f7c2"

    identity = get_agent_identity()

    assert identity == "pa_manny@a3f7c2"


@patch('macf.utils.identity._get_gecos_name')
@patch('macf.utils.identity._get_uuid_prefix')
@patch.dict(os.environ, {'USER': 'pa_manny'})
def test_get_agent_identity_fallback_missing_uuid(mock_uuid, mock_gecos):
    """get_agent_identity() uses 'unknown' when UUID file missing."""
    mock_gecos.return_value = "MannyMacEff"
    mock_uuid.return_value = "unknown"

    identity = get_agent_identity()

    assert identity == "MannyMacEff@unknown"


# ============================================================================
# _get_uuid_prefix() Tests
# ============================================================================

def test_get_uuid_prefix_returns_first_six_chars(tmp_path):
    """_get_uuid_prefix() returns first 6 characters from UUID file."""
    # Create temporary UUID file
    uuid_file = tmp_path / ".maceff_primary_agent.id"
    uuid_file.write_text("a3f7c2b8d1e4")

    with patch('macf.utils.identity.Path.home', return_value=tmp_path):
        uuid_prefix = _get_uuid_prefix()

    assert uuid_prefix == "a3f7c2"


def test_get_uuid_prefix_fallback_file_missing():
    """_get_uuid_prefix() returns 'unknown' when file doesn't exist."""
    with patch('macf.utils.identity.Path.home') as mock_home:
        mock_home.return_value = Path("/nonexistent")
        uuid_prefix = _get_uuid_prefix()

    assert uuid_prefix == "unknown"


def test_get_uuid_prefix_fallback_empty_file(tmp_path):
    """_get_uuid_prefix() returns 'unknown' when file is empty."""
    uuid_file = tmp_path / ".maceff_primary_agent.id"
    uuid_file.write_text("")

    with patch('macf.utils.identity.Path.home', return_value=tmp_path):
        uuid_prefix = _get_uuid_prefix()

    assert uuid_prefix == "unknown"
