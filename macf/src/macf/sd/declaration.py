"""The system declaration a system daemon runs from: the schema both prototypes import.

A system daemon is one root-run supervisor per system. The file it reads lists its units,
and for each one:
- the account it runs as;
- whether the system daemon starts it (``parent``) or only observes it (``watch``);
- its whole environment;
- its restart policy and its exit table.

This is the format that the Linux container prototype and the macOS host prototype of
MIS-0007 (draft, #855) both build against. It was agreed on #850 before either prototype
froze it. This module loads and validates a declaration, and starts nothing.

Two environment values belong to the system daemon, never to a unit:
- ``TZ``, which it sets from the declaration's one ``time_zone``;
- ``MACEFF_SD_UNIT``, the unit's name, by which the unit's own processes and its identity
  probe know which unit they belong to. It isn't how the daemon finds them: root in a
  container without ``CAP_SYS_PTRACE`` can't read another account's environment.

A unit that declares either one is refused, so a declaration can never disagree with what
the daemon sets.

**The exit table** is the primal daemon's ``ExitCodes``, read the way its core reads it:

| a parented unit exits with | ``restart: always`` | ``on-failure`` | ``never`` |
|---|---|---|---|
| a code in ``success`` | restarted | stays stopped | stays stopped |
| a code in ``no_restart`` | stays stopped | stays stopped | stays stopped |
| any other code | a failure, restarted with backoff | a failure, restarted with backoff | a failure, stays down |

So under ``on-failure``, a unit that wants to be restarted has to fail. A watched unit
isn't the system daemon's to restart, so its ``restart`` is ``never`` until the draft
settles whether the daemon may kickstart a watched job. Nor does the daemon start or stop
one, so a watched unit carries no command, environment, exit table, groups, memory limit
or stop grace: each would be a key the daemon ignores.

**Not here, for the loader:** reading the file belongs to whatever loads it. The loader
opens the file by descriptor, checks that root owns it, and refuses one that a group or
others can write. It also refuses an account that resolves to uid 0 at start, which the
name check below can't see. On launchd, it also refuses a unit whose account doesn't
already hold each group the unit names, because launchd takes a job's groups from the
directory, not from the daemon.
"""
import re
from typing import Dict, List, Literal, Optional, Tuple, Union
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from macf.pd.interface import ExitCodes

#: Environment names the system daemon sets in every unit itself.
RESERVED_ENVIRONMENT = ("TZ", "MACEFF_SD_UNIT")

#: Supplementary groups a unit may declare. macOS's setgroups(2) refuses more than 16, and
#: one format holds on every platform, so the limit is applied everywhere at load, even on
#: launchd, where the daemon checks the memberships rather than setting them.
MAX_GROUPS = 16

#: The keys only a parented unit uses: the system daemon neither starts nor stops a
#: watched unit, so on one each of these would be ignored.
PARENT_ONLY = ("command", "environment", "exit_codes", "groups", "memory_limit_mb", "stop_grace_s")

_ENV_NAME = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
_ACCOUNT = r"^[a-z_][a-z0-9_-]{0,31}$"
_NAME = r"^[a-z][a-z0-9_-]{0,47}$"


class _Closed(BaseModel):
    model_config = ConfigDict(extra="forbid")


class LinuxPlatform(_Closed):
    """How a unit is stopped on Linux.

    ``cgroup`` needs a control-group subtree delegated to the system daemon. ``subreaper``
    works without one. A supervisor of the unit's own runs as the unit's account and is the
    subreaper of the unit's tree, so every process the unit leaves behind is reparented to
    it, and it ends them all. A container whose cgroup hierarchy is mounted read-only can use
    only the second."""

    kind: Literal["linux"]
    stop: Literal["cgroup", "subreaper"]


class LaunchdPlatform(_Closed):
    """How a unit is reached on macOS, where launchd is every job's parent: the domain the
    job lives in and its label.

    A login has two domains of its own: ``gui``, only while it holds a GUI session, and
    ``user``, for its background work. A job in either belongs to that login, so the system
    daemon watches it and never starts it. The loader addresses such a job as
    ``<domain>/<uid>`` with the uid of the unit's ``account``, so ``account`` names the
    domain's owner; launchd ignores ``UserName`` for these jobs."""

    kind: Literal["launchd"]
    domain: Literal["system", "gui", "user"]
    label: str = Field(pattern=r"^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$")


class SystemUnit(_Closed):
    """One unit of a system daemon."""

    name: str = Field(pattern=_NAME)
    account: str = Field(pattern=_ACCOUNT)
    relationship: Literal["parent", "watch"]
    command: List[str] = Field(default_factory=list)
    environment: Dict[str, str] = Field(default_factory=dict)
    identity_probe: List[str] = Field(default_factory=list)
    restart: Literal["always", "on-failure", "never"]
    exit_codes: ExitCodes = Field(default_factory=ExitCodes)
    stop_grace_s: float = Field(default=10.0, gt=0)
    liveness_interval_s: float = Field(gt=0)
    #: Required on a parented unit; a watched unit's memory isn't the daemon's to limit.
    memory_limit_mb: Optional[int] = Field(default=None, gt=0)
    #: Supplementary groups. On Linux the system daemon sets them before exec. On launchd
    #: they name memberships the install step grants, which the loader verifies.
    groups: List[str] = Field(default_factory=list)
    after: List[str] = Field(default_factory=list)
    platform: Union[LinuxPlatform, LaunchdPlatform] = Field(discriminator="kind")

    @field_validator("environment")
    @classmethod
    def _environment(cls, env: Dict[str, str]) -> Dict[str, str]:
        bad = sorted(k for k in env if not _ENV_NAME.match(k))
        if bad:
            raise ValueError(f"environment names must match {_ENV_NAME.pattern}: {', '.join(map(repr, bad))}")
        reserved = sorted(k for k in env if k in RESERVED_ENVIRONMENT)
        if reserved:
            raise ValueError(f"{', '.join(reserved)} is the system daemon's to set, not a unit's; "
                             f"TZ comes from the declaration's time_zone")
        return env

    @field_validator("groups")
    @classmethod
    def _groups(cls, groups: List[str]) -> List[str]:
        bad = [g for g in groups if not re.match(_ACCOUNT, g)]
        if bad:
            raise ValueError(f"group names must match {_ACCOUNT}: {', '.join(map(repr, bad))}")
        if len(groups) > MAX_GROUPS:
            raise ValueError(f"{len(groups)} supplementary groups; at most {MAX_GROUPS}, the most "
                             f"macOS's setgroups accepts")
        return groups

    @model_validator(mode="after")
    def _relationship_fits(self) -> "SystemUnit":
        if self.relationship == "parent":
            if not self.command:
                raise ValueError(f"unit {self.name}: a parented unit needs the command its parent starts")
            if self.account == "root":
                raise ValueError(f"unit {self.name}: a parented unit runs feature code, which never runs "
                                 f"as root; give it an unprivileged account")
            if isinstance(self.platform, LaunchdPlatform) and self.platform.domain != "system":
                raise ValueError(f"unit {self.name}: a job in a login's {self.platform.domain} domain "
                                 f"belongs to that login, so the system daemon watches it and can't "
                                 f"parent it")
            if self.memory_limit_mb is None:
                raise ValueError(f"unit {self.name}: a parented unit needs memory_limit_mb, the limit "
                                 f"its process tree is held to")
        else:
            if isinstance(self.platform, LinuxPlatform):
                raise ValueError(f"unit {self.name}: nothing names what to watch on Linux yet; the Linux "
                                 f"host form, which adds the identifier, hasn't been decided")
            if self.restart != "never":
                raise ValueError(f"unit {self.name}: a watched unit isn't the system daemon's to restart, "
                                 f"so its restart is never until the draft settles whether the daemon "
                                 f"may kickstart a watched job")
            ignored = [k for k in PARENT_ONLY if k in self.model_fields_set]
            if ignored:
                raise ValueError(f"unit {self.name}: the system daemon neither starts nor stops a watched "
                                 f"unit, so it would ignore {', '.join(ignored)}; leave them out")
        return self


class SystemDeclaration(_Closed):
    """A system daemon's whole declaration. It is validated closed: a key the daemon would
    ignore is refused, because whoever wrote it believes it is in force."""

    version: Literal[1] = 1
    system: str = Field(pattern=_NAME)
    time_zone: str
    #: The outer manager's limit on stopping the whole system daemon: a container's
    #: ``docker stop -t``, or launchd's ``ExitTimeOut``. Every stop must finish inside it.
    stop_timeout_s: float = Field(gt=0)
    units: List[SystemUnit] = Field(min_length=1)

    @field_validator("time_zone")
    @classmethod
    def _zone(cls, zone: str) -> str:
        try:
            ZoneInfo(zone)
        except (ZoneInfoNotFoundError, ValueError):
            raise ValueError(f"time_zone {zone!r} is not an IANA zone name this system knows") from None
        return zone

    @model_validator(mode="after")
    def _units_fit_together(self) -> "SystemDeclaration":
        kinds = sorted({u.platform.kind for u in self.units})
        if len(kinds) > 1:
            raise ValueError(f"a declaration describes one system, so its units share one platform; "
                             f"found {', '.join(kinds)}")
        names = [u.name for u in self.units]
        duplicated = sorted({n for n in names if names.count(n) > 1})
        if duplicated:
            raise ValueError(f"unit names must be unique: {', '.join(duplicated)}")
        for unit in self.units:
            unknown = [a for a in unit.after if a not in names]
            if unknown:
                raise ValueError(f"unit {unit.name} starts after unknown unit(s): {', '.join(unknown)}")
        # One label per launchd domain. A login's own domains are counted per account.
        claimed: Dict[Tuple[str, ...], str] = {}
        for unit in self.units:
            if not isinstance(unit.platform, LaunchdPlatform):
                continue
            domain, label = unit.platform.domain, unit.platform.label
            key = (domain, label) if domain == "system" else (domain, unit.account, label)
            if key in claimed:
                where = "the system domain" if domain == "system" else f"{unit.account}'s {domain} domain"
                raise ValueError(f"units {claimed[key]} and {unit.name} both claim the label {label} in "
                                 f"{where}; launchd would refuse the second when it is bootstrapped")
            claimed[key] = unit.name
        start_order(self)  # refuses a cycle
        needed, chain = longest_stop(self)
        if needed >= self.stop_timeout_s:
            raise ValueError(f"stopping takes up to {needed:g} s along {' -> '.join(chain)} (each unit's "
                             f"stop_grace_s, in reverse start order), which doesn't fit inside "
                             f"stop_timeout_s {self.stop_timeout_s:g}; raise the outer manager's stop "
                             f"timeout or shorten a grace")
        return self


def start_order(declaration: SystemDeclaration) -> List[str]:
    """The units' names in an order that starts each one after every unit its ``after`` names,
    keeping the declared order wherever ``after`` leaves it free. A cycle is refused."""
    after = {u.name: list(u.after) for u in declaration.units}
    placed: List[str] = []
    visiting: List[str] = []

    def place(name: str) -> None:
        if name in placed:
            return
        if name in visiting:
            raise ValueError(f"start order has a cycle: {' -> '.join(visiting[visiting.index(name):] + [name])}")
        visiting.append(name)
        for first in after[name]:
            place(first)
        visiting.pop()
        placed.append(name)

    for unit in declaration.units:
        place(unit.name)
    return placed


def longest_stop(declaration: SystemDeclaration) -> Tuple[float, List[str]]:
    """The longest a full stop can take, and the chain it takes that long along.

    Units stop in reverse start order: a unit stops before the units its ``after`` names,
    one after another, while units with no order between them stop together. So the worst
    case is the chain whose stop graces add up to the most. A watched unit adds no grace,
    since the system daemon never stops it, but it still orders the units on either side."""
    by_name = {u.name: u for u in declaration.units}
    best: Dict[str, Tuple[float, List[str]]] = {}
    for name in start_order(declaration):
        unit = by_name[name]
        grace = unit.stop_grace_s if unit.relationship == "parent" else 0.0
        before = max((best[a] for a in unit.after), key=lambda t: t[0], default=(0.0, []))
        best[name] = (grace + before[0], [name] + before[1])
    return max(best.values(), key=lambda t: t[0])


def unit_environment(declaration: SystemDeclaration, unit: SystemUnit) -> Dict[str, str]:
    """The environment the system daemon gives a unit: exactly what the unit declares, plus
    ``TZ`` from the declaration and the unit's marker, which nothing declared can override."""
    return {**unit.environment, "TZ": declaration.time_zone, "MACEFF_SD_UNIT": unit.name}
