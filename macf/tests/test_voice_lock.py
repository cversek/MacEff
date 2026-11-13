"""The voice lock (MIS-0008 R34 to R37, R39, R41): enrollment and its report, and the gate on delivery."""
import numpy as np
import pytest

from macf.voice.capture.backends import RATE
from macf.voice.lock.model import LockRefused, VoiceLock
from macf.voice.lock.train import LockSet, train
from voice_fakes import OTHER_VOICE_MARK, OTHER_WAKE, SILENCE, SPEECH, WAKE, FakeAudio, ScriptedTranscriber, make_unit, secs


def same_voice(audio) -> bool:
    """The fake voice lock: anything holding another voice's frames doesn't match."""
    return not np.any(audio == OTHER_VOICE_MARK)


def attempt(audio: FakeAudio, voice=WAKE) -> FakeAudio:
    """One call of the phrase, spoken in ``voice``, then a pause past the cooldown."""
    return audio.then((voice, 4), (SPEECH, secs(1)), (SILENCE, secs(3.5)))


def test_only_matching_speaker_delivered():
    """R34: with a voice lock declared, the enrolled voice's utterance is delivered, marked matched;
    another voice saying the same phrase is not."""
    events = []
    rig = make_unit(attempt(attempt(FakeAudio(), OTHER_WAKE)), ScriptedTranscriber("yo tom", "yo tom check"),
                    speaker=same_voice, on_voice_event=lambda kind, data: events.append(kind))
    rig.run(len(rig.audio.script))
    assert [(u.text, u.voice_lock) for u in rig.delivered] == [("check", "matched")]
    assert events == ["unmatched"]


def test_failure_discards_audio_untranscribed_and_sends_contentless_notice():
    """R37: a voice that doesn't match is never transcribed, and what the agent is told holds no words."""
    transcriber = ScriptedTranscriber("yo tom")
    events = []
    rig = make_unit(attempt(FakeAudio(), OTHER_WAKE), transcriber, speaker=same_voice,
                    on_voice_event=lambda kind, data: events.append((kind, data)))
    rig.run(len(rig.audio.script))
    assert transcriber.calls == [] and rig.delivered == []
    assert events == [("unmatched", {"attempts": 1, "of": 3})]


def test_failures_in_window_start_lockout():
    """R39: the declared count of failures inside the window starts the lockout, announced once."""
    events = []
    audio = FakeAudio()
    for _ in range(3):
        attempt(audio, OTHER_WAKE)
    rig = make_unit(audio, ScriptedTranscriber(), speaker=same_voice,
                    on_voice_event=lambda kind, data: events.append(kind), lockout_s=600.0)
    rig.run(len(rig.audio.script))
    assert events == ["unmatched", "unmatched", "unmatched", "lockout"]
    assert rig.unit.locked_out_until is not None


def test_failures_outside_the_window_do_not_add_up():
    events = []
    audio = FakeAudio()
    for _ in range(3):
        attempt(audio, OTHER_WAKE)
    rig = make_unit(audio, ScriptedTranscriber(), speaker=same_voice, lockout_window_s=3.0,
                    on_voice_event=lambda kind, data: events.append(kind))
    rig.run(len(rig.audio.script))
    assert "lockout" not in events


def test_lockout_delivers_nothing_and_counts():
    """R41: during a lockout even the enrolled voice delivers nothing, and each attempt is counted."""
    audio = FakeAudio()
    for _ in range(3):
        attempt(audio, OTHER_WAKE)
    attempt(attempt(audio))
    transcriber = ScriptedTranscriber("yo tom", "yo tom check")
    rig = make_unit(audio, transcriber, speaker=same_voice, lockout_s=600.0)
    rig.run(len(rig.audio.script))
    assert rig.delivered == [] and transcriber.calls == [] and rig.unit.locked_out_attempts == 2


# ---------------------------------------------------------------- enrollment and its report

def tone(freq, seconds=1.5, rng=None):
    rng = rng or np.random.default_rng(0)
    t = np.arange(int(seconds * RATE)) / RATE
    return (np.sin(2 * np.pi * freq * t) * 0.3 + rng.normal(0, 0.01, t.size)).astype(np.float32)


def pitch_embed(audio) -> np.ndarray:
    """A stand-in speaker embedding: energy in eight bands."""
    spectrum = np.abs(np.fft.rfft(np.asarray(audio, np.float64)))
    return np.array([band.sum() for band in np.array_split(spectrum[:4000], 8)])


def enrolled(home, rng, others=True):
    lock = LockSet(home)
    for _ in range(16):
        lock.add("operator", tone(220 + rng.integers(-10, 10), rng=rng), "desk mic")
    if others:
        for _ in range(8):
            lock.add("other_speaker", tone(1400 + rng.integers(-50, 50), rng=rng), "colleague")
            lock.add("synthetic", tone(2600 + rng.integers(-50, 50), rng=rng), "synthetic voice")
    return lock


def test_threshold_needs_report(tmp_path):
    """R35: a threshold is never stored without the report that chose it."""
    lock = VoiceLock(centroid=np.ones(8), threshold=0.9, report={})
    with pytest.raises(LockRefused, match="only with its test report"):
        lock.save(tmp_path / "lock.npz")
    trained = train(enrolled(tmp_path, np.random.default_rng(4)), pitch_embed)
    trained.save(tmp_path / "lock.npz")
    back = VoiceLock.load(tmp_path / "lock.npz")
    assert back.report["false_rejects"] == trained.report["false_rejects"] and back.threshold == trained.threshold


def test_test_set_includes_impostors(tmp_path):
    """R36: a lock whose held-out set has no other speakers or synthetic speech is refused."""
    with pytest.raises(LockRefused, match="other speakers and synthetic speech"):
        train(enrolled(tmp_path, np.random.default_rng(6), others=False), pitch_embed)
    report = train(enrolled(tmp_path / "b", np.random.default_rng(6)), pitch_embed).report
    assert report["held_out"]["other_speaker"] == 2 and report["held_out"]["synthetic"] == 2
    assert set(report["false_accepts"]) == {"other_speaker", "synthetic"}


# ---------------------------------------------------------------- the daemon: notices and the raised guard (R37, R42, R44)

import json  # noqa: E402
import time  # noqa: E402

from macf.agent_events_log import read_events  # noqa: E402
from test_primal_daemon import ask, base, run_daemon  # noqa: E402,F401 - fixtures
from test_voice_capture import receipt_of, voice_home  # noqa: E402


def send_from_unit(vh, request):
    """Have the declared capture unit itself send ``request`` to its daemon, and return the reply."""
    tmp = vh.go.with_suffix(".tmp")
    tmp.write_text(json.dumps(request))
    tmp.replace(vh.go)
    return receipt_of(vh.out)


def test_lockout_raises_guard(tmp_path, base, run_daemon, isolated_events_log):
    """R42: a lockout from the capture unit raises the guard, recorded, shown in status, and kept
    across a daemon restart, since it is read from the log; the agent gets a notice without content."""
    vh = voice_home(tmp_path, base)
    daemon = run_daemon(vh.home, base)
    until = time.time() + 600
    assert send_from_unit(vh, {"op": "voice_event", "kind": "lockout", "until": until})["ok"]
    assert abs(ask(daemon, {"op": "status"})["voice_guard_until"] - until) < 1
    raised = [e["data"] for e in read_events(reverse=False, scope="all", only=("pd_voice_guard",))]
    assert raised and raised[-1]["raised_until"] == until
    assert daemon.voice.guard_until() == until, "the guard must be read from the log, so a restart keeps it"


def test_a_voice_event_comes_only_from_the_capture_unit(tmp_path, base, run_daemon, isolated_events_log):
    """R12 for voice events: a process that is not the capture unit can neither raise nor fake one."""
    vh = voice_home(tmp_path, base)
    daemon = run_daemon(vh.home, base)
    reply = ask(daemon, {"op": "voice_event", "kind": "lockout", "until": time.time() + 600})
    assert not reply["ok"] and "only from the declared capture unit" in reply["error"]
    assert ask(daemon, {"op": "status"}).get("voice_guard_until") is None


def test_agent_cannot_lower_own_guard(tmp_path, base, run_daemon, isolated_events_log):
    """R44: the agent cannot lower its raised guard; the operator can."""
    vh = voice_home(tmp_path, base)
    daemon = run_daemon(vh.home, base)
    send_from_unit(vh, {"op": "voice_event", "kind": "lockout", "until": time.time() + 600})
    lower = {"op": "voice_guard", "act": "lower", "reason": "I am sure it was them"}
    refused = ask(daemon, {**lower, "asked_by": {"kind": "agent"}})
    assert not refused["ok"] and "only the operator" in refused["error"]
    assert ask(daemon, {"op": "status"})["voice_guard_until"] is not None
    assert ask(daemon, {**lower, "asked_by": {"kind": "operator"}})["ok"]
    assert ask(daemon, {"op": "status"}).get("voice_guard_until") is None


def test_the_operator_lowering_the_guard_ends_the_lockout():
    """R44: once the operator lowers the guard, the lockout ends and the enrolled voice is heard again;
    until then, the same call is ignored and counted."""
    lowered = [False]
    audio = FakeAudio()
    for _ in range(3):
        attempt(audio, OTHER_WAKE)
    attempt(audio)
    rig = make_unit(audio, ScriptedTranscriber("yo tom", "yo tom check"), speaker=same_voice, lockout_s=600.0,
                    guard_lowered=lambda: lowered[0])
    rig.run(len(rig.audio.script))
    assert rig.delivered == [] and rig.unit.locked_out_attempts == 1
    lowered[0] = True
    attempt(rig.audio)
    rig.run(len(rig.audio.script))
    assert [u.text for u in rig.delivered] == ["check"] and rig.unit.locked_out_until is None


def test_an_unmatched_voice_leaves_the_agent_a_notice_without_content(tmp_path, base, run_daemon, isolated_events_log):
    """R37 across both halves: the capture unit's unmatched event leaves the agent owed a
    pd_voice_unmatched notice, whose record and event hold counts only."""
    vh = voice_home(tmp_path, base)
    daemon = run_daemon(vh.home, base)
    assert send_from_unit(vh, {"op": "voice_event", "kind": "unmatched", "attempts": 1, "of": 3})["ok"]
    owed = [a for a in daemon.notifier.owed if a.startswith("pd_voice_unmatched:")]
    assert len(owed) == 1
    [event] = [e["data"] for e in read_events(reverse=False, scope="all", only=("pd_voice_unmatched",))]
    assert set(event) == {"agent", "attempts", "of"}


def test_a_raised_guard_is_in_every_prompt_until_it_ends(isolated_events_log):
    """R42, the hook half: the prompt hook shows the guard while raised, and not once it ends or the
    operator lowers it, reading the newest guard event."""
    from macf.agent_events_log import append_event
    from macf.voice import guard
    assert guard.prompt_line() == ""
    append_event("pd_voice_guard", {"agent": "Tester_abc123", "raised_until": time.time() + 600, "by": "lockout"})
    assert "Voice guard raised until" in guard.prompt_line() and "Only the operator lowers it" in guard.prompt_line()
    assert guard.prompt_line(now=time.time() + 601) == ""
    append_event("pd_voice_guard", {"agent": "Tester_abc123", "raised_until": None, "by": "operator"})
    assert guard.prompt_line() == ""
