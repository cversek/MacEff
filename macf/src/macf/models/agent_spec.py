"""
Pydantic models for agents.yaml configuration validation.

Models correspond to the YAML structure documented in:
docs/arch_v0.3_named_agents/05_implementation_guide.md (lines 48-125)
"""

from enum import Enum
from typing import List, Optional, Dict, Any
from pydantic import BaseModel, Field, field_validator, model_validator


class AgentFlavor(str, Enum):
    """How much of the MacEff framework an account receives.

    MACEFF: the full footprint — consciousness artifact trees, hooks, PREAMBLEs,
        layered CLAUDE.md, personal policies, framework commands/skills/output-styles.

    VANILLA: a plain Linux account with a home directory, SSH access, shell
        environment, toolchain, workspace and mailbox — and none of the above.
        Vanilla accounts exist so a deployment can host agents (or humans) that
        should see an ordinary environment, with no framework-specific files,
        tools, or context anywhere in their home.
    """

    MACEFF = "maceff"
    VANILLA = "vanilla"


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
    - channels: Launch-time channel plugins (-> --channels flag)

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
    channels: Optional[List[str]] = Field(
        default=None,
        description="Channel plugins to activate at launch (e.g., ['plugin:telegram@claude-plugins-official']). Passed as --channels flag to claude."
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


class EgressPolicy(BaseModel):
    """Outbound network restrictions applied to an agent's own uid.

    A restriction on what an agent may REACH cannot be enforced by the component
    the agent is supposed to reach, because nothing compels the agent to use it.
    An allowlist held by a mail broker is defeated not by a flaw in the broker but
    by the agent opening its own socket. Enforcement therefore lives in network
    policy, keyed on the kernel identity the agent cannot forge, and is applied by
    provisioning — outside the principal being restricted.

    Declaring this is opt-in per deployment: a config with no ``egress`` block
    anywhere behaves exactly as before. Within a deployment that declares it,
    the polarity is deny-by-default — an agent inherits ``defaults.egress`` unless
    it overrides, so an account added later is covered rather than silently exempt.
    Exemption must be written explicitly, which makes it visible in config review.
    """

    deny_tcp_ports: List[int] = Field(
        default_factory=list,
        description=(
            "Outbound TCP destination ports this agent's uid may not reach, over "
            "every address family. Typically the mail transport ports [25, 465, 587]. "
            "An empty list is a deliberate exemption, not an oversight — say so in a "
            "comment next to it."
        )
    )

    @field_validator('deny_tcp_ports', mode='before')
    @classmethod
    def validate_ports(cls, v: Any) -> Any:
        """Reject port values that cannot name a real destination.

        A wrong port here fails OPEN — the rule lands on a port nothing uses while
        the intended port stays reachable, and every log says the policy applied.
        So this refuses rather than letting provisioning report success for a
        restriction that restricts nothing.

        Runs in ``before`` mode deliberately. Pydantic's lax coercion would
        otherwise turn ``True`` into ``1`` before an ``after`` validator could see
        it, and YAML spells booleans ``on``/``yes``/``true`` — so a stray
        ``deny_tcp_ports: [on]`` would install a live-looking rule for port 1.
        Seeing the raw value is the only way to catch that.
        """
        if not isinstance(v, list):
            raise ValueError(f"deny_tcp_ports must be a list, got {type(v).__name__}")
        for port in v:
            # bool before int: bool IS an int subclass, so the order matters.
            if isinstance(port, bool) or not isinstance(port, int):
                raise ValueError(
                    f"deny_tcp_ports entries must be plain integers, got {port!r} "
                    f"({type(port).__name__}). Quote nothing and spell ports as numbers."
                )
            if not (1 <= port <= 65535):
                raise ValueError(f"deny_tcp_ports entry out of range 1-65535: {port}")
        if len(set(v)) != len(v):
            raise ValueError(f"deny_tcp_ports contains duplicates: {v}")
        return v


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

    flavor: AgentFlavor = Field(
        default=AgentFlavor.MACEFF,
        description=(
            "How much of the MacEff framework this account receives. "
            "'maceff' (default) installs the full footprint; 'vanilla' installs none "
            "of it. Defaulting to 'maceff' keeps every pre-existing agents.yaml valid."
        )
    )

    personality: Optional[str] = Field(
        default=None,
        description=(
            "Path to personality file (Identity layer CLAUDE.md source). "
            "Required for maceff-flavored agents, meaningless for vanilla ones — "
            "enforced by the require_personality_for_maceff validator rather than by "
            "the field itself, so vanilla accounts need not invent one."
        )
    )

    ssh_keys: Optional[List[str]] = Field(
        default=None,
        description=(
            "Public keys authorized for this account, in order. Each entry is either "
            "a key NAME resolved against the mounted key directory (e.g. 'cversek' -> "
            "/keys/cversek.pub) or a literal public key line ('ssh-ed25519 AAAA...'). "
            "All entries are installed, which is what lets an account be shared with a "
            "collaborator. When omitted, provisioning falls back to the legacy "
            "single-file lookup (/keys/{username}.pub) so existing deployments are "
            "unaffected."
        )
    )

    egress: Optional[EgressPolicy] = Field(
        default=None,
        description=(
            "Outbound network restrictions for this agent's uid. When omitted, the "
            "agent inherits defaults.egress; when defaults declares none either, no "
            "rules are installed and behaviour is unchanged from before this field "
            "existed. Declare an empty deny list to exempt an agent explicitly."
        )
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

    @property
    def is_vanilla(self) -> bool:
        """True when this account must receive no MacEff footprint at all."""
        return self.flavor == AgentFlavor.VANILLA

    @model_validator(mode='after')
    def require_personality_for_maceff(self) -> 'AgentSpec':
        """A maceff-flavored agent needs an identity layer; a vanilla one must not have one.

        Rejecting a personality on a vanilla account is deliberate. Silently ignoring
        it would let a deployment believe it had configured an identity that was never
        installed — the config would report one thing while the home directory showed
        another.
        """
        if self.flavor == AgentFlavor.MACEFF and not self.personality:
            raise ValueError(
                f"agent '{self.username}': personality is required for "
                f"flavor='maceff' (omit it only on flavor='vanilla')"
            )
        if self.flavor == AgentFlavor.VANILLA and self.personality:
            raise ValueError(
                f"agent '{self.username}': personality is meaningless for "
                f"flavor='vanilla' and would never be installed — remove it"
            )
        return self

    @field_validator('ssh_keys')
    @classmethod
    def validate_ssh_keys(cls, v: Optional[List[str]]) -> Optional[List[str]]:
        """Reject empty entries and an empty list.

        An empty list is rejected rather than treated as "no keys" because the two
        readings differ in consequence: it most likely means the operator intended to
        list keys and the templating produced nothing, which would silently lock the
        account out. Omit the field entirely to get the legacy single-key fallback.
        """
        if v is None:
            return v
        if not v:
            raise ValueError(
                "ssh_keys must not be an empty list — omit the field entirely for "
                "the legacy /keys/{username}.pub fallback"
            )
        for entry in v:
            if not entry or not entry.strip():
                raise ValueError("ssh_keys entries must be non-empty")
        return v


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

    egress: Optional[EgressPolicy] = Field(
        default=None,
        description=(
            "Default outbound network restrictions, inherited by every agent that "
            "does not declare its own. Declaring this here is how a deployment opts "
            "in: absent, no rules are installed anywhere and behaviour is unchanged. "
            "Present, every agent is covered unless it overrides — including agents "
            "added later, which is the point. Enforcement requires the container to "
            "carry NET_ADMIN and to have iptables available; provisioning FAILS "
            "rather than proceeding if a declared restriction cannot be installed."
        )
    )

    admin_ssh_keys: Optional[List[str]] = Field(
        default=None,
        description=(
            "Public keys authorized for the container's admin (sudoer) account, in "
            "the same NAME-or-literal form as AgentSpec.ssh_keys. Declared here "
            "rather than resolved from a hardcoded /keys/admin.pub so that operator "
            "access is configuration like every other account. When omitted, the "
            "legacy /keys/admin.pub lookup still applies."
        )
    )

    container_env: Dict[str, str] = Field(
        default_factory=dict,
        description=(
            "Container-wide environment variables. Written to /etc/environment "
            "(PAM/SSH coverage), /etc/profile.d/maceff-deployment-env.sh "
            "(login bash), and sourced by /etc/profile.d/maceff-bash-env.sh "
            "(non-login bash via BASH_ENV) at container start. Replaces the "
            "old pattern of declaring deployment env via Dockerfile ENV + "
            "manual /etc/environment writes — keep these declarative here "
            "instead. Per-agent overrides intentionally not supported in v1: "
            "container env is process-wide; per-user env belongs in "
            "~/.bash_init.sh which already exists."
        )
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
