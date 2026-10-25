"""
Pydantic models for agents.yaml configuration validation.

Models correspond to the YAML structure documented in:
docs/arch_v0.3_named_agents/05_implementation_guide.md (lines 48-125)
"""

from enum import Enum
from typing import Any, ClassVar, Dict, List, Optional
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


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

    # AN UNKNOWN KEY IS AN ERROR, NOT SOMETHING TO IGNORE.
    #
    # pydantic's default is extra="ignore", so a key this model does not define
    # was dropped at load with no warning, no log line and no non-zero exit.
    # That produced the worst shape a bug can take: a deployment missing ONE
    # capability and correct about everything else, with a config file stating
    # the capability is present. Two live instances were found this way, both
    # added deliberately, both carrying explanatory comments -- and one of them
    # sent an investigation after an entirely wrong cause, because the file
    # said the right thing.
    #
    # The forward-compatibility argument for tolerant parsing does not reach
    # here: these files are the sanctioned, hand-edited interface to a
    # deployment, provisioning runs unattended at container start, and its log
    # is read only when something already looks wrong -- which it does not,
    # because the ignored key was never needed to come up.
    model_config = ConfigDict(extra="forbid")


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

    # AN UNKNOWN KEY IS AN ERROR, NOT SOMETHING TO IGNORE.
    #
    # pydantic's default is extra="ignore", so a key this model does not define
    # was dropped at load with no warning, no log line and no non-zero exit.
    # That produced the worst shape a bug can take: a deployment missing ONE
    # capability and correct about everything else, with a config file stating
    # the capability is present. Two live instances were found this way, both
    # added deliberately, both carrying explanatory comments -- and one of them
    # sent an investigation after an entirely wrong cause, because the file
    # said the right thing.
    #
    # The forward-compatibility argument for tolerant parsing does not reach
    # here: these files are the sanctioned, hand-edited interface to a
    # deployment, provisioning runs unattended at container start, and its log
    # is read only when something already looks wrong -- which it does not,
    # because the ignored key was never needed to come up.
    model_config = ConfigDict(extra="forbid")


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

    # AN UNKNOWN KEY IS AN ERROR, NOT SOMETHING TO IGNORE.
    #
    # pydantic's default is extra="ignore", so a key this model does not define
    # was dropped at load with no warning, no log line and no non-zero exit.
    # That produced the worst shape a bug can take: a deployment missing ONE
    # capability and correct about everything else, with a config file stating
    # the capability is present. Two live instances were found this way, both
    # added deliberately, both carrying explanatory comments -- and one of them
    # sent an investigation after an entirely wrong cause, because the file
    # said the right thing.
    #
    # The forward-compatibility argument for tolerant parsing does not reach
    # here: these files are the sanctioned, hand-edited interface to a
    # deployment, provisioning runs unattended at container start, and its log
    # is read only when something already looks wrong -- which it does not,
    # because the ignored key was never needed to come up.
    model_config = ConfigDict(extra="forbid")


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
    # A seat a person types into can want this off. Claude Code shows a grey
    # predicted next prompt that Tab or Right-arrow accepts, and typing after an
    # accepted suggestion APPENDS to it. After a MacEff recovery hook the
    # predictor offers "Do your recovery", so a habitual Tab turned "/exit" into
    # "Do your recovery/exit". Declared here, it survives a rebuilt home; left
    # unset, Claude Code's own default applies.
    promptSuggestionEnabled: Optional[bool] = Field(
        default=None,
        description="Show Claude Code's predicted next prompt (false disables it); unset keeps the client default"
    )


class ClaudeCodeConfig(BaseModel):
    """Combined Claude Code configuration for container agents.

    Separates settings by concern into two sub-configs:
    - settings: Project/capability settings (-> ~/.claude/settings.json)
    - preferences: Person/UI settings (-> ~/.claude.json)
    - channels: Launch-time channel plugins (-> --channels flag)

    Per-agent values override deployment-level defaults.
    """

    # AN UNKNOWN KEY IS AN ERROR, NOT SOMETHING TO IGNORE.
    #
    # pydantic's default is extra="ignore", so a key this model does not define
    # was dropped at load with no warning, no log line and no non-zero exit.
    # That produced the worst shape a bug can take: a deployment missing ONE
    # capability and correct about everything else, with a config file stating
    # the capability is present. Two live instances were found this way, both
    # added deliberately, both carrying explanatory comments -- and one of them
    # sent an investigation after an entirely wrong cause, because the file
    # said the right thing.
    #
    # The forward-compatibility argument for tolerant parsing does not reach
    # here: these files are the sanctioned, hand-edited interface to a
    # deployment, provisioning runs unattended at container start, and its log
    # is read only when something already looks wrong -- which it does not,
    # because the ignored key was never needed to come up.
    model_config = ConfigDict(extra="forbid")


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

    # AN UNKNOWN KEY IS AN ERROR, NOT SOMETHING TO IGNORE.
    #
    # pydantic's default is extra="ignore", so a key this model does not define
    # was dropped at load with no warning, no log line and no non-zero exit.
    # That produced the worst shape a bug can take: a deployment missing ONE
    # capability and correct about everything else, with a config file stating
    # the capability is present. Two live instances were found this way, both
    # added deliberately, both carrying explanatory comments -- and one of them
    # sent an investigation after an entirely wrong cause, because the file
    # said the right thing.
    #
    # The forward-compatibility argument for tolerant parsing does not reach
    # here: these files are the sanctioned, hand-edited interface to a
    # deployment, provisioning runs unattended at container start, and its log
    # is read only when something already looks wrong -- which it does not,
    # because the ignored key was never needed to come up.
    model_config = ConfigDict(extra="forbid")


    private: Optional[List[str]] = Field(
        default=None,
        description="Private artifact types (checkpoints, reflections, learnings)"
    )
    public: Optional[List[str]] = Field(
        default=None,
        description="Public artifact types (roadmaps, reports, observations, experiments, ideas, roles, delegation_trails)"
    )
    immutable_structure: bool = Field(
        default=True,
        description="Prevent creation of new CA types via read-only parent directories (555 permissions)"
    )


class EgressPolicy(BaseModel):
    """Outbound network restrictions applied to an agent's own uid.

    **Policy**: ``capability_boundaries.md`` — read it before changing this.
    Consult it for why enforcement cannot live in the component being reached, what
    a deployment must do before a declaration means anything, and what an agent
    should do on meeting a boundary. This class is that policy's first concrete
    instance; the policy is where the reasoning lives, and an agent that hits one of
    these rules discovers the reason through ``macf_tools policy``, not by reading
    this source.

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

    # AN UNKNOWN KEY IS AN ERROR, NOT SOMETHING TO IGNORE.
    #
    # pydantic's default is extra="ignore", so a key this model does not define
    # was dropped at load with no warning, no log line and no non-zero exit.
    # That produced the worst shape a bug can take: a deployment missing ONE
    # capability and correct about everything else, with a config file stating
    # the capability is present. Two live instances were found this way, both
    # added deliberately, both carrying explanatory comments -- and one of them
    # sent an investigation after an entirely wrong cause, because the file
    # said the right thing.
    #
    # The forward-compatibility argument for tolerant parsing does not reach
    # here: these files are the sanctioned, hand-edited interface to a
    # deployment, provisioning runs unattended at container start, and its log
    # is read only when something already looks wrong -- which it does not,
    # because the ignored key was never needed to come up.
    model_config = ConfigDict(extra="forbid")


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


#: MacEff's own periodic mail checks: each runs as a schedule, where its runs, owed and done,
#: are recorded, never as a unit that loops on its own (MIS-0002-R54). The daemon runs as a
#: module (`-m`), or as its script, which carries its own interpreter line.
INBOUND_MODULE = 'macf.amail.daemons.inbound'
INBOUND_SCRIPT = 'amail/daemons/inbound.py'
PERIODIC_INBOUND_VERBS = ('watchdog', 'sweep')


def declaration_body(value: Optional[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    """A ``primal_daemon`` body in agents.yaml: a persistent_layer declaration without ``agent``
    and ``version``, which container start-up fills in. Checked against the closed model when the
    file loads, so a body the daemon would refuse never reaches a start. A unit that runs one of
    MacEff's periodic mail checks is refused here too: it belongs in ``schedules``
    (MIS-0002-R54 (periodic_mail_clock_MUST_be_schedule))."""
    if value is None:
        return value
    if 'agent' in value or 'version' in value:
        raise ValueError("primal_daemon must not set agent or version; the container fills them in")
    for unit in value.get('units', []):
        command = [str(word) for word in unit.get('command', [])]
        at = next((i for i, word in enumerate(command[:-1])
                   if word == INBOUND_MODULE or word.endswith(INBOUND_SCRIPT)), None)
        if at is not None:
            verb = command[at + 1]
            if verb in PERIODIC_INBOUND_VERBS:
                raise ValueError(
                    f"unit {unit.get('name')!r} runs `{INBOUND_MODULE} {verb}`, a periodic mail check: "
                    f"declare it in schedules, with its missed-run policy, so each run is recorded "
                    f"(MIS-0002-R54 (periodic_mail_clock_MUST_be_schedule))")
    from macf.pd.interface import Declaration
    Declaration(version=1, agent="placeholder@000000",
                **with_schedule_targets(value, "placeholder@000000"))
    return value


#: The schedule target that names the declaring agent's own session in agents.yaml. The card
#: carries an id the file can't know, so the container fills it in when it renders the
#: declaration (``with_schedule_targets``), the way it fills in ``agent`` itself.
OWN_CARD_TARGET = "{card}"


def with_schedule_targets(body: dict, card: str) -> dict:
    """*body* with every schedule target of ``{card}`` replaced by *card*. A target naming a
    literal card is left alone, so the declaration's own check still refuses a foreign one
    (MIS-0002-R29 (schedule_MUST_declare_target))."""
    schedules = body.get('schedules')
    if not schedules:
        return body
    return {**body, 'schedules': [
        {**s, 'target': card} if isinstance(s, dict) and s.get('target') == OWN_CARD_TARGET else s
        for s in schedules]}


class AgentSpec(BaseModel):
    """Specification for a Primary Agent (PA)."""

    # AN UNKNOWN KEY IS AN ERROR, NOT SOMETHING TO IGNORE.
    #
    # pydantic's default is extra="ignore", so a key this model does not define
    # was dropped at load with no warning, no log line and no non-zero exit.
    # That produced the worst shape a bug can take: a deployment missing ONE
    # capability and correct about everything else, with a config file stating
    # the capability is present. Two live instances were found this way, both
    # added deliberately, both carrying explanatory comments -- and one of them
    # sent an investigation after an entirely wrong cause, because the file
    # said the right thing.
    #
    # The forward-compatibility argument for tolerant parsing does not reach
    # here: these files are the sanctioned, hand-edited interface to a
    # deployment, provisioning runs unattended at container start, and its log
    # is read only when something already looks wrong -- which it does not,
    # because the ignored key was never needed to come up.
    model_config = ConfigDict(extra="forbid")


    username: str = Field(
        ...,
        description="Linux username for the agent (e.g., pa_manny)"
    )

    uid: int = Field(
        ...,
        description=(
            "The agent's uid, which its own group also takes as its gid. Declared, never "
            "assigned by creation order, and inside the deployment's id block, in the agent "
            "slots (IdBlock): a container without user-namespace remapping shares the "
            "host's id space, so a number that is also a host account's would make the two "
            "one identity (container_operations policy)."
        )
    )

    display_name: Optional[str] = Field(
        default=None,
        description="Human-readable display name for GECOS field and statusline (e.g., 'Manny MacEff')"
    )

    harness_session: Optional[str] = Field(
        default=None,
        description=(
            "tmux session name for this agent's supervised harness. DECLARED "
            "rather than derived from the agent key, because remote attach "
            "helpers bind to this exact string: renaming the session when a "
            "moniker or key changes strands every client that cannot be reached "
            "to update. Falls back to the agent key when omitted, which is why "
            "a deployment whose two values coincide never notices the "
            "difference. Provisioning exports it as MACEFF_HARNESS_SESSION."
        )
    )

    conda_env: Optional[str] = Field(
        default=None,
        description=(
            "Conda environment activated for this agent's shells. Declared here "
            "because deployments were already declaring it and the model was "
            "discarding it: with no schema field the key vanished at load, so a "
            "deployment that wanted a specific interpreter had to hardcode the "
            "name in a shell script instead. That duplicate then became a file "
            "that could go missing with nothing to notice -- which is what "
            "happened. Declaring the field does not itself activate anything; "
            "it makes the value visible to the framework so a consumer can read "
            "it rather than each deployment restating it."
        )
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
            "existed. Declare an empty deny list to exempt an agent explicitly. "
            "See the capability_boundaries policy for what a deployment must do "
            "before this declaration means anything, and how to verify it holds."
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

    primal_daemon: Optional[Dict[str, Any]] = Field(
        default=None,
        description=(
            "This agent's primal daemon declaration, the body of a persistent_layer declaration "
            "without `agent` and `version`, which the container fills in. Container start-up renders "
            "it owned by root, in a directory the agent can't write, and the daemon reads it from "
            "there only, so no run, which executes as the agent, can change its schedules "
            "(MIS-0002-R33 (run_MUST-NOT_change_schedules)). Absent, the agent gets no daemon from "
            "the container."
        ),
    )

    calling_card: Optional[str] = Field(
        default=None,
        pattern=r"^[A-Za-z][A-Za-z0-9]{0,47}$",
        description=(
            "The name this agent goes by, its calling card's first half; the second half is the "
            "first six characters of the agent's identity file. Container start-up writes it into "
            "the agent's home as agent_identity.calling_card in .maceff/config.json, where the "
            "primal daemon reads it, and refuses to overwrite a different card already there. "
            "Required with primal_daemon (persistent_layer 10.1)."
        ),
    )

    @field_validator('primal_daemon')
    @classmethod
    def _primal_daemon_is_a_declaration(cls, value):
        """Refused at load, not at start: a body the daemon would refuse is caught here."""
        return declaration_body(value)

    @property
    def is_vanilla(self) -> bool:
        """True when this account must receive no MacEff footprint at all."""
        return self.flavor == AgentFlavor.VANILLA

    @model_validator(mode='after')
    def no_primal_daemon_for_vanilla(self) -> 'AgentSpec':
        """A vanilla account gets no MacEff footprint, so nothing starts a primal daemon for it,
        and a schedule it declared would have no daemon to run it. Refused when agents.yaml loads,
        which container start does (MIS-0002-R11 (CI_MUST_fail_unhosted_schedule))."""
        if self.flavor == AgentFlavor.VANILLA and self.primal_daemon is not None:
            raise ValueError(
                f"{self.username} is vanilla and declares primal_daemon: a vanilla account gets no "
                "MacEff footprint, so no daemon would run its units or schedules. Remove primal_daemon, "
                "or make the account maceff-flavored")
        return self

    @model_validator(mode='after')
    def _a_daemon_has_a_name(self) -> 'AgentSpec':
        """A daemon runs under its agent's calling card, which a container agent's home holds only
        if agents.yaml declares it: without one the declaration can't be rendered at start. So the
        pair is refused when agents.yaml loads, naming the agent. A card without a daemon is fine;
        a card on a vanilla account is not, since writing it would give the account a footprint."""
        if self.primal_daemon is not None and self.calling_card is None:
            raise ValueError(
                f"agent '{self.username}' declares primal_daemon without calling_card: the daemon "
                "runs under the agent's calling card, which start-up writes into its home from "
                "agents.yaml. Add calling_card beside primal_daemon")
        if self.flavor == AgentFlavor.VANILLA and self.calling_card is not None:
            raise ValueError(
                f"agent '{self.username}' is vanilla and declares calling_card: a vanilla account "
                "gets no MacEff footprint, so no card is written for it. Remove calling_card")
        return self

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

    # AN UNKNOWN KEY IS AN ERROR, NOT SOMETHING TO IGNORE.
    #
    # pydantic's default is extra="ignore", so a key this model does not define
    # was dropped at load with no warning, no log line and no non-zero exit.
    # That produced the worst shape a bug can take: a deployment missing ONE
    # capability and correct about everything else, with a config file stating
    # the capability is present. Two live instances were found this way, both
    # added deliberately, both carrying explanatory comments -- and one of them
    # sent an investigation after an entirely wrong cause, because the file
    # said the right thing.
    #
    # The forward-compatibility argument for tolerant parsing does not reach
    # here: these files are the sanctioned, hand-edited interface to a
    # deployment, provisioning runs unattended at container start, and its log
    # is read only when something already looks wrong -- which it does not,
    # because the ignored key was never needed to come up.
    model_config = ConfigDict(extra="forbid")


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

    # AN UNKNOWN KEY IS AN ERROR, NOT SOMETHING TO IGNORE.
    #
    # pydantic's default is extra="ignore", so a key this model does not define
    # was dropped at load with no warning, no log line and no non-zero exit.
    # That produced the worst shape a bug can take: a deployment missing ONE
    # capability and correct about everything else, with a config file stating
    # the capability is present. Two live instances were found this way, both
    # added deliberately, both carrying explanatory comments -- and one of them
    # sent an investigation after an entirely wrong cause, because the file
    # said the right thing.
    #
    # The forward-compatibility argument for tolerant parsing does not reach
    # here: these files are the sanctioned, hand-edited interface to a
    # deployment, provisioning runs unattended at container start, and its log
    # is read only when something already looks wrong -- which it does not,
    # because the ignored key was never needed to come up.
    model_config = ConfigDict(extra="forbid")


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
            "carry NET_ADMIN and to have iptables available (capability_boundaries "
            "policy explains why enforcement must abort rather than warn); "
            "provisioning FAILS "
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


class SecretSpec(BaseModel):
    """One credential a service needs, declared by NAME and DESTINATION.

    Declaration lives beside the account that needs it, so a reviewer reading
    the deployment sees what each service may hold -- the same reasoning that
    puts `ssh_keys` next to the account it authorises. The VALUE never appears
    here; only where it comes from and what custody it must end up under.

    The source is resolved as `<secrets mount>/<name>` from a read-only host
    directory whose mount point is 0700 root-owned, so no agent uid can reach
    it even before placement. Provisioning copies, chowns, chmods and then
    VERIFIES -- and a declared-but-absent secret is a hard startup refusal,
    because a configured-and-missing credential passes every naive truthiness
    check and then fails at the edge, where the diagnosis reads as somebody
    else's network problem rather than as ours.
    """

    # AN UNKNOWN KEY IS AN ERROR, NOT SOMETHING TO IGNORE.
    #
    # pydantic's default is extra="ignore", so a key this model does not define
    # was dropped at load with no warning, no log line and no non-zero exit.
    # That produced the worst shape a bug can take: a deployment missing ONE
    # capability and correct about everything else, with a config file stating
    # the capability is present. Two live instances were found this way, both
    # added deliberately, both carrying explanatory comments -- and one of them
    # sent an investigation after an entirely wrong cause, because the file
    # said the right thing.
    #
    # The forward-compatibility argument for tolerant parsing does not reach
    # here: these files are the sanctioned, hand-edited interface to a
    # deployment, provisioning runs unattended at container start, and its log
    # is read only when something already looks wrong -- which it does not,
    # because the ignored key was never needed to come up.
    model_config = ConfigDict(extra="forbid")


    name: str = Field(..., description="File name under the secrets mount")
    dest: str = Field(..., description="Absolute path to place it at")
    owner: str = Field(..., description="Owning user after placement")
    group: Optional[str] = Field(default=None, description="Owning group (defaults to owner)")
    mode: str = Field(default="0600", description="Octal mode after placement")


class ServiceSpec(BaseModel):
    """A non-agent service account the deployment provisions.

    Distinct from an AgentSpec because these have no home, no personality and no
    consciousness artifacts -- they exist to hold a capability an agent must NOT
    have. Identity separation is the precondition that makes any owner-scoped
    guarantee statable at all: "only the broker may read this credential" is not
    a weaker rule without a separate uid, it is an INEXPRESSIBLE one.
    """

    # AN UNKNOWN KEY IS AN ERROR, NOT SOMETHING TO IGNORE.
    #
    # pydantic's default is extra="ignore", so a key this model does not define
    # was dropped at load with no warning, no log line and no non-zero exit.
    # That produced the worst shape a bug can take: a deployment missing ONE
    # capability and correct about everything else, with a config file stating
    # the capability is present. Two live instances were found this way, both
    # added deliberately, both carrying explanatory comments -- and one of them
    # sent an investigation after an entirely wrong cause, because the file
    # said the right thing.
    #
    # The forward-compatibility argument for tolerant parsing does not reach
    # here: these files are the sanctioned, hand-edited interface to a
    # deployment, provisioning runs unattended at container start, and its log
    # is read only when something already looks wrong -- which it does not,
    # because the ignored key was never needed to come up.
    model_config = ConfigDict(extra="forbid")


    secrets: List[SecretSpec] = Field(
        default_factory=list,
        description="Credentials this service holds"
    )

    primal_daemon: Optional[Dict[str, Any]] = Field(
        default=None,
        description=(
            "The service account's own primal daemon declaration, the same body as an agent's. "
            "Container start-up renders it owned by root and gives the account an identity, and the "
            "daemon runs the service's long-lived processes as units and its periodic work as "
            "schedules, under the account's own uid. The mail broker's account declares one for the "
            "broker, its inbound watcher and the aged sweep (MIS-0002-R53 (mail_broker_MUST_be_managed), "
            "MIS-0002-R54 (periodic_mail_clock_MUST_be_schedule)). Every unit runs as the service account."
        ),
    )

    calling_card: Optional[str] = Field(
        default=None,
        pattern=r"^[A-Za-z][A-Za-z0-9]{0,47}$",
        description=(
            "The name the service's primal daemon goes by, its calling card's first half. Start-up "
            "derives the second half from the account and the deployment's id block, so the card "
            "holds across recreates and differs between deployments. Required with primal_daemon."
        ),
    )

    @field_validator('primal_daemon')
    @classmethod
    def _primal_daemon_is_a_declaration(cls, value):
        return declaration_body(value)

    @model_validator(mode='after')
    def _a_daemon_has_a_name(self) -> 'ServiceSpec':
        """A daemon needs a card to run under, and a card names nothing without a daemon."""
        if (self.primal_daemon is None) != (self.calling_card is None):
            raise ValueError("a service declares primal_daemon and calling_card together")
        return self


#: Container ids start here, clear of every host's human accounts (useradd hands those out
#: from 1000 up) and of its system ids (below 1000).
ID_BLOCK_FLOOR = 20000
ID_BLOCK_SIZE = 1000


class IdBlock(BaseModel):
    """The uid and gid numbers a deployment's container owns: ``base`` to ``base + 999``.

    A container without user-namespace remapping shares the host's id space, so every
    account and group the framework creates takes its number from here, never from
    creation order. Each deployment on a host gets its own block, so two deployments'
    agents are never one identity either.

    Fixed slots, the same in every block (offsets from ``base``): ``admin`` at 0 (uid and
    gid); the groups ``agents_all`` 1, ``sa_all`` 2, ``policyeditors`` 3; the agents at
    100-899, each its own declared uid; 900-997 for the deployment's own service
    accounts; ``amail_broker`` 998 and ``amail_ingest`` 999.
    """

    model_config = ConfigDict(extra="forbid")

    base: int = Field(
        ...,
        description=f"First number of the block: a multiple of {ID_BLOCK_SIZE}, at least {ID_BLOCK_FLOOR}"
    )

    @field_validator('base')
    @classmethod
    def _base_is_a_block(cls, v: int) -> int:
        if v < ID_BLOCK_FLOOR or v % ID_BLOCK_SIZE:
            raise ValueError(
                f"ids.base must be a multiple of {ID_BLOCK_SIZE} and at least {ID_BLOCK_FLOOR}, "
                f"clear of the host's own accounts (got {v}); see the container_operations policy")
        if v + ID_BLOCK_SIZE - 1 > 65533:
            raise ValueError(f"ids.base {v} runs the block past 65533")
        return v

    #: Offsets of the fixed slots.
    SLOTS: ClassVar[Dict[str, int]] = {
        "admin": 0, "agents_all": 1, "sa_all": 2, "policyeditors": 3,
        "amail_broker": 998, "amail_ingest": 999,
    }
    AGENT_FIRST: ClassVar[int] = 100
    AGENT_LAST: ClassVar[int] = 899

    def slot(self, name: str) -> int:
        """The number of a fixed slot, by its account or group name."""
        return self.base + self.SLOTS[name]

    def agent_range(self) -> range:
        return range(self.base + self.AGENT_FIRST, self.base + self.AGENT_LAST + 1)


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

    # AN UNKNOWN KEY IS AN ERROR, NOT SOMETHING TO IGNORE.
    #
    # pydantic's default is extra="ignore", so a key this model does not define
    # was dropped at load with no warning, no log line and no non-zero exit.
    # That produced the worst shape a bug can take: a deployment missing ONE
    # capability and correct about everything else, with a config file stating
    # the capability is present. Two live instances were found this way, both
    # added deliberately, both carrying explanatory comments -- and one of them
    # sent an investigation after an entirely wrong cause, because the file
    # said the right thing.
    #
    # The forward-compatibility argument for tolerant parsing does not reach
    # here: these files are the sanctioned, hand-edited interface to a
    # deployment, provisioning runs unattended at container start, and its log
    # is read only when something already looks wrong -- which it does not,
    # because the ignored key was never needed to come up.
    model_config = ConfigDict(extra="forbid")


    ids: IdBlock = Field(
        ...,
        description="The uid and gid block this deployment's container owns (IdBlock)"
    )

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

    services: Dict[str, ServiceSpec] = Field(
        default_factory=dict,
        description="Non-agent service accounts and the secrets they hold"
    )

    @model_validator(mode='after')
    def _agent_uids_in_their_slots(self) -> 'AgentsConfig':
        """Every agent's uid sits in the block's agent slots, and no two agents share one."""
        slots = self.ids.agent_range()
        seen: Dict[int, str] = {}
        for name, spec in self.agents.items():
            if spec.uid not in slots:
                raise ValueError(
                    f"agent {name!r} declares uid {spec.uid}, outside the agent slots "
                    f"{slots.start}-{slots.stop - 1} of ids.base {self.ids.base}")
            if spec.uid in seen:
                raise ValueError(
                    f"agents {seen[spec.uid]!r} and {name!r} both declare uid {spec.uid}; "
                    f"one uid names one agent")
            seen[spec.uid] = name
        return self

    @model_validator(mode='after')
    def _service_units_run_as_the_service(self) -> 'AgentsConfig':
        """A daemon starts its units only as its own user, so each unit of a service's daemon runs
        as that service's account. Refused at load, rather than as a failed unit at start."""
        for name, spec in self.services.items():
            for unit in (spec.primal_daemon or {}).get('units', []):
                if unit.get('account') != name:
                    raise ValueError(
                        f"services.{name}.primal_daemon: unit {unit.get('name')!r} names account "
                        f"{unit.get('account')!r}, but a service's daemon starts units only as the "
                        f"service account, {name}")
        return self
