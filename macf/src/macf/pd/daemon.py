"""The primal daemon as a process: the core, its control socket, and its record.

``python -m macf.pd <agent home>`` is the whole command line an outer tier
renders (MIS-0002-R04 (outer_tier_MUST-NOT_hold_agent_config)). Everything else comes
from the home: the declaration from its ``.maceff/pd/``, and the identity from its own
files, never from the environment (MIS-0002-R02 (pd_MUST-NOT_take_identity_from_env)).

The control socket is a Unix socket only (MIS-0002-R80 (pd_MUST-NOT_listen_on_network)).
It serves one request per connection, one JSON object per line each way, and only to
the daemon's own user, which the kernel reports. The record beside it is written after
the socket is bound, so a client that finds a record finds a daemon it can reach.
"""
import os
import selectors
import socket
import sys
from pathlib import Path
from typing import List, Optional

from pydantic import ValidationError

from macf.notify.session import proc_start, verify_incarnation
from macf.pd.core import POLICY_POINTER, Core, DeclarationRefused, load_declaration
from macf.pd.interface import (
    ActRequest,
    DaemonRecord,
    IdentityError,
    Peer,
    Response,
    StatusRequest,
    agent_card,
    check_socket_path,
    control_socket,
    parse_request,
    ensure_runtime_dir,
    record_path,
    runtime_dir,
)
from macf.utils.peercred import peer_credentials

#: The askers a control-socket request may name. The daemon's own policy and the harness
#: ask from inside, so no requesting process exists to record (MIS-0002-R52
#: (control_act_MUST_name_who_asked)).
SOCKET_ASKERS = ("operator", "wind_down")

#: How often the core makes its pass when nothing else wakes the loop.
TICK_S = 0.25

#: How long a connected client has to send its request line.
REQUEST_TIMEOUT_S = 2.0

#: The longest request line read; anything longer is refused, not buffered.
MAX_REQUEST_BYTES = 64 * 1024


class AlreadyRunning(RuntimeError):
    """Another primal daemon of this agent is alive (MIS-0002-R01
    (agent_MUST_have_one_primal_daemon))."""


def card_for_home(agent_home: Path) -> str:
    """The calling card of the agent whose home this is, read from that home's own files
    by the step 1 interface and never from the environment (MIS-0002-R02
    (pd_MUST-NOT_take_identity_from_env)). A home that names no agent refuses the
    daemon's start, with the reason."""
    try:
        return agent_card(Path(agent_home))
    except IdentityError as e:
        raise DeclarationRefused(str(e)) from e


class Daemon:
    """One agent's primal daemon: ``start``, then ``serve`` until ``stop``."""

    def __init__(self, agent_home: Path, *, base: Optional[Path] = None, **core_options):
        self.home = Path(agent_home)
        self.card = card_for_home(self.home)
        self.base = Path(base) if base else runtime_dir()
        self.control_path = control_socket(self.card, self.base)
        self.record_path = record_path(self.card, self.base)
        check_socket_path(self.control_path)
        placeholders = {"agent_home": str(self.home), "card": self.card, "runtime_dir": str(self.base)}
        self.core = Core(load_declaration(self.home, self.card), self.card,
                         placeholders=placeholders, **core_options)
        self._listener: Optional[socket.socket] = None
        self._wake_r, self._wake_w = os.pipe()
        os.set_blocking(self._wake_w, False)
        self._stopping = False
        self._stop_units = False
        self._bound: Optional[tuple] = None             # (st_dev, st_ino) of the socket bound
        self._record: Optional[DaemonRecord] = None     # the record this daemon wrote

    # ------------------------------------------------------------------ life

    def start(self) -> None:
        """Claim the agent's daemon slot, bind the socket, publish the record, say the
        daemon started, boot."""
        ensure_runtime_dir(self.base)
        self._claim()
        listener = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        listener.bind(str(self.control_path))
        st = os.stat(self.control_path)
        self._bound = (st.st_dev, st.st_ino)
        os.chmod(self.control_path, 0o600)
        listener.listen(8)
        listener.setblocking(False)
        self._listener = listener
        record = self._record = self._write_record()
        self.core.record_start(record.pid, record.proc_start)
        self.core.boot()

    def serve(self) -> None:
        """Run until ``stop``, then remove the socket and record. The units keep running for
        the next daemon to adopt unless the stop asked for them too, so a restart through
        the outer tier restarts the daemon alone."""
        sel = selectors.DefaultSelector()
        sel.register(self._listener, selectors.EVENT_READ, "control")
        sel.register(self._wake_r, selectors.EVENT_READ, "wake")
        try:
            while not self._stopping:
                for key, _ in sel.select(timeout=TICK_S):
                    if key.data == "control":
                        self._accept()
                    else:
                        os.read(self._wake_r, 512)
                self.core.tick()
        finally:
            sel.close()
            if self._stop_units:
                self.core.shutdown("every unit stopped as asked, with the daemon")
            self._release()

    def stop(self, units: bool = False) -> None:
        """Ask ``serve`` to finish, and with ``units`` to stop every unit first; a plain stop,
        as a signal gives, leaves them running. Safe from a signal handler or another thread."""
        self._stop_units = self._stop_units or units
        self._stopping = True
        try:
            os.write(self._wake_w, b"x")
        except BlockingIOError:
            pass  # the pipe is full, so the loop is already awake

    # ------------------------------------------------------------------ the slot

    def _claim(self) -> None:
        if self.record_path.exists():
            try:
                record = DaemonRecord.model_validate_json(self.record_path.read_text())
            except (OSError, ValidationError) as e:
                print(f"⚠️ MACF: pd: the record at {self.record_path} is unreadable "
                      f"(checking the socket instead): {e}", file=sys.stderr)
                record = None
            if record is not None and verify_incarnation(record.pid, record.proc_start):
                raise AlreadyRunning(
                    f"{self.card}'s primal daemon already runs as pid {record.pid}")
        # Whatever the record says, a socket something answers on is a live daemon's: its
        # record can be missing, as after a sweep of the runtime directory.
        if self.control_path.exists() and self._socket_answers():
            raise AlreadyRunning(f"something answers on {self.control_path}")
        # What is left belongs to a daemon that is gone.
        self.control_path.unlink(missing_ok=True)
        self.record_path.unlink(missing_ok=True)

    def _socket_answers(self) -> bool:
        probe = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        probe.settimeout(1.0)
        try:
            probe.connect(str(self.control_path))
            return True
        except OSError:
            return False
        finally:
            probe.close()

    def _write_record(self) -> DaemonRecord:
        record = DaemonRecord(pid=os.getpid(), proc_start=proc_start(os.getpid()) or "unknown")
        tmp = self.record_path.with_name(self.record_path.name + ".tmp")
        tmp.write_text(record.model_dump_json())
        os.chmod(tmp, 0o600)
        os.replace(tmp, self.record_path)
        return record

    def _release(self) -> None:
        """Remove the socket and record only while they are still this daemon's. A daemon
        started after a missing record may already have bound the path and written its own."""
        if self._listener is not None:
            self._listener.close()
        for path, still_mine in ((self.control_path, self._socket_is_mine),
                                 (self.record_path, self._record_is_mine)):
            try:
                if still_mine():
                    path.unlink()
            except FileNotFoundError:
                continue  # already gone, which is what a release wants
            except (OSError, ValidationError) as e:
                print(f"⚠️ MACF: pd: could not release {path}: {e}", file=sys.stderr)

    def _socket_is_mine(self) -> bool:
        st = os.stat(self.control_path)
        return (st.st_dev, st.st_ino) == self._bound

    def _record_is_mine(self) -> bool:
        record = DaemonRecord.model_validate_json(self.record_path.read_text())
        return self._record is not None and (record.pid, record.proc_start) == (
            self._record.pid, self._record.proc_start)

    # ------------------------------------------------------------------ requests

    def _accept(self) -> None:
        try:
            conn, _ = self._listener.accept()
        except BlockingIOError:
            return  # noqa: MACEFF003 - nothing was pending: a spurious wakeup, not a failure
        with conn:
            conn.setblocking(True)
            conn.settimeout(REQUEST_TIMEOUT_S)
            response = self._handle(conn)
            if not response.ok:
                # Every refusal, now and later, names the policy that explains it.
                response = response.model_copy(
                    update={"error": f"{response.error}\n{POLICY_POINTER}"})
            try:
                conn.sendall(response.model_dump_json(exclude_none=True).encode() + b"\n")
            except OSError as e:
                print(f"⚠️ MACF: pd: the reply was not delivered: {e}", file=sys.stderr)

    def _handle(self, conn: socket.socket) -> Response:
        try:
            creds = peer_credentials(conn)
        except OSError as e:
            return Response(ok=False, error=f"the peer cannot be identified: {e}")
        if creds.uid != os.getuid():
            return Response(ok=False, error="this socket serves only the daemon's own user")
        try:
            line = self._read_line(conn)
        except OSError as e:
            return Response(ok=False, error=f"the request could not be read: {e}")
        if line is None:
            return Response(ok=False, error="no complete request line arrived")
        try:
            request = parse_request(line)
        except ValidationError as e:
            return Response(ok=False, error=f"request refused: {e.errors()[0]['msg']}")
        if isinstance(request, StatusRequest):
            return Response(ok=True, units=self.core.statuses())
        if isinstance(request, ActRequest):
            if request.asked_by.kind not in SOCKET_ASKERS:
                return Response(ok=False, error=(
                    f"a request over this socket is asked by the operator or the declared wind-down, "
                    f"not {request.asked_by.kind!r}: that asker acts from inside and has no process "
                    f"to record (MIS-0002-R52 (control_act_MUST_name_who_asked))"))
            started = proc_start(creds.pid)
            if not started:
                return Response(ok=False, error=(
                    f"the asking process (pid {creds.pid}) has no start time to record, "
                    f"so who asked cannot be named (MIS-0002-R52 (control_act_MUST_name_who_asked))"))
            peer = Peer(uid=creds.uid, pid=creds.pid, proc_start=started)
            act = {"start": self.core.start, "stop": self.core.stop,
                   "restart": self.core.restart}[request.op]
            try:
                act(request.unit, request.asked_by, request.reason, peer=peer)
            except KeyError as e:
                return Response(ok=False, error=str(e.args[0]))
            return Response(ok=True, units=self.core.statuses())
        return Response(ok=False, error="compaction is not available in step 1")

    @staticmethod
    def _read_line(conn: socket.socket) -> Optional[str]:
        """The first line the client sent, or None when it sent no complete line.
        A timeout or a broken connection raises, so the reply can say which."""
        chunks: List[bytes] = []
        size = 0
        while size <= MAX_REQUEST_BYTES:
            chunk = conn.recv(4096)
            if not chunk:
                break
            chunks.append(chunk)
            size += len(chunk)
            if b"\n" in chunk:
                break
        data = b"".join(chunks)
        if b"\n" not in data:
            return None
        return data.split(b"\n", 1)[0].decode("utf-8", errors="replace")
