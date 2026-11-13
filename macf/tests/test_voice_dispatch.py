"""One capture unit for several agents, and the signed route down to each (MIS-0008 R46 to R50;
MIS-0007 R29, R52, R55 to R57, R67)."""
from __future__ import annotations

import json
import socket

import pytest
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from pydantic import ValidationError

from macf.agent_events_log import read_events
from macf.amail.crypto import public_key_line
from macf.pd import broker as b
from macf.pd.interface import Declaration, VoiceSection
from macf.pd.voice_carriage import VoiceCarriage, _Attached
from macf.voice.capture.members import DispatchSender
from macf.voice.capture.unit import AgentBinding, CaptureConfig, CaptureUnit, InlineExecutor
from macf.voice.dispatch import (NonceRecord, Verifier, receipt_topic, sign_utterance, signing_payload,
                                 voice_topic)
from voice_fakes import (FRAME_S, SILENCE, SPEECH, WAKE, FakeAudio, FakeLock, LoudGate, PushedKeys,
                         RecordingIndicator, ScriptedTranscriber, WakeDetector, secs)

SYSTEM = "System_5a5e00"
ALPHA = "Alpha_aaa111"
BRAVO = "Bravo_bbb222"
NOW = 1794600000.0

KEY = Ed25519PrivateKey.generate()
OTHER_KEY = Ed25519PrivateKey.generate()


def registry(card):
    """The operator's registry, as a member reads it: only the system daemon has a key."""
    return [public_key_line(KEY)] if card == SYSTEM else []


def signed(target=ALPHA, *, key=KEY, now=NOW, lifetime=30.0, text="check the build", **over):
    fields = dict(signer=SYSTEM, target=target, private=key, now=now, lifetime_s=lifetime, trigger="wake_phrase",
                  spoken_at=now - 2, screen="unlocked", voice_lock="not_declared", capture_unit="voice-capture",
                  text=text)
    fields.update(over)
    return sign_utterance(**fields)


def verifier(card=ALPHA, **kw):
    return Verifier(card, SYSTEM, registry, **kw)


# ---------------------------------------------------------------- R46, R47: one unit, the target follows the trigger

class PhraseDetector(WakeDetector):
    """Fires on one agent's own wake frames, so two agents' phrases are told apart by frame."""

    def __init__(self, mark):
        self.mark = mark

    def score(self, frame):
        return 1.0 if frame[0] == self.mark else 0.0


ALPHA_WAKE = WAKE.copy()
BRAVO_WAKE = WAKE.copy() + 2      # a different loud frame: Bravo's phrase


def shared_unit(audio, transcriber, delivered, indicator=None):
    members = [AgentBinding(agent=ALPHA, wake_phrase="hey alpha", hold_key="KEY_F9",
                            detector=PhraseDetector(int(ALPHA_WAKE[0]))),
               AgentBinding(agent=BRAVO, wake_phrase="hey bravo", hold_key="KEY_F11", toggle_key="KEY_F12",
                            detector=PhraseDetector(int(BRAVO_WAKE[0])))]
    keys = PushedKeys()
    unit = CaptureUnit(CaptureConfig(agent=SYSTEM), audio=audio, lock=FakeLock(), indicator=indicator or
                       RecordingIndicator(), triggers=keys, gate=LoudGate(), transcribe=transcriber,
                       deliver=delivered.append, clock=lambda: audio.reads * FRAME_S,
                       wall=lambda: NOW + audio.reads * FRAME_S, executor=InlineExecutor(), members=members)
    return unit, keys


def run(unit, frames):
    for _ in range(frames):
        unit.tick()


def test_system_capture_serves_members():
    """R46: one capture unit hears each member's own phrase and sends each utterance to that member,
    showing the indicator for the agent it records for."""
    audio = FakeAudio().then((SILENCE, 3), (ALPHA_WAKE, secs(0.5)), (SPEECH, secs(1)), (SILENCE, secs(5)),
                             (BRAVO_WAKE, secs(0.5)), (SPEECH, secs(1)), (SILENCE, secs(5)))
    delivered, indicator = [], RecordingIndicator()
    unit, _ = shared_unit(audio, ScriptedTranscriber("hey alpha", "hey alpha run the tests", "hey bravo",
                                                     "hey bravo read the mail"), delivered, indicator)
    run(unit, len(audio.script))
    assert [(u.agent, u.text) for u in delivered] == [(ALPHA, "run the tests"), (BRAVO, "read the mail")]
    assert [c[1] for c in indicator.calls if c[0] == "show"] == [ALPHA, BRAVO]


def test_target_follows_trigger():
    """R47: a key opens a recording for the agent whose key it is; another agent's key does nothing
    while that recording runs, and a key nobody declared does nothing at all."""
    audio = FakeAudio().then((SPEECH, secs(3)), (SILENCE, secs(2)))
    delivered = []
    unit, keys = shared_unit(audio, ScriptedTranscriber("open the door", "close it"), delivered)
    keys.press("KEY_F1")                      # nobody's key
    run(unit, 2)
    assert unit.recording is None
    keys.press("KEY_F11")                     # Bravo's hold key
    run(unit, 2)
    keys.press("KEY_F9")                      # Alpha's, while Bravo's recording runs: ignored
    run(unit, secs(1))
    keys.release("KEY_F9")
    run(unit, 2)
    assert unit.recording is not None and unit.recording.agent.b.agent == BRAVO
    keys.release("KEY_F11")
    run(unit, 2)
    assert [(u.agent, u.trigger, u.text) for u in delivered] == [(BRAVO, "hold_key", "open the door")]


def test_one_members_lockout_never_silences_another():
    """R39 per agent on a shared unit: Bravo's failed voice-lock attempts lock out Bravo alone, and
    Alpha, declared first, is still heard. (Bravo second, so a count kept on the first agent shows.)"""
    audio = FakeAudio()
    for _ in range(3):
        audio.then((SILENCE, secs(4)), (BRAVO_WAKE, secs(0.5)), (SPEECH, secs(1)))
    audio.then((SILENCE, secs(4)), (ALPHA_WAKE, secs(0.5)), (SPEECH, secs(1)), (SILENCE, secs(5)))
    events, delivered = [], []
    members = [AgentBinding(agent=ALPHA, wake_phrase="hey alpha", detector=PhraseDetector(int(ALPHA_WAKE[0])),
                            speaker=lambda a: True, on_voice_event=lambda k, d: events.append((ALPHA, k))),
               AgentBinding(agent=BRAVO, wake_phrase="hey bravo", detector=PhraseDetector(int(BRAVO_WAKE[0])),
                            speaker=lambda a: False, on_voice_event=lambda k, d: events.append((BRAVO, k)))]
    unit = CaptureUnit(CaptureConfig(agent=SYSTEM), audio=audio, lock=FakeLock(), indicator=RecordingIndicator(),
                       triggers=PushedKeys(), gate=LoudGate(),
                       transcribe=ScriptedTranscriber("hey alpha", "hey alpha status"), deliver=delivered.append,
                       clock=lambda: audio.reads * FRAME_S, wall=lambda: NOW + audio.reads * FRAME_S,
                       executor=InlineExecutor(), members=members)
    run(unit, len(audio.script))
    assert events == [(BRAVO, "unmatched"), (BRAVO, "unmatched"), (BRAVO, "unmatched"), (BRAVO, "lockout")]
    assert unit.agents[1].locked_out_until is not None and unit.agents[0].locked_out_until is None
    assert [(u.agent, u.text, u.voice_lock) for u in delivered] == [(ALPHA, "status", "matched")]


def test_when_two_wake_models_fire_at_once_the_first_declared_is_checked():
    """R47 on a tie: if one frame fires two members' models, the member declared first has its phrase
    checked, a fixed rule rather than whichever model happened to score last."""
    both = WAKE.copy() + 4

    class Both(WakeDetector):
        def score(self, frame):
            return 1.0 if frame[0] == both[0] else 0.0

    audio = FakeAudio().then((SILENCE, 3), (both, secs(0.5)), (SPEECH, secs(1)), (SILENCE, secs(5)))
    delivered = []
    members = [AgentBinding(agent=ALPHA, wake_phrase="hey alpha", detector=Both()),
               AgentBinding(agent=BRAVO, wake_phrase="hey bravo", detector=Both())]
    unit = CaptureUnit(CaptureConfig(agent=SYSTEM), audio=audio, lock=FakeLock(), indicator=RecordingIndicator(),
                       triggers=PushedKeys(), gate=LoudGate(),
                       transcribe=ScriptedTranscriber("hey alpha", "hey alpha go"), deliver=delivered.append,
                       clock=lambda: audio.reads * FRAME_S, wall=lambda: NOW + audio.reads * FRAME_S,
                       executor=InlineExecutor(), members=members)
    run(unit, len(audio.script))
    assert [(u.agent, u.text) for u in delivered] == [(ALPHA, "go")]


def test_the_sender_signs_for_the_agent_that_fired_and_never_retains():
    """R47, R48 on the sending side: the envelope names the agent whose binding fired, verifies, and
    goes to that agent's own topic; an utterance for an agent the unit doesn't serve goes nowhere."""
    sent = []
    send = DispatchSender(SYSTEM, KEY, "voice-capture", [ALPHA, BRAVO],
                          lambda topic, payload: sent.append((topic, payload)) or True, lifetime_s=30, now=lambda: NOW)

    class U:
        trigger, spoken_at, screen, voice_lock, text = "hold_key", NOW, "unlocked", "not_declared", "hello"

    u = U()
    u.agent = BRAVO
    assert send(u) is not None
    [(topic, payload)] = sent
    assert topic == voice_topic(BRAVO) == "voice/bravo_bbb222/in"
    assert verifier(BRAVO).check(payload, retained=False, now=NOW).accepted
    u.agent = "Stranger_ccc333"
    assert send(u) is None and len(sent) == 1


# ---------------------------------------------------------------- R48, R50: the member's check

def test_dispatched_utterance_signed():
    """R48: the signature covers every field; changing any one, the words or the target included,
    breaks it, and a key the registry doesn't hold for the dispatcher never verifies."""
    env = signed()
    assert verifier().check(env.model_dump_json().encode(), retained=False, now=NOW).accepted
    assert b"check the build" in signing_payload(env)
    for field, value in [("text", "delete the build"), ("target", BRAVO), ("expires_at", NOW + 9000),
                         ("nonce", "0" * 32), ("screen", "locked"), ("trigger", "hold_key")]:
        forged = env.model_copy(update={field: value})
        check = verifier(BRAVO if field == "target" else ALPHA).check(forged.model_dump_json().encode(),
                                                                       retained=False, now=NOW)
        assert check.verdict == "bad_signature", field
    stranger = signed(key=OTHER_KEY)
    assert verifier().check(stranger.model_dump_json().encode(), retained=False, now=NOW).verdict == "bad_signature"


@pytest.mark.parametrize("make,when,verdict", [
    (lambda: b"{not json", NOW, "malformed"),
    (lambda: signed().model_dump_json().replace('"v":1', '"v":1,"extra":1').encode(), NOW, "malformed"),
    (lambda: signed(signer=BRAVO).model_dump_json().encode(), NOW, "unknown_signer"),
    (lambda: signed(target=BRAVO).model_dump_json().encode(), NOW, "wrong_target"),
    (lambda: signed().model_dump_json().encode(), NOW + 30 + 5.1, "expired"),
    (lambda: signed(lifetime=3600).model_dump_json().encode(), NOW, "expiry_too_far"),
])
def test_bad_signature_expiry_or_nonce_refused(make, when, verdict):
    """R50: each failed check refuses, by name."""
    assert verifier().check(make(), retained=False, now=when).verdict == verdict


def test_expiry_allows_the_declared_clock_difference():
    """MIS-0007 R57: an utterance just past its expiry, inside the clock allowance, is still taken."""
    payload = signed().model_dump_json().encode()
    assert verifier().check(payload, retained=False, now=NOW + 30 + 4.9).accepted


def test_a_replay_is_refused():
    """MIS-0007 R55: the same signed utterance a second time is refused."""
    v = verifier()
    payload = signed().model_dump_json().encode()
    assert v.check(payload, retained=False, now=NOW).accepted
    assert v.check(payload, retained=False, now=NOW + 1).verdict == "replayed"


def test_a_retained_message_is_dropped_unread():
    """MIS-0007 R67: retained, it is dropped before its contents are read, however well signed."""
    payload = signed().model_dump_json().encode()
    check = verifier().check(payload, retained=True, now=NOW)
    assert check.verdict == "retained" and check.envelope is None


def test_an_unreadable_registry_refuses_rather_than_raises():
    def broken(card):
        raise ValueError("registry owned by uid 1000")
    check = Verifier(ALPHA, SYSTEM, broken).check(signed().model_dump_json().encode(), retained=False, now=NOW)
    assert check.verdict == "unknown_signer" and "can't be read" in check.reason


# ---------------------------------------------------------------- the carriage: delivered, recorded, and a restart

@pytest.fixture
def carriage(tmp_path):
    voice = VoiceSection(dispatched_by=SYSTEM)
    c = VoiceCarriage(ALPHA, tmp_path / "voice.sock", voice, lambda peer: "", lambda unit: None)
    ours, theirs = socket.socketpair()
    attached = _Attached(pid=1, deadline=0)
    attached.ready = True
    c.channels[ours] = attached
    yield c, theirs
    ours.close()
    theirs.close()


def test_an_accepted_utterance_reaches_the_session_labelled_signed(carriage, isolated_events_log):
    """R48 and MIS-0007 R52: the session gets the words, labelled by this daemon's verdict; the log
    gets the verdict, nonce and expiry and never the words (R10)."""
    c, session = carriage
    receipt = c.dispatched(signed().model_dump_json().encode(), retained=False, verifier=verifier(), now=NOW)
    assert receipt["receipt"] == "delivered" and receipt["verdict"] == "accepted"
    record = json.loads(session.recv(65536).decode())
    assert record["route"] == "system_signed" and record["text"] == "check the build"
    logged = json.dumps(list(read_events(reverse=False, scope="all")))
    assert "check the build" not in logged
    [event] = [e["data"] for e in read_events(reverse=False, scope="all", only=("pd_voice_dispatch",))]
    assert event["verdict"] == "accepted" and event["nonce"] and event["chars"] == len("check the build")
    assert "check the build" not in json.dumps(receipt)


def test_a_refusal_is_recorded_and_delivers_nothing(carriage, isolated_events_log):
    """R50: a forged utterance is refused, recorded with its reason, and never reaches the session."""
    c, session = carriage
    forged = signed().model_copy(update={"text": "merge it"}).model_dump_json().encode()
    receipt = c.dispatched(forged, retained=False, verifier=verifier(), now=NOW)
    assert receipt["receipt"] == "refused" and receipt["verdict"] == "bad_signature"
    session.setblocking(False)
    with pytest.raises(BlockingIOError):
        session.recv(1)
    [event] = [e["data"] for e in read_events(reverse=False, scope="all", only=("pd_voice_dispatch",))]
    assert event["verdict"] == "bad_signature" and event["reason"]


def test_nonce_record_survives_restart(carriage, isolated_events_log):
    """MIS-0007 R56: after a restart, a verifier rebuilt from the log still refuses a replay of an
    utterance accepted before it, until that utterance's expiry has passed."""
    c, _session = carriage
    payload = signed().model_dump_json().encode()
    assert c.dispatched(payload, retained=False, verifier=verifier(), now=NOW)["verdict"] == "accepted"
    from macf.agent_events_log import append_event   # another agent's acceptance, in a shared log: not ours
    append_event("pd_voice_dispatch", {"agent": BRAVO, "verdict": "accepted", "nonce": "f" * 32,
                                       "expires_at": NOW + 30})
    rebuilt = NonceRecord.from_events(read_events(scope="all", only=("pd_voice_dispatch",)), ALPHA, 5.0)
    assert len(rebuilt) == 1
    again = c.dispatched(payload, retained=False, verifier=verifier(nonces=rebuilt), now=NOW + 1)
    assert again["verdict"] == "replayed"


def test_a_local_utterance_to_a_dispatched_agent_is_refused(carriage, isolated_events_log):
    """R46: an agent served by its system's capture unit takes nothing over its own control socket."""
    from macf.pd.interface import UtteranceRequest
    c, _ = carriage

    class Peer:
        pid = 1

    reply = c.utterance(UtteranceRequest(op="utterance", trigger="hold_key", spoken_at=NOW, screen="unlocked",
                                         voice_lock="not_declared", text="hi"), Peer())
    assert reply.receipt == "refused" and SYSTEM in reply.error


def test_a_dispatched_lockout_owes_the_member_its_notice_and_raises_its_guard(carriage, isolated_events_log):
    """R37, R42 by the downward route: the system unit's signed lockout for this member raises its
    guard and owes it the notice without content; the same event forged raises nothing."""
    from macf.voice.dispatch import sign_voice_event
    c, _ = carriage
    owed = []
    until = NOW + 600
    forged = sign_voice_event(signer=SYSTEM, target=ALPHA, private=OTHER_KEY, now=NOW, lifetime_s=30,
                              kind="lockout", until=until)
    receipt = c.dispatched(forged.model_dump_json().encode(), retained=False, verifier=verifier(), now=NOW,
                           raise_notice=lambda source, notice_id: owed.append(source))
    assert receipt["verdict"] == "bad_signature" and owed == [] and c.guard_until(now=NOW) is None
    event = sign_voice_event(signer=SYSTEM, target=ALPHA, private=KEY, now=NOW, lifetime_s=30, kind="lockout",
                             until=until)
    receipt = c.dispatched(event.model_dump_json().encode(), retained=False, verifier=verifier(), now=NOW,
                           raise_notice=lambda source, notice_id: owed.append(source))
    assert receipt["receipt"] == "recorded" and owed == ["pd_voice_lockout"]
    assert c.guard_until(now=NOW) == until


def test_an_utterances_signature_cannot_be_reused_as_a_voice_events():
    """An utterance's signature, moved onto an event with the same nonce, doesn't verify. Today that
    holds because the two kinds sign different fields; covering ``type`` as well keeps it holding if
    two kinds ever came to share every field (a mutation leaving ``type`` out is equivalent now)."""
    from macf.voice.dispatch import DispatchedVoiceEvent
    env = signed()
    common = env.model_dump(include={"signer", "target", "issued_at", "expires_at", "nonce", "signature"})
    forged = DispatchedVoiceEvent(kind="unmatched", attempts=1, of=3, **common)
    assert verifier().check(forged.model_dump_json().encode(), retained=False, now=NOW).verdict == "bad_signature"


def test_the_sender_carries_a_members_voice_event_down():
    sent = []
    send = DispatchSender(SYSTEM, KEY, "voice-capture", [ALPHA], lambda t, p: sent.append((t, p)) or True,
                          lifetime_s=30, now=lambda: NOW)
    assert send.voice_event(ALPHA, "unmatched", {"attempts": 2, "of": 3}) is not None
    assert send.voice_event(BRAVO, "unmatched", {"attempts": 1, "of": 3}) is None
    [(topic, payload)] = sent
    check = verifier().check(payload, retained=False, now=NOW)
    assert topic == voice_topic(ALPHA) and check.accepted and check.envelope.kind == "unmatched"
    assert check.envelope.attempts == 2


# ---------------------------------------------------------------- R49: the broker's rules and the member link

def test_member_reads_only_own_voice_subtree():
    """R49: the association alone writes voice topics, and each member reads its own and no other's;
    a member the system doesn't serve reads none."""
    rules = b.render_access_rules(SYSTEM, members=[ALPHA, BRAVO, "Carol_ccc333"], association=True,
                                  voice_members=[ALPHA, BRAVO])
    blocks = {blk.splitlines()[0].split()[1]: blk.splitlines()[1:] for blk in rules.strip().split("\n\n")}
    assert "topic write voice/#" in blocks[b.cert_name(SYSTEM)]
    assert [ln for ln in blocks["alpha_aaa111"] if "voice" in ln] == ["topic read voice/alpha_aaa111/in"]
    assert [ln for ln in blocks["bravo_bbb222"] if "voice" in ln] == ["topic read voice/bravo_bbb222/in"]
    assert not [ln for ln in blocks["carol_ccc333"] if "voice" in ln]
    for card in ("alpha_aaa111", "bravo_bbb222", "carol_ccc333"):
        assert not any("write voice" in ln or "#" in ln.split()[-1] and "voice" in ln for ln in blocks[card])
    with pytest.raises(b.BrokerRefused):
        b.render_access_rules(SYSTEM, members=[ALPHA], association=True, voice_members=[BRAVO])


class FakeClient:
    def __init__(self):
        self.subscribed, self.published = [], []
        self.on_connect = self.on_connect_fail = self.on_message = None

    def subscribe(self, topic, qos=0):
        self.subscribed.append(topic)

    def publish(self, topic, payload, qos=0, retain=False):
        self.published.append((topic, payload, retain))

        class R:
            def wait_for_publish(self, t):
                return None
        return R()


class Message:
    def __init__(self, topic, payload, retain=False):
        self.topic, self.payload, self.retain = topic, payload, retain


def export_link(tmp_path, on_voice):
    from macf.pd.broker_link import ExportLink
    from macf.pd.interface import AssociationLink
    link = AssociationLink(port=18883, certificate_authority_file="ca", client_certificate_file="c",
                           client_key_file="k")
    client = FakeClient()
    return ExportLink(ALPHA, tmp_path / "log.jsonl", link, {}, client=client, on_voice=on_voice), client


def test_a_dispatched_members_link_subscribes_to_its_own_voice_topic_only(tmp_path):
    """R49 with MIS-0007 R67: the link subscribes to this agent's voice topic and nothing else, hands
    each message on with its retained flag, ignores any other topic, and publishes the receipt on its
    own subtree, not retained."""
    taken = []
    link, client = export_link(tmp_path, lambda payload, retained: taken.append((payload, retained)) or
                               {"verdict": "accepted", "receipt": "delivered"})
    link._on_connect(client, None, None, None)
    assert client.subscribed == [voice_topic(ALPHA)]
    link._on_message(client, None, Message(voice_topic(BRAVO), b"theirs"))
    link._on_message(client, None, Message(voice_topic(ALPHA), b"ours", retain=True))
    link.tick()
    assert taken == [(b"ours", True)]
    receipts = [(t, r) for t, _p, r in client.published if t == receipt_topic(ALPHA)]
    assert receipts == [(receipt_topic(ALPHA), False)]


def test_a_message_the_carriage_cannot_handle_is_refused_and_the_link_goes_on(tmp_path, capsys):
    """One message that raises is refused, said, and answered; the next is still handled. A queue
    that overflowed between passes says how many it dropped."""
    calls = []

    def on_voice(payload, retained):
        calls.append(payload)
        if payload == b"bad":
            raise OSError("log not writable")
        return {"verdict": "accepted", "receipt": "delivered"}

    link, client = export_link(tmp_path, on_voice)
    for p in (b"bad", b"good"):
        link._on_message(client, None, Message(voice_topic(ALPHA), p))
    link.tick()
    assert calls == [b"bad", b"good"]
    receipts = [json.loads(p) for t, p, _r in client.published if t == receipt_topic(ALPHA)]
    assert [r["receipt"] for r in receipts] == ["refused", "delivered"]
    for i in range(70):
        link._on_message(client, None, Message(voice_topic(ALPHA), b"m%d" % i))
    link.tick()
    assert "6 message(s) on the voice topic were dropped" in capsys.readouterr().err


def test_an_undispatched_members_link_still_subscribes_to_nothing(tmp_path):
    """MIS-0007 R67 unchanged for every member its system's capture unit doesn't serve."""
    link, client = export_link(tmp_path, None)
    link._on_connect(client, None, None, None)
    link._on_message(client, None, Message(voice_topic(ALPHA), b"x"))
    assert client.subscribed == [] and link.voice_messages == type(link.voice_messages)(maxlen=64)


# ---------------------------------------------------------------- the declarations

def test_a_voice_section_names_one_source():
    with pytest.raises(ValidationError, match="not both"):
        VoiceSection(capture_unit="voice-capture", dispatched_by=SYSTEM)
    with pytest.raises(ValidationError, match="not both"):
        VoiceSection()


def test_a_dispatched_agent_cannot_bind_its_own_phrase_or_keys():
    """MIS-0007 R29: only the system declaration binds a member's phrase and keys."""
    with pytest.raises(ValidationError, match="no hold_key of its own"):
        VoiceSection(dispatched_by=SYSTEM, hold_key="KEY_F9", trigger_devices=["/dev/input/x"])


def system_declaration(**voice_dispatch):
    vd = {"capture_unit": "voice-capture", "signing_key_file": "/var/lib/maceff_system/voice.key",
          "trigger_devices": ["/dev/input/by-id/kbd"],
          "members": {ALPHA: {"hold_key": "KEY_F9"}, BRAVO: {"hold_key": "KEY_F11"}}}
    vd.update(voice_dispatch)
    return {"version": 1, "agent": SYSTEM, "kind": "system", "members": [ALPHA, BRAVO],
            "broker": {"port": 18883, "certificate_authority_file": "ca", "server_certificate_file": "s",
                       "server_key_file": "sk", "client_certificate_file": "c", "client_key_file": "k"},
            "units": [{"name": "voice-capture", "command": ["true"], "account": "maceff_system", "restart": "always",
                       "liveness_interval_s": 30, "memory_limit_mb": 512}],
            "voice_dispatch": vd}


def test_a_system_binds_only_its_declared_members_and_tells_them_apart():
    """R26, R46: a binding for a card that isn't a member, or two members sharing a key, is refused."""
    assert Declaration.model_validate(system_declaration()).voice_dispatch.members[BRAVO].hold_key == "KEY_F11"
    with pytest.raises(ValidationError, match="doesn't declare as members"):
        Declaration.model_validate(system_declaration(members={"Carol_ccc333": {"hold_key": "KEY_F9"}}))
    with pytest.raises(ValidationError, match="both declare the key KEY_F9"):
        Declaration.model_validate(system_declaration(members={ALPHA: {"hold_key": "KEY_F9"},
                                                               BRAVO: {"hold_key": "KEY_F9"}}))
    with pytest.raises(ValidationError, match="one card in two cases"):
        Declaration.model_validate(system_declaration(members={ALPHA: {"hold_key": "KEY_F9"},
                                                               ALPHA.upper(): {"toggle_key": "KEY_F10"}}))


def test_the_system_capture_unit_is_built_from_the_system_declaration(tmp_path):
    """R46 to R48 end to end on fakes: the unit the system declaration describes signs with the key
    file it names, sends a member's wake down that member's topic only, and a member's failed voice
    lock as a signed event."""
    from macf.amail.crypto import generate_keypair, load_private_key
    from macf.voice.capture.__main__ import build_system
    key_dir = tmp_path / "keys"
    generate_keypair(key_dir / "voice.key")
    system_key = load_private_key(key_dir / "voice.key")
    decl = Declaration.model_validate(system_declaration(
        signing_key_file="{agent_home}/keys/voice.key",
        members={ALPHA: {"wake_phrase": "hey alpha", "wake_model": "alpha.npz"}, BRAVO: {"hold_key": "KEY_F11"}}))
    audio = FakeAudio().then((SILENCE, 3), (ALPHA_WAKE, secs(0.5)), (SPEECH, secs(1)), (SILENCE, secs(5)))
    sent = []
    unit = build_system(tmp_path, SYSTEM, decl, publish=lambda t, p: sent.append((t, p)) or True,
                        detector_for=lambda path: PhraseDetector(int(ALPHA_WAKE[0])),
                        backends=dict(audio=audio, lock=FakeLock(), indicator=RecordingIndicator(),
                                      triggers=PushedKeys(), gate=LoudGate(), executor=InlineExecutor(),
                                      transcribe=ScriptedTranscriber("hey alpha", "hey alpha deploy"),
                                      clock=lambda: audio.reads * FRAME_S))
    run(unit, len(audio.script))
    [(topic, payload)] = sent
    member_view = Verifier(ALPHA, SYSTEM, lambda c: [public_key_line(system_key)] if c == SYSTEM else [])
    check = member_view.check(payload, retained=False, now=json.loads(payload)["issued_at"])
    assert topic == voice_topic(ALPHA) and check.accepted and check.envelope.text == "deploy"
    unit.agents[0].b.on_voice_event("unmatched", {"attempts": 1, "of": 3})
    event = member_view.check(sent[-1][1], retained=False, now=json.loads(sent[-1][1])["issued_at"])
    assert sent[-1][0] == voice_topic(ALPHA) and event.accepted and event.envelope.kind == "unmatched"


# ---------------------------------------------------------------- status on both daemons

def test_status_says_whom_the_system_serves_and_how_the_last_message_down_ended():
    from macf.pd.cli import voice_dispatch_lines
    system = Declaration.model_validate(system_declaration())
    assert voice_dispatch_lines(system, None) == [
        f"  voice: the capture unit voice-capture serves {ALPHA}, {BRAVO}"]
    member = Declaration.model_validate({"version": 1, "agent": ALPHA, "voice": {"dispatched_by": SYSTEM},
                                         "association": {"port": 18883, "certificate_authority_file": "a",
                                                         "client_certificate_file": "b", "client_key_file": "c"},
                                         "broker": {"port": 18884, "certificate_authority_file": "ca",
                                                    "server_certificate_file": "s", "server_key_file": "sk",
                                                    "client_certificate_file": "c", "client_key_file": "k"}})
    [none_yet] = voice_dispatch_lines(member, None)
    assert SYSTEM in none_yet and "nothing has come down yet" in none_yet
    refused = {"timestamp": NOW, "data": {"type": "utterance", "verdict": "expired", "reason": "expired 40 s ago",
                                          "chars": 12}}
    [line] = voice_dispatch_lines(member, refused)
    assert "was expired" in line and "expired 40 s ago" in line and "12" not in line.split(":")[-1]


def test_a_dispatched_member_needs_an_association():
    """R49: dispatched utterances arrive only through the association's broker."""
    with pytest.raises(ValidationError, match="names no association"):
        Declaration.model_validate({"version": 1, "agent": ALPHA, "voice": {"dispatched_by": SYSTEM}})
