"""The tray's controller: which agents are installed, what their primal daemons say, and
what the operator asks of them. No desktop code here; ``app`` draws what this returns.

Installed means rendered for the outer tier. On macOS that is a per-user LaunchAgent
labelled ``maceff_pd.<id>``, whose program is ``python -m macf.pd <agent home>``.
The card comes from the identity file in that home, never from the label, a socket name
or the environment (MIS-0002-R69). Every request goes to that agent's own control socket
(R70), and an answer counts only from the process the daemon's record names (R123); a
peer that cannot be checked is unreachable, never trusted.

``asked_by: operator`` in a request is a claim, not a proof. On a shared login every agent
has the same uid, so the socket's peer credentials cannot tell the operator's tray from
another agent's process. The daemon's control socket is where the operator is
established, by whatever step 1 settles: a grant only the operator's session holds, or
the socket's mode and group where the operator has a uid of its own. Until then, the
daemon must not treat this field alone as the operator.
"""
from __future__ import annotations

import json
import os
import plistlib
import socket
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Dict, List, Optional

from .model import Entry, TrayState, act_request, entry, union

#: How long one status request may take before the agent counts as unreachable.
TIMEOUT_S = 2.0


def launch_agents_dir() -> Path:
    return Path(os.path.expanduser("~")) / "Library" / "LaunchAgents"


def installed_homes(agents_dir: Optional[Path] = None) -> List[Path]:
    """The agent homes the outer tier starts, read from each ``maceff_pd.*`` LaunchAgent."""
    homes = []
    for plist in sorted((agents_dir or launch_agents_dir()).glob("maceff_pd.*.plist")):
        try:
            argv = plistlib.loads(plist.read_bytes()).get("ProgramArguments") or []
        except (OSError, plistlib.InvalidFileException, ValueError) as e:
            print(f"⚠️ MACF tray: unreadable LaunchAgent {plist.name}: {e}", file=sys.stderr)
            continue
        home = _agent_home_arg(argv)
        if home:
            homes.append(Path(home))
        else:
            print(f"⚠️ MACF tray: {plist.name} runs no 'macf.pd <agent home>'; skipped", file=sys.stderr)
    return homes


def _agent_home_arg(argv: List[str]) -> Optional[str]:
    """The agent home in ``... -m macf.pd <agent home>``, the interface's command line."""
    for i in range(len(argv) - 2):
        if argv[i] == "-m" and argv[i + 1] == "macf.pd" and not argv[i + 2].startswith("-"):
            return argv[i + 2]
    return None


@dataclass(frozen=True)
class Resolvers:
    """Where an agent's card, control socket and record come from."""

    card_of: Callable
    control_socket: Callable
    record_path: Callable


@dataclass(frozen=True)
class Agent:
    card: str
    control: Path
    record: Path


def _default_paths() -> Resolvers:
    """The interface's card resolver and socket paths. Absent before step 1 lands."""
    from macf.pd.interface import agent_card, control_socket, record_path
    return Resolvers(card_of=agent_card, control_socket=control_socket, record_path=record_path)


def _default_peer_check(sock: socket.socket, record: Path) -> Optional[str]:
    """None when the peer is the process the daemon's record names; else why not."""
    try:
        rec = json.loads(record.read_text())
    except (OSError, ValueError) as e:
        return f"no daemon record ({e})"
    try:
        from macf.utils.peercred import peer_credentials
    except ImportError:
        return "this installation cannot read a socket peer's credentials"
    from macf.notify.session import verify_incarnation
    try:
        peer = peer_credentials(sock)
    except OSError as e:
        return f"the socket's peer could not be read ({e})"
    if peer.pid != rec.get("pid"):
        return "the socket's peer is not the process the daemon's record names"
    if not verify_incarnation(peer.pid, rec.get("proc_start")):
        return "the daemon's record is stale"
    return None


class Controller:
    """Polls each installed agent's primal daemon and sends the operator's acts."""

    def __init__(self, homes: Callable[[], List[Path]] = installed_homes,
                 paths: Optional[Callable] = None,
                 peer_check: Callable = _default_peer_check,
                 connect: Optional[Callable] = None):
        self._homes = homes
        self._paths = paths or _default_paths
        self._peer_check = peer_check
        self._connect = connect or self._unix_connect
        self.agents: Dict[str, Agent] = {}
        self.found: List[Agent] = []
        self.errors: List[str] = []

    @staticmethod
    def _unix_connect(path: Path) -> socket.socket:
        s = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        s.settimeout(TIMEOUT_S)
        s.connect(str(path))
        return s

    def discover(self) -> Dict[str, Agent]:
        """Installed agents by card. A home that names no agent is reported, not guessed at.

        Every claimant is kept in ``found``, so two homes claiming one card reach the union,
        which marks both failed. ``agents`` holds only cards with one claimant: an act on an
        ambiguous card would not know which daemon to ask, so it is refused.
        """
        self.errors = []
        self.found = []
        try:
            paths = self._paths()
        except ImportError:
            self.errors.append("the primal daemon's interface is not installed")
            self.agents = {}
            return self.agents
        for home in self._homes():
            try:
                card = paths.card_of(home)
            except ValueError as e:
                self.errors.append(f"{home}: {e}")
                continue
            self.found.append(Agent(card, paths.control_socket(card), paths.record_path(card)))
        cards = [a.card for a in self.found]
        self.agents = {a.card: a for a in self.found if cards.count(a.card) == 1}
        return self.agents

    def _ask(self, agent: Agent, line: str) -> Optional[dict]:
        """One request line to one daemon, one response line back, or None when unreachable."""
        try:
            sock = self._connect(agent.control)
        except OSError as e:
            print(f"⚠️ MACF tray: {agent.card} unreachable: {e}", file=sys.stderr)
            return None
        with sock:
            refused = self._peer_check(sock, agent.record)
            if refused:
                return {"ok": False, "error": refused}
            try:
                sock.sendall(line.encode() + b"\n")
                data = b""
                while not data.endswith(b"\n"):
                    chunk = sock.recv(65536)
                    if not chunk:
                        break
                    data += chunk
                return json.loads(data.decode() or "null")
            except (OSError, ValueError) as e:
                print(f"⚠️ MACF tray: {agent.card} answered badly: {e}", file=sys.stderr)
                return None

    def poll(self) -> TrayState:
        """Every agent's entry from its own daemon, and the icon over all of them."""
        self.discover()
        entries: List[Entry] = []
        for agent in self.found:
            entries.append(entry(agent.card, self._ask(agent, json.dumps({"op": "status"}))))
        return union(entries)

    def act(self, card: str, act: str, unit: str) -> dict:
        """Send one start, stop or restart, asked by the operator, to that agent's daemon only."""
        agent = self.agents.get(card)
        if agent is None:
            if any(a.card == card for a in self.found):
                return {"ok": False, "error": f"two installed agents claim the card {card!r}; neither is asked"}
            return {"ok": False, "error": f"no installed agent with the card {card!r}"}
        return self._ask(agent, act_request(act, unit)) or {"ok": False, "error": "no answer"}
