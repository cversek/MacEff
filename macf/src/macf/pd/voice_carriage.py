"""The primal daemon's half of the MacEff Voice Input Channel, for one agent (MIS-0008 6.2, 6.3).

An utterance travels one path: the declared capture unit hands it to its agent's daemon on the
control socket, and the daemon hands it to the session's Voice Input Channel on the voice socket.
This module is the daemon's part of that path:

  * it takes an utterance only from a process of the capture unit the voice section names,
    checked by the kernel's peer pid against that unit's live process (MIS-0008 R12);
  * it sets the utterance's id and capture unit itself, from the transport, and passes the
    capture unit's closed verdicts on unchanged (R05);
  * it serves the voice socket only to a channel below the session's live process, the check
    the Notification Channel's socket makes (MIS-0002-R122), and sends utterances only to a
    channel whose hello says it takes them;
  * it records each utterance's metadata and never its words (R10), and answers every one with
    a receipt (R11).

An utterance that finds no channel ready is refused, not held: dictation delivered after the
operator has moved on would read as if it were said now. The capture unit gets the refusal as
its receipt and can say so, so the speech doesn't vanish silently.
"""
from __future__ import annotations

import os
import secrets
import selectors
import socket
import sys
import time
from pathlib import Path
from typing import Callable, Dict, Optional

from pydantic import ValidationError

from macf.agent_events_log import append_event
from macf.notify.session import descends_from
from macf.pd.interface import (EVENT_VOICE_CHANNEL_DECLARED, EVENT_VOICE_GUARD, EVENT_VOICE_UNMATCHED,
                               EVENT_VOICE_UTTERANCE, ChannelHello, Response, VoiceEventRequest, VoiceGuardRequest,
                               UtteranceRecord, UtteranceRequest, VoiceSection)
from macf.utils.peercred import peer_credentials

#: How long a newly attached voice channel has to send its hello.
HELLO_TIMEOUT_S = 2.0
#: The longest hello line taken; a channel that writes more broke the protocol.
MAX_HELLO_BYTES = 8 * 1024
#: The source a voice channel's hello must name to be sent utterances.
TAKES = "utterance"


def new_utterance_id() -> str:
    """An id for one utterance, unique across restarts: the time in nanoseconds and a random tail."""
    return f"utt-{time.time_ns()}-{secrets.token_hex(3)}"


class _Attached:
    """One voice channel attached to the socket: its pid, its hello so far, and whether it said
    it takes utterances."""

    def __init__(self, pid: int, deadline: float):
        self.pid = pid
        self.deadline = deadline
        self.got = b""
        self.ready = False


class VoiceCarriage:
    """The voice socket and the utterance request, for an agent whose declaration has a voice section.

    ``outside_session(peer)`` is the daemon's own lineage check: "" when ``peer`` descends from
    the session's live process, else why not. ``incarnation(unit)`` is the core's live (pid,
    proc_start) for a unit, or None.
    """

    def __init__(self, card: str, path: Path, voice: VoiceSection,
                 outside_session: Callable[[object], str],
                 incarnation: Callable[[str], Optional[tuple]]):
        self.card = card
        self.path = Path(path)
        self.voice = voice
        self._outside_session = outside_session
        self._incarnation = incarnation
        self.listener: Optional[socket.socket] = None
        self._bound: Optional[tuple] = None
        self.channels: Dict[socket.socket, _Attached] = {}
        #: The daemon's selector while it serves, so a channel is watched and unwatched here.
        self.selector: Optional[selectors.BaseSelector] = None

    # ------------------------------------------------------------------ the socket

    def bind(self) -> socket.socket:
        """Bind the voice socket, readable and writable by the daemon's user alone."""
        self.path.unlink(missing_ok=True)   # the daemon's slot is claimed, so a socket here is a dead daemon's
        listener = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        listener.bind(str(self.path))
        st = os.stat(self.path)
        self._bound = (st.st_dev, st.st_ino)
        os.chmod(self.path, 0o600)
        listener.listen(4)
        listener.setblocking(False)
        self.listener = listener
        return listener

    def release(self) -> None:
        """Close every channel and the listener, and remove the socket while it is still ours."""
        for conn in list(self.channels):
            self._drop(conn, None)
        if self.listener is not None:
            self.listener.close()
            self.listener = None
        if self._still_ours():
            self.path.unlink(missing_ok=True)

    def _still_ours(self) -> bool:
        """Whether the socket at the path is the one this daemon bound: False when it's gone (what a
        release wants), another daemon's, or unreadable (said on stderr)."""
        try:
            st = os.stat(self.path)
        except FileNotFoundError:
            return False
        except OSError as e:
            print(f"⚠️ MACF: pd: could not read the voice socket to release it: {e}", file=sys.stderr)
            return False
        return (st.st_dev, st.st_ino) == self._bound

    def accept(self) -> None:
        """Attach a voice channel, but only one below the session's live process (MIS-0002-R122)."""
        try:
            conn, _ = self.listener.accept()
        except BlockingIOError:
            return  # noqa: MACEFF003 - nothing was pending: a spurious wakeup, not a failure
        try:
            peer = peer_credentials(conn)
        except OSError as e:
            print(f"⚠️ MACF: pd: cannot read a voice channel's peer (refusing it): {e}", file=sys.stderr)
            conn.close()
            return
        why = self._outside_session(peer)
        if why:
            print(f"⚠️ MACF: pd: refused a voice channel: {why}", file=sys.stderr)
            conn.close()
            return
        conn.setblocking(False)
        self.channels[conn] = _Attached(peer.pid, time.monotonic() + HELLO_TIMEOUT_S)
        if self.selector is not None:
            self.selector.register(conn, selectors.EVENT_READ, "voice_attached")
        print(f"🎙️ MACF: pd: voice channel attached (pid {peer.pid})", file=sys.stderr)

    def readable(self, conn: socket.socket) -> None:
        """A voice channel writes one line, its hello, and nothing after. Anything else, or its
        closing, drops it."""
        attached = self.channels.get(conn)
        if attached is None:
            return
        try:
            data = conn.recv(4096)
        except BlockingIOError:
            return  # noqa: MACEFF003 - a spurious wakeup, not a failure
        except OSError:
            data = b""
        if not data:
            self._drop(conn, "it closed")
            return
        if attached.ready:
            self._drop(conn, "it wrote after its hello, which channels never do")
            return
        attached.got += data
        if b"\n" not in attached.got:
            if len(attached.got) > MAX_HELLO_BYTES:
                self._drop(conn, f"its hello ran past {MAX_HELLO_BYTES} bytes with no line end")
            return
        line, rest = attached.got.split(b"\n", 1)
        if rest:
            self._drop(conn, "it wrote more after its hello")
            return
        try:
            hello = ChannelHello.model_validate_json(line)
        except ValidationError as e:
            self._drop(conn, f"its hello is malformed ({e.error_count()} problem(s))")
            return
        if TAKES not in hello.hello.takes:
            self._drop(conn, f"its hello doesn't take {TAKES!r}, so it isn't a Voice Input Channel")
            return
        attached.ready = True
        append_event(EVENT_VOICE_CHANNEL_DECLARED, {"agent": self.card, "pid": attached.pid})
        print(f"🎙️ MACF: pd: the voice channel (pid {attached.pid}) takes utterances", file=sys.stderr)

    def hellos_due(self) -> None:
        """Drop each channel whose hello didn't arrive in time: a voice channel that declares
        nothing is sent nothing, and holding it would only hide that."""
        now = time.monotonic()
        for conn, attached in list(self.channels.items()):
            if not attached.ready and now >= attached.deadline:
                self._drop(conn, f"it sent no hello within {HELLO_TIMEOUT_S:g} s")

    def _drop(self, conn: socket.socket, why: Optional[str]) -> None:
        attached = self.channels.pop(conn, None)
        if why and attached is not None:
            print(f"⚠️ MACF: pd: dropping the voice channel (pid {attached.pid}): {why}", file=sys.stderr)
        if self.selector is not None:
            try:
                self.selector.unregister(conn)
            except (KeyError, ValueError):  # noqa: S110 - never registered, or already closed: nothing to unwatch
                pass
        conn.close()

    # ------------------------------------------------------------------ utterances

    def utterance(self, request: UtteranceRequest, peer) -> Response:
        """Take one utterance from the capture unit and deliver it, or refuse it; either way the
        capture unit gets a receipt (R11) and the log gets the metadata (R10)."""
        utterance_id = new_utterance_id()
        unit = self.voice.capture_unit
        live = self._incarnation(unit)
        if live is None or not descends_from(peer.pid, *live):
            why = (f"the capture unit {unit!r} isn't running" if live is None
                   else f"pid {peer.pid} is not a process of the capture unit {unit!r}")
            return self._receipt(request, utterance_id, None, "refused",
                                 f"an utterance comes only from the declared capture unit: {why} (MIS-0008 R12)",
                                 peer_pid=peer.pid)
        record = UtteranceRecord(utterance_id=utterance_id, trigger=request.trigger, spoken_at=request.spoken_at,
                                 screen=request.screen, voice_lock=request.voice_lock, capture_unit=unit,
                                 text=request.text)
        line = record.model_dump_json().encode() + b"\n"
        sent = 0
        for conn, attached in list(self.channels.items()):
            if not attached.ready:
                continue
            try:
                conn.sendall(line)
                sent += 1
            except OSError as e:
                self._drop(conn, f"sending an utterance failed: {e}")
        if not sent:
            return self._receipt(request, utterance_id, unit, "refused",
                                 "no Voice Input Channel is attached to the session, so the words were dropped, "
                                 "not held (MIS-0008 R11)")
        return self._receipt(request, utterance_id, unit, "delivered", None)

    def _receipt(self, request: UtteranceRequest, utterance_id: str, unit: Optional[str], receipt: str,
                 reason: Optional[str], **extra) -> Response:
        return receipt_for(self.card, request, utterance_id, unit, receipt, reason, **extra)


    # ------------------------------------------------------------------ the voice lock's notices and the guard

    def guard_until(self, now: Optional[float] = None) -> Optional[float]:
        """When the raised guard ends, or None when none is raised. Read from the log, the one
        durable record, so a daemon restart never lowers a guard (R42)."""
        from macf.agent_events_log import read_events
        for event in read_events(reverse=True, scope="all", only=(EVENT_VOICE_GUARD,)):
            data = event.get("data") or {}
            if data.get("agent") != self.card:
                continue
            until = data.get("raised_until")
            return until if until is not None and until > (now or time.time()) else None
        return None

    def voice_event(self, request: VoiceEventRequest, peer, raise_notice: Callable[[str, str], bool]) -> Response:
        """The capture unit's word that the voice lock failed or locked out: a notice without
        content for the agent (R37), and on a lockout the guard raised (R42). Taken only from the
        declared capture unit, as an utterance is (R12)."""
        unit = self.voice.capture_unit
        live = self._incarnation(unit)
        if live is None or not descends_from(peer.pid, *live):
            return Response(ok=False, error=f"a voice event comes only from the declared capture unit {unit!r} (MIS-0008 R12)")
        stamp = time.time_ns()
        if request.kind == "unmatched":
            append_event(EVENT_VOICE_UNMATCHED, {"agent": self.card, "attempts": request.attempts, "of": request.of})
            raise_notice("pd_voice_unmatched", f"pd_voice_unmatched:{stamp}")
            return Response(ok=True)
        until = request.until if request.until is not None else time.time() + self.voice.lockout_s
        append_event(EVENT_VOICE_GUARD, {"agent": self.card, "raised_until": until, "by": "lockout"})
        raise_notice("pd_voice_lockout", f"pd_voice_lockout:{stamp}")
        return Response(ok=True, voice_guard_until=until)

    def lower_guard(self, request: VoiceGuardRequest) -> Response:
        """Only the operator lowers a raised guard before its period ends (R44)."""
        if request.asked_by.kind != "operator":
            return Response(ok=False, error="only the operator lowers a raised voice guard before its period ends "
                                            "(MIS-0008 R44)")
        if self.guard_until() is None:
            return Response(ok=True)
        append_event(EVENT_VOICE_GUARD, {"agent": self.card, "raised_until": None, "by": "operator",
                                         "reason": request.reason})
        return Response(ok=True)


def receipt_for(card: str, request: UtteranceRequest, utterance_id: str, unit: Optional[str], receipt: str,
                reason: Optional[str], **extra) -> Response:
    """Record how one utterance ended, by its metadata and never its words (R10), and answer the
    capture unit with that receipt (R11)."""
    data = {"agent": card, "utterance_id": utterance_id, "trigger": request.trigger,
            "spoken_at": request.spoken_at, "screen": request.screen, "voice_lock": request.voice_lock,
            "capture_unit": unit, "receipt": receipt, "chars": len(request.text), **extra}
    if reason:
        data["reason"] = reason
    append_event(EVENT_VOICE_UTTERANCE, data)
    if receipt == "delivered":
        return Response(ok=True, receipt=receipt, utterance_id=utterance_id)
    return Response(ok=False, error=reason, receipt=receipt, utterance_id=utterance_id)


def refuse_without_voice(card: str, request: UtteranceRequest, peer) -> Response:
    """An utterance to an agent whose declaration has no voice section: refused, with its receipt
    and its metadata recorded, since speech must never vanish silently (R11)."""
    return receipt_for(card, request, new_utterance_id(), None, "refused",
                       "this agent's declaration has no voice section, so it takes no utterances (MIS-0008 R12)",
                       peer_pid=peer.pid)
