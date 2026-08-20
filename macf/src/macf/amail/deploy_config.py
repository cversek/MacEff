"""Declarative deployment configuration for the amail broker daemon.

A deployment describes the broker in a root-owned JSON file; the daemon entry
point loads it through these models. Pydantic is the framework convention for
declarative config (the agents.yaml account model set the precedent), and it
buys the property a hand-rolled ``raw["key"]`` parser cannot offer honestly:
**a misspelled or unknown key refuses to start** (``extra="forbid"``) instead
of being ignored — an ignored key in a security config silently changes what
the broker enforces, which is the config-file form of a silent failure.

The file is deliberately separate from :class:`~macf.amail.broker.BrokerConfig`:
that dataclass is the broker's in-memory shape; this is the on-disk contract a
deployment writes, validated at the trust boundary where operator-authored
JSON becomes broker authority.
"""
from pathlib import Path
from typing import Dict, Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator

from macf.amail.broker import BrokerConfig


class AgentBinding(BaseModel):
    """One local agent: its address local-part maps to a home and a uid.

    The agent NAME (the mapping key in :class:`BrokerDeployConfig.agents`) is
    the address local-part; the unix account may be named differently — the
    home path and uid are what bind them.
    """

    model_config = ConfigDict(extra="forbid")

    home: Path = Field(description="the agent's home directory (its mail store lives here)")
    uid: int = Field(
        description="the agent's unix uid. THE authentication table entry: "
                    "the kernel's view of who is on the socket is the fact; "
                    "a submitted sender field is only a claim.")


class BrokerDeployConfig(BaseModel):
    """The on-disk broker daemon configuration (``broker_config.json``).

    Must be root-owned and read-only to the broker uid: the broker must not be
    able to rewrite its own authority.
    """

    model_config = ConfigDict(extra="forbid")

    domain: str = Field(description="the address domain this broker owns")
    agents: Dict[str, AgentBinding] = Field(
        description="agent name (address local-part) -> home + uid")
    contacts_path: Optional[Path] = Field(
        default=None, description="outbound allowlist, re-read on every decision")
    audit_path: Optional[Path] = Field(
        default=None, description="broker-owned audit log (jsonl)")
    socket_path: Path = Field(
        default=Path("/run/amail/broker.sock"),
        description="the submission socket the broker binds")
    credentials_path: Optional[Path] = Field(
        default=None,
        description="smarthost credential; null until the outbound leg exists. "
                    "When set: 0600, owned by the broker uid — serve() refuses "
                    "to start otherwise.")
    inbound_quarantine: Optional[Path] = Field(
        default=None, description="broker-owned quarantine for refused internet mail")
    inbound_handoff: Optional[Path] = Field(
        default=None,
        description="pickup boxes: handoff/<agent>/ owned by the broker, "
                    "group = the recipient's group; the recipient ingests as itself")
    dispositions_dir: Optional[Path] = Field(
        default=None,
        description="broker-owned, agent-READABLE records of what became of "
                    "each submitted message. Without it a sender holds a copy "
                    "of what it sent and cannot learn whether it left, which "
                    "is the outbound face of a silent drop.")
    rate_limit_dir: Optional[Path] = Field(
        default=None,
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

    @field_validator("agents")
    @classmethod
    def _agents_nonempty_and_uids_unique(cls, v: Dict[str, AgentBinding]):
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

    def to_broker_config(self) -> BrokerConfig:
        """The in-memory shape the broker actually runs on.

        EVERY FIELD ABOVE MUST APPEAR BELOW. A field declared in the on-disk
        contract and dropped here is worse than an absent one: the operator
        writes it, the config validates, the broker starts, and the setting
        does nothing — a silent partial with the shape of a complete one. The
        test suite asserts the two sides agree rather than trusting this note.
        """
        return BrokerConfig(
            domain=self.domain,
            agent_homes={name: b.home for name, b in self.agents.items()},
            contacts_path=self.contacts_path,
            audit_path=self.audit_path,
            socket_path=self.socket_path,
            credentials_path=self.credentials_path,
            inbound_quarantine=self.inbound_quarantine,
            inbound_handoff=self.inbound_handoff,
            dispositions_dir=self.dispositions_dir,
            rate_limiter=self._build_rate_limiter(),
            transport=self._build_transport(),
            opsec_scan=self._build_scan() if self.opsec_scan else None,
            refuse_unscanned=self.refuse_unscanned,
            agent_uids={b.uid: name for name, b in self.agents.items()},
        )

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

    def _build_rate_limiter(self):
        """The limiter, or None when the deployment declares no budget.

        Requires BOTH a state directory and at least one cap. A cap with
        nowhere to record consumption cannot enforce anything, and a directory
        with no cap enforces nothing -- either alone would produce a limiter
        that looks configured and permits everything, which is worse than an
        absent one because submit() would stop announcing it.
        """
        if not self.rate_limit_dir:
            return None
        limits = {}
        if self.rate_limit_per_agent:
            from macf.amail.ratelimit import RateLimit
            for name in self.agents:
                limits[name] = RateLimit(self.rate_limit_per_agent,
                                         self.rate_limit_window_seconds)
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
