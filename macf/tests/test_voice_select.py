"""Choosing an agent's voice (MIS-0008 R30, R31) and ``voice speak``."""
import json
from types import SimpleNamespace

import pytest

from macf.pd.interface import Declaration, Unit, VoiceSection, declaration_path
from macf.voice.speech import cli as speech_cli
from macf.voice.speech import select
from macf.voice.speech import worker as speech

from test_primal_daemon import CARD, ME, make_home


def voice_home(tmp_path):
    unit = Unit(name="capture", command=["true"], account=ME, restart="never", liveness_interval_s=60.0,
                memory_limit_mb=64)
    home = make_home(tmp_path, [unit])
    declaration_path(home).write_text(Declaration(version=1, agent=CARD, units=[unit],
                                                  voice=VoiceSection(capture_unit="capture")).model_dump_json())
    return home


def test_choice_recorded_with_traits(tmp_path):
    """R30: the chosen candidate goes into the voice section with the traits the operator agreed,
    and the declaration still loads."""
    home = voice_home(tmp_path)
    traits = ["deep", "calm", "british"]
    select.keep_candidates(home, traits, select.candidates(traits))
    select.record_choice(home, 2)
    speech_settings = Declaration.model_validate_json(declaration_path(home).read_text()).voice.speech
    chosen = select.candidates(traits)[1]
    assert (speech_settings.voice, speech_settings.speed, speech_settings.traits) == (chosen.voice, chosen.speed, traits)
    assert speech_settings.chosen_at is not None


def test_traits_steer_the_candidates():
    """The first mapping reads accent, timbre and pace words; a blend of the two best is always offered."""
    british_deep = select.candidates(["deep", "british", "measured"])
    assert british_deep[0].voice == "bm_george" and british_deep[0].speed < 1.0
    brisk = select.candidates(["bright", "brisk", "american"])
    assert brisk[0].voice.startswith("a") and brisk[0].speed > 1.0
    assert "," in brisk[-1].voice and len(brisk) == 4


@pytest.mark.parametrize("prepare, why", [
    ("nothing", "no candidates have been made"),
    ("no voice section", "no voice section"),
    ("rendered", "rendered by the operator's tooling"),
    ("bad number", "there is no candidate 9"),
])
def test_a_choice_that_cannot_be_recorded_is_refused_by_name(tmp_path, prepare, why):
    from macf.pd.names import rendered_declaration_path
    home = voice_home(tmp_path)
    if prepare != "nothing":
        select.keep_candidates(home, ["calm"], select.candidates(["calm"]))
    if prepare == "no voice section":
        raw = json.loads(declaration_path(home).read_text())
        raw["voice"] = None
        declaration_path(home).write_text(json.dumps(raw))
    if prepare == "rendered":
        rendered_declaration_path(home).parent.mkdir(parents=True, exist_ok=True)
        rendered_declaration_path(home).write_text("{}")
    before = declaration_path(home).read_text()
    with pytest.raises(select.ChoiceRefused, match=why):
        select.record_choice(home, 9 if prepare == "bad number" else 1)
    assert declaration_path(home).read_text() == before, "a refused choice changed the declaration"


def test_speak_queues_only_for_a_running_worker(tmp_path, monkeypatch, capsys):
    """With no worker, nothing is queued: it would be spoken whenever one next started, out of its time."""
    monkeypatch.setattr(speech_cli, "_home", lambda: tmp_path)
    monkeypatch.setattr(speech, "lock_path", lambda: tmp_path / "speech.lock")
    args = SimpleNamespace(text=["Hello", "there."], stop=False, voice=None, speed=1.1, say_as=None, unsay=None)
    assert speech_cli.cmd_speak(args) == 1
    assert not list(speech.queue_dir(tmp_path).glob("*.json"))
    assert "not spoken: no speech worker is running" in capsys.readouterr().err
    held = speech.WorkerLock(tmp_path / "speech.lock")
    assert held.acquire()
    assert speech_cli.cmd_speak(args) == 0
    held.release()
    [queued] = list(speech.queue_dir(tmp_path).glob("*.json"))
    assert json.loads(queued.read_text()) == {"text": "Hello there.", "speed": 1.1}


def test_say_as_keeps_a_respelling(tmp_path, monkeypatch):
    monkeypatch.setattr(speech_cli, "_home", lambda: tmp_path)
    args = SimpleNamespace(text=[], stop=False, voice=None, speed=None, say_as=["Ira=Eyera"], unsay=None)
    assert speech_cli.cmd_speak(args) == 0
    assert speech.pronunciations(tmp_path) == {"Ira": "Eyera"}


def test_the_speech_commands_are_on_the_cli():
    from macf.cli import _build_parser
    parser = _build_parser()
    assert parser.parse_args(["voice", "speak", "hi"]).func is speech_cli.cmd_speak
    assert parser.parse_args(["voice", "select", "choose", "2"]).func is speech_cli.cmd_choose
    assert parser.parse_args(["voice", "select", "samples", "--traits", "calm"]).func is speech_cli.cmd_samples
    assert parser.parse_args(["voice", "show"]).func is speech_cli.cmd_show
