"""Observation and attach (MIS-0002 R81-R102, R111).

Attach: R100 (attach_MUST_resolve_from_pd) and R101 (readout_MUST_say_nothing_attachable).
Observation acts: R82, R86-R90, R92, R94 and R111. The stream: R83, R84, R85 and R93.
"""
import json as _json
from dataclasses import dataclass

import pytest

from macf.observe import acts, stream
from macf.utils.attach import CLIENT, NONE, TMUX, plan_attach, readout_line


@dataclass
class _Info:
    session_id: str
    kind: str


def _resp(state="running", pid=4187, proc_start="Sat Oct 10 10:23:30 2026"):
    return {"ok": True, "units": [{"unit": "session", "state": state, "pid": pid,
                                   "proc_start": proc_start, "since": 0.0}]}


def _plan(response, info=None, verified=True, chain=(4187, 4120, 4094), panes=None, **kw):
    return plan_attach(response, "session",
                       read_info=lambda pid: info,
                       verify=lambda pid, start: verified,
                       ancestors=lambda pid: list(chain),
                       tmux_panes=lambda: dict(panes or {}), **kw)


def test_attach_resolves_from_pd():
    """The daemon's pid decides: a client-hosted session attaches through the client,
    a tmux one by exact session name, never by a name lookup."""
    hosted = _plan(_resp(), info=_Info("32149023-da95-480f-bb4a-866d6bc083a0", "bg"))
    assert hosted.kind == CLIENT
    assert hosted.argv == ["claude", "attach", "32149023-da95-480f-bb4a-866d6bc083a0"]

    in_tmux = _plan(_resp(), info=_Info("89f47c46-71a2", "interactive"), panes={4120: "IraMacEff_ee9a78"})
    assert in_tmux.kind == TMUX
    assert in_tmux.argv == ["tmux", "attach", "-t", "=IraMacEff_ee9a78", "-d"]
    ro = _plan(_resp(), info=None, panes={4094: "x"}, read_only=True, control=True)
    assert ro.argv == ["tmux", "-CC", "attach", "-t", "=x", "-r"]


def test_no_answer_is_not_a_name_lookup():
    """A daemon that does not answer resolves nothing, even with a tmux session of the agent's name."""
    plan = _plan(None, panes={4120: "IraMacEff_ee9a78"})
    assert plan.kind == NONE and "did not answer" in plan.reason
    refused = _plan({"ok": False, "error": "peer is not the daemon's user"})
    assert refused.kind == NONE and "peer" in refused.reason


def test_a_recycled_pid_is_not_attached():
    plan = _plan(_resp(), info=_Info("x", "bg"), verified=False)
    assert plan.kind == NONE and "no longer" in plan.reason


def test_nothing_attachable_said():
    """R101: a stopped unit, a missing unit and a bare terminal each say why there is nothing to attach to."""
    stopped = _plan(_resp(state="stopped", pid=None))
    assert stopped.kind == NONE and "stopped" in stopped.reason
    missing = _plan({"ok": True, "units": []})
    assert missing.kind == NONE and "no unit named 'session'" in missing.reason
    bare = _plan(_resp(), info=_Info("x", "interactive"), panes={})
    assert bare.kind == NONE and "not under tmux" in bare.reason
    assert readout_line(bare).startswith("Attach:       nothing attachable hosts this session (")
    assert "claude attach" in readout_line(_plan(_resp(), info=_Info("abc", "bg")))


# ---------------------------------------------------------------------------
# Observation acts (R82, R86-R90, R92, R94, R111): events in the observed agent's log
# ---------------------------------------------------------------------------

ME, THEM = "IraMacEff@ee9a78", "OnlookerAgent@ab12cd"


def _host(card):
    return None


def _log(*events):
    return list(events)


def _invited(lease_until=None, now=None):
    inv = acts.invite(ME, THEM, 1200, {}, container_of=_host, lease_until=lease_until, now=now)
    return inv, _log(inv.event)


def test_onlooker_needs_invitation():
    """R82: nothing is admitted before the invitation, and only with its own secret after."""
    assert acts.admit(THEM, "anything", acts.fold([]), now=1500.0) is None
    inv, log = _invited()
    state = acts.fold(log)
    assert acts.admit(THEM, inv.secret, state, now=1500.0).stream_from == 1200
    assert acts.admit(THEM, "a guess", state, now=1500.0) is None
    assert acts.admit("SomeoneElse@abcdef", inv.secret, state, now=1500.0) is None


def test_observation_events():
    """R90: invite, pause, resume and end are each an event; the log, folded, is the state."""
    inv, log = _invited()
    log.append(acts.pause(THEM, acts.fold(log), at=1300))
    log.append(acts.resume(THEM, acts.fold(log), at=1400))
    log.append(acts.end(THEM, "observed", acts.fold(log)))
    assert [e["event"] for e in log] == [acts.EVENT_INVITE, acts.EVENT_PAUSE, acts.EVENT_RESUME, acts.EVENT_END]
    assert acts.fold(log)[THEM].status == acts.ENDED


def test_the_log_never_holds_the_secret():
    inv, log = _invited()
    assert inv.secret not in str(log) and len(inv.event["data"]["secret_sha256"]) == 64


def test_pause_resume():
    """R92: the owner pauses and resumes; a paused observation is still admitted, to show the pause."""
    inv, log = _invited()
    log.append(acts.pause(THEM, acts.fold(log), at=1300))
    state = acts.fold(log)
    assert state[THEM].status == acts.PAUSED and acts.admit(THEM, inv.secret, state, now=1500.0) is not None
    with pytest.raises(acts.ActRefused):
        acts.pause(THEM, state, at=1350)
    log.append(acts.resume(THEM, state, at=1400))
    assert acts.fold(log)[THEM].status == acts.ACTIVE


def test_a_pause_withholds_from_where_it_was_taken():
    """R92: a pause records the transcript offset at the pause and at the resume. The
    transcript only grows, so an offset earlier than the last one recorded is refused; a
    resume before its own pause would otherwise withhold nothing."""
    inv, log = _invited()
    with pytest.raises(acts.ActRefused):
        acts.pause(THEM, acts.fold(log), at=1100)          # before the invitation's offset
    log.append(acts.pause(THEM, acts.fold(log), at=1300))
    with pytest.raises(acts.ActRefused):
        acts.resume(THEM, acts.fold(log), at=1250)         # would end before it began
    log.append(acts.resume(THEM, acts.fold(log), at=1400))
    with pytest.raises(acts.ActRefused):
        acts.pause(THEM, acts.fold(log), at=1350)          # inside the range already withheld
    log.append(acts.pause(THEM, acts.fold(log), at=1500))
    assert acts.fold(log)[THEM].pauses == ((1300, 1400), (1500, None))


def test_either_party_ends():
    """R86: the observed agent or the onlooker ends it; after that nothing is admitted."""
    for who in ("observed", "onlooker"):
        inv, log = _invited()
        log.append(acts.end(THEM, who, acts.fold(log)))
        state = acts.fold(log)
        assert state[THEM].ended_by == who and acts.admit(THEM, inv.secret, state, now=1500.0) is None


def test_operator_ends():
    """R87: the operator may end any observation."""
    inv, log = _invited()
    log.append(acts.end(THEM, "operator", acts.fold(log)))
    assert acts.fold(log)[THEM].ended_by == "operator"
    with pytest.raises(acts.ActRefused):
        acts.end(THEM, "a passer-by", acts.fold(_invited()[1]))


def test_lease_ends_invitation():
    """R88: a lease ends the invitation at its declared time."""
    inv, log = _invited(lease_until=2000.0, now=1000.0)
    assert acts.expired(acts.fold(log), now=1999.0) == []
    owed = acts.expired(acts.fold(log), now=2000.0)
    log.extend(owed)
    state = acts.fold(log)
    assert state[THEM].status == acts.ENDED and acts.admit(THEM, inv.secret, state, now=1500.0) is None
    with pytest.raises(acts.ActRefused):
        acts.invite(ME, THEM, 0, {}, container_of=_host, lease_until=5.0, now=10.0)


def test_lease_end_same_event():
    """R89: a lease's end is the same event a party's end is, told apart only by who ended it."""
    _, log = _invited(lease_until=2000.0, now=1000.0)
    by_lease = acts.expired(acts.fold(log), now=3000.0)[0]
    by_party = acts.end(THEM, "onlooker", acts.fold(log))
    assert by_lease["event"] == by_party["event"] == acts.EVENT_END
    assert set(by_lease["data"]) == set(by_party["data"])
    assert by_lease["data"]["ended_by"] == "lease"


def test_onlooker_by_card():
    """R94: an invitation names its onlooker by calling card, never by login user."""
    for name in ("someuser", "operator", "OnlookerAgent", "OnlookerAgent@AB12CD", "OnlookerAgent@ab12cdx"):
        with pytest.raises(acts.ActRefused):
            acts.invite(ME, name, 0, {}, container_of=_host)
    with pytest.raises(acts.ActRefused):
        acts.invite(ME, ME, 0, {}, container_of=_host)


def test_no_invitation_across_containers():
    """R111: an agent in one container does not invite an onlooker in another, and an
    onlooker that cannot be placed is not invited either."""
    places = {ME: "container-a", THEM: "container-b"}
    with pytest.raises(acts.ActRefused):
        acts.invite(ME, THEM, 0, {}, container_of=places.get)
    places[THEM] = "container-a"
    assert acts.invite(ME, THEM, 0, {}, container_of=places.get).event["event"] == acts.EVENT_INVITE

    def unknown(card):
        raise LookupError("no such agent here")
    with pytest.raises(acts.ActRefused):
        acts.invite(ME, THEM, 0, {}, container_of=unknown)


def test_a_live_observation_is_not_invited_twice():
    _, log = _invited()
    with pytest.raises(acts.ActRefused):
        acts.invite(ME, THEM, 5, acts.fold(log), container_of=_host)
    log.append(acts.end(THEM, "observed", acts.fold(log)))
    again = acts.invite(ME, THEM, 5, acts.fold(log), container_of=_host)
    log.append(again.event)
    assert acts.fold(log)[THEM].status == acts.ACTIVE and acts.fold(log)[THEM].stream_from == 5


def test_a_lapsed_lease_is_not_admitted_before_its_end_is_logged():
    """R88: the lease ends the invitation at its time, not at the next sweep."""
    inv, log = _invited(lease_until=2000.0, now=1000.0)
    state = acts.fold(log)
    assert state[THEM].status == acts.ACTIVE  # no end event yet
    assert acts.admit(THEM, inv.secret, state, now=1999.0) is not None
    assert acts.admit(THEM, inv.secret, state, now=2000.0) is None


# ---------------------------------------------------------------------------
# The stream (R83, R84, R85, R93): from the invitation on, what a person would see, no input
# ---------------------------------------------------------------------------


def _row(**kw):
    return _json.dumps(kw) + "\n"


def _transcript(tmp_path, rows):
    p = tmp_path / "session.jsonl"
    p.write_text("".join(rows))
    return p


BEFORE = _row(type="user", origin={"kind": "human"}, message={"content": "a secret plan from before"})
AFTER = [
    _row(type="user", origin={"kind": "human"}, message={"content": "please run the tests"}),
    _row(type="assistant", message={"content": [
        {"type": "thinking", "thinking": "private reasoning"},
        {"type": "text", "text": "Running them now."},
        {"type": "tool_use", "name": "Bash", "input": {"command": "pytest -q", "description": "Run the tests"}}]}),
    _row(type="user", message={"content": [{"type": "tool_result", "content": "token=abc123 leaked output",
                                            "is_error": False}]}),
    _row(type="attachment", attachment={"type": "hook_additional_context", "content": "hook text"}),
    _row(type="user", isMeta=True, message={"content": "Base directory for this skill: ..."}),
    _row(type="user", isMeta=True, origin={"kind": "channel"},
         message={"content": '<channel source="plugin:telegram:telegram" chat_id="8660107588" message_id="9">'
                             'are you done?</channel>'}),
]


class _Clock:
    def __init__(self, t=1500.0):
        self.t = t

    def __call__(self):
        return self.t


def _said(text):
    return _row(type="assistant", message={"content": [{"type": "text", "text": text}]})


def _write(path, *rows):
    with open(path, "a") as fh:
        fh.write("".join(rows))
    return path.stat().st_size


def _serve_once(path, state_log, rounds=1, clock=None, on_send=None, wait=None):
    """Serve THEM's observation, as admitted now, for ``rounds`` reads."""
    sent = []

    def send(frame):
        sent.append(frame)
        if on_send:
            on_send(frame)
    stream.serve(send, acts.fold(state_log)[THEM], lambda: acts.fold(state_log),
                 lambda off: stream.rows_from(path, off), clock or _Clock(), wait or (lambda: None),
                 rounds=rounds)
    return sent


def test_stream_starts_at_invitation(tmp_path):
    """R84: nothing from before the invitation's offset is ever sent."""
    path = _transcript(tmp_path, [BEFORE] + AFTER)
    offset = len(BEFORE.encode())
    inv = acts.invite(ME, THEM, offset, {}, container_of=_host)
    sent = _serve_once(path, [inv.event])
    assert "a secret plan from before" not in str(sent)
    assert sent[0] == {"t": "", "kind": "prompt", "text": "please run the tests"}


def test_what_a_person_would_see_and_no_more(tmp_path):
    path = _transcript(tmp_path, AFTER)
    inv = acts.invite(ME, THEM, 0, {}, container_of=_host)
    kinds = [f["kind"] for f in _serve_once(path, [inv.event])]
    assert kinds == ["prompt", "agent", "tool", "result", "channel"]
    text = str(_serve_once(path, [inv.event]))
    for withheld in ("private reasoning", "token=abc123", "hook text", "Base directory", "8660107588"):
        assert withheld not in text
    assert "Run the tests" in text and "plugin:telegram:telegram" in text and "are you done?" in text


def test_stream_stops_at_end(tmp_path):
    """R85: the end is read before every frame, so nothing follows it."""
    path = _transcript(tmp_path, AFTER)
    inv = acts.invite(ME, THEM, 0, {}, container_of=_host)
    log = [inv.event]

    def end_after_first(frame):
        if frame.get("kind") == "prompt":
            log.append(acts.end(THEM, "observed", acts.fold(log)))
    sent = _serve_once(path, log, rounds=2, on_send=end_after_first)
    assert [f["kind"] for f in sent] == ["prompt", "ended"]


def test_a_lease_that_runs_out_stops_the_stream(tmp_path):
    path = _transcript(tmp_path, AFTER)
    inv = acts.invite(ME, THEM, 0, {}, container_of=_host, lease_until=1600.0, now=1000.0)
    clock = _Clock(1500.0)

    def tick(frame):
        clock.t = 1700.0
    sent = _serve_once(path, [inv.event], rounds=2, clock=clock, on_send=tick)
    assert sent[0]["kind"] == "prompt" and sent[-1] == {"kind": "ended"} and len(sent) == 2


def test_pause_shown(tmp_path):
    """R93: a stream that reaches a pause says so, once, and sends nothing past it. One
    opened after the resume sends what came before and after the pause, and marks the gap."""
    path = _transcript(tmp_path, AFTER[:1])
    inv = acts.invite(ME, THEM, 0, {}, container_of=_host)
    log = [inv.event]
    log.append(acts.pause(THEM, acts.fold(log), at=path.stat().st_size))
    held = _write(path, _said("SECRET printed while paused"))
    sent = _serve_once(path, log, rounds=3)
    assert [f["kind"] for f in sent] == ["prompt", "paused"]
    log.append(acts.resume(THEM, acts.fold(log), at=held))
    _write(path, _said("after the resume"))
    later = _serve_once(path, log)
    assert [f.get("text") or f["kind"] for f in later] == [
        "please run the tests", "paused", "resumed", "after the resume"]
    assert "SECRET" not in str(sent + later)


class _Sock:
    def __init__(self, first_line):
        self._incoming = [first_line]
        self.recv_calls = 0
        self.out = b""

    def recv(self, n):
        self.recv_calls += 1
        return self._incoming.pop(0) if self._incoming else b"typed into the session\n"

    def sendall(self, data):
        self.out += data


def test_onlooker_has_no_keyboard(tmp_path):
    """R83: the socket is read for the one handshake line and never again."""
    path = _transcript(tmp_path, AFTER)
    inv = acts.invite(ME, THEM, 0, {}, container_of=_host)
    log = [inv.event]
    sock = _Sock(_json.dumps({"onlooker": THEM, "secret": inv.secret}).encode() + b"\n")
    stream.serve_connection(sock, lambda: acts.fold(log), lambda off: stream.rows_from(path, off),
                            _Clock(), lambda: None, poll_rounds=3)
    assert sock.recv_calls == 1 and b"please run the tests" in sock.out
    assert b"typed into the session" not in sock.out


def test_a_wrong_secret_is_refused_and_told(tmp_path):
    path = _transcript(tmp_path, AFTER)
    inv = acts.invite(ME, THEM, 0, {}, container_of=_host)
    sock = _Sock(_json.dumps({"onlooker": THEM, "secret": "guess"}).encode() + b"\n")
    why = stream.serve_connection(sock, lambda: acts.fold([inv.event]), lambda off: stream.rows_from(path, off),
                                  _Clock(), lambda: None, poll_rounds=1)
    assert why == "not admitted" and b"refused" in sock.out and b"please run" not in sock.out


def test_a_half_written_row_waits(tmp_path):
    p = tmp_path / "t.jsonl"
    p.write_text(AFTER[0] + '{"type": "user", "mess')
    rows = list(stream.rows_from(p, 0))
    assert len(rows) == 1 and rows[0][0] == len(AFTER[0].encode())


def test_what_is_written_during_a_pause_is_never_sent(tmp_path):
    """R92: the pause protects what is printed while it holds; resuming must not replay it."""
    path = _transcript(tmp_path, [_said("before the pause")])
    inv = acts.invite(ME, THEM, 0, {}, container_of=_host)
    log = [inv.event]
    rounds = {"n": 0}

    def wait():
        rounds["n"] += 1
        if rounds["n"] == 1:      # after the first frame: the owner pauses, then prints a secret
            log.append(acts.pause(THEM, acts.fold(log), at=path.stat().st_size))
            _write(path, _said("SECRET printed while paused"))
        elif rounds["n"] == 3:    # the owner resumes, then work goes on
            log.append(acts.resume(THEM, acts.fold(log), at=path.stat().st_size))
        elif rounds["n"] == 4:
            _write(path, _said("after the resume"))

    sent = _serve_once(path, log, rounds=6, wait=wait)
    texts = [f.get("text") or f["kind"] for f in sent]
    assert texts == ["before the pause", "paused", "resumed", "after the resume"]
    assert "SECRET" not in str(sent)


@pytest.mark.parametrize("between", ["reads", "rows"])
def test_a_pause_the_stream_never_saw_still_withholds(tmp_path, between):
    """R92: a pause and its resume can both fall between two of the stream's reads, or
    between two rows of one read, so every check finds the observation active. What was
    written between them is still withheld, because the pause records where it began."""
    path = _transcript(tmp_path, [_said("before the pause")])
    inv = acts.invite(ME, THEM, 0, {}, container_of=_host)
    log = [inv.event]

    def pause_print_resume(frame=None):
        if len(log) == 1:
            log.append(acts.pause(THEM, acts.fold(log), at=path.stat().st_size))
            log.append(acts.resume(THEM, acts.fold(log), at=_write(path, _said("SECRET printed while paused"))))
            _write(path, _said("after the resume"))
    hook = {"wait": pause_print_resume} if between == "reads" else {"on_send": pause_print_resume}
    sent = _serve_once(path, log, rounds=3, **hook)
    assert [f.get("text") or f["kind"] for f in sent] == [
        "before the pause", "paused", "resumed", "after the resume"]
    assert "SECRET" not in str(sent)


def test_an_end_and_a_new_invitation_the_stream_never_saw_still_end_it(tmp_path):
    """R85: an end followed at once by a new invitation for the same onlooker leaves an
    active observation at the next check, but not this one: its secret is new. The stream
    ends instead of serving the new invitation from the old one's place."""
    path = _transcript(tmp_path, [_said("before the end")])
    inv = acts.invite(ME, THEM, 0, {}, container_of=_host)
    log = [inv.event]

    def end_and_invite_again():
        if len(log) == 1:
            log.append(acts.end(THEM, "observed", acts.fold(log)))
            again = acts.invite(ME, THEM, _write(path, _said("PRIVATE, written with nobody invited")),
                                acts.fold(log), container_of=_host)
            log.append(again.event)
            _write(path, _said("for the new invitation"))
    sent = _serve_once(path, log, rounds=3, wait=end_and_invite_again)
    assert sent == [{"t": "", "kind": "agent", "text": "before the end"}, {"kind": "ended"}]
