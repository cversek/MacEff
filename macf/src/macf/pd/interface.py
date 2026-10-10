"""The primal daemon's interface: what step 1 and every later step build against.

PROPOSED, for the head maintainer to accept, change or redraw (MIS-0002 section 12,
step 1). Nothing here runs a daemon. It fixes four contracts, so that the outside
watch, the container rendering, the channel and the macOS rendering can be built in
parallel with the daemon itself instead of guessing at it:

  1. **Names and paths.** One function names every surface of an agent's primal daemon
     (systemd unit, launchd label, sockets, record), from the identity file's calling
     card through ``session_identifier``, which already maps a card to a name systemd
     and tmux both accept (MIS-0002-R06 (pd_identifiers_MUST_use_maceff_pd)).
  2. **The declaration.** What an agent declares about its managed units and schedules
     (MIS-0002-R08 (unit_MUST_be_declared), MIS-0002-R09
     (declaration_MUST_state_unit_fields)), validated closed: an unknown key is refused.
  3. **The events.** Liveness, unit state and control acts, all in the agent's own event
     log, with no second store (MIS-0002-R16 (layer_MUST-NOT_keep_second_ledger)).
  4. **The sockets.** A control socket, request and response; a channel socket, a stream
     of closed notice records; and the record a peer checks the daemon against.

Process start times are ``macf.notify.session.proc_start`` strings everywhere, the form
the client itself stores, compared through ``verify_incarnation``. One representation,
so a liveness probe, the channel's peer check and the readout agree.
"""
import os
from pathlib import Path
from typing import Annotated, Dict, List, Literal, Optional, Union, get_args

from pydantic import BaseModel, ConfigDict, Field, TypeAdapter, model_validator

from macf.amail.broker import SUN_PATH_MAX
from macf.utils.identity import session_identifier

#: MIS-0002-R06: every process, unit, label and socket name of a primal daemon carries it.
PD_IDENTIFIER = "maceff_pd"

#: The declaration format this module reads. A daemon refuses a declaration whose
#: version it does not know, rather than guessing at fields it has never seen.
DECLARATION_VERSION = 1

#: MIS-0002-R20 (unit_MUST_have_listed_state), in the order a unit moves through them.
State = Literal["declared", "starting", "running", "waiting_on_a_person", "failed", "stopped"]
UNIT_STATES = get_args(State)


# ============================================================================
# 1. Names and paths
# ============================================================================

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
    """Where the daemon's sockets and record live: per user, mode 0700, never shared."""
    base = os.environ.get("XDG_RUNTIME_DIR")
    if base:
        return Path(base) / PD_IDENTIFIER
    return Path(f"/tmp/{PD_IDENTIFIER}-{os.getuid()}")


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
    return agent_home / ".maceff" / "pd" / "declaration.json"


# ============================================================================
# 2. The declaration
# ============================================================================

class _Closed(BaseModel):
    model_config = ConfigDict(extra="forbid")


class ExitCodes(_Closed):
    """A unit's exit-code contract (R09): which codes mean done and which mean
    "do not restart me", the field's convention for a unit that knows it cannot recover."""

    success: List[int] = Field(default_factory=lambda: [0])
    no_restart: List[int] = Field(default_factory=lambda: [78])


class Unit(_Closed):
    """One managed unit (MIS-0002-R09, MIS-0002-R59 (unit_MUST_declare_memory_limit),
    MIS-0002-R63 (unit_MUST_declare_privacy_grants)).

    ``account`` must be the daemon's own user in step 1. Starting a unit as another
    account needs a privilege the daemon does not hold, and taking it from a file the
    agent writes would let an agent widen its own reach
    (MIS-0002-R78 (layer_MUST-NOT_widen_permissions)); see the open questions.
    """

    name: str = Field(pattern=r"^[a-z][a-z0-9_-]{0,47}$")
    command: List[str] = Field(min_length=1)
    account: str = Field(min_length=1)
    restart: Literal["always", "on-failure", "never"]
    exit_codes: ExitCodes = Field(default_factory=ExitCodes)
    liveness_interval_s: float = Field(gt=0)
    memory_limit_mb: int = Field(gt=0)
    environment: Dict[str, str] = Field(default_factory=dict)
    optional: bool = False
    privacy_grants: List[str] = Field(default_factory=list)


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


class Schedule(_Closed):
    """A schedule, for step 2 (MIS-0002-R24, MIS-0002-R29 (schedule_MUST_declare_target)).
    Declared now so the format does not change under the steps that come later."""

    name: str = Field(pattern=r"^[a-z][a-z0-9_-]{0,47}$")
    cron: str = Field(min_length=1)
    missed_run: MissedRunPolicy
    target: Union[Literal["isolated"], str]
    prompt_file: str = Field(min_length=1)


class Declaration(_Closed):
    """Everything an agent declares to its primal daemon. Audited by reading it.

    ``operator_channels`` are the channel names whose events count as the operator's
    activity; every other name counts as not the operator
    (MIS-0002-R107 (hooks_MUST_tell_channels_apart_by_name)).
    """

    version: Literal[1]
    agent: str = Field(min_length=1)
    units: List[Unit] = Field(default_factory=list)
    schedules: List[Schedule] = Field(default_factory=list)
    operator_channels: List[str] = Field(default_factory=list)
    quiet_windows: List[Window] = Field(default_factory=list)

    @model_validator(mode="after")
    def _names_unique(self) -> "Declaration":
        names = [u.name for u in self.units] + [s.name for s in self.schedules]
        dupes = sorted({n for n in names if names.count(n) > 1})
        if dupes:
            raise ValueError(f"names declared more than once: {', '.join(dupes)}")
        return self


# ============================================================================
# 3. The events (all appended to the agent's own event log)
# ============================================================================

#: Event names. Data models below; each is the ``data`` of an ``append_event`` call.
EVENT_LIVENESS = "pd_unit_alive"
EVENT_STATE = "pd_unit_state"
EVENT_CONTROL = "pd_control"


class Liveness(_Closed):
    """MIS-0002-R14 (unit_MUST_emit_liveness_events), written by the unit itself at its
    declared interval: the unit's own loop ran, which a process that merely exists does
    not show. ``pid`` and ``proc_start`` let the readout confirm the writer is still that
    unit before calling it alive (MIS-0002-R15 (readout_MUST_probe_liveness))."""

    agent: str
    unit: str
    pid: int = Field(gt=1)
    proc_start: str = Field(min_length=1)
    interval_s: float = Field(gt=0)


class UnitState(_Closed):
    """A unit entering one of the states of MIS-0002-R20, written by the daemon."""

    agent: str
    unit: str
    state: State
    pid: Optional[int] = None
    proc_start: Optional[str] = None
    reason: str = ""


class Asker(_Closed):
    """Who asked for a control act (MIS-0002-R52 (control_act_MUST_name_who_asked)).

    ``harness`` is for a compaction nobody asked for, found by the absence of an ask
    (MIS-0002-R127 (harness_compaction_MUST_be_recorded)); ``policy`` for the daemon's
    own restart policy acting on a failed unit.
    """

    kind: Literal["operator", "wind_down", "policy", "harness"]
    card: Optional[str] = None


class Control(_Closed):
    """A stop, start, restart or compaction the daemon performed, written by the daemon."""

    agent: str
    act: Literal["start", "stop", "restart", "compact"]
    unit: str
    asked_by: Asker
    reason: str = Field(min_length=1)


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
    """A compaction: only the operator or the agent's declared wind-down may ask
    (MIS-0002-R108 (compaction_MUST_be_asked_by_operator_or_wind-down))."""

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
