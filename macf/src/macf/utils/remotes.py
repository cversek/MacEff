"""The places the operator attaches to from this machine, and the ssh hand-off to each.

``harness attach lumen`` on a laptop has to find the Lumen seats on another machine
without the operator carrying their port, account and socket directory in his head
(persistent_layer 4). The operator declares each place once, in his own config; this
module asks each one who is there and hands an attach off to it.

**Declared, not discovered.** The file lives in the operator's config directory
(``$XDG_CONFIG_HOME/maceff/remotes.yaml``, else ``~/.config/maceff/remotes.yaml``),
never in an agent's home: which machines a person reaches is that person's
configuration, not any agent's state.

**The remote attaches itself.** The laptop matches a name against each remote's own
``harness list --json`` and then runs ``ssh -t`` of the remote's ``harness attach --card``.
The remote resolves the session from its own daemon (MIS-0002-R100), so no socket path,
pid or session name ever crosses the wire, and the laptop holds no knowledge that a
restart on the remote could make stale.

**Nothing a remote says becomes an ssh option.** A roster is data from the machine where
the agents live, and its ``account`` names the login for a seat's hand-off. Each account
and card is checked against what it can legitimately be when the roster is read, and
again when the hand-off is built; ssh is always given ``-l <login>`` and ``--`` before
the host, so no value can reach ssh's option parsing even if a check is loosened later.

**No credential passes through macf.** ssh uses the operator's own keys, agent and
``~/.ssh/config``; macf reads none of them and stores nothing. A roster is asked for with
``BatchMode``, so a remote that would prompt for a password answers "unreachable" instead
of hanging completion; the attach itself is interactive, and ssh may prompt there.
"""
from __future__ import annotations

import json
import os
import re
import shlex
import subprocess
from pathlib import Path
from typing import Callable, List, Optional

import yaml
from pydantic import BaseModel, ConfigDict, ValidationError, field_validator, model_validator

from .roster import RosterEntry

#: The login value meaning "each seat's own account": a container seat is reached as itself.
SEAT = "seat"

#: Seconds ssh may take to connect when asking for a roster (completion's deadline is the caller's).
CONNECT_TIMEOUT_S = 5

#: A POSIX account name: what a login can legitimately be. Never begins with ``-``.
ACCOUNT = re.compile(r"^[a-z_][a-z0-9_-]{0,31}$")

#: A calling card (``Moniker@uuid``), or a bare moniker: letters, digits, ``_ . -``, never
#: beginning with ``-``.
CARD = re.compile(r"^[A-Za-z0-9_][A-Za-z0-9_.-]{0,63}(@[0-9a-f]{6})?$")

#: A host name or address for ssh: never beginning with ``-``.
HOST = re.compile(r"^[A-Za-z0-9_.:\[\]%-]+$")


def _checked(value: Optional[str], pattern: "re.Pattern", what: str) -> Optional[str]:
    if value is not None and (not pattern.match(value) or value.startswith("-")):
        raise ValueError(f"{what} {value!r} is not a legitimate {what}")
    return value


class RemotesRefused(ValueError):
    """The remotes declaration can't be used; the message names the field and the file."""


class RemoteTooOld(RuntimeError):
    """The remote's macf has no ``harness list``: it can be attached to by hand, not by name."""


class Remote(BaseModel):
    """One place the operator attaches to."""

    model_config = ConfigDict(extra="forbid")

    name: str
    host: str
    port: Optional[int] = None
    #: A fixed login, or ``seat``: each agent's own account (a container's seats).
    login: str
    #: The account that asks for the roster when ``login`` is ``seat``: any one seat, since
    #: a seat may read every home's published summary (persistent_layer 8).
    list_login: Optional[str] = None
    #: The remote's command, for a remote where it is not on a non-login shell's PATH.
    macf_tools: str = "macf_tools"
    #: iTerm2 control mode for this remote; unset follows the file's ``control``.
    control: Optional[bool] = None

    @field_validator("host")
    @classmethod
    def _host(cls, v: str) -> str:
        return _checked(v, HOST, "host")

    @field_validator("login", "list_login")
    @classmethod
    def _login(cls, v: Optional[str]) -> Optional[str]:
        return v if v == SEAT else _checked(v, ACCOUNT, "login")

    @model_validator(mode="after")
    def _seat_needs_a_lister(self):
        if self.login == SEAT and not self.list_login:
            raise ValueError(f"remote {self.name!r}: login 'seat' needs list_login, the account "
                             f"that asks for the roster")
        return self


class RemotesConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    #: iTerm2 control mode (``tmux -CC``) by default, for an operator attaching from iTerm2.
    control: bool = False
    remotes: List[Remote] = []

    @model_validator(mode="after")
    def _names_are_unique(self):
        names = [r.name for r in self.remotes]
        doubled = sorted({n for n in names if names.count(n) > 1})
        if doubled:
            raise ValueError(f"remote names must be unique: {', '.join(doubled)}")
        return self


def remotes_path(environ=os.environ) -> Path:
    """Where the operator's remotes declaration lives."""
    base = environ.get("XDG_CONFIG_HOME") or str(Path(environ.get("HOME", "~")).expanduser() / ".config")
    return Path(base) / "maceff" / "remotes.yaml"


def load_remotes(path: Optional[Path] = None) -> RemotesConfig:
    """The declaration, or an empty one when there is no file; a file that can't be used is
    refused whole, naming what is wrong, rather than read in part."""
    path = path or remotes_path()
    try:
        text = path.read_text()
    except FileNotFoundError:
        return RemotesConfig()
    except OSError as e:
        raise RemotesRefused(f"{path}: {e}") from e
    try:
        return RemotesConfig.model_validate(yaml.safe_load(text) or {})
    except (yaml.YAMLError, ValidationError) as e:
        raise RemotesRefused(f"{path}: {e}") from e


def _destination(remote: Remote, login: str) -> List[str]:
    """``-l login [-p port] -- host``: the login and host as values, after which ssh reads
    no more options."""
    _checked(login, ACCOUNT, "login")
    return ["-l", login] + (["-p", str(remote.port)] if remote.port else []) + ["--", remote.host]


def roster_argv(remote: Remote, connect_timeout: float = CONNECT_TIMEOUT_S) -> List[str]:
    """The non-interactive ssh that asks ``remote`` who is there."""
    login = remote.list_login if remote.login == SEAT else remote.login
    # --local: the remote lists only itself, so a remote with remotes of its own can't recurse.
    remote_cmd = f"{shlex.quote(remote.macf_tools)} harness list --json --local"
    return (["ssh", "-o", "BatchMode=yes", "-o", f"ConnectTimeout={max(1, int(connect_timeout))}"]
            + _destination(remote, login) + [remote_cmd])


def plain_command(remote: Remote, login: Optional[str] = None) -> str:
    """The ssh a person can type when the remote can't be asked by name."""
    login = login or (remote.list_login if remote.login == SEAT else remote.login)
    return shlex.join(["ssh", "-t"] + _destination(remote, login) + [remote.macf_tools, "harness", "attach"])


def parse_roster(remote: Remote, stdout: str) -> List[RosterEntry]:
    """The remote's ``harness list --json``, each entry marked as the remote's."""
    try:
        objects = json.loads(stdout)
    except ValueError as e:
        raise RuntimeError(f"{remote.name}: the roster could not be read: {e}") from e
    if not isinstance(objects, list):
        raise RuntimeError(f"{remote.name}: the roster is not a list")
    # Fields this macf doesn't know are dropped, so a remote a version ahead still lists;
    # the model's own rule (unknown is never empty) still holds for the fields it keeps.
    known = set(RosterEntry.model_fields)
    try:
        entries = [RosterEntry.model_validate({**{k: v for k, v in o.items() if k in known},
                                               "endpoint": remote.name}) for o in objects]
    except (AttributeError, ValidationError) as e:
        raise RuntimeError(f"{remote.name}: the roster could not be read: {e}") from e
    # A name that isn't a legitimate account or card is refused with the whole roster: a
    # remote that serves one can't be believed about the rest.
    for e in entries:
        try:
            _checked(e.account, ACCOUNT, "account")
            _checked(e.card, CARD, "card")
        except ValueError as bad:
            raise RuntimeError(f"{remote.name}: the roster is refused: {bad}") from None
    return entries


def fetch_roster(remote: Remote, timeout: float, *, run: Callable = subprocess.run) -> List[RosterEntry]:
    """Ask ``remote`` who is there, within ``timeout`` seconds, or raise saying why not."""
    try:
        done = run(roster_argv(remote, connect_timeout=timeout), capture_output=True, text=True,
                   timeout=timeout + 1, stdin=subprocess.DEVNULL)
    except subprocess.TimeoutExpired as e:
        raise RuntimeError(f"{remote.name}: no answer within {timeout:g} s") from e
    except OSError as e:
        raise RuntimeError(f"{remote.name}: ssh could not run: {e}") from e
    if done.returncode != 0:
        said = (done.stderr or done.stdout or "").strip()
        if any(sign in said for sign in ("invalid choice: 'list'", "invalid choice: 'harness'",
                                         "unrecognized arguments: --local")):
            raise RemoteTooOld(f"{remote.name}: its macf is too old to list who is there; "
                               f"attach by hand: {plain_command(remote)}")
        raise RuntimeError(f"{remote.name}: unreachable (ssh exit {done.returncode}: {said[-200:]})")
    return parse_roster(remote, done.stdout)


class Fetcher:
    """One remote's roster fetch, named, for ``roster.gather``."""

    def __init__(self, remote: Remote, run: Callable = subprocess.run):
        self.remote = remote
        self.name = remote.name
        self._run = run

    def __call__(self, timeout: float) -> List[RosterEntry]:
        return fetch_roster(self.remote, timeout, run=self._run)


def handoff_argv(remote: Remote, entry: RosterEntry, *, control: Optional[bool] = None,
                 default_control: bool = False, read_only: bool = False) -> List[str]:
    """The interactive ssh that attaches to ``entry`` on ``remote``, as the remote resolves it.

    The card travels, nothing else: the remote's own ``harness attach --card`` finds the
    session from its daemon. A seat's remote is reached as that seat's own account.
    """
    if not entry.card:
        raise ValueError(f"{remote.name}: the entry has no card, so it can't be named to the remote")
    login = remote.login
    if login == SEAT:
        if not entry.account:
            raise ValueError(f"{remote.name}: {entry.card} has no account to log in as")
        login = entry.account
    _checked(entry.card, CARD, "card")
    if control is None:
        control = remote.control if remote.control is not None else default_control
    remote_cmd = [remote.macf_tools, "harness", "attach", "--card", entry.card,
                  "--control" if control else "--no-control"] + (["--read-only"] if read_only else [])
    return ["ssh", "-t"] + _destination(remote, login) + [shlex.join(remote_cmd)]
