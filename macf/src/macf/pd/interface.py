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
import re
from pathlib import Path
from typing import Annotated, Any, Dict, List, Literal, Optional, Union, get_args
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from pydantic import BaseModel, ConfigDict, Field, TypeAdapter, field_validator, model_validator

from macf.pd.names import (  # re-exported: interface's callers import these from here
    PD_IDENTIFIER,
    IdentityError,
    agent_card,
    channel_socket,
    control_socket,
    declaration_path,
    ensure_runtime_dir,
    events_socket,
    launchd_label,
    pd_id,
    record_path,
    runtime_dir,
    systemd_unit,
)
from macf.utils.peercred import SUN_PATH_MAX


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


# ============================================================================
# 1. Identity, names and paths: in ``macf.pd.names``, re-exported above
# ============================================================================

def check_socket_path(path: Path) -> None:
    """MIS-0002-R129 (adapter_MUST_check_socket_path_length): refuse, with the reason,
    a path the kernel would refuse with a bare error."""
    if len(str(path).encode()) > SUN_PATH_MAX:
        raise OSError(f"socket path {path} is longer than {SUN_PATH_MAX} bytes; "
                      f"use a shorter runtime directory")


def render(value: str, context: Dict[str, str]) -> str:
    """Fill a declared value's placeholders from the daemon's own context at start."""
    return _PLACEHOLDER.sub(lambda m: context[m.group(1)], value)


# ============================================================================
# 2. The declaration
# ============================================================================

class _Closed(BaseModel):
    model_config = ConfigDict(extra="forbid")


_ENV_NAME = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")


def _usable_environment(env: Dict[str, str]) -> Dict[str, str]:
    """A declared environment whose names a process can carry, and whose values name only
    placeholders the daemon fills. An empty name, or one with ``=`` in it, would load and
    then fail every start, so it is refused where it is written."""
    bad = sorted(k for k in env if not _ENV_NAME.match(k))
    if bad:
        raise ValueError(f"environment names must match {_ENV_NAME.pattern}: {', '.join(repr(k) for k in bad)}")
    _known_placeholders(list(env.values()))
    return env


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
        return _usable_environment(v)

    @model_validator(mode="after")
    def _liveness_names_this_unit(self) -> "Unit":
        # The daemon sets both from the unit itself (persistent_layer 11.2); a declaration may
        # still state them, but never different, or the unit would beat as another or late.
        env = self.environment
        if "MACF_PD_UNIT" in env and env["MACF_PD_UNIT"] != self.name:
            raise ValueError(f"unit {self.name}: MACF_PD_UNIT is {env['MACF_PD_UNIT']!r}; the daemon "
                             f"sets it to the unit's name, so leave it out")
        if "MACF_PD_LIVENESS_S" in env:
            try:
                same = float(env["MACF_PD_LIVENESS_S"]) == self.liveness_interval_s
            except ValueError:
                same = False
            if not same:
                raise ValueError(f"unit {self.name}: MACF_PD_LIVENESS_S is {env['MACF_PD_LIVENESS_S']!r}, "
                                 f"not its liveness_interval_s {self.liveness_interval_s:g}; the daemon "
                                 "sets it, so leave it out")
        return self

    @field_validator("privacy_grants")
    @classmethod
    def _grants_known(cls, v: List[str]) -> List[str]:
        bad = [g for g in v if g not in PRIVACY_GRANTS and not _AUTOMATION_GRANT.match(g)]
        if bad:
            raise ValueError(f"unknown privacy grant(s) {bad}; known: {', '.join(PRIVACY_GRANTS)}, "
                             f"automation:<bundle id>")
        return v

    @model_validator(mode="after")
    def _session_restarts_always(self) -> "Unit":
        # The session unit's wrapper exits 0 however the session ends, since it reports its
        # tmux server, not claude: under on-failure or never, an ended session stays down.
        if self.kind == "session" and self.restart != "always":
            raise ValueError(f"unit {self.name!r} is the session unit, whose restart must be 'always', "
                             f"not {self.restart!r}: its wrapper exits 0 however the session ends, "
                             f"so nothing else would bring the session back")
        return self


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
    #: Added to the run's fixed ``PATH`` and ``HOME``, rendered like a unit's environment;
    #: a key declared here overrides those two.
    environment: Dict[str, str] = Field(default_factory=dict)

    @field_validator("command")
    @classmethod
    def _command_placeholders(cls, v: List[str]) -> List[str]:
        return _known_placeholders(v)

    @field_validator("environment")
    @classmethod
    def _environment_placeholders(cls, v: Dict[str, str]) -> Dict[str, str]:
        return _usable_environment(v)


#: An argument slot in a check template: an argv element that is exactly ``<name>``. It's
#: replaced whole by the argument's value, so a value can never become a second argument.
ARG_SLOT = re.compile(r"^<([a-z][a-z0-9_]{0,31})>$")


class CheckArg(_Closed):
    """A check template's argument: an integer, or text that matches ``pattern`` whole."""

    kind: Literal["integer", "pattern"]
    pattern: Optional[str] = None

    @model_validator(mode="after")
    def _pattern_iff_pattern(self) -> "CheckArg":
        if (self.kind == "pattern") != (self.pattern is not None):
            raise ValueError("a pattern is given exactly when the argument's kind is pattern")
        if self.pattern is not None:
            re.compile(self.pattern)
        return self

    def accepts(self, value: str) -> bool:
        if self.kind == "integer":
            return re.fullmatch(r"-?\d{1,18}", value) is not None
        # A run renders its command's placeholders ({agent_home}) after the slots are filled,
        # so a brace in a value would turn a checked value into another (MIS-0002-R143).
        if "{" in value or "}" in value:
            return False
        return re.fullmatch(self.pattern, value) is not None


class CheckTemplate(_Closed):
    """A command the operator declares for agents' ``check`` entries (the scheduler design, 4.2):
    inline argv run with no shell, and typed arguments, each filling one whole argv element. Its
    program may not live in the agent's home, where the agent could rewrite it; the daemon
    refuses one that does. It wakes the agent when its condition holds, as a CommandRun does."""

    command: List[str] = Field(min_length=1)
    args: Dict[str, CheckArg] = Field(default_factory=dict)
    wake_when: Literal["exit_code", "stdout"]
    timeout_s: float = Field(gt=0, le=600)

    @model_validator(mode="after")
    def _slots_match_args(self) -> "CheckTemplate":
        slots = [m.group(1) for m in map(ARG_SLOT.match, self.command) if m]
        if sorted(slots) != sorted(self.args):
            raise ValueError(f"the command's slots {sorted(slots)} and the declared args {sorted(self.args)} differ")
        if ARG_SLOT.match(self.command[0]):
            raise ValueError("the program itself can't be an argument")
        _known_placeholders([a for a in self.command if not ARG_SLOT.match(a)])
        return self

    def argv(self, args: Dict[str, str]) -> List[str]:
        """The command with each slot filled, or ValueError naming what doesn't fit."""
        if sorted(args) != sorted(self.args):
            raise ValueError(f"this template takes {sorted(self.args)}, not {sorted(args)}")
        bad = [k for k, v in args.items() if not self.args[k].accepts(v)]
        if bad:
            raise ValueError(f"not a valid {', '.join(bad)}")
        return [args[m.group(1)] if (m := ARG_SLOT.match(a)) else a for a in self.command]


class Schedule(_Closed):
    """A schedule, for step 2 (MIS-0002-R24, MIS-0002-R29 (schedule_MUST_declare_target)).
    Declared now so the format does not change under the steps that come later. ``target`` is
    ``isolated`` or the declaring agent's own card; the declaration refuses any other card.
    ``timeout_s`` is required (MIS-0002-R36 (run_MUST_have_wall-clock_limit)). ``restarts_unit``
    marks a schedule whose act restarts a unit, a run a downtime never replays
    (MIS-0002-R27 (scheduler_MUST-NOT_replay_restart_runs))."""

    name: str = Field(pattern=r"^[a-z][a-z0-9_-]{0,47}$")
    cron: str = Field(min_length=1)
    missed_run: MissedRunPolicy
    target: Union[Literal["isolated"], Annotated[str, Field(min_length=1)]]
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
#: How a state change for an authentication failure begins its reason (MIS-0002-R19). The
#: session is still running, so a daemon that starts while it reads failed adopts it by this.
AUTH_FAILED_REASON = "authentication failed"
#: The notice source of mail left unread past the declared threshold (MIS-0002-R55).
UNREAD_MAIL_SOURCE = "pd_unread_mail"
#: The notice source of a prompt run that met a permission prompt (MIS-0002-R32).
RUN_FAILED_SOURCE = "pd_run_failed"


class ChannelPlugin(_Closed):
    """A channel plugin as Claude Code's organization allowlist names one: the plugin and the
    marketplace it comes from. The client admits a channel only when both match an entry."""

    plugin: str = Field(min_length=1)
    marketplace: str = Field(min_length=1)

    def __str__(self) -> str:
        return f"{self.plugin}@{self.marketplace}"

#: How long the keystroke wake rests after each wake when the declaration says nothing: the
#: ten minutes the mail clocks learned, which the operator kept as the default on 2026-10-17.
DEFAULT_WAKE_REFRACTORY_S = 600.0
#: The longest window a pace may set, unless the declaration says otherwise: the outside watch's
#: allowance for a held wake (``watch.WAKE_HELD_ALERT_S``), so no pace can keep an agent unwoken
#: past the point where a stuck wake would have reached the operator.
DEFAULT_WAKE_REFRACTORY_CEILING_S = 1800.0


#: A source pattern on the event stream: an event name, with ``*`` and ``?`` globs.
_STREAM_SOURCE = r"^[A-Za-z0-9_*?\[\]-]{1,200}$"
#: A subscriber's name on the event stream, as its hello gives it and a rule names it after ``@``.
STREAM_SUBSCRIBER_NAME = r"^[a-z][a-z0-9_-]{0,47}$"


class StreamGrant(_Closed):
    """A uid other than the agent's own that may subscribe to its event stream, and the sources
    it may take (MIS-0002-R156 (subscriber_MUST_be_granted_agents); persistent_layer 11.4). Least
    privilege: a tray or a host-wide watch is granted unit states and notices, not tool events."""

    uid: int = Field(ge=0)
    sources: List[Annotated[str, Field(pattern=_STREAM_SOURCE)]] = Field(min_length=1)


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
    - ``allowlisted_channels``: every channel plugin the deployment's organization allowlist
      admits, the operator's channels included
      (MIS-0002-R124 (allowlist_declaration_MUST_list_every_channel)). The allowlist replaces
      Claude Code's default list, so a channel it leaves out stops loading at the next restart;
      listing them here is what lets ``pd install`` and the daemon compare the two.
      Absent means the deployment sets no allowlist.
    - ``wind_down``: absent means no wind-down, so only the operator may ask to compact.
    - ``timezone``: the IANA name crons and quiet windows are read in, required once any
      schedule or quiet window is declared, because a host reads a bare time of day in its
      local time and a container usually in UTC, so the same declaration would act at
      different moments.
    - ``stream_grants``: the other uids that may subscribe to the event stream, each with the
      sources it may take; the agent's own uid needs none (persistent_layer 11.4).
    - ``operator_uid``: where the operator has an account of its own, as in a container, the
      only uid the daemon takes the event stream's rules from. None: the daemon's own uid, as
      for every control act.
    """

    version: Literal[1]
    agent: str = Field(min_length=1)
    units: List[Unit] = Field(default_factory=list)
    schedules: List[Schedule] = Field(default_factory=list)
    operator_channels: Optional[List[str]] = None
    allowlisted_channels: Optional[List[ChannelPlugin]] = None
    notice_routes: Dict[str, NoticeRoute] = Field(default_factory=dict)
    #: How long a new session incarnation may run before its MacEff channel attaches; past it,
    #: the channel is dark (MIS-0002-R115). None: no channel is expected, and none is watched.
    channel_connect_s: Optional[float] = Field(default=None, gt=0)
    #: How long mail may sit in the agent's pickup box, while its session runs, before the
    #: daemon raises the ``pd_unread_mail`` notice (MIS-0002-R55). None: no notice.
    unread_mail_threshold_s: Optional[float] = Field(default=None, gt=0)
    #: How long the keystroke wake rests after each wake, until the agent paces it otherwise
    #: over the control socket (persistent_layer 1.9).
    wake_refractory_s: float = Field(default=DEFAULT_WAKE_REFRACTORY_S, gt=0, allow_inf_nan=False)
    #: The shortest window a pace may set. Only the declaration sets it, never the socket, and
    #: in a container the declaration is rendered by root. None: no floor.
    wake_refractory_floor_s: Optional[float] = Field(default=None, gt=0, allow_inf_nan=False)
    #: The longest window a pace may set. Only the declaration sets it, like the floor.
    wake_refractory_ceiling_s: float = Field(default=DEFAULT_WAKE_REFRACTORY_CEILING_S, gt=0,
                                             allow_inf_nan=False)
    quiet_windows: List[Window] = Field(default_factory=list)
    keep_harness_idle_compaction: bool = False
    wind_down: Optional[WindDown] = None
    timezone: Optional[str] = None
    #: Commands the agent's ``check`` entries may run, by name (the scheduler design, 4.2).
    check_templates: Dict[str, CheckTemplate] = Field(default_factory=dict)
    stream_grants: List[StreamGrant] = Field(default_factory=list)
    operator_uid: Optional[int] = Field(default=None, ge=0)

    @model_validator(mode="after")
    def _one_grant_per_uid(self) -> "Declaration":
        uids = [g.uid for g in self.stream_grants]
        dupes = sorted({u for u in uids if uids.count(u) > 1})
        if dupes:
            raise ValueError(f"stream_grants names uid {', '.join(map(str, dupes))} more than once; "
                             f"give each uid one grant listing every source it may take")
        return self

    @model_validator(mode="after")
    def _names_unique(self) -> "Declaration":
        names = [u.name for u in self.units] + [s.name for s in self.schedules]
        dupes = sorted({n for n in names if names.count(n) > 1})
        if dupes:
            raise ValueError(f"names declared more than once: {', '.join(dupes)}")
        if sum(u.kind == "session" for u in self.units) > 1:
            raise ValueError("at most one unit may be the session")
        bad = sorted(n for n in self.check_templates if not re.fullmatch(r"[a-z][a-z0-9_-]{0,47}", n))
        if bad:
            raise ValueError(f"check template names must be short lowercase words: {', '.join(bad)}")
        return self

    @model_validator(mode="after")
    def _wake_floor_under_its_window(self) -> "Declaration":
        floor = self.wake_refractory_floor_s
        if floor is not None and floor > self.wake_refractory_s:
            raise ValueError(f"wake_refractory_floor_s ({floor:g} s) is above wake_refractory_s "
                             f"({self.wake_refractory_s:g} s): the declared window would be under its own floor")
        ceiling = self.wake_refractory_ceiling_s
        if self.wake_refractory_s > ceiling:
            raise ValueError(f"wake_refractory_s ({self.wake_refractory_s:g} s) is above wake_refractory_ceiling_s "
                             f"({ceiling:g} s): the declared window would be over its own ceiling")
        return self

    @model_validator(mode="after")
    def _routes_are_ones_that_are_served(self) -> "Declaration":
        # A route that reaches nobody is refused, not accepted and dropped (MIS-0002-R42
        # (notice_source_MUST_be_routed); the repo owner's ruling of 2026-10-21, option A). The
        # agent's route is served for every source; the operator's only for unread mail, by the
        # outside watch; holding until the operator is present is served nowhere yet. A source
        # routed to `both` keeps its agent half, and the daemon says at start that the operator's
        # half is unserved (half_served_routes), so a half-served route never stops a daemon.
        for source, route in sorted(self.notice_routes.items()):
            if route == "held_until_present":
                raise ValueError(f"notice_routes routes {source!r} to 'held_until_present', which no "
                                 f"part of the layer serves yet, so its notices would reach nobody; "
                                 f"route it to 'agent'")
            if route == "operator" and source != UNREAD_MAIL_SOURCE:
                raise ValueError(f"notice_routes routes {source!r} to 'operator', but only "
                                 f"{UNREAD_MAIL_SOURCE!r} reaches the operator today (by the outside "
                                 f"watch), so its notices would reach nobody; route it to 'agent'")
        return self

    def half_served_routes(self) -> List[str]:
        """Sources routed to `both` whose operator half nothing serves yet: every one but unread mail."""
        return sorted(s for s, r in self.notice_routes.items() if r == "both" and s != UNREAD_MAIL_SOURCE)

    @model_validator(mode="after")
    def _unread_mail_notice_is_routed(self) -> "Declaration":
        # A threshold with nowhere to send its notice would be enforcement nobody hears
        # (MIS-0002-R42 (notice_source_MUST_be_routed)).
        if self.unread_mail_threshold_s is not None and UNREAD_MAIL_SOURCE not in self.notice_routes:
            raise ValueError(f"unread_mail_threshold_s is declared, so notice_routes must route "
                             f"{UNREAD_MAIL_SOURCE!r}: to 'agent', 'operator' or 'both'")
        return self

    @model_validator(mode="after")
    def _schedules_target_isolated_or_own_session(self) -> "Declaration":
        # A schedule targets an isolated session or its own agent's live session, never another
        # agent's (MIS-0002-R29 (schedule_MUST_declare_target)). A foreign card is refused here,
        # at load, rather than accepted and never run.
        for s in self.schedules:
            if s.target not in ("isolated", self.agent):
                raise ValueError(f"schedule {s.name!r} targets {s.target!r}, but a schedule may target "
                                 f"only 'isolated' or this declaration's own agent, {self.agent!r}")
        return self

    @model_validator(mode="after")
    def _a_failed_prompt_run_is_routed(self) -> "Declaration":
        # A prompt run that meets a permission prompt fails with a notice
        # (MIS-0002-R32 (run_MUST_fail_on_prompt)). Only the agent's routes deliver a daemon
        # notice today, so any other route would reach nobody.
        if any(s.target == "isolated" and isinstance(s.run, PromptRun) for s in self.schedules) \
                and self.notice_routes.get(RUN_FAILED_SOURCE, "agent") not in ("agent", "both"):
            raise ValueError(f"an isolated prompt run is declared, so notice_routes must route "
                             f"{RUN_FAILED_SOURCE!r} to 'agent' or 'both', the routes its notice is "
                             f"delivered on")
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
#: A running unit crossed above its declared memory limit, and back below it (MIS-0002-R60).
EVENT_OVER_LIMIT = "pd_unit_over_limit"
EVENT_UNDER_LIMIT = "pd_unit_back_under_limit"
#: The session's MacEff channel went dark, and came back (MIS-0002-R115).
EVENT_CHANNEL_DARK = "pd_channel_dark"
EVENT_CHANNEL_BACK = "pd_channel_back"
#: An attached MacEff channel said which notice sources it takes (MIS-0002-R149). ``takes``
#: lists them; a channel that sent no hello declares nothing and has no such event.
EVENT_CHANNEL_DECLARED = "pd_channel_declared"
#: Mail sat in the agent's pickup box past its declared threshold, and the box was then
#: emptied (MIS-0002-R55). One of each per unread spell.
EVENT_UNREAD_MAIL = "pd_unread_mail"
EVENT_UNREAD_MAIL_CLEARED = "pd_unread_mail_cleared"
#: At start, the organization allowlist and the declaration's ``allowlisted_channels`` differ
#: (MIS-0002-R124). ``findings`` names each difference.
EVENT_ALLOWLIST_MISMATCH = "pd_allowlist_mismatch"
EVENT_DAEMON_START = "pd_daemon_start"
#: An operator's rule for the event stream: what its rules in force fold to (persistent_layer 11.4).
EVENT_STREAM_RULE = "pd_stream_rule"


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
    - ``auth_failed``: what the harness said when it could not authenticate, while it can't;
      the daemon reads the session failed until it can again
      (MIS-0002-R19 (auth_failure_MUST_read_failed)).
    """

    agent: str
    unit: str
    pid: int = Field(gt=1)
    proc_start: str = Field(min_length=1)
    interval_s: float = Field(gt=0)
    in_flight: Optional[int] = Field(default=None, ge=0)
    waiting_on: Optional[str] = Field(default=None, max_length=200)
    auth_failed: Optional[str] = Field(default=None, max_length=200)


class UnitState(_Closed):
    """A unit entering one of the states of MIS-0002-R20, written by the daemon."""

    agent: str
    unit: str
    state: State
    pid: Optional[int] = None
    proc_start: Optional[str] = None
    reason: str = ""
    #: The host boot this was recorded in (Linux's ``boot_id``), so a later daemon adopts
    #: the pid only within the same boot. None where the platform has no boot id.
    boot_id: Optional[str] = None


class Asker(_Closed):
    """Who asked for a control act, as the asker claimed it
    (MIS-0002-R52 (control_act_MUST_name_who_asked)).

    ``harness`` is for a compaction nobody asked for, found by the absence of an ask
    (MIS-0002-R127 (harness_compaction_MUST_be_recorded)); ``policy`` for the daemon
    acting on its own declared rules: a unit's restart policy after a failure, the start of
    declared units at boot, and the stops of a shutdown. ``agent`` is the agent itself, over
    the control socket from its own command line, pacing its wake (persistent_layer 1.9).
    """

    kind: Literal["operator", "wind_down", "policy", "harness", "agent"]
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
    observation and this record is the decision. A pace acts on no unit, so its ``unit`` is
    empty, and the window it set is in its ``WakePaced`` record.
    """

    agent: str
    act: Literal["start", "stop", "restart", "compact", "pace"]
    unit: str
    asked_by: Asker
    peer: Optional[Peer] = None
    reason: str = Field(min_length=1)

    @model_validator(mode="after")
    def _peer_iff_requested(self) -> "Control":
        requested = self.asked_by.kind in ("operator", "wind_down", "agent")
        if requested != (self.peer is not None):
            raise ValueError("an act asked for over the control socket records its peer, "
                             "and only such an act does")
        return self


class WakePaced(_Closed):
    """The keystroke wake was paced over the control socket (persistent_layer 1.9): written
    before the daemon answers, beside the act's ``Control`` record, and read back by the next
    daemon at its start, which re-asserts it. ``refractory_s`` is the window asked for, or None
    to go back to the declared one; ``previous_s`` is the window it replaced."""

    agent: str
    refractory_s: Optional[float] = Field(default=None, gt=0, allow_inf_nan=False)
    previous_s: float = Field(gt=0)
    asked_by: Asker
    peer: Peer
    reason: str = Field(min_length=1)


class StreamRule(_Closed):
    """A rule the operator set for the event stream, written before it takes effect; the
    daemon's rules in force are what these events fold to, so a rule survives a restart
    (MIS-0002-R152 (operator_MUST_silence_and_reroute)).

    ``silence`` and ``unsilence`` name a source pattern, or a subscriber as ``@name``; ``route``
    sends the sources ``target`` matches only to the subscriber ``subscriber`` names, and
    ``unroute`` takes that route away. A silenced source still lands in the log."""

    agent: str
    act: Literal["silence", "unsilence", "route", "unroute"]
    target: str = Field(min_length=1, max_length=200)
    subscriber: Optional[str] = Field(default=None, pattern=STREAM_SUBSCRIBER_NAME)
    asked_by: Asker
    peer: Optional[Peer] = None
    reason: str = ""

    @model_validator(mode="after")
    def _well_formed(self) -> "StreamRule":
        _check_stream_rule(self.act, self.target, self.subscriber)
        return self


def _check_stream_rule(act: str, target: str, subscriber: Optional[str]) -> None:
    """A rule names a source pattern, or a subscriber where silencing; a route names both."""
    if target.startswith("@"):
        if act not in ("silence", "unsilence"):
            raise ValueError(f"a {act} names a source, not a subscriber ({target!r})")
        if not re.fullmatch(STREAM_SUBSCRIBER_NAME, target[1:]):
            raise ValueError(f"{target!r} is not a subscriber name: '@' and a short lowercase word")
    elif not re.fullmatch(_STREAM_SOURCE, target):
        raise ValueError(f"{target!r} is not a source: an event name, with * and ? globs")
    if (act == "route") != (subscriber is not None):
        raise ValueError("a route names the subscriber it sends the source to, and only a route does")


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
#   channel  the daemon writes closed notice records, one per line. The channel writes
#            one line only, its hello, right after it attaches (``ChannelHello``): the
#            notice sources it takes, so the daemon holds the rest for a channel that takes
#            them (MIS-0002-R149 (pd_MUST_hold_sources_channel_did_not_declare)). Anything
#            else a channel writes breaks the protocol, and the daemon drops it.
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


#: A notice source as a hello names it: the names the channel's records use.
_SOURCE_NAME = Annotated[str, Field(pattern=r"^[a-z][a-z0-9_]{0,63}$")]


class HelloBody(_Closed):
    """The sources a channel takes. A source this daemon doesn't know is declared all the
    same: a newer channel may take one, and declaring it holds nothing."""

    takes: List[_SOURCE_NAME] = Field(max_length=64)


class ChannelHello(_Closed):
    """The one line a MacEff channel writes, ``{"hello": {"takes": [...]}}``, right after it
    attaches and has checked its peer (MIS-0002-R149). A channel that sends none declares
    nothing, so the daemon sends it nothing and holds every notice for one that declares."""

    hello: HelloBody


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


class EntryAddRequest(_Closed):
    """An agent's own entry, asked from its live session: the daemon takes it only from a
    process below the session unit (the scheduler design, sections 1 and 4.1)."""

    op: Literal["entry_add"]
    when: str = Field(min_length=1, max_length=200)
    purpose: str = Field(min_length=1, max_length=500)
    action: Literal["wake", "check"]
    missed: Literal["once", "skip", "report"]
    #: For a ``check``: the operator's template it runs, and its arguments (design 4.2).
    template: Optional[str] = Field(default=None, max_length=48)
    args: Dict[str, str] = Field(default_factory=dict)

    @model_validator(mode="after")
    def _template_iff_check(self) -> "EntryAddRequest":
        if (self.action == "check") != (self.template is not None):
            raise ValueError("a template is named exactly when the action is check")
        return self


class EntryListRequest(_Closed):
    """The entries the agent holds. Anyone with the daemon's uid may read them, the operator
    included (the scheduler design, 5.5); only making one needs the live session."""

    op: Literal["entry_list"]


class EntryRemoveRequest(_Closed):
    """Remove an entry the agent holds. Removing only ever stops work, so anyone with the
    daemon's uid may ask: the agent, from its session, and the operator, revoking an entry that
    is already active (the scheduler design, 5.4)."""

    op: Literal["entry_remove"]
    id: str = Field(pattern=r"^e-[0-9a-f]{12}$")


class PaceRequest(_Closed):
    """How long the keystroke wake rests after each wake, or None to go back to the declared
    window. The agent paces itself, or the operator paces it; it acts on no unit. No pace goes
    under the declared floor, which only the declaration sets (persistent_layer 1.9)."""

    op: Literal["pace"]
    refractory_s: Optional[float] = Field(default=None, gt=0, allow_inf_nan=False)
    asked_by: Asker
    reason: str = Field(min_length=1)

    @model_validator(mode="after")
    def _only_agent_or_operator(self) -> "PaceRequest":
        if self.asked_by.kind not in ("agent", "operator"):
            raise ValueError("only the agent or the operator may pace the wake")
        return self


class StreamRuleRequest(_Closed):
    """Silence, unsilence or reroute a source or a subscriber of the event stream, asked by the
    operator; it takes effect at once and is recorded first (persistent_layer 11.4)."""

    op: Literal["stream_rule"]
    act: Literal["silence", "unsilence", "route", "unroute"]
    target: str = Field(min_length=1, max_length=200)
    subscriber: Optional[str] = Field(default=None, pattern=STREAM_SUBSCRIBER_NAME)
    asked_by: Asker
    reason: str = Field(default="", max_length=500)

    @model_validator(mode="after")
    def _operator_and_well_formed(self) -> "StreamRuleRequest":
        if self.asked_by.kind != "operator":
            raise ValueError("only the operator sets the event stream's rules")
        _check_stream_rule(self.act, self.target, self.subscriber)
        return self


Request = Union[StatusRequest, ActRequest, CompactRequest, PaceRequest, EntryAddRequest,
                EntryListRequest, EntryRemoveRequest, StreamRuleRequest]


class UnitStatus(_Closed):
    """A unit as the daemon sees it now. ``restart_held_until`` is the end of the quiet
    window, ``HH:MM`` in the declaration's time, that a session's restart waits for,
    asked or due by its policy (MIS-0002-R50 (layer_MUST-NOT_act_in_quiet_window)), so
    whoever asked for it learns that it waits rather than that it happened."""

    unit: str
    state: State
    pid: Optional[int] = None
    proc_start: Optional[str] = None
    since: float
    restart_held_until: Optional[str] = None


class Response(_Closed):
    """``wake_refractory_s`` and ``wake_window_from`` answer a status or a pace where a session
    unit has a keystroke wake: the window in force, and where it came from."""

    ok: bool
    error: Optional[str] = None
    units: Optional[List[UnitStatus]] = None
    entries: Optional[List[dict]] = None
    wake_refractory_s: Optional[float] = None
    wake_window_from: Optional[str] = None
    #: The event stream's rules in force, answering a stream rule.
    stream_rules: Optional[Dict[str, Any]] = None


_REQUEST = TypeAdapter(Annotated[Request, Field(discriminator="op")])


def parse_request(line: str) -> Request:
    """One control request from one line, refused whole if any part of it is unknown.

    Raises ``pydantic.ValidationError``; the daemon answers ``Response(ok=False)`` with
    the reason and acts on nothing.
    """
    return _REQUEST.validate_json(line)
