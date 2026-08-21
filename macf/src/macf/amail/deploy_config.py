"""Declarative deployment configuration for the amail broker daemon.

A deployment describes the broker in a root-owned **YAML** file; the daemon
entry point loads it through these models. Pydantic is the framework convention
for declarative config (the ``agents.yaml`` account model set the precedent),
and it buys the property a hand-rolled ``raw["key"]`` parser cannot offer
honestly: **a misspelled or unknown key refuses to start** (``extra="forbid"``)
instead of being ignored — an ignored key in a security config silently changes
what the broker enforces, which is the config-file form of a silent failure.

**YAML, NOT JSON, AND THE REASON IS THE COMMENT.** These files are
hand-authored and hand-maintained; nothing generates them. Combining JSON with
``extra="forbid"`` produced a format in which a deployment literally could not
record why it set a value or which model governs the schema — an unknown key is
refused, and JSON has no comment syntax, so annotation was impossible. The
strictness is right and stays; a format that forbids strictness AND annotation
is hostile to the next person editing it, and that person usually has no idea
which Python class governs the file. YAML also matches the convention every
other first-class MacEff subsystem already follows.

The file is deliberately separate from :class:`~macf.amail.broker.BrokerConfig`:
that dataclass is the broker's in-memory shape; this is the on-disk contract a
deployment writes, validated at the trust boundary where operator-authored
configuration becomes broker authority.
"""
import pwd
from pathlib import Path
from typing import Any, Dict, List, Optional

import yaml
from pydantic import (BaseModel, ConfigDict, Field, field_validator,
                      model_validator)

from macf.amail.broker import BrokerConfig


class ConfigError(Exception):
    """A declarative config could not be read or parsed.

    Distinct from Pydantic's ValidationError, which means the file parsed and
    said something wrong. This means we never got far enough to find out --
    a distinction the caller needs, because one points at the file's CONTENT
    and the other at the file itself.
    """


def load_declarative_config(path: Path) -> Dict[str, Any]:
    """Read one YAML config into a mapping, or raise with a usable reason.

    ABSENCE, UNREADABILITY AND MALFORMEDNESS ARE THREE DIFFERENT FACTS and each
    sends the reader somewhere different: place the file, fix its permissions,
    or fix its syntax. Collapsing them into "config error" makes the reader
    check all three.

    A file that parses to something other than a mapping is refused rather than
    coerced. An empty file yields ``None`` from the YAML parser, and treating
    that as ``{}`` would hand Pydantic an empty mapping and produce a
    complaint about missing required keys -- pointing at the schema when the
    real fault is an empty file.
    """
    path = Path(path)
    try:
        text = path.read_text()
    except FileNotFoundError as e:
        raise ConfigError(f"no config at {path}; nothing to start from") from e
    except OSError as e:
        raise ConfigError(f"config at {path} could not be read: {e}") from e

    try:
        raw = yaml.safe_load(text)
    except yaml.YAMLError as e:
        raise ConfigError(f"config at {path} is not valid YAML: {e}") from e

    if raw is None:
        raise ConfigError(
            f"config at {path} is empty. Reported as empty rather than passed "
            f"on as an empty mapping, which would surface as a complaint about "
            f"missing required keys and point at the schema instead of the file.")
    if not isinstance(raw, dict):
        raise ConfigError(
            f"config at {path} parsed as {type(raw).__name__}, not a mapping")
    return raw


class AgentBinding(BaseModel):
    """One local agent: its address local-part maps to a home and a uid.

    The agent NAME (the mapping key in :class:`BrokerDeployConfig.agents`) is
    the address local-part; the unix account may be named differently — the
    home path and uid are what bind them.
    """

    model_config = ConfigDict(extra="forbid")

    account: Optional[str] = Field(
        default=None,
        description="the unix account. Preferred form: uid and home are then "
                    "resolved from the system, so this file cannot disagree "
                    "with the kernel about who an agent is.")
    home: Optional[Path] = Field(
        default=None,
        description="the agent's home directory (its mail store lives here). "
                    "Resolved from `account` when omitted.")
    uid: Optional[int] = Field(
        default=None,
        description="the agent's unix uid. THE authentication table entry: "
                    "the kernel's view of who is on the socket is the fact; "
                    "a submitted sender field is only a claim. Resolved from "
                    "`account` when omitted.")

    @model_validator(mode="after")
    def _resolve_from_account(self):
        """Resolve uid and home from the account, and refuse any disagreement.

        The uid mapping built from this file IS the authentication table: an
        incoming connection's SO_PEERCRED uid is looked up in it to decide which
        agent is speaking. A stale number therefore does not fail — it assigns
        that agent's identity to whoever now holds the uid, and refuses the real
        one. Accounts are renumbered exactly when they are recreated, which is
        what a rebuild does.

        Resolving from the account makes this file and the kernel read the same
        source. When both are given they are compared, so a stale value is loud
        rather than silent.
        """
        if self.account:
            try:
                pw = pwd.getpwnam(self.account)
            except KeyError:
                raise ValueError(
                    f"account '{self.account}' does not exist on this system; "
                    f"refusing to guess its uid")
            if self.uid is not None and self.uid != pw.pw_uid:
                raise ValueError(
                    f"account '{self.account}' has uid {pw.pw_uid}, but this "
                    f"config declares {self.uid}. The declared value would be "
                    f"used as the authentication table entry, so the mismatch "
                    f"is refused rather than resolved.")
            if self.home is not None and Path(self.home) != Path(pw.pw_dir):
                raise ValueError(
                    f"account '{self.account}' has home {pw.pw_dir}, but this "
                    f"config declares {self.home}")
            self.uid = pw.pw_uid
            self.home = Path(pw.pw_dir)
        if self.uid is None or self.home is None:
            raise ValueError(
                "declare `account` (preferred — uid and home are resolved from "
                "it), or both `uid` and `home` explicitly")
        return self


class AgentAddressing(AgentBinding):
    """One agent's mailbox identity: its account, and who it may write to.

    The mapping key is the address local-part, which need not equal the unix
    account name. Contacts live here rather than in a parallel file because
    they are per-agent facts about the same subject; a second file keyed by the
    same agent names can disagree with this one.

    Fields:
        account   unix account; uid and home resolve from it (see AgentBinding).
        contacts  addresses this agent may send to. Strings, or mappings with
                  `address` and optionally `key`/`keys`, `push`, `note`.
    """

    contacts: List[Any] = Field(default_factory=list)
    rate_limit: Optional[int] = Field(
        default=None,
        description="this agent's submission cap per window, overriding the "
                    "broker's default. Stated beside the agent so the "
                    "exception is visible to whoever reads about it.")


class AddressingConfig(BaseModel):
    """The amail deployment's identity: its domain, its agents, their contacts.

    Separate from the broker's configuration because it answers a different
    question. This file says WHO EXISTS and WHO THEY MAY TALK TO; the broker
    config says how the broker behaves. It is also deployment fact — a map of
    the correspondents this system has — so it lives outside the repository
    while the broker's tuning does not.
    """

    model_config = ConfigDict(extra="forbid")

    domain: str = Field(description="the address domain this deployment owns")
    agents: Dict[str, AgentAddressing] = Field(
        description="address local-part -> agent")

    @field_validator("agents")
    @classmethod
    def _agents_nonempty_and_uids_unique(cls, v: Dict[str, AgentAddressing]):
        if not v:
            raise ValueError(
                "no agents configured: an empty table means nobody can be "
                "authenticated and every submission would be refused")
        uids: Dict[int, str] = {}
        for name, binding in v.items():
            if binding.uid in uids:
                raise ValueError(
                    f"agents {uids[binding.uid]!r} and {name!r} share uid "
                    f"{binding.uid}: the uid table is the authentication table, "
                    "and one uid cannot be two identities")
            uids[binding.uid] = name
        return v


class BrokerDeployConfig(BaseModel):
    """The on-disk broker daemon configuration (``broker_config.yaml``).

    Tunes the broker: stores, limits, transport, gates. The deployment's
    identity — domain, agents, contacts — lives in the addressing config this
    one points at.

    Must be root-owned and read-only to the broker uid: the broker must not be
    able to rewrite its own authority.
    """

    model_config = ConfigDict(extra="forbid")

    addressing_path: Path = Field(
        description="the deployment's addressing config: domain, agents, and "
                    "each agent's contacts. Deployment identity lives there; "
                    "this file tunes the broker.")
    # ------------------------------------------------------------------
    # DEFAULTS ARE FOR PLUMBING, NEVER FOR AUTHORIZATION.
    #
    # The store paths below default to the locations the BASE IMAGE actually
    # provisions, so a deployment states only what differs from the standard
    # layout. That is safe precisely because the base image creates those exact
    # directories with those exact owners and modes — the default is not a
    # guess about where things might be, it is the same fact the Dockerfile
    # asserts.
    #
    # `credentials_path` deliberately KEEPS `None` and must be declared. It is
    # security-relevant, and a security-relevant path that can be inherited
    # silently is one a reviewer never sees. `null` additionally MEANS
    # something — unconfigured, which starts and announces itself — and is a
    # distinct state from a configured-and-missing credential, which is a hard
    # refusal. A default would erase a state the custody model depends on.
    #
    # `addressing_path` is required for the same reason and has no default:
    # "which addresses may this deployment write to" must be answerable by
    # reading this file, not by knowing what the model does when a key is
    # absent.
    # ------------------------------------------------------------------
    credentials_path: Optional[Path] = Field(
        default=None,
        description="submission credential. NOT defaulted, and null MEANS "
                    "unconfigured (starts, announces itself) as distinct from "
                    "configured-and-absent (hard refusal). When set: 0600, "
                    "owned by the broker uid — serve() refuses otherwise.")

    audit_path: Optional[Path] = Field(
        default=Path("/var/lib/amail_broker/audit.jsonl"),
        description="broker-owned audit log (jsonl)")
    socket_path: Path = Field(
        default=Path("/run/amail/broker.sock"),
        description="the submission socket the broker binds")
    inbound_quarantine: Optional[Path] = Field(
        default=Path("/var/lib/amail_broker/quarantine"),
        description="broker-owned quarantine for refused internet mail")
    inbound_handoff: Optional[Path] = Field(
        default=Path("/var/lib/amail/handoff"),
        description="pickup boxes: handoff/<agent>/ owned by the broker, "
                    "group = the recipient's group; the recipient ingests as itself")
    dispositions_dir: Optional[Path] = Field(
        default=Path("/var/lib/amail_broker/dispositions"),
        description="broker-owned, agent-READABLE records of what became of "
                    "each submitted message. Without it a sender holds a copy "
                    "of what it sent and cannot learn whether it left, which "
                    "is the outbound face of a silent drop.")
    rate_limit_dir: Optional[Path] = Field(
        default=Path("/var/lib/amail_broker/ratelimit"),
        description="broker-owned, agent-READABLE rate-limit state. On disk "
                    "rather than in memory: a budget held in memory resets "
                    "when the broker restarts, which turns a restart into a "
                    "way to spend the budget twice.")
    rate_limit_per_agent: Optional[int] = Field(
        default=None, description="max submissions per agent per window")
    rate_limit_broker: Optional[int] = Field(
        default=None,
        description="max broker-originated messages (non-delivery notices) per "
                    "window. Separate from the per-agent budget because no "
                    "agent composed them.")
    rate_limit_window_seconds: int = Field(
        default=3600, description="the sliding window, in seconds")
    transport_endpoint: Optional[str] = Field(
        default=None,
        description="the outbound submission endpoint. Null until the outbound "
                    "leg exists, and null is why sends REFUSE rather than "
                    "silently doing nothing: the broker names the missing "
                    "transport at the rung that needed it. THIS FIELD IS THE "
                    "ONLY WAY A DEPLOYMENT CAN OBTAIN A TRANSPORT -- the class "
                    "existed and was unit-tested for a full phase while nothing "
                    "on the deployment path could construct one, so a broker "
                    "holding a valid credential still had no route to the "
                    "internet.")
    transport_timeout: float = Field(
        default=30.0,
        description="seconds to wait on the submission endpoint. Bounded "
                    "because an unbounded submit holds the socket open and a "
                    "sender learns nothing while it waits.")
    opsec_scan: bool = Field(
        default=True,
        description="run the pre-send OPSEC scrub on every outbound message. "
                    "Defaults ON: a gate is only a control if the deployment "
                    "that ships has it, and an opt-in security default is off "
                    "everywhere nobody remembered to turn it on. Set false "
                    "only for a closed fleet, deliberately.")
    refuse_unscanned: bool = Field(
        default=True,
        description="refuse a message with a part the scrub could not read as "
                    "text. What is forbidden is the third option, where an "
                    "unscanned part silently counts as scanned.")

    def to_broker_config(self) -> BrokerConfig:
        """The in-memory shape the broker actually runs on.

        EVERY FIELD ABOVE MUST APPEAR BELOW. A field declared in the on-disk
        contract and dropped here is worse than an absent one: the operator
        writes it, the config validates, the broker starts, and the setting
        does nothing — a silent partial with the shape of a complete one. The
        test suite asserts the two sides agree rather than trusting this note.
        """
        addressing = self.load_addressing()
        return BrokerConfig(
            domain=addressing.domain,
            agent_homes={name: b.home for name, b in addressing.agents.items()},
            contacts_path=self.addressing_path,
            audit_path=self.audit_path,
            socket_path=self.socket_path,
            credentials_path=self.credentials_path,
            inbound_quarantine=self.inbound_quarantine,
            inbound_handoff=self.inbound_handoff,
            dispositions_dir=self.dispositions_dir,
            rate_limiter=self._build_rate_limiter(addressing.agents),
            transport=self._build_transport(),
            opsec_scan=self._build_scan() if self.opsec_scan else None,
            refuse_unscanned=self.refuse_unscanned,
            agent_uids={b.uid: name for name, b in addressing.agents.items()},
        )

    def load_addressing(self) -> "AddressingConfig":
        """Load and validate the deployment's addressing config."""
        return AddressingConfig.model_validate(
            load_declarative_config(self.addressing_path))

    def _build_transport(self):
        """The outbound transport, or None when no endpoint is declared.

        NONE RATHER THAN A NULL TRANSPORT, deliberately. The broker's rung-3
        path already refuses on a missing transport and names the recipient
        that needed one; returning a refusing object here would give one
        condition two refusal paths with two messages, and two mechanisms for
        one property drift apart the first time only one of them is touched.
        NullTransport remains the right default for a caller building a
        BrokerConfig directly, where no rung check stands behind it.

        THE GAP THIS CLOSES was the wiring chain a layer deeper than the one
        that ate ``dispositions_dir``. The transport class was written, tested
        and complete; the on-disk contract had no field for an endpoint, so
        ``to_broker_config`` had nothing to translate and every deployment ran
        with ``transport=None`` no matter what its credential said. The
        declared-vs-consumed guard could not see it: that test walks the
        on-disk fields and asserts each is consumed, which finds a DROPPED
        field and is structurally blind to a BrokerConfig field that no
        on-disk field FEEDS. Absence again, on the axis the instrument does
        not scan.
        """
        if not self.transport_endpoint:
            return None
        from macf.amail.transport import HttpTransport
        return HttpTransport(self.transport_endpoint, timeout=self.transport_timeout)

    def _build_rate_limiter(self, agents=None):
        """The limiter, or None when the deployment declares no budget.

        Requires BOTH a state directory and at least one cap. A cap with
        nowhere to record consumption cannot enforce anything, and a directory
        with no cap enforces nothing -- either alone would produce a limiter
        that looks configured and permits everything, which is worse than an
        absent one because submit() would stop announcing it.
        """
        if not self.rate_limit_dir:
            return None
        agents = agents or {}
        limits = {}
        if self.rate_limit_per_agent:
            from macf.amail.ratelimit import RateLimit
            for name, binding in agents.items():
                # A UNIFORM CAP HAS TO BE SIZED FOR THE NOISIEST AGENT, which
                # defeats the control: reputation aggregates at the
                # organisational domain, so provisioning every agent for the
                # loudest one spends an asset belonging to all of them. The
                # per-agent override sits beside the agent in the addressing
                # config, where a reviewer reading about that agent sees it.
                cap = binding.rate_limit or self.rate_limit_per_agent
                limits[name] = RateLimit(cap, self.rate_limit_window_seconds)
        if self.rate_limit_broker:
            from macf.amail.ratelimit import RateLimit, BROKER_PRINCIPAL
            limits[BROKER_PRINCIPAL] = RateLimit(self.rate_limit_broker,
                                                 self.rate_limit_window_seconds)
        if not limits:
            return None
        from macf.amail.ratelimit import RateLimiter
        return RateLimiter(self.rate_limit_dir, limits)

    @staticmethod
    def _build_scan():
        """The pre-send scrub as a callable the broker can invoke.

        Bound here rather than in the broker so the broker holds no opinion
        about which scanner it runs, and a deployment can substitute one
        without touching enforcement code. The patterns are derived from the
        RUNNING environment at scan time (hostname, account, agent home), so
        nothing private is written into the deployment file.
        """
        from macf.opsec import scan_message
        return scan_message


class InboundDeployConfig(BaseModel):
    """The on-disk INBOUND configuration (``inbound_config.json``).

    THIS EXISTS BECAUSE THE INBOUND ENTRY POINT HAND-ROLLED ITS CONFIG. The
    broker daemon loads its file through :class:`BrokerDeployConfig` — validated,
    unknown keys refused, every field carried. The inbound consumer parsed a
    dict by hand and built a :class:`BrokerConfig` from four fields, so it ran
    with ``opsec_scan=None``, ``rate_limiter=None`` and ``transport=None``.

    The consequence was live and silent: a non-delivery notice was **never
    scrubbed**, was charged against **no budget**, and could not be sent — while
    the code implementing all three was correct and fully tested. Two entry
    points to one deployment, one validated and one by hand, and the hand-rolled
    one dropped two security controls without saying anything.

    THE DUPLICATION WAS THE CRUFT. The old file re-declared ``domain``,
    ``agents``, ``contacts_path`` and ``audit_path`` — all of which the broker
    config already carries — so the two could drift apart, and did. The broker
    half is now READ FROM THE BROKER'S OWN FILE and this contract holds only
    what is genuinely inbound.
    """

    model_config = ConfigDict(extra="forbid")

    spool_dir: Path = Field(description="the receiver's spool; this consumer's input")
    quarantine_dir: Path = Field(description="broker-owned quarantine for refused mail")
    handoff_dir: Path = Field(
        default=Path("/var/lib/amail/handoff"),
        description="pickup boxes: handoff/<agent>/, broker-owned, recipient-group readable")
    verdict_authority: str = Field(
        default="",
        description="the authserv-id this deployment trusts in "
                    "Authentication-Results. A verdict stamped by anyone else "
                    "is treated as ABSENT, never as a failure.")
    push_wake_enabled: bool = Field(
        default=False,
        description="while the wake mechanism is unbuilt this stays false and "
                    "no path may produce the push-wake outcome")
    broker_config_path: Path = Field(
        default=Path("/etc/amail/broker_config.json"),
        description="the BROKER's deployment config. Read through the same "
                    "validated model the broker daemon uses, so both entry "
                    "points agree by construction rather than by discipline.")
    contacts_path: Optional[Path] = Field(
        default=None,
        description="OPTIONAL override of the broker's contact list for INBOUND "
                    "authorization. Null means use the broker's, which is what "
                    "the amail spec prefers: one broker-owned store whose "
                    "AUTHORITY is per-agent. A separate list here makes "
                    "who-may-write-to-me and who-I-may-write-to two different "
                    "questions with two different answers, which is a "
                    "deployment's choice to make DELIBERATELY and not by "
                    "inheriting an old file.")
    audit_path: Optional[Path] = Field(
        default=None, description="OPTIONAL override of the broker's audit log")

    def to_inbound_config(self):
        """Compose the in-memory inbound config, broker half included.

        The broker half comes from the broker's own validated file, so a
        control added there — a scrubber, a limiter, a transport — reaches this
        entry point WITHOUT anyone remembering to add it in a second place.
        That is the whole point: the previous arrangement required remembering,
        and the remembering did not happen.
        """
        from macf.amail.inbound import InboundConfig

        bc = BrokerDeployConfig.model_validate(
            load_declarative_config(self.broker_config_path)).to_broker_config()
        outbound_audit = bc.audit_path
        if self.contacts_path is not None:
            bc.contacts_path = self.contacts_path
        if self.audit_path is not None:
            bc.audit_path = self.audit_path
        return InboundConfig(
            broker_config=bc,
            # Captured BEFORE any inbound override is applied above, so a
            # deployment that splits its logs still files outbound traffic
            # outbound.
            outbound_audit_path=outbound_audit,
            spool_dir=self.spool_dir,
            quarantine_dir=self.quarantine_dir,
            handoff_dir=self.handoff_dir,
            verdict_authority=self.verdict_authority,
            push_wake_enabled=self.push_wake_enabled,
        )
