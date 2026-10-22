"""The primal daemon as a process: the core, its control socket, and its record.

``python -m macf.pd <agent home>`` is the whole command line an outer tier
renders (MIS-0002-R04 (outer_tier_MUST-NOT_hold_agent_config)). Everything else comes
from the home: the declaration from its ``.maceff/pd/``, and the identity from its own
files, never from the environment (MIS-0002-R02 (pd_MUST-NOT_take_identity_from_env)).

The control socket is a Unix socket only (MIS-0002-R80 (pd_MUST-NOT_listen_on_network)).
It serves one request per connection, one JSON object per line each way, and only to
the daemon's own user, which the kernel reports. A request line has one deadline to arrive
whole, and a request that fails inside the daemon costs that request alone, so no client
can hold or end the loop that supervises the units. The record beside it is written after
the socket is bound, so a client that finds a record finds a daemon it can reach.
"""
import os
import selectors
import socket
import sys
import time
from pathlib import Path
from typing import Callable, Iterable, List, Optional

from pydantic import ValidationError

from macf.agent_events_log import append_event, read_events
from macf.notify.session import descends_from, proc_start, verify_incarnation
from macf.pd.core import POLICY_POINTER, Core, DeclarationRefused, load_declaration
from macf.pd.interface import (
    EVENT_CHANNEL_DECLARED,
    EVENT_CONTROL,
    ActRequest,
    ChannelHello,
    Control,
    DaemonRecord,
    EntryAddRequest,
    EntryListRequest,
    EntryRemoveRequest,
    EVENT_STREAM_RULE,
    IdentityError,
    PaceRequest,
    Peer,
    Response,
    StatusRequest,
    StreamRule,
    StreamRuleRequest,
    WakePaced,
    agent_card,
    channel_socket,
    check_socket_path,
    control_socket,
    parse_request,
    ensure_runtime_dir,
    events_socket,
    record_path,
    runtime_dir,
)
from macf.pd.channel_watch import DarkChannel
from macf.pd.unread_mail import UnreadMail, pickup_box
from macf.pd.notifier import Notifier
from macf.utils.peercred import peer_credentials

#: The askers an act over the control socket may name. The daemon's own policy and the harness
#: ask from inside, so no requesting process exists to record (MIS-0002-R52
#: (control_act_MUST_name_who_asked)). A pace, which acts on no unit, names the agent or the
#: operator (``PaceRequest``).
SOCKET_ASKERS = ("operator", "wind_down")

#: How often the core makes its pass when nothing else wakes the loop.
TICK_S = 0.25

#: How often a running daemon refreshes its record. Without XDG_RUNTIME_DIR the record
#: lives in /tmp, and macOS's tmp_cleaner deletes a regular file there once it has gone
#: three days unread, unwritten and unchanged; the sockets and their directory are never
#: taken. An hour keeps the record far inside that window at no measurable cost.
RECORD_REFRESH_S = 3600.0

#: The notice a denied grant raises (MIS-0002-R65); the channel names its pointer.
GRANT_NOTICE_SOURCE = "pd_grant_denied"

#: How long a connected client has to send its whole request line, and the daemon to send
#: its reply.
REQUEST_TIMEOUT_S = 2.0

#: The longest request line read; anything longer is refused, not buffered.
MAX_REQUEST_BYTES = 64 * 1024

#: How long an attached channel has to send its hello (MIS-0002-R149). One that sends none in
#: time declares nothing and stays attached; one whose hello is still partial then is dropped.
HELLO_TIMEOUT_S = 2.0

#: The longest hello read. A channel's hello is a list of source names, far below this.
MAX_HELLO_BYTES = 8 * 1024


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

    def __init__(self, agent_home: Path, *, base: Optional[Path] = None,
                 record_refresh_s: float = RECORD_REFRESH_S,
                 managed_settings: Optional[List[Path]] = None,
                 grant_probes: Optional[Callable[[], Iterable[dict]]] = None, **core_options):
        #: Where the organization allowlist is read: None, the client's own paths.
        self._managed = list(managed_settings) if managed_settings is not None else None
        #: The recorded grant probes, newest first: None, the event log.
        self._grant_probes = grant_probes
        self._record_refresh_s = record_refresh_s
        self._record_kept = time.monotonic()
        self.home = Path(agent_home)
        self.card = card_for_home(self.home)
        self.base = Path(base) if base else runtime_dir()
        self.control_path = control_socket(self.card, self.base)
        self.record_path = record_path(self.card, self.base)
        self.channel_path = channel_socket(self.card, self.base)
        self.events_path = events_socket(self.card, self.base)
        check_socket_path(self.control_path)
        check_socket_path(self.channel_path)
        check_socket_path(self.events_path)
        placeholders = {"agent_home": str(self.home), "card": self.card, "runtime_dir": str(self.base)}
        self.core = Core(load_declaration(self.home, self.card), self.card,
                         placeholders=placeholders, **core_options)
        #: The declared schedules and the agent's own entries, run by this daemon (MIS-0002 step
        #: 2). It runs with no schedule declared, since an agent's entries need it all the same.
        from macf.pd.names import rendered_declaration_path
        from macf.pd.scheduler import Scheduler
        # A rendered declaration is out of the agent's reach; a home copy is checked against
        # what pd install recorded (MIS-0002-R33 (run_MUST-NOT_change_schedules)).
        self.scheduler = Scheduler(self.core.declaration, self.card, placeholders,
                                   work_dir=self.base / f"{self.record_path.stem}.runs",
                                   check_installed=not rendered_declaration_path(self.home).exists())
        #: The event stream (persistent_layer 11.4): the log, followed and fanned out.
        from macf.agent_events_log import get_log_path
        from macf.pd.stream import EventStream
        self.stream = EventStream(self.card, get_log_path(), self.core.declaration.stream_grants)
        self._events_bound: Optional[tuple] = None
        self._listener: Optional[socket.socket] = None
        self._channel_listener: Optional[socket.socket] = None
        self._channel_bound: Optional[tuple] = None     # (st_dev, st_ino) of the channel socket bound
        #: Each attached channel still owed its hello: (deadline, peer pid, bytes so far).
        self._hellos: dict = {}
        # The stream's rules, read live at each delivery: _bind_stream folds them anew at start
        # and a stream rule changes them at runtime (MIS-0002-R152).
        self.notifier = Notifier(self.home, self.core.declaration.notice_routes,
                                 rules=lambda: self.stream.rules)
        #: The agent's duties, hosted so a duty that falls due wakes it (the scheduler design, 4.4).
        from macf.agent_events_log import append_event, read_events
        from macf.pd.duties import HostedDuties
        from macf.roles.location import ROLES_DIR_ENV
        from macf.roles.source import EVENT as DUTY_EVENT
        roles = Path(os.environ.get(ROLES_DIR_ENV) or self.home / "agent" / "public" / "roles")
        self.duties = HostedDuties(self.card, roles, append_event,
                                   lambda: read_events(reverse=False, scope="all", only=(DUTY_EVENT,)),
                                   self.notifier.raise_notice, time.monotonic)
        self.core.on_notice = self.notifier.raise_notice    # the core's own notices (R60)
        self.scheduler.on_notice = self.notifier.raise_notice   # a denied prompt run (R32)
        half = self.core.declaration.half_served_routes()
        if half:
            print(f"⚠️ MACF: pd: notice_routes routes {', '.join(half)} to 'both', and only the agent's half "
                  f"is served: the operator hears unread mail alone today, so the rest reach the agent only "
                  f"(MIS-0002-R42)", file=sys.stderr)
        connect_s = self.core.declaration.channel_connect_s
        #: Where a channel is expected, whether it is dark (R115); the outside watch tells the operator.
        self.dark_channel = DarkChannel(self.card, connect_s) if connect_s else None
        #: Where a threshold is declared, mail left unread past it (R55): one notice per spell.
        threshold = self.core.declaration.unread_mail_threshold_s
        self.unread_mail = UnreadMail(self.card, threshold, pickup_box(self.home),
                                      self.notifier.raise_notice) if threshold else None
        #: Where the keystroke wake's window in force came from, for a status or a pace to say.
        self._wake_from = "the declaration"
        if any(u.kind == "session" for u in self.core.declaration.units):
            # The keystroke fallback types into the session unit's own pane (pd.session_unit),
            # recording each wake first so it never reads as the operator (MIS-0002-R105).
            from macf.pd.wake import TmuxPane, Waker, saved_screens_dir
            from macf.supervisor import record_keys_sent
            from macf.utils.identity import session_identifier
            ident = session_identifier(self.card)
            self.notifier.waker = Waker(TmuxPane(ident, self.base),
                                        record_keys=lambda text, kind: record_keys_sent(text, kind, ident),
                                        card=self.card, screens_dir=saved_screens_dir(self.home),
                                        refractory_s=self.core.declaration.wake_refractory_s)
        self._sel: Optional[selectors.BaseSelector] = None
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
        self.channel_path.unlink(missing_ok=True)   # the slot is ours, so a socket left here is a dead daemon's
        channel = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        channel.bind(str(self.channel_path))
        st = os.stat(self.channel_path)
        self._channel_bound = (st.st_dev, st.st_ino)
        os.chmod(self.channel_path, 0o600)
        channel.listen(4)
        channel.setblocking(False)
        self._channel_listener = channel
        self._bind_stream()
        record = self._record = self._write_record()
        self.core.record_start(record.pid, record.proc_start)
        self._compare_allowlist()
        self.core.boot()
        self._publish_units()
        self.notifier.boot()
        self._notice_denied_grants()
        self._reassert_pace()
        if self.unread_mail is not None:
            self.unread_mail.boot()
        self.scheduler.boot()
        self.duties.boot()

    def _bind_stream(self) -> None:
        """Bind the event stream's socket, fold the operator's rules from the log, and learn this
        process's own appends as it makes them, so they carry ``origin: daemon``."""
        from macf.agent_events_log import add_append_listener
        from macf.pd.stream import fold_rules
        self.stream.rules = fold_rules(read_events(reverse=False, scope="all", only=(EVENT_STREAM_RULE,)),
                                       self.card)
        self.stream.bind(self.events_path)
        st = os.stat(self.events_path)
        self._events_bound = (st.st_dev, st.st_ino)
        add_append_listener(self.stream.note_own_append)

    def _publish_units(self) -> None:
        """Publish a summary of this agent's units into its own public tree, for its peers in a
        shared container (MIS-0002-R62 (agent_MUST_see_shared_container)): names, kinds, limits,
        restart rules, never a command or environment (``shared_view.summarize``). The
        declaration is read only at start, so a changed declaration is published by the restart
        that loads it. A home with no public tree has no peers reading it, and gets none made.
        Publishing never stops the daemon: a failure is said, and peers read the home as
        UNPUBLISHED, or see the old summary's age."""
        from macf.pd import shared_view
        if not (self.home / "agent" / "public").is_dir():
            return
        try:
            shared_view.publish(self.home, self.core.declaration)
        except Exception as e:  # noqa: BLE001 - GUARD, not handler: a peer's view must not end the daemon
            print(f"⚠️ MACF: pd: could not publish this agent's units at "
                  f"{shared_view.published_path(self.home)} (the daemon goes on; peers see "
                  f"no summary or an old one, with its age): {e!r}", file=sys.stderr)

    def _notice_denied_grants(self) -> None:
        """Owe the agent a notice for each declared grant the last install found denied
        (MIS-0002-R65 (denied_grant_MUST_raise_notice)). The probe runs only at install,
        where a person can answer its dialogs, so a start reads its record instead of
        probing again. The notice's id names the grant; the event log holds the rest."""
        import re
        from macf.agent_events_log import read_events
        from macf.pd.cli import EVENT_GRANT_PROBE
        probes = self._grant_probes or (lambda: read_events(reverse=True, scope="all",
                                                            only=(EVENT_GRANT_PROBE,)))
        declared = {g for u in self.core.declaration.units for g in u.privacy_grants}
        for event in probes():
            data = event.get("data") or {}
            if not isinstance(data, dict) or data.get("agent") != self.card:
                continue
            if not data.get("tested"):
                # The newest install couldn't test them, so nothing older speaks for them now.
                print(f"⚠️ MACF: pd: the last pd install couldn't test the declared grants "
                      f"({data.get('why', 'no reason recorded')}); none is noticed as denied", file=sys.stderr)
                return
            verdicts = data.get("verdicts") or {}
            stamp = int(event.get("timestamp") or 0)
            for grant in sorted(g for g, v in verdicts.items() if v == "denied" and g in declared):
                print(f"⚠️ MACF: pd: the declared grant {grant} was denied when pd install last "
                      f"tested it", file=sys.stderr)
                self.notifier.raise_notice(GRANT_NOTICE_SOURCE,
                                           f"pd_grant_denied:{re.sub(r'[^A-Za-z0-9._:-]', '-', grant)}:{stamp}")
            return                     # only the newest probe speaks for the grants now

    def _compare_allowlist(self) -> None:
        """Say at start where the organization allowlist and the declaration disagree
        (MIS-0002-R124 (allowlist_declaration_MUST_list_every_channel)). Managed settings can
        change after ``pd install`` compared them, and a channel the list leaves out stops
        loading at the session's next start. The daemon runs on: its units don't depend on it."""
        from macf.agent_events_log import append_event
        from macf.pd import allowlist
        from macf.pd.interface import EVENT_ALLOWLIST_MISMATCH

        try:
            found = allowlist.findings(self.core.declaration, allowlist.managed_allowlist(self._managed))
        except (OSError, ValueError) as e:
            found = [f"the managed settings can't be read, so the organization allowlist can't be "
                     f"compared with the declaration: {e}"]
        if not found:
            return
        for line in found:
            print(f"⚠️ MACF: pd: {line}", file=sys.stderr)
        append_event(EVENT_ALLOWLIST_MISMATCH, {"agent": self.card, "findings": found})

    def serve(self) -> None:
        """Run until ``stop``, then remove the socket and record. The units keep running for
        the next daemon to adopt unless the stop asked for them too, so a restart through
        the outer tier restarts the daemon alone."""
        sel = self._sel = selectors.DefaultSelector()
        self.notifier.on_detach = self._channel_gone
        self.stream.on_register = lambda conn: sel.register(conn, selectors.EVENT_READ, "subscriber")
        self.stream.on_unregister = sel.unregister
        sel.register(self.stream.listener, selectors.EVENT_READ, "events")
        sel.register(self._listener, selectors.EVENT_READ, "control")
        sel.register(self._channel_listener, selectors.EVENT_READ, "channel")
        sel.register(self._wake_r, selectors.EVENT_READ, "wake")
        try:
            while not self._stopping:
                for key, _ in sel.select(timeout=TICK_S):
                    if key.data == "control":
                        self._accept()
                    elif key.data == "channel":
                        self._accept_channel()
                    elif key.data == "attached":
                        self._channel_readable(key.fileobj)
                    elif key.data == "events":
                        self.stream.accept()
                    elif key.data == "subscriber":
                        self.stream.readable(key.fileobj)
                    else:
                        os.read(self._wake_r, 512)
                self.core.tick()
                self.scheduler.tick()
                self._hellos_due()
                self.notifier.poll()
                self.notifier.flush()
                self.notifier.wake()
                if self.dark_channel is not None:
                    self.dark_channel.tick(self.core.session_incarnation(), bool(self.notifier.channels))
                if self.unread_mail is not None:
                    self.unread_mail.tick(self.core.session_active_since())
                self.duties.tick()
                self._pump_stream()
                self._keep_record()
        finally:
            for conn in self.notifier.channels:
                self.notifier.detach(conn)
            self.notifier.on_detach = None
            self.stream.on_unregister = None
            self.stream.close()
            self.scheduler.shutdown()
            sel.close()
            self._sel = None
            if self._stop_units:
                self.core.shutdown("every unit stopped as asked, with the daemon")
            self._release()

    def _pump_stream(self) -> None:
        """One pass of the event stream. A failure inside it costs the stream's pass, never the
        loop that supervises the units (MIS-0002-R153 (subscriber_MUST-NOT_block_layer))."""
        try:
            self.stream.pump()
        except Exception as e:  # noqa: BLE001 - GUARD, not handler: the stream must not end the daemon
            print(f"⚠️ MACF: pd: the event stream's pass failed (the daemon goes on): {e!r}", file=sys.stderr)

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

    def _keep_record(self) -> None:
        """Touch the record now and then, so a temp-directory cleaner never takes it for
        abandoned; write it again if one already has. It is this daemon's own record, and
        ``pd status`` believes the daemon only through it."""
        now = time.monotonic()
        if now - self._record_kept < self._record_refresh_s:
            return
        self._record_kept = now
        try:
            os.utime(self.record_path)
        except FileNotFoundError:
            print(f"⚠️ MACF: pd: the record at {self.record_path} was removed while the daemon ran; "
                  "writing it again", file=sys.stderr)
            self._record = self._write_record()
        except OSError as e:
            print(f"⚠️ MACF: pd: could not refresh the record at {self.record_path}: {e}", file=sys.stderr)

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
        if self._channel_listener is not None:
            self._channel_listener.close()
        from macf.agent_events_log import remove_append_listener
        remove_append_listener(self.stream.note_own_append)
        self.stream.close()
        for path, still_mine in ((self.control_path, self._socket_is_mine),
                                 (self.channel_path, self._channel_is_mine),
                                 (self.events_path, self._events_is_mine),
                                 (self.record_path, self._record_is_mine)):
            try:
                if still_mine():
                    path.unlink()
            except FileNotFoundError:
                continue  # already gone, which is what a release wants
            except (OSError, ValidationError) as e:
                print(f"⚠️ MACF: pd: could not release {path}: {e}", file=sys.stderr)

    def _channel_is_mine(self) -> bool:
        st = os.stat(self.channel_path)
        return (st.st_dev, st.st_ino) == self._channel_bound

    def _events_is_mine(self) -> bool:
        st = os.stat(self.events_path)
        return (st.st_dev, st.st_ino) == self._events_bound

    def _socket_is_mine(self) -> bool:
        st = os.stat(self.control_path)
        return (st.st_dev, st.st_ino) == self._bound

    def _record_is_mine(self) -> bool:
        record = DaemonRecord.model_validate_json(self.record_path.read_text())
        return self._record is not None and (record.pid, record.proc_start) == (
            self._record.pid, self._record.proc_start)

    # ------------------------------------------------------------------ requests

    # ------------------------------------------------------------------ the channel

    def _accept_channel(self) -> None:
        """Attach a MacEff channel to the notifier, but only one whose process descends
        from the session unit's live process. Every command the agent runs has the same
        uid, so the uid alone can't tell the session's channel from anything else
        (MIS-0002-R122 (pd_MUST_check_channel_peer_lineage)). A channel that connects
        while no session runs is refused, and connects again: its notices are held."""
        try:
            conn, _ = self._channel_listener.accept()
        except BlockingIOError:
            return  # noqa: MACEFF003 - nothing was pending: a spurious wakeup, not a failure
        try:
            peer = peer_credentials(conn)
        except OSError as e:
            print(f"⚠️ MACF: pd: cannot read a channel's peer (refusing it): {e}", file=sys.stderr)
            conn.close()
            return
        why = self._outside_session(peer)
        if why:
            print(f"⚠️ MACF: pd: refused a channel: {why}", file=sys.stderr)
            conn.close()
            return
        conn.setblocking(False)
        self.notifier.attach(conn)          # declaring nothing until its hello (R149)
        self._hellos[conn] = (time.monotonic() + HELLO_TIMEOUT_S, peer.pid, b"")
        if self._sel is not None:
            self._sel.register(conn, selectors.EVENT_READ, "attached")
        print(f"📡 MACF: pd: channel attached (pid {peer.pid}); "
              f"{len(self.notifier.owed)} notice(s) owed", file=sys.stderr)

    def _outside_session(self, peer) -> str:
        """Why ``peer`` isn't the agent's live session, or "" when it is: the same uid, and a
        process that descends from the session unit's live process. Every command the agent
        runs shares the uid, so lineage is what tells the session from a cron job, a run or
        another shell (MIS-0002-R122 (pd_MUST_check_channel_peer_lineage)). The channel is
        checked this way, and so are an agent's requests about its own entries."""
        session = self.core.session_incarnation()
        if peer.uid == os.getuid() and session is not None and descends_from(peer.pid, *session):
            return ""
        return ("no session unit runs" if session is None
                else f"pid {peer.pid} (uid {peer.uid}) is not below the session unit's pid {session[0]}")

    def _channel_readable(self, conn: socket.socket) -> None:
        """A channel writes one line, its hello, right after it attaches (MIS-0002-R149
        (pd_MUST_hold_sources_channel_did_not_declare)). A partial hello is kept until its
        line ends or its time runs out; the read never blocks the loop. After the hello, a
        readable channel has closed or broken the protocol, and either way it is dropped."""
        try:
            data = conn.recv(4096)
        except BlockingIOError:
            return  # noqa: MACEFF003 - a spurious wakeup, not a failure
        except OSError:
            data = b""
        pending = self._hellos.get(conn)
        if pending is None or not data:
            if data:
                print("⚠️ MACF: pd: a channel wrote to the daemon after its hello, which channels "
                      "never do; dropping it", file=sys.stderr)
            self.notifier.detach(conn)
            return
        deadline, pid, got = pending
        got += data
        if b"\n" not in got:
            if len(got) > MAX_HELLO_BYTES:
                self._drop_hello(conn, f"its hello ran past {MAX_HELLO_BYTES} bytes with no line end")
            else:
                self._hellos[conn] = (deadline, pid, got)
            return
        line, rest = got.split(b"\n", 1)
        if rest:
            self._drop_hello(conn, "it wrote more after its hello")
            return
        try:
            hello = ChannelHello.model_validate_json(line)
        except ValidationError as e:
            self._drop_hello(conn, f"its hello is malformed ({e.error_count()} problem(s))")
            return
        del self._hellos[conn]
        takes = sorted(set(hello.hello.takes))
        self.notifier.declare(conn, takes)
        append_event(EVENT_CHANNEL_DECLARED, {"agent": self.card, "pid": pid, "takes": takes})
        print(f"📡 MACF: pd: the channel (pid {pid}) takes {', '.join(takes) or 'nothing'}", file=sys.stderr)

    def _drop_hello(self, conn: socket.socket, why: str) -> None:
        print(f"⚠️ MACF: pd: dropping a channel: {why} (MIS-0002-R149)", file=sys.stderr)
        self.notifier.detach(conn)

    def _hellos_due(self) -> None:
        """End each hello wait whose time ran out. A channel that sent nothing declares nothing
        and stays attached, so it is sent nothing and its notices stay held; one that sent part
        of a line broke the protocol."""
        now = time.monotonic()
        for conn, (deadline, pid, got) in list(self._hellos.items()):
            if now < deadline:
                continue
            if got:
                self._drop_hello(conn, f"its hello didn't end within {HELLO_TIMEOUT_S:g} s")
                continue
            del self._hellos[conn]
            print(f"⚠️ MACF: pd: the channel (pid {pid}) sent no hello within {HELLO_TIMEOUT_S:g} s; it "
                  f"declares no source, so every notice is held for one that does (MIS-0002-R149)",
                  file=sys.stderr)

    def _channel_gone(self, conn: socket.socket) -> None:
        """The notifier is closing ``conn``: stop watching it, and stop waiting on its hello."""
        self._hellos.pop(conn, None)
        if self._sel is not None:
            self._sel.unregister(conn)

    # ------------------------------------------------------------------ requests

    def _accept(self) -> None:
        try:
            conn, _ = self._listener.accept()
        except BlockingIOError:
            return  # noqa: MACEFF003 - nothing was pending: a spurious wakeup, not a failure
        with conn:
            conn.setblocking(True)
            conn.settimeout(REQUEST_TIMEOUT_S)
            try:
                response = self._handle(conn)
            except Exception as e:  # noqa: BLE001 - GUARD, not handler: one request must not end the daemon
                # Deliberately broad, as the core's pass is: a request that fails inside the
                # daemon costs that request, and is announced and answered, never absorbed. A
                # failure of the listener itself still ends the daemon, so its outer tier binds a
                # fresh one.
                print(f"⚠️ MACF: pd: a control request failed (the daemon goes on): {e!r}",
                      file=sys.stderr)
                response = Response(ok=False, error=f"the request failed inside the daemon: {e}")
            if not response.ok:
                # Every refusal, now and later, names the policy that explains it.
                response = response.model_copy(
                    update={"error": f"{response.error}\n{POLICY_POINTER}"})
            conn.settimeout(REQUEST_TIMEOUT_S)   # reading the line spent the first one
            try:
                conn.sendall(response.model_dump_json(exclude_none=True).encode() + b"\n")
            except OSError as e:
                print(f"⚠️ MACF: pd: the reply was not delivered: {e}", file=sys.stderr)

    def _handle(self, conn: socket.socket) -> Response:
        try:
            creds = peer_credentials(conn)
        except OSError as e:
            return Response(ok=False, error=f"the peer cannot be identified: {e}")
        operator_uid = self.core.declaration.operator_uid
        if creds.uid != os.getuid() and creds.uid != operator_uid:
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
        if isinstance(request, StreamRuleRequest):
            return self._stream_rule(request, creds)
        if creds.uid != os.getuid():
            return Response(ok=False, error="this socket serves only the daemon's own user, but for the "
                                            "operator's rules for the event stream")
        if isinstance(request, (EntryAddRequest, EntryListRequest, EntryRemoveRequest)):
            return self._entry_request(request, creds)
        if isinstance(request, StatusRequest):
            return Response(ok=True, units=self.core.statuses(), **self._wake_window())
        if isinstance(request, PaceRequest):
            return self._pace(request, creds)
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

    def _entry_request(self, request, creds) -> Response:
        """An agent's request about its own entries, taken only from its live session. A
        relative time is fixed now, so "in 20m" means the same moment after a restart. The
        event log is the store: what is held is what its events fold to."""
        from datetime import datetime, timezone
        from zoneinfo import ZoneInfo

        from macf.agent_events_log import append_event, read_events
        from macf.pd.entries import (ENTRY_EVENTS, EVENT_ENTRY_ADDED, EVENT_ENTRY_REMOVED, OneShot, fold, new_entry_id,
                                     parse_when)
        from macf.pd.taint import taint
        why = self._outside_session(creds)
        if why and isinstance(request, EntryAddRequest):
            return Response(ok=False, error=f"an entry is made only from the agent's live session, and {why}")
        if isinstance(request, EntryRemoveRequest):
            held = fold(read_events(reverse=False, scope="all", only=ENTRY_EVENTS), self.card)
            if request.id not in held:
                return Response(ok=False, error=f"no entry {request.id} is held")
            removed = {"agent": self.card, "id": request.id, "at": datetime.now(timezone.utc).isoformat(),
                       "by_pid": creds.pid, "from_session": not why}
            if not append_event(EVENT_ENTRY_REMOVED, removed):
                return Response(ok=False, error="the removal could not be recorded in the event log")
            self.scheduler.entries.pop(request.id, None)
        if isinstance(request, EntryAddRequest):
            zone = self.core.declaration.timezone
            tz = ZoneInfo(zone) if zone else timezone.utc
            now = datetime.now(timezone.utc)
            try:
                when = parse_when(request.when, tz, now)
            except ValueError as e:
                return Response(ok=False, error=f"the entry's time was refused: {e}")
            first = when.next_after(now)
            if request.action == "check":
                why = self.scheduler.template_refusal(request.template, request.args)
                if why:
                    return Response(ok=False, error=f"the check was refused: {why}")
            # The operator's consent is the ask prompt on pd entry add, met before this request
            # was made. Taint is kept as provenance: an entry made after untrusted input is marked,
            # and says so wherever it's shown (the scheduler design, 5.3, as the repo owner ruled
            # it on #744). The whole log is asked for, and the scan stops at the context's boundary.
            marked = taint(read_events(reverse=True, scope="all"))
            entry = {"agent": self.card, "id": new_entry_id(),
                     "when": first.isoformat() if isinstance(when, OneShot) else request.when,
                     "start": now.isoformat(), "zone": zone or "UTC", "first": first.isoformat() if first else None,
                     "purpose": request.purpose, "action": request.action, "missed": request.missed,
                     "asked_by_pid": creds.pid, "marked": marked,
                     "template": request.template, "args": request.args}
            if not append_event(EVENT_ENTRY_ADDED, entry):
                return Response(ok=False, error="the entry could not be recorded in the event log")
            self.scheduler.add_entry(entry)
        held = fold(read_events(reverse=False, scope="all", only=ENTRY_EVENTS), self.card)
        return Response(ok=True, entries=list(held.values()))

    # ------------------------------------------------------------------ the event stream's rules

    def _stream_rule(self, request: StreamRuleRequest, creds) -> Response:
        """The operator silences, unsilences or reroutes a source or a subscriber of the event
        stream, the agent's session among them as ``@channel`` (MIS-0002-R152
        (operator_MUST_silence_and_reroute)). The rule is recorded as a
        ``pd_stream_rule`` event before it takes effect, so the next daemon folds it back, and
        takes effect at once. Where the declaration names the operator's own uid, as in a
        container, only that uid may set one; elsewhere the client's ask prompt on the command is
        the operator's act (persistent_layer 11.4)."""
        operator_uid = self.core.declaration.operator_uid
        if operator_uid is not None and creds.uid != operator_uid:
            return Response(ok=False, error=(f"the event stream's rules are taken only from the operator's "
                                             f"uid {operator_uid}, not uid {creds.uid}"))
        started = proc_start(creds.pid)
        if not started:
            return Response(ok=False, error=(
                f"the asking process (pid {creds.pid}) has no start time to record, "
                f"so who asked cannot be named (MIS-0002-R52 (control_act_MUST_name_who_asked))"))
        rule = StreamRule(agent=self.card, act=request.act, target=request.target,
                          subscriber=request.subscriber, asked_by=request.asked_by,
                          peer=Peer(uid=creds.uid, pid=creds.pid, proc_start=started), reason=request.reason)
        if not append_event(EVENT_STREAM_RULE, rule.model_dump()):
            return Response(ok=False, error=("the rule could not be recorded, so it is not set: a rule the "
                                             "next daemon cannot read back would be lost at its restart"))
        self.stream.rules.apply(rule.act, rule.target, rule.subscriber)
        return Response(ok=True, stream_rules=self.stream.rules.as_dict())

    # ------------------------------------------------------------------ the wake's pace

    def _wake_window(self) -> dict:
        """The keystroke wake's window in force and where it came from, for a reply; nothing
        where no session unit is declared, since there is no keystroke wake."""
        waker = self.notifier.waker
        if waker is None:
            return {}
        return {"wake_refractory_s": waker.refractory_s, "wake_window_from": self._wake_from}

    def _pace(self, request: PaceRequest, creds) -> Response:
        """The agent, or the operator, sets how long the keystroke wake rests (persistent_layer
        1.9). The floor comes only from the declaration, never from this socket. The pace is
        recorded like every act, and in ``pd_wake_paced``, which the next daemon re-asserts,
        before the waker changes and before it is answered."""
        from macf.pd.wake import EVENT_PACED, pace_refusal, pace_source
        if self.notifier.waker is None:
            return Response(ok=False, error="no session unit is declared, so there is no keystroke wake to pace")
        declaration = self.core.declaration
        refused = pace_refusal(request.refractory_s, declaration.wake_refractory_floor_s,
                               declaration.wake_refractory_ceiling_s)
        if refused:
            return Response(ok=False, error=refused)
        started = proc_start(creds.pid)
        if not started:
            return Response(ok=False, error=(
                f"the asking process (pid {creds.pid}) has no start time to record, "
                f"so who asked cannot be named (MIS-0002-R52 (control_act_MUST_name_who_asked))"))
        peer = Peer(uid=creds.uid, pid=creds.pid, proc_start=started)
        paced = WakePaced(agent=self.card, refractory_s=request.refractory_s,
                          previous_s=self.notifier.waker.refractory_s, asked_by=request.asked_by,
                          peer=peer, reason=request.reason)
        if not append_event(EVENT_PACED, paced.model_dump()):
            return Response(ok=False, error=(
                "the pace could not be recorded, so it is not set: a pace the next daemon "
                "cannot read back would be lost at its restart"))
        if not append_event(EVENT_CONTROL, Control(agent=self.card, act="pace", unit="",
                                                   asked_by=request.asked_by, peer=peer,
                                                   reason=request.reason).model_dump()):
            print(f"⚠️ MACF: pd: the pace's {EVENT_CONTROL} event was not recorded", file=sys.stderr)
        back_to_declared = request.refractory_s is None
        self.notifier.pace(declaration.wake_refractory_s if back_to_declared else request.refractory_s)
        self._wake_from = ("the declaration" if back_to_declared
                           else pace_source(time.time(), request.asked_by.kind, request.reason))
        return Response(ok=True, **self._wake_window())

    def _reassert_pace(self) -> None:
        """A pace outlives the daemon that set it. At start, the newest ``pd_wake_paced`` of this
        agent is read back once and re-asserted, naming the event it came from; a floor declared
        above it since then wins, and the daemon says so."""
        if self.notifier.waker is None:
            return
        from macf.pd.wake import EVENT_PACED, window_at_boot
        # A lifetime read, scope "all": a pace holds until another replaces it, across compactions,
        # restarts and log rotation, so no cycle bounds where the newest one is. It stops there.
        newest = next((e for e in read_events(reverse=True, scope="all", only={EVENT_PACED})
                       if (e.get("data") or {}).get("agent") == self.card), None)
        declaration = self.core.declaration
        window, source = window_at_boot(declaration.wake_refractory_s,
                                        declaration.wake_refractory_floor_s, newest,
                                        declaration.wake_refractory_ceiling_s)
        self.notifier.pace(window)
        self._wake_from = source
        if newest is not None:
            print(f"maceff_pd: the wake rests {window:g} s after each wake, from {source}", file=sys.stderr)

    @staticmethod
    def _read_line(conn: socket.socket) -> Optional[str]:
        """The first line the client sent, or None when it sent no complete line.

        The whole line has one deadline, so a client that sends a byte at a time cannot hold
        the loop for longer than a client that sends nothing. A spent deadline or a broken
        connection raises, so the reply can say which."""
        deadline = time.monotonic() + REQUEST_TIMEOUT_S
        late = f"no complete request line within {REQUEST_TIMEOUT_S:g} s"
        chunks: List[bytes] = []
        size = 0
        while size <= MAX_REQUEST_BYTES:
            left = deadline - time.monotonic()
            if left <= 0:
                raise TimeoutError(late)
            conn.settimeout(left)
            try:
                chunk = conn.recv(4096)
            except TimeoutError as e:   # socket.timeout is TimeoutError from Python 3.10
                raise TimeoutError(late) from e
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
