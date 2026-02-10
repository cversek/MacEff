"""
Pydantic models for agents.yaml configuration validation.

Models correspond to the YAML structure documented in:
docs/arch_v0.3_named_agents/05_implementation_guide.md (lines 48-125)
"""

from typing import List, Optional, Dict, Any
from pydantic import BaseModel, Field, field_validator


class ClaudeCodePreferencesConfig(BaseModel):
    """Claude Code UI preferences for container agents.

    These settings go in ~/.claude.json (person layer).
    Controls how the agent experiences their environment.
    """

    verbose: bool = Field(
        default=True,
        description="Enable verbose output for debugging"
    )
    autoCompactEnabled: bool = Field(
        default=False,
        description="Enable auto-compaction (False for MANUAL_MODE agents)"
    )


class ClaudeCodePermissionsConfig(BaseModel):
    """Claude Code permission rules for container agents.

    These settings control tool authorization in ~/.claude/settings.json.
    Allows declarative configuration of allow/ask/deny rules via agents.yaml.
    """

    allow: Optional[List[str]] = Field(
        default=None,
        description="Tools that run without confirmation (e.g., ['Read', 'Glob'])"
    )
    ask: Optional[List[str]] = Field(
        default=None,
        description="Tools that prompt for confirmation (e.g., ['TodoWrite', 'Bash'])"
    )
    deny: Optional[List[str]] = Field(
        default=None,
        description="Tools that are blocked entirely"
    )
    defaultMode: Optional[str] = Field(
        default=None,
        description="Default permission mode for unlisted tools ('allow', 'ask', 'deny')"
    )


class ClaudeCodeSettingsConfig(BaseModel):
    """Claude Code project/capability settings for container agents.

    These settings go in ~/.claude/settings.json (project layer).
    Controls what capabilities are authorized.
    """

    cleanupPeriodDays: int = Field(
        default=99999,
        description="Days before Claude Code cleans up old sessions (99999 = effectively never)"
    )
    thinking: Optional[str] = Field(
        default=None,
        description="Thinking mode: 'enabled' for extended thinking, None for default"
    )
    outputStyle: Optional[str] = Field(
        default=None,
        description="Output style name (e.g., 'maceff-compliance'). Must match file in output-styles/"
    )
    env: Dict[str, str] = Field(
        default_factory=lambda: {
            "CLAUDE_BASH_MAINTAIN_PROJECT_WORKING_DIR": "1"
        },
        description="Environment variables for Claude Code"
    )
    permissions: Optional[ClaudeCodePermissionsConfig] = Field(
        default=None,
        description="Permission rules for tool authorization (allow/ask/deny)"
    )


class ClaudeCodeConfig(BaseModel):
    """Combined Claude Code configuration for container agents.

    Separates settings by concern into two sub-configs:
    - settings: Project/capability settings (-> ~/.claude/settings.json)
    - preferences: Person/UI settings (-> ~/.claude.json)

    Per-agent values override deployment-level defaults.
    """

    settings: Optional[ClaudeCodeSettingsConfig] = Field(
        default=None,
        description="Project/capability settings for ~/.claude/settings.json"
    )
    preferences: Optional[ClaudeCodePreferencesConfig] = Field(
        default=None,
        description="Person/UI preferences for ~/.claude.json"
    )


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

    display_name: Optional[str] = Field(
        default=None,
        description="Human-readable display name for GECOS field and statusline (e.g., 'Manny MacEff')"
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

    claude_config: Optional[ClaudeCodeConfig] = Field(
        default=None,
        description="Claude Code settings override for this agent"
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

    claude_config: Optional[ClaudeCodeConfig] = Field(
        default=None,
        description="Default Claude Code settings for all agents"
    )


class AgentsConfig(BaseModel):
    """
    Root configuration model for agents.yaml.

    Example:
        agents:
          manny:
            username: pa_manny
            personality: ../custom/agents/manny_personality.md
            subagents: [DevOpsEng, TestEng]
            assigned_projects: [NeuroVEP]

        subagents:
          DevOpsEng:
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
