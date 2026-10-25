"""The shared view of a container: every agent's units and the container's budget, read-only.

MIS-0002-R62 (agent_MUST_see_shared_container): in a container several agents share, each
agent has a read-only view of every unit in it and of its shared budget. MIS-0002-R103
(shared_budget_MUST_change_only_by_operator): only the operator changes that budget.

**Every unit.** An agent's declaration is private (``~/.maceff/pd/``), and its environment can
carry secrets, so it is never read by a peer. Instead each agent publishes a summary of its
own units into its own ``~/agent/public/pd/units.json``: a name, a kind, a memory limit, a
restart rule, whether the unit is optional. No command, no environment. ``agent/public`` is
the tree peers already read through the ``agents_all`` group, and only its owner writes it, so
one agent cannot publish for another. A reader also checks that each file is owned by the
account whose home holds it.

**The budget** is the container's own cgroup, read where every process in it can read it:
``memory.max``, ``cpu.max`` and what the kernel cannot reclaim (``memory.stat``: anon +
kernel). Those files are root-owned on a read-only mount inside the container, so the view
has nothing to write even if it tried, and no declaration carries a field that names the
container's budget (R103). The operator changes it in the compose files and recreates.

Unknown is never "fine": a home whose summary cannot be read is listed as UNREADABLE, and a
budget file that cannot be read is shown as unknown. A summary outlives the daemon that wrote
it, so the view prints each one's age, and one left by a stopped daemon doesn't read as current.

**Who publishes.** The agent's primal daemon, at each start (``Daemon.start``). Its
declaration is read only when it starts, so a changed declaration takes effect, and is
published again, through a restart of the daemon.
"""
import argparse
import json
import os
import stat
import sys
import tempfile
import time
from pathlib import Path
from typing import List, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from macf.pd import interface

VIEW_VERSION = 1
CGROUP = Path("/sys/fs/cgroup")
HOMES = Path("/home")


def published_path(agent_home: Path) -> Path:
    """Where an agent publishes its units for its peers: in its own public tree."""
    return Path(agent_home) / "agent" / "public" / "pd" / "units.json"


class _Closed(BaseModel):
    model_config = ConfigDict(extra="forbid")


class UnitSummary(_Closed):
    """What a peer may know of a unit. Deliberately not its command or environment."""
    name: str
    kind: Literal["session", "service"]
    memory_limit_mb: int = Field(gt=0)
    restart: Literal["always", "on-failure", "never"]
    optional: bool


class PublishedUnits(_Closed):
    version: Literal[1]
    agent: str = Field(min_length=1)
    published_at: float
    units: List[UnitSummary]


def summarize(declaration: interface.Declaration, now: float) -> PublishedUnits:
    return PublishedUnits(
        version=VIEW_VERSION, agent=declaration.agent, published_at=now,
        units=[UnitSummary(name=u.name, kind=u.kind, memory_limit_mb=u.memory_limit_mb,
                           restart=u.restart, optional=u.optional) for u in declaration.units])


def publish(agent_home: Path, declaration: interface.Declaration, now: Optional[float] = None) -> Path:
    """Write this agent's summary, whole or not at all, readable by its peers (0644)."""
    path = published_path(agent_home)
    path.parent.mkdir(parents=True, exist_ok=True)
    text = summarize(declaration, time.time() if now is None else now).model_dump_json(indent=1)
    fd, tmp = tempfile.mkstemp(prefix=".units.", suffix=".tmp", dir=path.parent)
    try:
        os.fchmod(fd, 0o644)
        with os.fdopen(fd, "w") as fh:
            fh.write(text)
            fh.flush()
            os.fsync(fh.fileno())
        os.replace(tmp, path)
    except BaseException:
        try:
            os.unlink(tmp)
        except FileNotFoundError:
            pass
        raise
    return path


class AgentView(BaseModel):
    home: str
    status: Literal["PUBLISHED", "UNPUBLISHED", "UNREADABLE"]
    detail: str = ""
    units: Optional[PublishedUnits] = None


def read_agent(home: Path) -> AgentView:
    path = published_path(home)
    try:
        st = path.stat()
    except FileNotFoundError:
        return AgentView(home=str(home), status="UNPUBLISHED", detail="no units published")
    except OSError as e:
        return AgentView(home=str(home), status="UNREADABLE", detail=e.strerror or type(e).__name__)
    try:
        owner = Path(home).stat().st_uid
    except OSError as e:
        return AgentView(home=str(home), status="UNREADABLE", detail=e.strerror or type(e).__name__)
    if st.st_uid != owner:
        return AgentView(home=str(home), status="UNREADABLE",
                         detail="the summary is not owned by the account whose home holds it")
    try:
        units = PublishedUnits.model_validate_json(path.read_text())
    except OSError as e:
        return AgentView(home=str(home), status="UNREADABLE", detail=e.strerror or type(e).__name__)
    except (ValidationError, ValueError):
        return AgentView(home=str(home), status="UNREADABLE", detail="the summary does not parse")
    return AgentView(home=str(home), status="PUBLISHED", units=units)


def read_agents(homes: Path = HOMES) -> List[AgentView]:
    """Every home with a public tree, in name order. A home that can't be looked into is
    listed as UNREADABLE with the reason, never taken for a home without an agent.

    Asked home by home, with ``os.stat``: ``Path.is_dir`` raises on a permission error
    (Python 3.10), and one such home inside a single ``try`` emptied the whole view.
    """
    try:
        candidates = sorted(Path(homes).iterdir())
    except OSError:
        return []
    views = []
    for home in candidates:
        try:
            is_tree = stat.S_ISDIR(os.stat(home / "agent" / "public").st_mode)
        except (FileNotFoundError, NotADirectoryError):
            continue
        except OSError as e:
            views.append(AgentView(home=str(home), status="UNREADABLE",
                                   detail=e.strerror or type(e).__name__))
            continue
        if is_tree:
            views.append(read_agent(home))
    return views


class Budget(BaseModel):
    """The container's limits in force and what it holds. None means unknown, never zero."""
    memory_max_bytes: Optional[int] = None        # 0 = no limit
    cpus: Optional[float] = None                  # 0 = no limit
    memory_held_bytes: Optional[int] = None       # anon + kernel: what cannot be reclaimed
    unreadable: List[str] = Field(default_factory=list)


def read_budget(cgroup: Path = CGROUP) -> Budget:
    """Read only. Each file that cannot be read leaves its field unknown and is named."""
    b = Budget()
    cg = Path(cgroup)
    try:
        text = (cg / "memory.max").read_text().strip()
        b.memory_max_bytes = 0 if text == "max" else int(text)
    except (OSError, ValueError):
        b.unreadable.append("memory.max")
    try:
        quota, period = (cg / "cpu.max").read_text().split()
        b.cpus = 0.0 if quota == "max" else int(quota) / int(period)
    except (OSError, ValueError):
        b.unreadable.append("cpu.max")
    try:
        fields = dict(line.split(" ", 1) for line in (cg / "memory.stat").read_text().splitlines() if " " in line)
        b.memory_held_bytes = int(fields["anon"]) + int(fields.get("kernel", 0))
    except (OSError, ValueError, KeyError):
        b.unreadable.append("memory.stat")
    return b


def _gib(n: Optional[int]) -> str:
    if n is None:
        return "unknown"
    return "no limit" if n == 0 else f"{n / 2**30:.1f} GiB"


def _age(seconds: float) -> str:
    """How long ago, coarsely: a summary is declaration facts, so minutes are precision enough."""
    s = int(seconds)
    if s < 120:
        return f"{s}s"
    if s < 2 * 3600:
        return f"{s // 60}m"
    if s < 48 * 3600:
        return f"{s // 3600}h"
    return f"{s // 86400}d"


def published_age(units: PublishedUnits, now: float) -> str:
    """When a summary was published, as an age. The file outlives the daemon that wrote it, so
    the age is what tells a reader whether its writer still runs: a running daemon publishes at
    each start, and a summary days old was left by one that stopped."""
    ahead = units.published_at - now
    if ahead > 0:
        return f"stamped {_age(ahead)} ahead of this clock"
    return f"published {_age(-ahead)} ago"


def render(agents: List[AgentView], budget: Budget, now: Optional[float] = None) -> str:
    now = time.time() if now is None else now
    lines = ["Shared budget (the operator's; read-only here):",
             f"  memory limit {_gib(budget.memory_max_bytes)}, held {_gib(budget.memory_held_bytes)}"
             + (f" ({100 * budget.memory_held_bytes / budget.memory_max_bytes:.0f}%)"
                if budget.memory_max_bytes and budget.memory_held_bytes is not None else ""),
             "  cpus " + ("unknown" if budget.cpus is None else "no limit" if budget.cpus == 0 else f"{budget.cpus:g}")]
    if budget.unreadable:
        lines.append(f"  unreadable: {', '.join(budget.unreadable)}")
    declared = 0
    lines.append("Units:")
    for a in agents:
        if a.status != "PUBLISHED":
            lines.append(f"  {a.home}: {a.status}, {a.detail}")
            continue
        lines.append(f"  {a.units.agent}: summary {published_age(a.units, now)}"
                     + ("" if a.units.units else ", no units"))
        for u in a.units.units:
            declared += u.memory_limit_mb
            lines.append(f"  {a.units.agent} {u.name} ({u.kind}, {u.memory_limit_mb} MB, restart {u.restart}"
                         + (", optional" if u.optional else "") + ")")
    if budget.memory_max_bytes:
        lines.append(f"Declared unit limits sum to {declared} MB of the container's "
                     f"{budget.memory_max_bytes // 2**20} MB.")
    return "\n".join(lines)


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m macf.pd.shared_view",
                                     description="Every agent's units and the container's budget, read-only.")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)
    agents, budget = read_agents(), read_budget()
    if args.json:
        print(json.dumps({"budget": budget.model_dump(), "agents": [a.model_dump() for a in agents]}, indent=1))
    else:
        print(render(agents, budget))
    return 0


if __name__ == "__main__":
    sys.exit(main())
