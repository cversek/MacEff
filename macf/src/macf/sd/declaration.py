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
- ``MACEFF_SD_UNIT``, the marker by which it finds a unit's detached workers when no
  control group is available to stop them.

A unit that declares either one is refused, so a declaration can never disagree with what
the daemon sets.
"""
import re
from typing import Dict, List, Literal, Union
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from macf.pd.interface import ExitCodes

#: Environment names the system daemon sets in every unit itself.
RESERVED_ENVIRONMENT = ("TZ", "MACEFF_SD_UNIT")

_ENV_NAME = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
_ACCOUNT = r"^[a-z_][a-z0-9_-]{0,31}$"
_NAME = r"^[a-z][a-z0-9_-]{0,47}$"


class _Closed(BaseModel):
    model_config = ConfigDict(extra="forbid")


class LinuxPlatform(_Closed):
    """How a unit is stopped on Linux.

    ``cgroup`` needs a control-group subtree delegated to the system daemon. ``subreaper``
    works without one: the system daemon collects the unit's detached workers as their
    subreaper and finds them by their marker. A container whose cgroup hierarchy is mounted
    read-only can use only the second."""

    kind: Literal["linux"]
    stop: Literal["cgroup", "subreaper"]


class LaunchdPlatform(_Closed):
    """How a unit is reached on macOS, where launchd is every job's parent: the domain the
    job lives in and its label. A job in a login's ``gui`` domain belongs to that login's
    session, so the system daemon watches it and never starts it."""

    kind: Literal["launchd"]
    domain: Literal["system", "gui"]
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
    memory_limit_mb: int = Field(gt=0)
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
        return groups

    @model_validator(mode="after")
    def _relationship_fits(self) -> "SystemUnit":
        if self.relationship == "parent" and not self.command:
            raise ValueError(f"unit {self.name}: a parented unit needs the command its parent starts")
        if (isinstance(self.platform, LaunchdPlatform) and self.platform.domain == "gui"
                and self.relationship == "parent"):
            raise ValueError(f"unit {self.name}: a job in a login's gui domain belongs to that login's "
                             f"session, so the system daemon watches it and can't parent it")
        return self


class SystemDeclaration(_Closed):
    """A system daemon's whole declaration. It is validated closed: a key the daemon would
    ignore is refused, because whoever wrote it believes it is in force."""

    version: Literal[1] = 1
    system: str = Field(pattern=_NAME)
    time_zone: str
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
        names = [u.name for u in self.units]
        duplicated = sorted({n for n in names if names.count(n) > 1})
        if duplicated:
            raise ValueError(f"unit names must be unique: {', '.join(duplicated)}")
        for unit in self.units:
            unknown = [a for a in unit.after if a not in names]
            if unknown:
                raise ValueError(f"unit {unit.name} starts after unknown unit(s): {', '.join(unknown)}")
        start_order(self)  # refuses a cycle
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


def unit_environment(declaration: SystemDeclaration, unit: SystemUnit) -> Dict[str, str]:
    """The environment the system daemon gives a unit: exactly what the unit declares, plus
    ``TZ`` from the declaration and the unit's marker, which nothing declared can override."""
    return {**unit.environment, "TZ": declaration.time_zone, "MACEFF_SD_UNIT": unit.name}
