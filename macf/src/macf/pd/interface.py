"""The primal daemon's interface: what step 1 and every later step build against.

Accepted by both maintainers as step 1's interface on #555, revised with their changes
(MIS-0002 section 12, step 1). Nothing here runs a daemon. It fixes the contracts that
the outside watch, the outer tiers, the container rendering, the channel and the macOS
rendering build on, in parallel with the daemon itself:

  1. **Identity, names and paths.** The card comes from an explicitly named agent home,
     never from the environment (MIS-0002-R02 (pd_MUST-NOT_take_identity_from_env)), and
     one function names every surface from it through ``session_identifier``
     (MIS-0002-R06 (pd_identifiers_MUST_use_maceff_pd)).
  2. **The declaration.** What an agent declares about its managed units, schedules,
     notices and wind-down (MIS-0002-R08 (unit_MUST_be_declared), MIS-0002-R09
     (declaration_MUST_state_unit_fields)), validated closed: an unknown key is refused.
  3. **The events.** Liveness, unit state and control acts, all in the agent's own event
     log, with no second store (MIS-0002-R16 (layer_MUST-NOT_keep_second_ledger)).
  4. **The sockets.** A control socket, request and response; a channel socket, a stream
     of closed notice records; and the record a peer checks the daemon against.

Process start times are ``macf.notify.session.proc_start`` strings everywhere, the form
the client itself stores, compared through ``verify_incarnation``.
"""
import json
import os
import re
import stat
from pathlib import Path
from typing import Annotated, Dict, List, Literal, Optional, Union, get_args
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from pydantic import BaseModel, ConfigDict, Field, TypeAdapter, field_validator, model_validator

from macf.amail.broker import SUN_PATH_MAX
from macf.utils.identity import session_identifier

#: MIS-0002-R06: every process, unit, label and socket name of a primal daemon carries it.
PD_IDENTIFIER = "maceff_pd"

#: The declaration format this module reads. A daemon refuses a version it does not know.
DECLARATION_VERSION = 1

#: MIS-0002-R20 (unit_MUST_have_listed_state), in the order a unit moves through them.
State = Literal["declared", "starting", "running", "waiting_on_a_person", "failed", "stopped"]
UNIT_STATES = get_args(State)

#: The placeholders the daemon fills in when it renders a unit's command and environment
#: at start (MIS-0002-R13 (pd_MUST_render_env_at_start)). The same agent has a different
#: home on a host and in a container, so a declaration names it this way, never as a path.
PLACEHOLDERS = ("agent_home", "card", "runtime_dir")
_PLACEHOLDER = re.compile(r"\{([A-Za-z_][A-Za-z0-9_]*)\}")

#: macOS privacy grants a unit may declare (MIS-0002-R63 (unit_MUST_declare_privacy_grants)).
#: Closed, so a misspelling fails when the declaration is read, not as a missing grant later.
PRIVACY_GRANTS = ("local_network", "accessibility", "full_disk_access", "keychain")
_AUTOMATION_GRANT = re.compile(r"^automation:[A-Za-z0-9][A-Za-z0-9.-]*$")


class IdentityError(ValueError):
    """The agent home does not name an agent. The daemon refuses to start."""


# ============================================================================
# 1. Identity, names and paths
# ============================================================================

def agent_card(agent_home: Path) -> str:
    """The calling card of the agent whose home is *agent_home*, read only from that home.

    The name is ``agent_identity.calling_card`` (or ``moniker``) in
    ``<home>/.maceff/config.json``, and the suffix is the first six characters of
    ``<home>/.maceff_primary_agent.id``. No environment variable, no working directory,
    no fallback: ``get_agent_identity()`` reads ``MACEFF_AGENT_NAME`` first for a
    host-global agent, so a session and a daemon started by the outer tier, which has no
    such variable, could name different sockets for the same agent (MIS-0002-R02).
    """
    home = Path(agent_home)
    try:
        config = json.loads((home / ".maceff" / "config.json").read_text())
        uuid = (home / ".maceff_primary_agent.id").read_text().strip()
    except (OSError, ValueError) as e:
        raise IdentityError(f"{home} names no agent: {e}") from e
    identity = config.get("agent_identity") or {}
    name = next((identity[k].strip() for k in ("calling_card", "moniker")
                 if isinstance(identity.get(k), str) and identity[k].strip()), "")
    if not name or len(uuid) < 6:
        raise IdentityError(f"{home} names no agent: config.json needs agent_identity.calling_card "
                            f"and .maceff_primary_agent.id a UUID")
    return f"{name}@{uuid[:6]}"


def pd_id(card: str) -> str:
    """The per-agent part of every name: ``TheHarborMaster@ee5cd8`` -> ``TheHarborMaster_ee5cd8``.

    Several agents can share one login user, so every name carries the agent; and the
    card's ``@`` is substituted because systemd spells a template instance that way.
    """
    return session_identifier(card)


def systemd_unit(card: str) -> str:
    """The outer tier's unit on Linux: ``maceff_pd-<id>.service``."""
    return f"{PD_IDENTIFIER}-{pd_id(card)}.service"


def launchd_label(card: str) -> str:
    """The outer tier's label on macOS (MIS-0002-R05): ``maceff_pd.<id>``."""
    return f"{PD_IDENTIFIER}.{pd_id(card)}"


def runtime_dir() -> Path:
    """Where the daemon's sockets and record live: per user, never shared."""
    base = os.environ.get("XDG_RUNTIME_DIR")
    if base:
        return Path(base) / PD_IDENTIFIER
    return Path(f"/tmp/{PD_IDENTIFIER}-{os.getuid()}")


def ensure_runtime_dir(path: Optional[Path] = None) -> Path:
    """Create the runtime directory with mode 0700, or refuse an existing one that is not
    private: owned by another user, or open to its group or to others.

    Without ``XDG_RUNTIME_DIR`` the directory is in ``/tmp``, where anyone could have made
    it first, so this check is the difference between private and guessable.
    """
    path = path or runtime_dir()
    try:
        path.mkdir(mode=0o700, parents=False)
    except FileExistsError:
        pass
    info = path.lstat()
    if not stat.S_ISDIR(info.st_mode):
        raise OSError(f"{path} is not a directory; refusing it as the runtime directory")
    if info.st_uid != os.getuid():
        raise OSError(f"{path} is owned by uid {info.st_uid}, not this user; refusing it")
    if info.st_mode & 0o077:
        raise OSError(f"{path} is open to its group or others (mode {oct(info.st_mode & 0o777)}); refusing it")
    return path


def control_socket(card: str, base: Optional[Path] = None) -> Path:
    return (base or runtime_dir()) / f"{pd_id(card)}.control.sock"


def channel_socket(card: str, base: Optional[Path] = None) -> Path:
    return (base or runtime_dir()) / f"{pd_id(card)}.channel.sock"


def record_path(card: str, base: Optional[Path] = None) -> Path:
    return (base or runtime_dir()) / f"{pd_id(card)}.json"


def check_socket_path(path: Path) -> None:
    """MIS-0002-R129 (adapter_MUST_check_socket_path_length): refuse, with the reason,
    a path the kernel would refuse with a bare error."""
    if len(str(path).encode()) > SUN_PATH_MAX:
        raise OSError(f"socket path {path} is longer than {SUN_PATH_MAX} bytes; "
                      f"use a shorter runtime directory")


def declaration_path(agent_home: Path) -> Path:
    """The agent's declaration, in its own home: the outer tier holds none
    (MIS-0002-R04 (outer_tier_MUST-NOT_hold_agent_config))."""
    return Path(agent_home) / ".maceff" / "pd" / "declaration.json"


def render(value: str, context: Dict[str, str]) -> str:
    """Fill a declared value's placeholders from the daemon's own context at start."""
    return _PLACEHOLDER.sub(lambda m: context[m.group(1)], value)


# ============================================================================
# 2. The declaration
# ============================================================================

class _Closed(BaseModel):
    model_config = ConfigDict(extra="forbid")


def _known_placeholders(values: List[str]) -> List[str]:
    unknown = sorted({m for v in values for m in _PLACEHOLDER.findall(v) if m not in PLACEHOLDERS})
    if unknown:
        raise ValueError(f"unknown placeholder(s) {', '.join('{' + u + '}' for u in unknown)}; "
                         f"the daemon fills in only {', '.join('{' + p + '}' for p in PLACEHOLDERS)}")
    return values


class ExitCodes(_Closed):
    """A unit's exit-code contract (R09): which codes mean done and which mean
    "do not restart me", the field's convention for a unit that knows it cannot recover."""

    success: List[int] = Field(default_factory=lambda: [0])
    no_restart: List[int] = Field(default_factory=lambda: [78])


class Unit(_Closed):
    """One managed unit (MIS-0002-R09, MIS-0002-R59 (unit_MUST_declare_memory_limit),
    MIS-0002-R63).

    ``account`` must be the daemon's own user in step 1. Running a unit as another account
    widens what the layer may do (MIS-0002-R78 (layer_MUST-NOT_widen_permissions)), and
    that is the operator's decision. ``kind`` names the session unit, the one a quiet
    window, a compaction and the waiting-on-a-person inference apply to; at most one per
    declaration. ``stop_grace_s`` is how long a stop waits between SIGTERM and SIGKILL.
    """

    name: str = Field(pattern=r"^[a-z][a-z0-9_-]{0,47}$")
    kind: Literal["session", "service"] = "service"
    command: List[str] = Field(min_length=1)
    account: str = Field(min_length=1)
    restart: Literal["always", "on-failure", "never"]
    exit_codes: ExitCodes = Field(default_factory=ExitCodes)
    liveness_interval_s: float = Field(gt=0)
    memory_limit_mb: int = Field(gt=0)
    stop_grace_s: float = Field(default=10.0, gt=0)
    environment: Dict[str, str] = Field(default_factory=dict)
    optional: bool = False
    privacy_grants: List[str] = Field(default_factory=list)

    @field_validator("command")
    @classmethod
    def _command_placeholders(cls, v: List[str]) -> List[str]:
        return _known_placeholders(v)

    @field_validator("environment")
    @classmethod
    def _environment_placeholders(cls, v: Dict[str, str]) -> Dict[str, str]:
        _known_placeholders(list(v.values()))
        return v

    @field_validator("privacy_grants")
    @classmethod
    def _grants_known(cls, v: List[str]) -> List[str]:
        bad = [g for g in v if g not in PRIVACY_GRANTS and not _AUTOMATION_GRANT.match(g)]
        if bad:
            raise ValueError(f"unknown privacy grant(s) {bad}; known: {', '.join(PRIVACY_GRANTS)}, "
                             f"automation:<bundle id>")
        return v


class Window(_Closed):
    start: str = Field(pattern=r"^\d{2}:\d{2}$")
    end: str = Field(pattern=r"^\d{2}:\d{2}$")


class MissedRunPolicy(_Closed):
    """MIS-0002-R25 (missed-run_policy_MUST_be_listed). No default: a schedule without one
    is refused (MIS-0002-R109 (CI_MUST_fail_schedule_without_policy))."""

    kind: Literal["skip", "run_once", "run_once_in_window", "report_only"]
    window: Optional[Window] = None

    @model_validator(mode="after")
    def _window_iff_windowed(self) -> "MissedRunPolicy":
        if (self.kind == "run_once_in_window") != (self.window is not None):
            raise ValueError("a window is given exactly when the policy is run_once_in_window")
        return self


class PromptRun(_Closed):
    """A run that needs a model turn. ``allowed_tools`` are settled when the schedule is
    created and rendered into the isolated session's settings, so a run that meets a
    prompt fails instead of waiting (MIS-0002-R31 (schedule_MUST_settle_permission_at_creation),
    MIS-0002-R32 (run_MUST_fail_on_prompt))."""

    prompt_file: str = Field(min_length=1)
    allowed_tools: List[str] = Field(default_factory=list)


class CommandRun(_Closed):
    """A run that needs no judgment: a command, waking the agent only when its declared
    condition holds (MIS-0002-R37 (no-judgment_work_SHOULD_skip_model_turn))."""

    command: List[str] = Field(min_length=1)
    wake_when: Literal["exit_code", "stdout"]

    @field_validator("command")
    @classmethod
    def _command_placeholders(cls, v: List[str]) -> List[str]:
        return _known_placeholders(v)


class Schedule(_Closed):
    """A schedule, for step 2 (MIS-0002-R24, MIS-0002-R29 (schedule_MUST_declare_target)).
    Declared now so the format does not change under the steps that come later.
    ``timeout_s`` is required (MIS-0002-R36 (run_MUST_have_wall-clock_limit)). ``restarts_unit``
    marks a schedule whose act restarts a unit, a run a downtime never replays
    (MIS-0002-R27 (scheduler_MUST-NOT_replay_restart_runs))."""

    name: str = Field(pattern=r"^[a-z][a-z0-9_-]{0,47}$")
    cron: str = Field(min_length=1)
    missed_run: MissedRunPolicy
    target: Union[Literal["isolated"], str]
    run: Union[PromptRun, CommandRun]
    timeout_s: float = Field(gt=0)
    restarts_unit: bool = False


class WindDown(_Closed):
    """The agent's declared wind-down: the only party besides the operator that may ask
    for a compaction (MIS-0002-R108 (compaction_MUST_be_asked_by_operator_or_wind-down)).
    It asks through the control socket, with ``asked_by.kind`` ``wind_down``."""

    skill: str = Field(min_length=1)
    asks_by: Literal["control_socket"] = "control_socket"


NoticeRoute = Literal["agent", "operator", "both", "held_until_present"]


class Declaration(_Closed):
    """Everything an agent declares to its primal daemon. Audited by reading it.

    - ``operator_channels``: the channel names whose events count as the operator's
      activity; every other name counts as not the operator
      (MIS-0002-R107 (hooks_MUST_tell_channels_apart_by_name)). Absent means not yet
      declared, and an empty list declares that no channel is the operator's: a default
      here would decide for a deployment whether its operator's phone counts.
    - ``notice_routes``: per notice source, who must hear it
      (MIS-0002-R42 (notice_source_MUST_be_routed)).
    - ``keep_harness_idle_compaction``: the harness's own idle compaction stays off unless
      this keeps it (MIS-0002-R126 (adapter_MUST_turn_off_harness_idle_compaction)).
    - ``wind_down``: absent means no wind-down, so only the operator may ask to compact.
    - ``timezone``: the IANA name crons and quiet windows are read in, required once any
      schedule or quiet window is declared, because a host reads a bare time of day in its
      local time and a container usually in UTC, so the same declaration would act at
      different moments.
    """

    version: Literal[1]
    agent: str = Field(min_length=1)
    units: List[Unit] = Field(default_factory=list)
    schedules: List[Schedule] = Field(default_factory=list)
    operator_channels: Optional[List[str]] = None
    notice_routes: Dict[str, NoticeRoute] = Field(default_factory=dict)
    quiet_windows: List[Window] = Field(default_factory=list)
    keep_harness_idle_compaction: bool = False
    wind_down: Optional[WindDown] = None
    timezone: Optional[str] = None

    @model_validator(mode="after")
    def _names_unique(self) -> "Declaration":
        names = [u.name for u in self.units] + [s.name for s in self.schedules]
        dupes = sorted({n for n in names if names.count(n) > 1})
        if dupes:
            raise ValueError(f"names declared more than once: {', '.join(dupes)}")
        if sum(u.kind == "session" for u in self.units) > 1:
            raise ValueError("at most one unit may be the session")
        return self

    @model_validator(mode="after")
    def _crons_and_windows_name_their_timezone(self) -> "Declaration":
        if (self.schedules or self.quiet_windows) and not self.timezone:
            raise ValueError("a declaration with schedules or quiet windows names the timezone "
                             "its crons and windows are read in, as an IANA name such as 'UTC' "
                             "or 'America/New_York'")
        if self.timezone:
            try:
                ZoneInfo(self.timezone)
            except (ZoneInfoNotFoundError, ValueError, OSError) as e:
                # Where zones come from the tzdata package, a name that is one of its
                # directories, such as 'America', is opened as a file and raises OSError.
                raise ValueError(f"unknown timezone {self.timezone!r}: {e}") from e
        return self


# ============================================================================
# 3. The events (all appended to the agent's own event log)
# ============================================================================

#: Event names. Data models below; each is the ``data`` of an ``append_event`` call.
EVENT_LIVENESS = "pd_unit_alive"
EVENT_STATE = "pd_unit_state"
EVENT_CONTROL = "pd_control"
EVENT_DAEMON_START = "pd_daemon_start"


class Liveness(_Closed):
    """MIS-0002-R14 (unit_MUST_emit_liveness_events), written by the unit itself at its
    declared interval: the unit's own loop ran, which a process that merely exists does
    not show. ``pid`` and ``proc_start`` let the readout confirm the writer is still that
    unit before calling it alive (MIS-0002-R15 (readout_MUST_probe_liveness)).

    - ``in_flight``: work the unit has started and not finished, which the daemon checks
      before any restart (MIS-0002-R49 (pd_MUST_check_work_in_flight)). ``None`` means
      not reported; the daemon then takes the unit as idle and records that it assumed so.
    - ``waiting_on``: what the unit waits on a person for, if anything
      (MIS-0002-R21 (pd_MUST_report_waiting_on_person)); the daemon never restarts it for
      that (MIS-0002-R22 (layer_MUST-NOT_restart_waiting_unit)).
    """

    agent: str
    unit: str
    pid: int = Field(gt=1)
    proc_start: str = Field(min_length=1)
    interval_s: float = Field(gt=0)
    in_flight: Optional[int] = Field(default=None, ge=0)
    waiting_on: Optional[str] = Field(default=None, max_length=200)


class UnitState(_Closed):
    """A unit entering one of the states of MIS-0002-R20, written by the daemon."""

    agent: str
    unit: str
    state: State
    pid: Optional[int] = None
    proc_start: Optional[str] = None
    reason: str = ""


class Asker(_Closed):
    """Who asked for a control act, as the asker claimed it
    (MIS-0002-R52 (control_act_MUST_name_who_asked)).

    ``harness`` is for a compaction nobody asked for, found by the absence of an ask
    (MIS-0002-R127 (harness_compaction_MUST_be_recorded)); ``policy`` for the daemon's
    own restart policy acting on a failed unit.
    """

    kind: Literal["operator", "wind_down", "policy", "harness"]
    card: Optional[str] = None


class Peer(_Closed):
    """What the kernel proved about the process that asked: its user, its pid, and that
    pid's start time. Recorded beside the claimed ``Asker``, which it does not confirm."""

    uid: int = Field(ge=0)
    pid: int = Field(gt=0)
    proc_start: str = Field(min_length=1)


class Control(_Closed):
    """A stop, start, restart or compaction the daemon performed, written by the daemon.

    ``peer`` is absent only for acts with no requesting process: the daemon's own policy,
    and a harness compaction, where the event the harness detector wrote is the
    observation and this record is the decision.
    """

    agent: str
    act: Literal["start", "stop", "restart", "compact"]
    unit: str
    asked_by: Asker
    peer: Optional[Peer] = None
    reason: str = Field(min_length=1)

    @model_validator(mode="after")
    def _peer_iff_requested(self) -> "Control":
        requested = self.asked_by.kind in ("operator", "wind_down")
        if requested != (self.peer is not None):
            raise ValueError("an act asked for over the control socket records its peer, "
                             "and only such an act does")
        return self


class DaemonStart(_Closed):
    """A daemon's life began, written once by the daemon itself, with the fields of its
    record: after its sockets are bound and the record is written, and before it adopts or
    starts any unit. A second daemon refused for the agent never writes one
    (MIS-0002-R01 (agent_MUST_have_one_primal_daemon)).

    What a daemon observes outside its own units, such as a surface's state, is good only
    for that daemon's life, so a fold of those observations starts from the newest of
    these. Unit state is not reset by it: a restarted daemon reads its units' last states
    to adopt the ones still running.
    """

    agent: str
    pid: int = Field(gt=1)
    proc_start: str = Field(min_length=1)
    version: Literal[1] = 1


# ============================================================================
# 4. The sockets
# ============================================================================
#
# Two sockets, so that each carries one shape and has one peer rule:
#
#   control  request and response, one JSON object per line each way. The peer must be
#            the daemon's own user. The operator's command line and the tray connect here
#            (MIS-0002-R48 (outside_stop_MUST_override_gates), MIS-0002-R70
#            (tray_MUST_act_through_pd)).
#   channel  the daemon writes closed notice records, one per line, and reads nothing.
#            The peer must descend from the agent's live session
#            (MIS-0002-R122 (pd_MUST_check_channel_peer_lineage)). The record shape is the
#            channel's own (``macf.channels.maceff_channel.NoticeRecord``, #545).
#
# The daemon writes its record (pid and start time) after binding both, and a client
# checks the peer against it (MIS-0002-R123 (channel_MUST_check_its_peer_is_its_pd)).


class DaemonRecord(_Closed):
    """What the daemon publishes beside its sockets, written atomically after binding."""

    pid: int = Field(gt=1)
    proc_start: str = Field(min_length=1)
    version: Literal[1] = 1


class StatusRequest(_Closed):
    op: Literal["status"]


class ActRequest(_Closed):
    """Start, stop or restart one unit. A stop from outside a session succeeds whatever
    gate the session enforces (MIS-0002-R48)."""

    op: Literal["start", "stop", "restart"]
    unit: str
    asked_by: Asker
    reason: str = Field(min_length=1)


class CompactRequest(_Closed):
    """A compaction: only the operator or the agent's declared wind-down may ask (R108)."""

    op: Literal["compact"]
    asked_by: Asker
    reason: str = Field(min_length=1)

    @model_validator(mode="after")
    def _only_operator_or_wind_down(self) -> "CompactRequest":
        if self.asked_by.kind not in ("operator", "wind_down"):
            raise ValueError("only the operator or the agent's declared wind-down may ask for a compaction")
        return self


Request = Union[StatusRequest, ActRequest, CompactRequest]


class UnitStatus(_Closed):
    unit: str
    state: State
    pid: Optional[int] = None
    proc_start: Optional[str] = None
    since: float


class Response(_Closed):
    ok: bool
    error: Optional[str] = None
    units: Optional[List[UnitStatus]] = None


_REQUEST = TypeAdapter(Annotated[Request, Field(discriminator="op")])


def parse_request(line: str) -> Request:
    """One control request from one line, refused whole if any part of it is unknown.

    Raises ``pydantic.ValidationError``; the daemon answers ``Response(ok=False)`` with
    the reason and acts on nothing.
    """
    return _REQUEST.validate_json(line)
