"""
Pragmatic tests for agent_spec.py Pydantic models.

Tests focus on core validation: valid YAML parsing, required field enforcement,
type validation, and graceful error handling. Does NOT test every permutation.
"""

import pytest
from pydantic import ValidationError

from macf.models.agent_spec import (
    AgentSpec,
    SubagentSpec,
    ConsciousnessArtifactsConfig,
    DefaultsConfig,
    AgentsConfig,
)


def test_agent_spec_valid_minimal():
    """Valid AgentSpec with only required fields."""
    agent = AgentSpec(
        username="pa_manny",
        personality="../custom/agents/manny_personality.md"
    )

    assert agent.username == "pa_manny"
    assert agent.personality == "../custom/agents/manny_personality.md"
    assert agent.subagents == []  # Default empty list
    assert agent.assigned_projects == []  # Default empty list
    assert agent.consciousness_artifacts is None
    assert agent.hooks is None


def test_agent_spec_valid_full():
    """Valid AgentSpec with all optional fields."""
    agent = AgentSpec(
        username="pa_builder",
        personality="../custom/agents/builder.md",
        subagents=["devops_eng", "test_eng"],
        assigned_projects=["MacEff", "TestProject"],
        consciousness_artifacts=ConsciousnessArtifactsConfig(
            private=["checkpoints", "reflections"],
            public=["roadmaps", "reports"]
        ),
        hooks={"enabled": ["session_start", "stop"]}
    )

    assert len(agent.subagents) == 2
    assert "devops_eng" in agent.subagents
    assert agent.consciousness_artifacts.private == ["checkpoints", "reflections"]


def test_agent_spec_missing_required_field():
    """AgentSpec fails when required field missing."""
    with pytest.raises(ValidationError) as exc_info:
        AgentSpec(username="pa_manny")  # Missing personality

    error = exc_info.value
    assert "personality" in str(error)


def test_subagent_spec_valid():
    """Valid SubagentSpec with required fields."""
    subagent = SubagentSpec(
        role="Infrastructure and deployment specialist",
        tool_access="Read, Write, Edit, Bash, Glob, Grep"
    )

    assert subagent.role == "Infrastructure and deployment specialist"
    assert subagent.tool_access == "Read, Write, Edit, Bash, Glob, Grep"
    assert subagent.shell == "/usr/sbin/nologin"  # Default value


def test_subagent_spec_tool_access_must_be_string():
    """SubagentSpec rejects tool_access as list (must be comma-separated string)."""
    with pytest.raises(ValidationError) as exc_info:
        SubagentSpec(
            role="Test specialist",
            tool_access=["Read", "Write", "Edit"]  # Wrong: list instead of string
        )

    error = exc_info.value
    assert "tool_access" in str(error)


def test_consciousness_artifacts_config_defaults():
    """ConsciousnessArtifactsConfig allows None for both fields."""
    config = ConsciousnessArtifactsConfig()

    assert config.private is None
    assert config.public is None


def test_agents_config_valid():
    """Valid AgentsConfig with agents and subagents."""
    config = AgentsConfig(
        agents={
            "manny": AgentSpec(
                username="pa_manny",
                personality="../custom/agents/manny.md",
                subagents=["devops_eng"],
                assigned_projects=["NeuroVEP"]
            )
        },
        subagents={
            "devops_eng": SubagentSpec(
                role="Infrastructure specialist",
                tool_access="Read, Write, Bash"
            )
        }
    )

    assert "manny" in config.agents
    assert "devops_eng" in config.subagents
    assert config.defaults is None


def test_agents_config_with_defaults():
    """AgentsConfig supports optional defaults section."""
    config = AgentsConfig(
        agents={
            "manny": AgentSpec(username="pa_manny", personality="../agents/manny.md")
        },
        subagents={
            "devops_eng": SubagentSpec(role="DevOps", tool_access="Read, Bash")
        },
        defaults=DefaultsConfig(
            consciousness_artifacts=ConsciousnessArtifactsConfig(
                private=["checkpoints", "reflections"],
                public=["roadmaps", "reports"]
            )
        )
    )

    assert config.defaults is not None
    assert config.defaults.consciousness_artifacts.private == ["checkpoints", "reflections"]


def test_agents_config_missing_required_sections():
    """AgentsConfig fails when required sections missing."""
    # Missing agents section
    with pytest.raises(ValidationError) as exc_info:
        AgentsConfig(
            subagents={
                "devops_eng": SubagentSpec(role="DevOps", tool_access="Read")
            }
        )
    assert "agents" in str(exc_info.value)

    # Missing subagents section
    with pytest.raises(ValidationError) as exc_info:
        AgentsConfig(
            agents={
                "manny": AgentSpec(username="pa_manny", personality="../agents/manny.md")
            }
        )
    assert "subagents" in str(exc_info.value)
