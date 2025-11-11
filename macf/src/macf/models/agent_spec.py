"""
Pydantic models for agents.yaml configuration validation.

Models correspond to the YAML structure documented in:
docs/arch_v0.3_named_agents/05_implementation_guide.md (lines 48-125)
"""

from typing import List, Optional, Dict, Any
from pydantic import BaseModel, Field, field_validator


class ConsciousnessArtifactsConfig(BaseModel):
    """Configuration for consciousness artifacts directories."""

    private: Optional[List[str]] = Field(
        default=None,
        description="Private artifact types (checkpoints, reflections, learnings)"
    )
    public: Optional[List[str]] = Field(
        default=None,
        description="Public artifact types (roadmaps, reports, observations, experiments, delegation_trails)"
    )
    immutable_structure: bool = Field(
        default=True,
        description="Prevent creation of new CA types via read-only parent directories (555 permissions)"
    )


class AgentSpec(BaseModel):
    """Specification for a Primary Agent (PA)."""

    username: str = Field(
        ...,
        description="Linux username for the agent (e.g., pa_manny)"
    )

    personality: str = Field(
        ...,
        description="Path to personality file (Identity layer CLAUDE.md source)"
    )

    subagents: Optional[List[str]] = Field(
        default_factory=list,
        description="List of assigned subagent names"
    )

    assigned_projects: Optional[List[str]] = Field(
        default_factory=list,
        description="List of assigned project names"
    )

    consciousness_artifacts: Optional[ConsciousnessArtifactsConfig] = Field(
        default=None,
        description="Consciousness artifact configuration"
    )

    hooks: Optional[Dict[str, Any]] = Field(
        default=None,
        description="Hook configuration (enabled list, etc.)"
    )


class SubagentSpec(BaseModel):
    """Specification for a Subagent (SA)."""

    role: str = Field(
        ...,
        description="Description of subagent's role and specialization"
    )

    shell: str = Field(
        default="/usr/sbin/nologin",
        description="Shell for subagent (usually /usr/sbin/nologin)"
    )

    tool_access: str = Field(
        ...,
        description="Comma-separated list of allowed tools (e.g., 'Read, Write, Edit, Bash')"
    )

    consciousness_artifacts: Optional[ConsciousnessArtifactsConfig] = Field(
        default=None,
        description="Consciousness artifact configuration for subagent"
    )

    @field_validator('tool_access')
    @classmethod
    def validate_tool_access(cls, v: str) -> str:
        """Ensure tool_access is a string (not a list)."""
        if not isinstance(v, str):
            raise ValueError("tool_access must be a comma-separated string")
        return v


class DefaultsConfig(BaseModel):
    """Global defaults for agents."""

    consciousness_artifacts: Optional[ConsciousnessArtifactsConfig] = Field(
        default=None,
        description="Default consciousness artifact configuration"
    )

    hooks: Optional[Dict[str, Any]] = Field(
        default=None,
        description="Default hook configuration"
    )


class AgentsConfig(BaseModel):
    """
    Root configuration model for agents.yaml.

    Example:
        agents:
          manny:
            username: pa_manny
            personality: ../custom/agents/manny_personality.md
            subagents: [devops_eng, test_eng]
            assigned_projects: [NeuroVEP]

        subagents:
          devops_eng:
            role: Infrastructure and deployment specialist
            tool_access: Read, Write, Edit, Bash, Glob, Grep

        defaults:
          consciousness_artifacts:
            private: [checkpoints, reflections, learnings]
            public: [roadmaps, reports, observations]
    """

    agents: Dict[str, AgentSpec] = Field(
        ...,
        description="Dictionary of agent name to AgentSpec"
    )

    subagents: Dict[str, SubagentSpec] = Field(
        ...,
        description="Dictionary of subagent name to SubagentSpec"
    )

    defaults: Optional[DefaultsConfig] = Field(
        default=None,
        description="Global defaults for agent configuration"
    )
