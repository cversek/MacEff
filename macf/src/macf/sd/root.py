"""The system daemon's root process, in its Linux container form: the prototype MIS-0007 (draft, #855) asks for.

Root does only what R02 leaves it. It starts each declared unit as the unit's account, stops it, and
reaps it and reads its exit. Everything else runs without root:

- **The declaration** is opened by descriptor and refused unless root owns it, nobody else can write
  it, and it has one link (R04, R06). A child that has dropped to ``nobody`` parses it (R03), and root
  reads back only that child's canonical JSON.
- **Each unit** runs under a small supervisor of its own. It is a forked copy of this process that has
  become the unit's account and made itself the subreaper of everything the unit starts. A process the
  unit leaves behind is reparented to that supervisor, whatever session or process group it moved to
  and whatever environment it cleared, and the supervisor ends them all when the unit stops. That is
  R05 without control groups, which a container with a read-only cgroup mount can't delegate.

Run as a container's main command, under tini: ``python3 -m macf.sd.root /etc/maceff/system.json``.

``--experiment-stop-by-marker-only`` is the comparison the prototype measures. It runs no per-unit
supervisor, and a stop finds the unit's processes only by the ``MACEFF_SD_UNIT`` marker in their
environment.
"""
from __future__ import annotations

import argparse
import ctypes
import grp
import json
import os
import pwd
import signal
import socket
import stat
import sys
import time
from typing import Dict, List, Optional, Set, Tuple

from macf.sd.declaration import SystemDeclaration, SystemUnit, longest_stop, start_order, unit_environment

PR_SET_CHILD_SUBREAPER = 36
STATUS_SOCKET = "/run/maceff-sd/status.sock"
EX_CONFIG = 78  # sysexits: the declaration is refused
_libc = ctypes.CDLL(None, use_errno=True)


def log(event: str, **data) -> None:
    """One JSON line on stdout: the container's log is this prototype's record."""
    print(json.dumps({"t": round(time.time(), 3), "event": event, **data}), flush=True)


def set_subreaper() -> None:
    if _libc.prctl(PR_SET_CHILD_SUBREAPER, 1, 0, 0, 0) != 0:
        err = ctypes.get_errno()
        raise OSError(err, os.strerror(err))


# ── the declaration ──────────────────────────────────────────────────────────

class DeclarationRefused(Exception):
    pass


def open_declaration(path: str) -> int:
    """The declaration's descriptor, opened without following a link and checked on that descriptor: a regular
    file that root owns, with one link, that neither a group nor others can write (R04, R06)."""
    try:
        fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_CLOEXEC)
    except OSError as e:
        raise DeclarationRefused(f"{path}: can't be opened without following a link ({e.strerror})") from None
    st = os.fstat(fd)
    problems = []
    if not stat.S_ISREG(st.st_mode):
        problems.append("not a regular file")
    if st.st_uid != 0:
        problems.append(f"owned by uid {st.st_uid}, not root")
    if st.st_mode & (stat.S_IWGRP | stat.S_IWOTH):
        problems.append(f"writable by its group or others (mode {stat.S_IMODE(st.st_mode):o})")
    if st.st_nlink != 1:
        problems.append(f"{st.st_nlink} links, so another name can reach it")
    if problems:
        os.close(fd)
        raise DeclarationRefused(f"{path}: {'; '.join(problems)}")
    return fd


def parse_unprivileged(fd: int) -> Tuple[SystemDeclaration, int]:
    """Parse the declaration in a child that has dropped to ``nobody`` (R03), and the uid it parsed as. Root
    reads back only the child's canonical JSON and validates that again."""
    nobody = pwd.getpwnam("nobody")
    r, w = os.pipe()
    pid = os.fork()
    if pid == 0:  # the parser: no root from here on
        os.close(r)
        try:
            os.setgroups([])
            os.setgid(nobody.pw_gid)
            os.setuid(nobody.pw_uid)
            raw = b"".join(iter(lambda: os.read(fd, 65536), b""))
            decl = SystemDeclaration.model_validate_json(raw)
            reply = {"uid": os.getuid(), "declaration": json.loads(decl.model_dump_json())}
        except Exception as e:  # noqa: BLE001 - the parser reports any failure as the refusal it is
            reply = {"uid": os.getuid(), "error": str(e)}
        data = json.dumps(reply).encode()
        while data:
            data = data[os.write(w, data):]
        os._exit(0)
    os.close(w)
    data = b"".join(iter(lambda: os.read(r, 65536), b""))
    os.close(r)
    os.waitpid(pid, 0)
    reply = json.loads(data)
    if reply.get("uid") == 0:
        raise DeclarationRefused("the parser was still root")
    if "error" in reply:
        raise DeclarationRefused(f"refused by the parser (as uid {reply['uid']}): {reply['error']}")
    return SystemDeclaration.model_validate(reply["declaration"]), reply["uid"]


# ── the process table ────────────────────────────────────────────────────────

def _proc_stat(pid: int) -> Optional[Tuple[int, str]]:
    """``(ppid, state)`` of a process from /proc, or None once it is gone."""
    try:
        with open(f"/proc/{pid}/stat", "rb") as f:
            raw = f.read().decode(errors="replace")
    except OSError:
        return None  # noqa: MACEFF003 - a process that is gone has no stat: None is the answer here
    rest = raw[raw.rindex(")") + 2:].split()
    return int(rest[1]), rest[0]


def descendants(top: int) -> List[int]:
    """Every live process under ``top``, zombies left out: a zombie answers kill() but is already dead."""
    children: Dict[int, List[int]] = {}
    for name in os.listdir("/proc"):
        if name.isdigit():
            st = _proc_stat(int(name))
            if st and st[1] != "Z":
                children.setdefault(st[0], []).append(int(name))
    out, todo = [], [top]
    while todo:
        for child in children.get(todo.pop(), []):
            out.append(child)
            todo.append(child)
    return out


def carrying_marker(unit_name: str) -> List[int]:
    """Live processes whose environment carries this unit's marker. Only root can read every environment."""
    want = f"MACEFF_SD_UNIT={unit_name}".encode()
    out = []
    for name in os.listdir("/proc"):
        if not name.isdigit() or int(name) == os.getpid():
            continue
        try:
            with open(f"/proc/{name}/environ", "rb") as f:
                carries = want in f.read().split(b"\0")
        except OSError:
            continue
        st = _proc_stat(int(name))
        if carries and st and st[1] != "Z":
            out.append(int(name))
    return out


def _signal(pids, sig) -> None:
    for pid in pids:
        try:
            os.kill(pid, sig)
        except ProcessLookupError:
            pass


def _status_code(waitstatus: int) -> int:
    code = os.waitstatus_to_exitcode(waitstatus)
    return 128 - code if code < 0 else code  # a signal's death reads as 128 + the signal, as a shell reports it


# ── the per-unit supervisor, as the unit's account ───────────────────────────

def unit_supervisor(unit: SystemUnit, env: Dict[str, str]) -> None:
    """Runs as the unit's account, as the subreaper of everything the unit starts. It exits with the unit's own
    exit status once nothing the unit started is left: on a stop, or when the unit's main process ends."""
    set_subreaper()
    stopping = False

    def on_term(signum, frame):
        nonlocal stopping
        stopping = True

    signal.signal(signal.SIGTERM, on_term)
    signal.signal(signal.SIGHUP, signal.SIG_IGN)
    main = os.fork()
    if main == 0:
        signal.signal(signal.SIGTERM, signal.SIG_DFL)
        signal.signal(signal.SIGHUP, signal.SIG_DFL)
        try:
            os.execve(unit.command[0], unit.command, env)
        except OSError as e:
            print(f"unit {unit.name}: exec failed: {e}", file=sys.stderr)
        os._exit(127)

    status: Optional[int] = None

    def reap() -> None:
        nonlocal status
        while True:
            try:
                pid, ws = os.waitpid(-1, os.WNOHANG)
            except ChildProcessError:
                return  # noqa: MACEFF003 - no child left to reap ends the pass; it is not a failure
            if pid == 0:
                return
            if pid == main and status is None:
                status = _status_code(ws)

    while status is None and not stopping:
        reap()
        time.sleep(0.05)
    # The unit stops, or its main process has ended: everything it started ends too.
    me = os.getpid()
    _signal(descendants(me), signal.SIGTERM)
    deadline = time.monotonic() + unit.stop_grace_s
    while descendants(me) and time.monotonic() < deadline:
        reap()
        time.sleep(0.05)
    while descendants(me):  # orphans keep arriving as their parents die, so kill until none is left
        _signal(descendants(me), signal.SIGKILL)
        reap()
        time.sleep(0.02)
    reap()
    os._exit(status if status is not None else 128 + signal.SIGKILL)


# ── the root process ─────────────────────────────────────────────────────────

class UnitState:
    def __init__(self, unit: SystemUnit):
        self.unit = unit
        self.pid: Optional[int] = None
        self.uid: Optional[int] = None
        self.state = "waiting"
        self.restarts = 0
        self.failures = 0
        self.last_exit: Optional[int] = None
        self.start_at = 0.0


class SystemDaemon:
    def __init__(self, decl: SystemDeclaration, marker_only: bool = False):
        self.decl = decl
        self.marker_only = marker_only
        self.units: Dict[str, UnitState] = {u.name: UnitState(u) for u in decl.units}
        self.order = start_order(decl)
        self.stop_requested = False

    # starting

    def spawn(self, u: UnitState) -> None:
        unit = u.unit
        try:
            pw = pwd.getpwnam(unit.account)
            gids = [grp.getgrnam(g).gr_gid for g in unit.groups]
        except KeyError as e:
            u.state = "refused"
            log("unit_refused", unit=unit.name, reason=f"no such account or group: {e}")
            return
        if pw.pw_uid == 0:  # a name check can't see this; resolve it at start (the loader's duty)
            u.state = "refused"
            log("unit_refused", unit=unit.name, reason=f"account {unit.account} resolves to uid 0")
            return
        env = unit_environment(self.decl, unit)
        pid = os.fork()
        if pid == 0:
            try:
                os.setsid()
                os.setgroups(gids)
                os.setgid(pw.pw_gid)
                os.setuid(pw.pw_uid)
                try:
                    os.chdir(pw.pw_dir)
                except OSError:
                    os.chdir("/")
                if self.marker_only:
                    os.execve(unit.command[0], unit.command, env)
                unit_supervisor(unit, env)
            except BaseException as e:  # noqa: BLE001 - a child that can't start says so and exits
                print(f"unit {unit.name}: start failed: {e!r}", file=sys.stderr)
            os._exit(70)
        u.pid, u.uid, u.state = pid, pw.pw_uid, "running"
        log("unit_started", unit=unit.name, pid=pid, account=unit.account, uid=pw.pw_uid,
            time_zone=self.decl.time_zone)

    def start_due(self) -> None:
        now = time.monotonic()
        for name in self.order:
            u = self.units[name]
            if u.state == "waiting" and now >= u.start_at:
                self.spawn(u)

    # exits

    def decide(self, u: UnitState, code: int) -> str:
        """The exit table, as the primal daemon's core reads it (see the declaration module)."""
        unit = u.unit
        if code in unit.exit_codes.no_restart:
            return "stays stopped: no_restart"
        if code in unit.exit_codes.success:
            return "restart" if unit.restart == "always" else "stays stopped: success"
        return "restart after failure" if unit.restart in ("always", "on-failure") else "down: failure, restart never"

    def sweep_markers(self, unit: SystemUnit) -> Dict[str, List[int]]:
        """The marker-only stop: TERM what carries the marker, then KILL whatever still carries it after the grace."""
        found = carrying_marker(unit.name)
        _signal(found, signal.SIGTERM)
        deadline = time.monotonic() + unit.stop_grace_s
        while carrying_marker(unit.name) and time.monotonic() < deadline:
            self.reap_others()
            time.sleep(0.05)
        killed = carrying_marker(unit.name)
        _signal(killed, signal.SIGKILL)
        return {"termed": found, "killed": killed}

    def reap_others(self) -> None:
        """Reap without acting on units: used inside a sweep, which must not recurse into the exit table."""
        try:
            while True:
                pid, ws = os.waitpid(-1, os.WNOHANG)
                if pid == 0:
                    return
                self._exited(pid, ws, act=False)
        except ChildProcessError:
            return  # noqa: MACEFF003 - no child left to reap ends the pass; it is not a failure

    def reap(self) -> None:
        try:
            while True:
                pid, ws = os.waitpid(-1, os.WNOHANG)
                if pid == 0:
                    return
                self._exited(pid, ws, act=True)
        except ChildProcessError:
            return  # noqa: MACEFF003 - no child left to reap ends the pass; it is not a failure

    def _exited(self, pid: int, ws: int, act: bool) -> None:
        u = next((x for x in self.units.values() if x.pid == pid), None)
        if u is None:
            log("orphan_reaped", pid=pid, code=_status_code(ws))
            return
        code = _status_code(ws)
        u.pid, u.last_exit = None, code
        if self.marker_only and act:
            left = self.sweep_markers(u.unit)
            log("marker_sweep", unit=u.unit.name, **left)
        if self.stop_requested or not act:
            u.state = "stopped"
            log("unit_exited", unit=u.unit.name, code=code, decision="stopping")
            return
        decision = self.decide(u, code)
        if decision.startswith("restart"):
            failed = decision == "restart after failure"
            u.failures = u.failures + 1 if failed else 0
            delay = min(60.0, 2.0 ** (u.failures - 1)) if failed else 1.0
            u.restarts += 1
            u.state, u.start_at = "waiting", time.monotonic() + delay
            log("unit_exited", unit=u.unit.name, code=code, decision=decision, restart_in_s=delay)
        else:
            u.state = "down" if decision.startswith("down") else "stopped"
            log("unit_exited", unit=u.unit.name, code=code, decision=decision)

    # stopping

    def stop_all(self) -> None:
        """Reverse start order: a unit stops once every unit that starts after it has stopped, and units with no
        order between them stop together, so the stop takes the longest chain of graces (R20)."""
        need, chain = longest_stop(self.decl)
        log("stopping", longest_stop_s=need, chain=chain, stop_timeout_s=self.decl.stop_timeout_s)
        dependents = {n: [m for m in self.order if n in self.units[m].unit.after] for n in self.order}
        done: Set[str] = set()
        level = 0
        t0 = time.monotonic()
        while len(done) < len(self.order):
            ready = [n for n in self.order if n not in done and all(d in done for d in dependents[n])]
            level += 1
            log("stop_level", level=level, units=ready)
            running = [self.units[n] for n in ready if self.units[n].pid is not None]
            for u in running:
                if self.marker_only:
                    _signal([u.pid], signal.SIGTERM)
                    u.marker_found = carrying_marker(u.unit.name)
                    _signal(u.marker_found, signal.SIGTERM)
                else:
                    _signal([u.pid], signal.SIGTERM)  # its supervisor ends the unit's whole tree
            deadline = time.monotonic() + max((u.unit.stop_grace_s for u in running), default=0) + 2
            while any(u.pid is not None for u in running) and time.monotonic() < deadline:
                self.reap()
                time.sleep(0.05)
            for u in running:
                if u.pid is not None:
                    log("unit_stop_overran", unit=u.unit.name, pid=u.pid)
                    _signal([u.pid], signal.SIGKILL)
                if self.marker_only:
                    left = carrying_marker(u.unit.name)
                    _signal(left, signal.SIGKILL)
                    log("marker_sweep", unit=u.unit.name, termed=getattr(u, "marker_found", []), killed=left)
            self.reap()
            done.update(ready)
        log("stopped", elapsed_s=round(time.monotonic() - t0, 2))

    # status (R07: status only; nothing a caller sends is read)

    def status(self) -> dict:
        need, chain = longest_stop(self.decl)
        return {"system": self.decl.system, "time_zone": self.decl.time_zone,
                "stop": "marker only (experiment)" if self.marker_only else "per-unit subreaper",
                "stop_timeout_s": self.decl.stop_timeout_s, "longest_stop_s": need, "longest_stop_chain": chain,
                "egress_rule": egress_rule_state(),
                "units": [{"name": n, "account": u.unit.account, "uid": u.uid, "pid": u.pid, "state": u.state,
                           "restarts": u.restarts, "last_exit": u.last_exit} for n, u in self.units.items()]}

    def open_status_socket(self) -> socket.socket:
        os.makedirs(os.path.dirname(STATUS_SOCKET), mode=0o755, exist_ok=True)
        try:
            os.unlink(STATUS_SOCKET)
        except FileNotFoundError:
            pass
        s = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        s.bind(STATUS_SOCKET)
        os.chmod(STATUS_SOCKET, 0o666)
        s.listen(8)
        s.setblocking(False)
        return s

    def answer_status(self, srv: socket.socket) -> None:
        while True:
            try:
                conn, _ = srv.accept()
            except BlockingIOError:
                return  # noqa: MACEFF003 - no connection waiting ends the pass; it is not a failure
            with conn:
                conn.settimeout(1)
                try:
                    conn.sendall(json.dumps(self.status()).encode() + b"\n")
                except OSError:
                    pass

    def serve(self) -> None:
        if not self.marker_only:
            set_subreaper()  # the last net: a supervisor that dies leaves its orphans here, not with tini

        def on_term(signum, frame):
            self.stop_requested = True

        signal.signal(signal.SIGTERM, on_term)
        signal.signal(signal.SIGINT, on_term)
        srv = self.open_status_socket()
        while not self.stop_requested:
            self.reap()
            self.start_due()
            self.answer_status(srv)
            time.sleep(0.05)
        self.stop_all()


def egress_rule_state() -> str:
    """R22 asks status to say whether the egress rule is loaded. Reading the rule needs CAP_NET_ADMIN, which R02's
    list of root's acts doesn't name; this prototype's image has no iptables, so it can only say so."""
    for d in os.environ.get("PATH", "/usr/sbin:/usr/bin:/sbin:/bin").split(":"):
        if os.access(os.path.join(d, "iptables"), os.X_OK):
            return "not read: reading it is outside R02's list of root's acts"
    return "unknown: this system has no iptables"


def main(argv: Optional[List[str]] = None) -> int:
    ap = argparse.ArgumentParser(prog="macf.sd.root", description=__doc__.split("\n\n")[0])
    ap.add_argument("declaration")
    ap.add_argument("--check", action="store_true", help="load and validate the declaration, start nothing")
    ap.add_argument("--experiment-stop-by-marker-only", action="store_true",
                    help="the prototype's comparison: no per-unit supervisor, stop by the environment marker")
    args = ap.parse_args(argv)
    if os.getuid() != 0:
        print("the system daemon runs as root", file=sys.stderr)
        return 2
    try:
        decl, parser_uid = parse_unprivileged(open_declaration(args.declaration))
    except DeclarationRefused as e:
        log("declaration_refused", reason=str(e))
        return EX_CONFIG
    if any(u.platform.kind != "linux" or u.platform.stop != "subreaper" for u in decl.units):
        log("declaration_refused", reason="this prototype stops units by subreaper on Linux only")
        return EX_CONFIG
    log("declaration_loaded", system=decl.system, parser_uid=parser_uid, start_order=start_order(decl),
        time_zone=decl.time_zone, stop_timeout_s=decl.stop_timeout_s)
    if args.check:
        return 0
    SystemDaemon(decl, marker_only=args.experiment_stop_by_marker_only).serve()
    return 0


if __name__ == "__main__":
    sys.exit(main())
